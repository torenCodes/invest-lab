"""
short_term_backtest.py — grade the short-term boards on what they PROMISE.

list_backtest.py grades every board on buy-and-hold returns. That is the right
test for Underdogs or Insider Buying and the wrong one for a day-trading
nominee, which nobody means to hold. This asks each short-term board the
question its own card implies:

In Play Today and Highly Discussed promise a stock that MOVES.
  After the card appears, does the stock offer room to trade, and does it go
  the right way first? The key number is the first-touch rate: of the picks
  that reach either +X% or -X% after the flag, the share that reaches +X%
  first. For a stock with no edge that is about 50% however volatile it is,
  so 50% is the bar. Measured two ways: from the first 5-minute bar after the
  card appeared (flags after 3pm ET are skipped, too little session is left),
  and from the next morning's open.

Cadence promises BIG, STEADY daily swings.
  Does the rhythm persist after the list is published, and do higher scores
  deliver more of it? Realized average daily range and consistency over the
  next 5 and 20 sessions, against what the scan measured.

Reliability:
- 5-minute bars exist only for roughly the last 60 trading days, so the
  movement tests cover that window; Cadence uses daily bars and its full
  history.
- Control: the same first-touch test runs on SPY at the exact flag times. It
  should land near 50%; if it does not, the harness is biased and nothing
  else it says can be trusted.
- Coverage first, control second, findings last. Failed fetches are misses,
  never data.

Usage:  python Website/scripts/short_term_backtest.py
Output: Website/data/short_term_scorecard.json  (research output, not served)
"""

import datetime as dt
import json
import math
import os
import pickle
import statistics as st
import sys
import time
from collections import defaultdict
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import list_backtest as lb                               # noqa: E402  (git history + snapshots)
from cadence_scan import is_leveraged_product            # noqa: E402

REPO      = lb.REPO
CACHE_DIR = lb.CACHE_DIR
OUT_FILE  = os.path.join(REPO, "Website", "data", "short_term_scorecard.json")
ET, UTC   = ZoneInfo("America/New_York"), dt.timezone.utc

THRESHOLDS   = (1.0, 2.0, 3.0)        # first-touch levels, % from entry
SPY_LEVELS   = (0.25, 0.5, 1.0)       # SPY rarely travels 2-3% in a session
LAST_ENTRY   = (15, 0)                # skip same-day tests for flags at/after 3pm ET
CADENCE_FWD  = (5, 20)                # sessions of realized rhythm
CADENCE_MIN  = 3.0                    # the scan's own ADR floor (cadence_scan.MIN_ADR)


# ── data loaders (cached per day; a failed fetch is a miss, never data) ───────

