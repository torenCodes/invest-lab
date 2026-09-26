"""
early_signal_backtest.py — could the morning scan catch movers BEFORE the big move?

Why
---
Every In Play Today pick comes from Yahoo's day-gainers and most-active
screeners, so by construction it is a stock that has already jumped (median
+13.7% when flagged). short_term_backtest.py showed the #1 still moves after the
card appears but goes up first only about half the time. This asks whether
signals the scan could see earlier in the day point to better candidates: heavy
volume on a modest gain, a stock holding near its high, a stock in a leading
sector.

How (no hindsight anywhere)
---------------------------
- Universe: common stocks that traded $5-150 with a median $20M+ a day over the
  20 sessions to 2026-06-22, from the full-market daily bars the Cadence scan
  cached locally. That data ends before the test window begins, so the universe
  cannot know which names went on to move. Funds and leveraged products are
  excluded.
- Sector: each stock is assigned the SPDR sector fund its daily returns tracked
  most closely over Mar-Jun (both measured against SPY), again before the window.
- Simulated scans at 10:00 and 11:30 ET on every session in the ~60-day 5-minute
  window, after a 10-session warm-up. Each scan sees only the bars before its
  clock time. Relative volume = volume so far today / the median volume by the
  same time of day over the prior 10 sessions.
- Entry = open of the first 5-minute bar at the scan time. Outcomes, as in
  short_term_backtest.py: rest-of-day movement, up-first rate at +/-2% and
  +/-3% (~50% = no edge), return to the close, then next-day and 5-day returns
  against SPY over the same stretch.

Rules, fixed before any result was seen (eligible = $5-150 and $20M+ median daily
dollar volume over the prior 20 sessions, both point-in-time)
  BASE  biggest gainer: up 3%+ (Yahoo's day-gainers cut), ranked by gain. What
        the live scan's universe selects.
  A     volume on a modest gain: up 2-8%, relative volume >= 3x, ranked by it.
  B     holding near the high: up 2-8%, in the top 20% of the day's range so far,
        relative volume >= 2x, ranked by relative volume.
  C     leading sector: up 2-8%, its sector fund in the top 3 of 11 at the scan,
        relative volume >= 2x, ranked by relative volume.
  D     all three: up 2-8%, relative volume >= 3x, top 20% of range, top-3 sector.
  Reference rows, not candidates: every eligible stock; every stock up 2-8%.

Adoption test, also fixed in advance. A rule is worth building into the live scan
only if, at 10:00, its #1 each day beats BASE's #1 on BOTH the up-first rate at
+/-2% and the median return to the close, AND the up-first rate of everything it
flags has a 90% interval entirely above the all-eligible rate; and 11:30 points
the same way. Five rules at two times is ten looks at ~50 sessions, so a single
marginal win is not a finding.

First run (2026-09-26, sessions Jul 17 - Sep 25): no rule passed. The one lead is
rule C at 11:30 (everything it flagged went up first 60.6%, interval 55-66, vs
51.5% for all stocks), which did not appear at 10:00 and was one of ten looks.
Holdout, fixed now: once 40+ new sessions exist (late November 2026, before the
5-minute window rolls past them in late December), run with --after 2026-09-25.
The lead holds only if C's all-flags up-first interval at 11:30 again sits
entirely above the all-eligible rate.

Usage:  python Website/scripts/early_signal_backtest.py [--after YYYY-MM-DD]
Needs:  Website/scripts/.cadence_cache/ (local; written by cadence_scan.py runs)
Output: Website/data/early_signal_scorecard.json  (research output, not served)
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import statistics as st
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import short_term_backtest as stb                        # noqa: E402  (loaders, Wilson interval)
from cadence_scan import is_leveraged_product            # noqa: E402

REPO      = stb.REPO
ET        = stb.ET
GROUPED   = os.path.join(HERE, ".cadence_cache")
OUT_FILE  = os.path.join(REPO, "Website", "data", "early_signal_scorecard.json")

UNIVERSE_END  = "2026-06-22"          # last cached full-market day, before the 5m window
MIN_PRICE, MAX_PRICE = 5.0, 150.0     # the day board's price band
MIN_DOLLAR_VOL = 20_000_000
SECTOR_FUNDS  = ["XLK", "XLF", "XLV", "XLY", "XLI", "XLC", "XLP", "XLE", "XLU", "XLRE", "XLB"]
SCAN_TIMES    = (("10:00", 600), ("11:30", 690))   # minutes after midnight ET
WARMUP        = 10                    # sessions of same-time volume history
LEVELS        = (2.0, 3.0)
BIG_CLOSE     = 10.0                  # "went on to close up 10%+"

_FUND = re.compile(r"\b(?:ETF|ETN|ETP|Fund|iShares|SPDR|ProShares|Direxion|Invesco|Vanguard|"
                   r"Grayscale|Select Sector|Warrants?|Units?|Rights?|Preferred|Notes?|"
                   r"Depositary Shares)\b|%|Trust(?:,| ETF|\s*$)", re.I)


# ── universe + sector assignment, from data that ends before the test window ──

def _grouped_days():
    days = {}
    for path in sorted(glob.glob(os.path.join(GROUPED, "2026-*.json"))):
        day = os.path.basename(path)[:10]
        if day > UNIVERSE_END:
            continue
        rows = json.load(open(path)).get("results") or []
        if rows:
            days[day] = {r["T"]: r for r in rows}
    return days


def build_universe():
    days = _grouped_days()
    if len(days) < 40:
        sys.exit("need the Cadence scan's cached daily bars in %s" % GROUPED)
    names = json.load(open(os.path.join(GROUPED, "name_map.json")))
    order = sorted(days)
    last20 = order[-20:]
    universe = []
    for tk in days[order[-1]]:
        name = names.get(tk, "")
        if not name or _FUND.search(name) or is_leveraged_product(name) or not re.fullmatch(r"[A-Z]{1,5}", tk):
            continue
        bars = [days[d][tk] for d in last20 if tk in days[d]]
        if len(bars) < 18:
            continue
        px = st.median(b["c"] for b in bars)
        dv = st.median(b["c"] * b["v"] for b in bars)
        if MIN_PRICE <= px <= MAX_PRICE and dv >= MIN_DOLLAR_VOL:
            universe.append(tk)

    # sector: the fund whose excess-over-SPY daily returns the stock's tracked most closely
    def rets(tk):
        out = {}
        for a, b in zip(order, order[1:]):
            if tk in days[a] and tk in days[b] and days[a][tk]["c"]:
                out[b] = days[b][tk]["c"] / days[a][tk]["c"] - 1
        return out
    spy = rets("SPY")
    fund_ex = {f: {d: r - spy[d] for d, r in rets(f).items() if d in spy} for f in SECTOR_FUNDS}
    sector = {}
    for tk in universe:
        mine = {d: r - spy[d] for d, r in rets(tk).items() if d in spy}
        best, best_c = None, 0.0
        for f, fx in fund_ex.items():
            common = [d for d in mine if d in fx]
            if len(common) < 40:
                continue
            c = np.corrcoef([mine[d] for d in common], [fx[d] for d in common])[0, 1]
            if c > best_c:
                best, best_c = f, c
        sector[tk] = best                                  # None = tracks no sector; rule C cannot fire
    return sorted(universe), sector


# ── price data ────────────────────────────────────────────────────────────────

def _yf_ohlcv(chunk, **kw):
    import yfinance as yf
    d = yf.download(chunk, progress=False, auto_adjust=False, group_by="ticker", threads=True, **kw)
    out = {}
    for t in chunk:
        try:
            out[t] = (d[t] if len(chunk) > 1 else d)[["Open", "High", "Low", "Close", "Volume"]].dropna()
        except Exception:
            continue
    return out


def session_arrays(frame):
    """{date: dict of numpy arrays for regular-session 5m bars}."""
    idx = frame.index.tz_convert(ET)
    mins = np.asarray(idx.hour * 60 + idx.minute)
    keep = (mins >= 570) & (mins < 960)
    dates = np.asarray(idx.date)[keep]
    cols = {k: frame[c].to_numpy()[keep] for k, c in
            (("o", "Open"), ("h", "High"), ("l", "Low"), ("c", "Close"), ("v", "Volume"))}
    m = mins[keep]
    out = {}
    for d in np.unique(dates):
        sel = dates == d
        out[d] = {"m": m[sel], **{k: v[sel] for k, v in cols.items()}}
    return out


# ── outcomes ──────────────────────────────────────────────────────────────────

def outcome(bars, i0):
    """Path stats from the open of bar i0 to the close. A bar spanning both
    levels cannot be ordered and is unresolved, never a win."""
    o, h, l, c = bars["o"][i0], bars["h"][i0:], bars["l"][i0:], bars["c"][i0:]
    out = {"entry": o, "best": (h.max() / o - 1) * 100, "worst": (l.min() / o - 1) * 100,
           "to_close": (c[-1] / o - 1) * 100}
    for x in LEVELS:
        up = np.flatnonzero(h >= o * (1 + x / 100))
        dn = np.flatnonzero(l <= o * (1 - x / 100))
        iu = up[0] if len(up) else None
        idn = dn[0] if len(dn) else None
        if iu is None and idn is None:
            res = "neither"
        elif idn is None or (iu is not None and iu < idn):
            res = "up"
        elif iu is None or idn < iu:
            res = "down"
        else:
            res = "both"
        out[x] = res
    return out


def summarize(picks):
    if not picks:
        return {"n": 0}
    s = {"n": len(picks),
         "median_gain_at_flag": round(st.median(p["gain"] for p in picks), 2),
         "median_best": round(st.median(p["out"]["best"] for p in picks), 2),
         "median_worst": round(st.median(p["out"]["worst"] for p in picks), 2),
         "median_to_close": round(st.median(p["out"]["to_close"] for p in picks), 2),
         "closed_up_10_share": round(100.0 * sum(p["day_close_gain"] >= BIG_CLOSE for p in picks) / len(picks), 1)}
    for x in LEVELS:
        up = sum(p["out"][x] == "up" for p in picks)
        dn = sum(p["out"][x] == "down" for p in picks)
        s["reached_%g" % x] = round(100.0 * (up + dn + sum(p["out"][x] == "both" for p in picks)) / len(picks), 1)
        s["up_first_%g" % x] = round(100.0 * up / (up + dn), 1) if up + dn else None
        s["up_first_%g_90ci" % x] = stb._wilson(up, up + dn)
        s["resolved_%g" % x] = up + dn
    for k in ("t1", "t5"):
        ex = [p[k] for p in picks if p.get(k) is not None]
        s["median_%s_vs_spy" % k] = round(st.median(ex), 2) if ex else None
        s["beat_spy_%s" % k] = round(100.0 * sum(e > 0 for e in ex) / len(ex), 1) if ex else None
        s["n_%s" % k] = len(ex)
    return s


# ── the simulation ────────────────────────────────────────────────────────────

RULES = [
    ("BASE: biggest gainer (up 3%+)",
     lambda f: f["gain"] >= 3, lambda f: f["gain"]),
    ("A: volume on a modest gain",
     lambda f: 2 <= f["gain"] <= 8 and f["rvol"] >= 3, lambda f: f["rvol"]),
    ("B: holding near the high",
     lambda f: 2 <= f["gain"] <= 8 and f["pos"] >= 0.8 and f["rvol"] >= 2, lambda f: f["rvol"]),
    ("C: leading sector",
     lambda f: 2 <= f["gain"] <= 8 and f["sector_rank"] <= 3 and f["rvol"] >= 2, lambda f: f["rvol"]),
    ("D: all three",
     lambda f: 2 <= f["gain"] <= 8 and f["rvol"] >= 3 and f["pos"] >= 0.8 and f["sector_rank"] <= 3,
     lambda f: f["rvol"]),
]
REFERENCES = [
    ("ref: every eligible stock", lambda f: True),
    ("ref: every stock up 2-8%", lambda f: 2 <= f["gain"] <= 8),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", type=dt.date.fromisoformat,
                    help="test only sessions after this date (holdout); earlier ones still feed the volume baseline")
    args = ap.parse_args()

    universe, sector = build_universe()
    print("[universe] %d stocks ($%g-%g, $%dM+/day to %s); sector assigned for %d" % (
        len(universe), MIN_PRICE, MAX_PRICE, MIN_DOLLAR_VOL // 1_000_000, UNIVERSE_END,
        sum(1 for s in sector.values() if s)))

    everything = universe + ["SPY"] + SECTOR_FUNDS
    intraday = stb._load("intraday5mv", everything, lambda c: _yf_ohlcv(c, period="60d", interval="5m"))
    daily = stb._load("dailyv", everything, lambda c: _yf_ohlcv(c, start="2026-05-01", interval="1d"))
    for need in ["SPY"] + SECTOR_FUNDS:
        if need not in intraday or need not in daily:
            sys.exit("%s unavailable - refusing to run without the market and sector references" % need)

    sessions = sorted(session_arrays(intraday["SPY"]))
    bars = {t: session_arrays(f) for t, f in intraday.items()}
    closes = {t: {d.date(): float(c) for d, c in f["Close"].items()} for t, f in daily.items()}
    dvol = {t: {d.date(): float(c * v) for d, c, v in zip(f.index, f["Close"], f["Volume"])}
            for t, f in daily.items()}
    daily_days = sorted(closes["SPY"])

    day_pos = {d: i for i, d in enumerate(daily_days)}

    def prior_days(d, n):
        i = day_pos.get(d)
        return daily_days[max(0, i - n):i] if i is not None else []

    # volume traded before each scan time, per stock per session (used as today's
    # number and as the same-time-of-day baseline for the sessions after it)
    vol_before = {t: {d: {T: b["v"][b["m"] < T].sum() for _, T in SCAN_TIMES} for d, b in s.items()}
                  for t, s in bars.items()}
    median_dv = {}

    def liquid(tk, d):
        if (tk, d) not in median_dv:
            hist = [dvol[tk][x] for x in prior_days(d, 20) if x in dvol.get(tk, {})]
            median_dv[(tk, d)] = st.median(hist) if len(hist) >= 15 else 0
        return median_dv[(tk, d)] >= MIN_DOLLAR_VOL

    print("[sector] check: " + ", ".join("%s->%s" % (t, sector.get(t)) for t in
                                         ("INTC", "MU", "F", "NKE", "BAC", "WFC", "PFE", "CVS", "KO", "OXY", "KMI", "T",
                                          "DAL", "O", "NEE")))

    print("[data] 5-minute: %d of %d stocks, %d sessions (%s to %s); daily: %d" % (
        sum(1 for t in universe if t in bars), len(universe), len(sessions), sessions[0], sessions[-1],
        sum(1 for t in universe if t in closes)))

    flags = {name: {label: [] for label, _ in SCAN_TIMES} for name, *_ in RULES + REFERENCES}
    top1 = {name: {label: [] for label, _ in SCAN_TIMES} for name, *_ in RULES}
    skipped = defaultdict(int)

    first = WARMUP
    if args.after:
        first = max(WARMUP, next((i for i, d in enumerate(sessions) if d > args.after), len(sessions)))
        if first >= len(sessions):
            sys.exit("no sessions after %s in the 5-minute window yet" % args.after)
    for si in range(first, len(sessions)):
        d = sessions[si]
        if d not in daily_days:
            skipped["no daily bar for session"] += 1
            continue
        prev = prior_days(d, 1)
        if not prev:
            continue
        prev = prev[0]
        after = daily_days[daily_days.index(d):]
        for label, T in SCAN_TIMES:
            # sector ranking at the scan
            fund_gain = {}
            for f in SECTOR_FUNDS:
                b = bars[f].get(d)
                pc = closes[f].get(prev)
                if b is None or not pc:
                    continue
                pre = b["m"] < T
                if pre.any():
                    fund_gain[f] = b["c"][pre][-1] / pc - 1
            rank = {f: i + 1 for i, f in enumerate(sorted(fund_gain, key=fund_gain.get, reverse=True))}
            spy_b = bars["SPY"].get(d)
            spy_i = np.flatnonzero(spy_b["m"] >= T) if spy_b is not None else []
            if not len(spy_i):
                continue
            spy_entry = spy_b["o"][spy_i[0]]

            feats = []
            for tk in universe:
                b = bars.get(tk, {}).get(d)
                pc = closes.get(tk, {}).get(prev)
                if b is None or not pc:
                    continue
                pre = b["m"] < T
                post = np.flatnonzero(b["m"] >= T)
                if not pre.any() or len(post) < 6:
                    continue
                price = b["c"][pre][-1]
                if not (MIN_PRICE <= price <= MAX_PRICE) or not liquid(tk, d):
                    continue
                vb = vol_before[tk]
                base = [vb[x][T] for x in sessions[max(0, si - WARMUP):si] if x in vb and vb[x][T] > 0]
                if len(base) < 5:
                    continue
                hi, lo = b["h"][pre].max(), b["l"][pre].min()
                f = {"ticker": tk, "gain": (price / pc - 1) * 100,
                     "rvol": vb[d][T] / st.median(base),
                     "pos": (price - lo) / (hi - lo) if hi > lo else 0.5,
                     "sector_rank": rank.get(sector.get(tk), 99),
                     "day_close_gain": (b["c"][-1] / pc - 1) * 100}
                f["out"] = outcome(b, post[0])
                # next-day and 5-day, from the scan entry, against SPY from its own entry
                for k, n in (("t1", 1), ("t5", 5)):
                    if len(after) > n and after[n] in closes[tk] and after[n] in closes["SPY"]:
                        f[k] = ((closes[tk][after[n]] / f["out"]["entry"] - 1)
                                - (closes["SPY"][after[n]] / spy_entry - 1)) * 100
                feats.append(f)

            for name, ok, key in RULES:
                hits = [f for f in feats if ok(f)]
                flags[name][label].extend(hits)
                if hits:
                    top1[name][label].append(max(hits, key=key))
            for name, ok in REFERENCES:
                flags[name][label].extend(f for f in feats if ok(f))

    tested = len(sessions) - first
    card = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "universe": {"size": len(universe), "defined_through": UNIVERSE_END,
                         "price_band": [MIN_PRICE, MAX_PRICE], "min_dollar_volume": MIN_DOLLAR_VOL},
            "holdout_after": str(args.after) if args.after else None,
            "sessions_tested": tested, "window": [str(sessions[first]), str(sessions[-1])],
            "rules": [r[0] for r in RULES], "results": {}}

    print("\n=== 1. COVERAGE ===")
    print("  sessions tested %d (%s to %s) after a %d-session warm-up; skipped: %s" % (
        tested, sessions[first], sessions[-1], WARMUP, dict(skipped) or "none"))
    for label, _ in SCAN_TIMES:
        print("  %s  every eligible stock: %d stock-sessions" % (label, len(flags["ref: every eligible stock"][label])))
        for name, *_ in RULES:
            print("         %-32s #1 on %2d of %d sessions, %5d flags in all" % (
                name, len(top1[name][label]), tested, len(flags[name][label])))

    print("\n=== 2. SANITY: every eligible stock should sit near 50% up-first ===")
    for label, _ in SCAN_TIMES:
        s = summarize(flags["ref: every eligible stock"][label])
        print("  %s  up-first +/-2%%: %s%% %s   median to close %+.2f%%" % (
            label, s["up_first_2"], s["up_first_2_90ci"], s["median_to_close"]))

    print("\n=== 3. RESULTS (up-first with 90% interval; ~50% = no edge) ===")
    head = "  %-34s %5s %7s %22s %22s %7s %7s %7s %8s %8s"
    print(head % ("", "n", "up at", "up-first +/-2%", "up-first +/-3%", "reach3", "best", "close",
                  "t1 vsSPY", "t5 vsSPY"))
    row = "  %-34s %5d %+6.1f%% %22s %22s %6.0f%% %+6.1f%% %+6.1f%% %+7.2f%% %+7.2f%%"

    def show(name, s):
        if not s["n"]:
            print("  %-34s     0" % name)
            return
        uf = lambda x: ("%s%% (%s-%s)" % (s["up_first_%g" % x], *s["up_first_%g_90ci" % x])
                        if s["up_first_%g" % x] is not None else "-")
        print(row % (name, s["n"], s["median_gain_at_flag"], uf(2), uf(3), s["reached_3"], s["median_best"],
                     s["median_to_close"], s["median_t1_vs_spy"] or 0, s["median_t5_vs_spy"] or 0))

    for label, _ in SCAN_TIMES:
        card["results"][label] = {"top1": {}, "all_flags": {}, "reference": {}}
        print("\n  SCAN AT %s ET, the #1 each day (what a card would show)" % label)
        for name, *_ in RULES:
            s = summarize(top1[name][label])
            card["results"][label]["top1"][name] = s
            show(name, s)
        print("  SCAN AT %s ET, everything each rule flags" % label)
        for name, *_ in RULES:
            s = summarize(flags[name][label])
            card["results"][label]["all_flags"][name] = s
            show(name, s)
        for name, _ in REFERENCES:
            s = summarize(flags[name][label])
            card["results"][label]["reference"][name] = s
            show(name, s)

    print("\n=== 4. ADOPTION TEST (fixed in advance) ===")
    verdicts = {}
    for name, *_ in RULES[1:]:
        checks = []
        for label, _ in SCAN_TIMES:
            r, b = card["results"][label]["top1"][name], card["results"][label]["top1"][RULES[0][0]]
            a, n0 = card["results"][label]["all_flags"][name], card["results"][label]["reference"]["ref: every eligible stock"]
            ok = (r["n"] and b["n"] and r["up_first_2"] is not None and b["up_first_2"] is not None
                  and r["up_first_2"] > b["up_first_2"] and r["median_to_close"] > b["median_to_close"]
                  and a["n"] and a["up_first_2_90ci"] and a["up_first_2_90ci"][0] > n0["up_first_2"])
            checks.append(bool(ok))
        verdicts[name] = "PASS" if all(checks) else "fail"
        print("  %-34s 10:00 %-5s 11:30 %-5s -> %s" % (name, *("yes" if c else "no" for c in checks), verdicts[name]))
    card["adoption"] = verdicts
    card["universe"]["tickers"] = {t: sector.get(t) for t in universe}

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(card, f, indent=1, allow_nan=False, default=str)
    print("\n[scorecard] written to %s" % os.path.relpath(OUT_FILE, REPO))


if __name__ == "__main__":
    main()