def _load(kind, tickers, fetch):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "%s_%s.pkl" % (kind, dt.date.today().isoformat()))
    miss_path = os.path.join(CACHE_DIR, "%s_misses.json" % kind)
    data = pickle.load(open(path, "rb")) if os.path.exists(path) else {}
    misses = json.load(open(miss_path)) if os.path.exists(miss_path) else {}
    need = [t for t in sorted(set(tickers)) if t not in data and misses.get(t, 0) < lb.MAX_MISSES]
    step = 40
    for i in range(0, len(need), step):
        chunk = need[i:i + step]
        got = None
        for attempt in (1, 2):
            try:
                got = fetch(chunk)
                break
            except Exception as e:
                print("[%s] chunk %d attempt %d failed: %s" % (kind, i // step + 1, attempt, e))
                time.sleep(20)
        if got is None:
            continue
        for t in chunk:
            frame = got.get(t)
            if frame is None or not len(frame):
                misses[t] = misses.get(t, 0) + 1
            else:
                data[t] = frame
                misses.pop(t, None)
        print("[%s] %d / %d" % (kind, min(i + step, len(need)), len(need)))
    pickle.dump(data, open(path, "wb"))
    json.dump(misses, open(miss_path, "w"), indent=1)
    return data


def _yf_frames(chunk, **kw):
    import yfinance as yf
    syms = [t.replace(".", "-") for t in chunk]
    d = yf.download(syms, progress=False, auto_adjust=False, group_by="ticker", threads=True, **kw)
    out = {}
    for t, s in zip(chunk, syms):
        try:
            f = (d[s] if len(syms) > 1 else d)[["Open", "High", "Low", "Close"]].dropna()
        except Exception:
            continue
        out[t] = f
    return out


def load_intraday(tickers):
    """{ticker: DataFrame of 5-minute OHLC, index = bar START in UTC}."""
    return _load("intraday5m", tickers, lambda c: _yf_frames(c, period="60d", interval="5m"))


def load_daily(tickers, start):
    return _load("dailyohlc", tickers, lambda c: _yf_frames(c, start=start, interval="1d"))


# ── movement tests (In Play Today, Highly Discussed) ──────────────────────────

def path_stats(bars, entry, levels=THRESHOLDS):
    """First-touch outcome for each level, plus max favourable / adverse move
    and the close, all from `entry`. A bar that spans BOTH levels cannot be
    ordered from 5-minute data and is counted as unresolved, not a win."""
    hi = bars["High"].to_numpy()
    lo = bars["Low"].to_numpy()
    out = {"mfe": (hi.max() / entry - 1) * 100, "mae": (lo.min() / entry - 1) * 100,
           "close": (bars["Close"].iloc[-1] / entry - 1) * 100, "touch": {}}
    for x in levels:
        up, dn = entry * (1 + x / 100), entry * (1 - x / 100)
        res = "neither"
        for h, l in zip(hi, lo):
            if h >= up and l <= dn:
                res = "both-in-one-bar"
                break
            if h >= up:
                res = "up"
                break
            if l <= dn:
                res = "down"
                break
        out["touch"][x] = res
    return out


def session_bars(frame, day):
    idx = frame.index.tz_convert(ET)
    return frame[(idx.date == day) & (idx.time >= dt.time(9, 30)) & (idx.time < dt.time(16, 0))]


def movement(flags, intraday, bench):
    """flags: [(ticker, when_et)]. Returns per-flag stats for the same session
    after the flag, the next session from its open, and SPY at the same times."""
    rows = []
    days = sorted(set(bench.index.tz_convert(ET).date))
    for tk, when in flags:
        f = intraday.get(tk)
        if f is None:
            rows.append(None)
            continue
        rec = {"ticker": tk, "when": when.isoformat()}
        day = when.date()
        # same session, from the first bar starting at/after the flag
        if (when.hour, when.minute) < LAST_ENTRY:
            s = session_bars(f, day)
            s = s[s.index >= when.astimezone(UTC)]
            if len(s) >= 6:                                  # at least 30 minutes left
                rec["same"] = path_stats(s, float(s["Open"].iloc[0]))
                b = session_bars(bench, day)
                b = b[b.index >= s.index[0]]
                if len(b):
                    rec["spy_same"] = path_stats(b, float(b["Open"].iloc[0]), SPY_LEVELS)
        # next session, from its open
        later = [d for d in days if d > day]
        if later:
            n = session_bars(f, later[0])
            if len(n) >= 6:
                rec["next"] = path_stats(n, float(n["Open"].iloc[0]))
                b = session_bars(bench, later[0])
                if len(b):
                    rec["spy_next"] = path_stats(b, float(b["Open"].iloc[0]), SPY_LEVELS)
        rows.append(rec)
    return rows


def _wilson(k, n, z=1.645):
    """90% interval for a proportion. Keeps a 55% on n=20 from reading as an edge."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100 * (c - h), 1), round(100 * (c + h), 1)


def summarize_moves(rows, key, levels=THRESHOLDS):
    got = [r[key] for r in rows if r and key in r]
    if not got:
        return {"n": 0}
    out = {"n": len(got),
           "median_best_move": round(st.median(g["mfe"] for g in got), 2),
           "median_worst_move": round(st.median(g["mae"] for g in got), 2),
           "median_to_close": round(st.median(g["close"] for g in got), 2),
           "touch": {}}
    for x in levels:
        c = defaultdict(int)
        for g in got:
            c[g["touch"][x]] += 1
        resolved = c["up"] + c["down"]
        out["touch"]["%g" % x] = {
            "up_first": c["up"], "down_first": c["down"], "neither": c["neither"],
            "both_in_one_bar": c["both-in-one-bar"],
            "up_first_pct": round(100.0 * c["up"] / resolved, 1) if resolved else None,
            "up_first_90ci": _wilson(c["up"], resolved),
            "reached_either_pct": round(100.0 * resolved / len(got), 1)}
    return out


def top_card_flags(snapshots):
    """The card a visitor saw: the first market-hours scan of each day that has
    any names, and the highest-ranked name on it."""
    by_day = defaultdict(list)
    for when, rows in snapshots:
        if rows and when.weekday() < 5 and dt.time(9, 30) <= when.time() < dt.time(16, 0):
            by_day[when.date()].append((when, rows))
    out = []
    for day in sorted(by_day):
        when, rows = sorted(by_day[day])[0]
        out.append((min(rows, key=lambda r: r[1])[0], when))    # rank 1, as the page shows it
    return out


def all_candidate_flags(snapshots):
    return [(p["ticker"], p["when"]) for p in lb.picks_from(snapshots)
            if p["when"].weekday() < 5 and dt.time(9, 30) <= p["when"].time() < dt.time(16, 0)]


# ── Cadence: does the rhythm persist? ─────────────────────────────────────────

def _spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    if len(xs) < 10:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 3) if den else None


def cadence_test():
    """One snapshot per publish day. Realized rhythm over the next N sessions,
    starting with the first session a visitor could act on."""
    snaps, name_of = {}, {}
    cached = os.path.join(HERE, ".cadence_cache", "name_map.json")
    if os.path.exists(cached):
        name_of.update(json.load(open(cached)))
    for when, data in lb.versions("Website/MarketDashboard/data/cadence.json"):
        pub = when.date() + (dt.timedelta(days=1) if when.hour >= 16 else dt.timedelta(0))
        snaps.setdefault(pub, data.get("names") or [])       # first snapshot of each day
        for r in data.get("names") or []:
            if r.get("name"):                                 # early versions carried no names
                name_of[r["ticker"]] = r["name"]
    tickers = {r["ticker"] for rows in snaps.values() for r in rows} | {"SPY", "QQQ", "IWM"}
    first = min(snaps) - dt.timedelta(days=5)
    daily = load_daily(tickers, first.isoformat())

    def realized(tk, pub, n):
        f = daily.get(tk)
        if f is None:
            return None
        f = f[f.index.date >= pub]
        if len(f) < n:
            return None
        f = f.iloc[:n]
        rng = ((f["High"] - f["Low"]) / f["Close"] * 100).tolist()
        m = st.mean(rng)
        cv = (st.pstdev(rng) / m) if m else 1.0
        return {"adr": m, "consistency": max(0.0, min(1.0, (0.7 - cv) / 0.5)),
                "days_over_floor": sum(x >= CADENCE_MIN for x in rng) / len(rng)}

    obs, seen_first = [], set()
    for pub in sorted(snaps):
        for rank, r in enumerate(snaps[pub], 1):
            rec = {"ticker": r["ticker"], "pub": pub, "rank": rank, "score": r.get("cadence_score"),
                   "adr_scored": r.get("adr_pct"), "cons_scored": r.get("consistency"),
                   "leveraged": is_leveraged_product(name_of.get(r["ticker"])),
                   "first": r["ticker"] not in seen_first}
            seen_first.add(r["ticker"])
            for n in CADENCE_FWD:
                rec["fwd%d" % n] = realized(r["ticker"], pub, n)
            obs.append(rec)
    refs = {s: [realized(s, p, CADENCE_FWD[0]) for p in sorted(snaps)] for s in ("SPY", "QQQ", "IWM")}
    return obs, refs, daily


def summarize_cadence(obs, n):
    k = "fwd%d" % n
    got = [o for o in obs if o[k] and isinstance(o["adr_scored"], (int, float))]
    if not got:
        return {"n": 0}
    ratio = [o[k]["adr"] / o["adr_scored"] for o in got if o["adr_scored"]]
    return {"n": len(got),
            "median_scored_adr": round(st.median(o["adr_scored"] for o in got), 2),
            "median_realized_adr": round(st.median(o[k]["adr"] for o in got), 2),
            "median_realized_over_scored": round(st.median(ratio), 2),
            "still_above_floor_pct": round(100.0 * sum(o[k]["adr"] >= CADENCE_MIN for o in got) / len(got), 1),
            "median_share_of_days_over_floor": round(100 * st.median(o[k]["days_over_floor"] for o in got), 1),
            "median_scored_consistency": round(st.median(o["cons_scored"] for o in got
                                                         if isinstance(o["cons_scored"], (int, float))), 2),
            "median_realized_consistency": round(st.median(o[k]["consistency"] for o in got), 2),
            "spearman_scored_vs_realized_adr": _spearman([o["adr_scored"] for o in got],
                                                         [o[k]["adr"] for o in got]),
            "spearman_score_vs_realized_adr": _spearman([o["score"] for o in got],
                                                        [o[k]["adr"] for o in got])}


# ── report ────────────────────────────────────────────────────────────────────

def _fmt_touch(s, x):
    t = s.get("touch", {}).get("%g" % x)
    if not t or t["up_first_pct"] is None:
        return "%-30s" % "-"
    lo, hi = t["up_first_90ci"]
    return "%-30s" % ("%4.1f%% up-first (%2.0f-%2.0f) n=%d" % (t["up_first_pct"], lo, hi, t["up_first"] + t["down_first"]))


def main():
    snaps = lb.load_snapshots()
    groups = {
        "In Play Today: the top card each day": top_card_flags(snaps["movers_day"]),
        "In Play Today: every name listed":     all_candidate_flags(snaps["movers_day"]),
        "Highly Discussed: the top card each day": top_card_flags(snaps["highly_disc"]),
        "Highly Discussed: every name listed":  all_candidate_flags(snaps["highly_disc"]),
    }
    tickers = {t for flags in groups.values() for t, _ in flags} | {"SPY"}
    intraday = load_intraday(tickers)
    if "SPY" not in intraday:
        sys.exit("SPY intraday unavailable - no control, refusing to report")
    spy = intraday["SPY"]
    window_start = spy.index.tz_convert(ET).date.min()
    print("\n5-minute data window: %s -> %s" % (window_start, spy.index.tz_convert(ET).date.max()))

    results = {}
    print("\n=== 1. COVERAGE (flags inside the 5-minute window that got a same-session result) ===")
    for name, flags in groups.items():
        inwin = [(t, w) for t, w in flags if w.date() >= window_start]
        rows = movement(inwin, intraday, spy)
        results[name] = rows
        same = sum(1 for r in rows if r and "same" in r)
        nxt = sum(1 for r in rows if r and "next" in r)
        print("  %-42s %4d flags in window | same-session %4d | next-session %4d" % (name, len(inwin), same, nxt))

    card = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "window": [str(window_start), str(spy.index.tz_convert(ET).date.max())],
            "method": "entry at the first 5-minute bar after the card appeared (same session) or the "
                      "next session's open; up-first = share of picks reaching +X% before -X%, among "
                      "those that reached either; ~50% means no edge",
            "movement": {}, "control": {}}

    print("\n=== 2. CONTROL: SPY at the same moments, +/-0.25 / 0.5 / 1% (should sit near 50%) ===")
    for key in ("same", "next"):
        for name, rows in results.items():
            c = summarize_moves(rows, "spy_" + key, SPY_LEVELS)
            card["control"].setdefault(name, {})[key] = c
            if c["n"]:
                print("  %-5s %-42s %s%s%s" % (key, name, _fmt_touch(c, 0.25), _fmt_touch(c, 0.5), _fmt_touch(c, 1.0)))

    print("\n=== 3. MOVEMENT: does the stock go the right way first? (90% interval in brackets) ===")
    for key, label in (("same", "SAME SESSION, from the first bar after the card appeared"),
                       ("next", "NEXT SESSION, from the open")):
        print("\n  %s" % label)
        print("  %-42s %-30s%-30s%-30s %s" % ("", "+/-1%", "+/-2%", "+/-3%", "best / worst / to close (medians)"))
        for name, rows in results.items():
            s = summarize_moves(rows, key)
            card["movement"].setdefault(name, {})[key] = s
            if not s["n"]:
                continue
            print("  %-42s %s%s%s %+5.1f / %+5.1f / %+5.1f  n=%d" % (
                name, _fmt_touch(s, 1.0), _fmt_touch(s, 2.0), _fmt_touch(s, 3.0),
                s["median_best_move"], s["median_worst_move"], s["median_to_close"], s["n"]))

    print("\n=== 4. CADENCE: does the rhythm persist after the list is published? ===")
    obs, refs, _ = cadence_test()
    card["cadence"] = {}
    cuts = {
        "every name, every day":    lambda o: True,
        "first appearance only":    lambda o: o["first"],
        "top 10":                   lambda o: o["rank"] <= 10,
        "ranks 11-60":              lambda o: o["rank"] > 10,
        "leveraged funds (now excluded)": lambda o: o["leveraged"],
        "real companies":           lambda o: not o["leveraged"],
    }
    scores = sorted(o["score"] for o in obs if isinstance(o["score"], (int, float)))
    if len(scores) >= 30:
        lo_cut, hi_cut = scores[len(scores) // 3], scores[2 * len(scores) // 3]
        cuts["score: top third"] = lambda o, c=hi_cut: isinstance(o["score"], (int, float)) and o["score"] >= c
        cuts["score: bottom third"] = lambda o, c=lo_cut: isinstance(o["score"], (int, float)) and o["score"] < c
    print("  %-34s %6s %8s %9s %7s %11s %14s %s" % ("", "n", "scored", "realized", "ratio", "days >= 3%",
                                                   "steady (was)", "rank corr (ADR, score)"))
    for n in CADENCE_FWD:
        print("  next %d sessions%s" % (n, "  (5-day 'steady' reads high: CV from 5 ranges is biased low)" if n < 20 else ""))
        for name, f in cuts.items():
            s = summarize_cadence([o for o in obs if f(o)], n)
            card["cadence"].setdefault(name, {})["fwd%d" % n] = s
            if not s["n"]:
                continue
            print("  %-34s %6d %7.2f%% %8.2f%% %7.2f %10.0f%% %8.2f (%.2f)   %s / %s" % (
                name, s["n"], s["median_scored_adr"], s["median_realized_adr"],
                s["median_realized_over_scored"], s["median_share_of_days_over_floor"],
                s["median_realized_consistency"], s["median_scored_consistency"],
                s["spearman_scored_vs_realized_adr"], s["spearman_score_vs_realized_adr"]))
    print("  reference, median realized daily range over the same windows:",
          ", ".join("%s %.2f%%" % (k, st.median(x["adr"] for x in v if x)) for k, v in refs.items()))
    card["cadence_reference"] = {k: round(st.median(x["adr"] for x in v if x), 2) for k, v in refs.items()}

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(card, f, indent=1, allow_nan=False, default=str)
    print("\n[scorecard] written to %s" % os.path.relpath(OUT_FILE, REPO))


if __name__ == "__main__":
    main()
