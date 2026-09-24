"""
list_backtest.py — grade every board's FULL list, using git history as the
point-in-time record.

Why this exists
---------------
The track record archives one #1 pick per scan, so the lab could say how its
#1s did but not how the lists visitors actually browse perform. Insider Buying
shows ~300 names; the archive graded about one a week. Yet every scan commits
its whole list, so the repository already holds a dated snapshot of every board
(hundreds of versions each). This walks that history and grades every name.

Method
------
- Each ticker counts once per stint on a list: from its first appearance, or
  from a return after REENTRY_DAYS away. A name that sits on a list for weeks
  is one pick, not dozens of independent ones.
- Point-in-time: a snapshot's commit time is converted to US/Eastern. Anything
  committed after the 4pm close is actionable from the next session.
- Two entry modes. "close" boards enter at the close of the first actionable
  session. "snapshot" boards (the intraday Movers lists) enter at the price the
  scan saw, so the same-day close (t0) is a real day-trade result; a snapshot
  taken outside market hours falls back to "close" and gets no t0.
- Horizons are trading sessions: 0 (same-day close), 1, 5, 20, 60. Each board is
  read at its own natural horizon; nothing is forced onto one 30-day clock.
- Benchmark: IWM over the same sessions (SPY also reported). For snapshot
  entries the benchmark runs from the prior close, which slightly favours it.
- Order of reading, learned from insider_backtest.py: coverage first, benchmark
  sanity second, findings last.
- A failed price fetch is never stored as data. It increments a miss counter
  and is retried; a ticker is written off only after MAX_MISSES separate runs.

The day-pick selection rules in day_rule_test() were fixed before any result
was seen, and all are reported. With ~120 trading days of history, trying rules
until one wins would find noise.

Usage:  python Website/scripts/list_backtest.py [--refresh]
Output: Website/data/board_scorecard.json  (research output, not served)
"""

import argparse
import datetime as dt
import json
import math
import os
import pickle
import random
import statistics as st
import subprocess
import sys
import time
from collections import defaultdict
from zoneinfo import ZoneInfo

HERE      = os.path.dirname(os.path.abspath(__file__))
REPO      = os.path.dirname(os.path.dirname(HERE))
CACHE_DIR = os.path.join(HERE, ".list_cache")
OUT_FILE  = os.path.join(REPO, "Website", "data", "board_scorecard.json")

ET            = ZoneInfo("America/New_York")
SESSIONS      = (0, 1, 5, 20, 60)
REENTRY_DAYS  = 30
MAX_MISSES    = 3
PRICE_START   = "2026-03-20"
MODEL_REBUILD = dt.date(2026, 8, 20)   # insider conviction model rebuilt from backtest evidence

# Analyst cross-dashboard tags -> dashboard family, so two lenses of one board count once.
FAMILY = {"movers_day": "movers", "movers_swing": "movers", "tried_true": "tried_true",
          "underdogs": "underdogs", "insider": "insider", "patterns_coil": "patterns",
          "patterns_leader": "patterns"}

BOARDS = [
    # key,            label,                              file,                                        list key,       score field,        entry,      native
    ("movers_day",    "Movers: In Play Today",            "Website/MarketDashboard/data/results.json",  "day_trades",   "score",            "snapshot", 1),
    ("highly_disc",   "Movers: Highly Discussed",         "Website/MarketDashboard/data/results.json",  "reddit_cards", "mentions",         "snapshot", 20),
    ("cadence",       "Movers: Cadence Watchlist",        "Website/MarketDashboard/data/cadence.json",  "names",        "cadence_score",    "close",    5),
    ("coil",          "Pattern Scanner: Coiled",          "Website/PatternScanner/data/coil.json",      "coiled",       "coil_score",       "close",    20),
    ("leaders",       "Pattern Scanner: Leaders",         "Website/PatternScanner/data/coil.json",      "leaders",      "leader_score",     "close",    20),
    ("underdogs",     "Marathon: Underdogs",              "Website/TheMarathon/data/deep_value.json",   "nominees",     "composite_score",  "close",    60),
    ("tried_true",    "Marathon: Tried & True",           "Website/TheMarathon/data/consensus.json",    "top_10",       "score",            "close",    60),
    ("insider",       "Insider Buying: Corporate",        "Website/InsiderBuying/data/results.json",    "nominees",     "conviction_score", "close",    60),
    ("analyst",       "The Analyst",                      "Website/TheAnalyst/data/results.json",       "tickers",      "score",            "close",    20),
]


# ── git history ───────────────────────────────────────────────────────────────

def _git(*args):
    return subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def versions(path):
    """Yield (commit_time_et, parsed_json) for every committed version of path,
    oldest first. One `git cat-file --batch` process instead of a subprocess per
    version: the Movers results file alone has ~950 versions."""
    log = [l.split() for l in _git("log", "--reverse", "--format=%H %cI", "HEAD", "--", path).splitlines() if l.strip()]
    proc = subprocess.Popen(["git", "cat-file", "--batch"], cwd=REPO,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for sha, ts in log:
            proc.stdin.write(("%s:%s\n" % (sha, path)).encode())
            proc.stdin.flush()
            header = proc.stdout.readline().decode()
            if header.rstrip().endswith("missing"):
                continue
            size = int(header.split()[2])
            blob = proc.stdout.read(size)
            proc.stdout.read(1)
            try:
                yield dt.datetime.fromisoformat(ts).astimezone(ET), json.loads(blob)
            except ValueError:
                continue                                   # a half-written file in history
    finally:
        proc.stdin.close()
        proc.wait()


def _snapshot_rows(data, list_key, score_field):
    out = []
    for rank, row in enumerate(data.get(list_key) or [], 1):
        tk = (row.get("ticker") or row.get("symbol") or "").upper().strip()
        if not tk:
            continue
        extra = {}
        if "cross_dashboard_tags" in row:
            extra["families"] = len({FAMILY.get(t.get("source_key"), t.get("source_key"))
                                     for t in row["cross_dashboard_tags"] or []})
        if "tier" in row:
            extra["tier"] = row["tier"]
        out.append((tk, rank, row.get(score_field), row.get("current_price") or row.get("price"),
                    row.get("change_pct"), extra))
    return out


def load_snapshots(refresh=False):
    """{board_key: [(when_et, [rows...]), ...]}, cached per file by commit count."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    by_file = defaultdict(list)
    for b in BOARDS:
        by_file[b[2]].append(b)
    snaps = {}
    for path, boards in by_file.items():
        tag = path.replace("/", "_")
        n_commits = _git("rev-list", "--count", "HEAD", "--", path).strip()
        cache = os.path.join(CACHE_DIR, "snap_%s_%s.pkl" % (tag, n_commits))
        if os.path.exists(cache) and not refresh:
            part = pickle.load(open(cache, "rb"))
        else:
            part = {b[0]: [] for b in boards}
            for when, data in versions(path):
                for key, _l, _p, list_key, score_field, _e, _n in boards:
                    part[key].append((when, _snapshot_rows(data, list_key, score_field)))
            pickle.dump(part, open(cache, "wb"))
        snaps.update(part)
        print("[history] %-46s %s versions" % (path.split("Website/")[1], n_commits))
    return snaps


def picks_from(snapshots):
    """First appearance per ticker, plus re-entries after REENTRY_DAYS away."""
    last_seen, picks = {}, []
    for when, rows in snapshots:
        for tk, rank, score, price, chg, extra in rows:
            prev = last_seen.get(tk)
            if prev is None or (when - prev).days >= REENTRY_DAYS:
                picks.append({"ticker": tk, "when": when, "rank": rank, "score": score,
                              "price": price, "chg": chg, "extra": extra})
            last_seen[tk] = when
    return picks


# ── prices ────────────────────────────────────────────────────────────────────

def load_prices(tickers):
    """{ticker: {date: close}}. Cached for the day. A ticker that comes back
    empty is a MISS, not data: it is retried on later runs and only written off
    after MAX_MISSES of them. Caching a failure as 'no data' once marked 69% of
    the insider universe as delisted, MSFT and KO included."""
    import pandas as pd
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    day_cache = os.path.join(CACHE_DIR, "prices_%s.pkl" % dt.date.today().isoformat())
    miss_file = os.path.join(CACHE_DIR, "price_misses.json")
    closes = pickle.load(open(day_cache, "rb")) if os.path.exists(day_cache) else {}
    misses = json.load(open(miss_file)) if os.path.exists(miss_file) else {}

    need = [t for t in sorted(set(tickers)) if t not in closes and misses.get(t, 0) < MAX_MISSES]
    for i in range(0, len(need), 80):
        chunk = need[i:i + 80]
        yf_syms = [t.replace(".", "-") for t in chunk]
        frame = None
        for attempt in (1, 2):
            try:
                frame = yf.download(yf_syms, start=PRICE_START, auto_adjust=True,
                                    progress=False, threads=True)["Close"]
                break
            except Exception as e:
                print("[prices] chunk %d attempt %d failed: %s" % (i // 80 + 1, attempt, e))
                time.sleep(20)
        if frame is None:
            continue                                        # whole chunk retried next run
        if isinstance(frame, pd.Series):
            frame = frame.to_frame(yf_syms[0])
        for t, s in zip(chunk, yf_syms):
            ser = frame[s].dropna() if s in frame.columns else None
            if ser is None or not len(ser):
                misses[t] = misses.get(t, 0) + 1
                continue
            closes[t] = {d.date(): float(v) for d, v in ser.items()}
            misses.pop(t, None)
        print("[prices] %d / %d tickers" % (min(i + 80, len(need)), len(need)))

    pickle.dump(closes, open(day_cache, "wb"))
    json.dump(misses, open(miss_file, "w"), indent=1)
    return closes, misses


# ── grading ───────────────────────────────────────────────────────────────────

def _sessions_from(calendar, day):
    """Trading dates on or after `day`."""
    lo, hi = 0, len(calendar)
    while lo < hi:
        mid = (lo + hi) // 2
        if calendar[mid] < day:
            lo = mid + 1
        else:
            hi = mid
    return lo


def grade_pick(p, entry_mode, closes, calendar):
    """Return {k: {'ret': %, 'iwm': %, 'spy': %}} for each horizon it has reached."""
    px = closes.get(p["ticker"])
    if not px:
        return None
    w = p["when"]
    in_hours = w.weekday() < 5 and (9 * 60 + 30) <= (w.hour * 60 + w.minute) < 16 * 60
    ref = w.date() + (dt.timedelta(days=1) if w.hour >= 16 else dt.timedelta(0))
    i0 = _sessions_from(calendar, ref)
    if i0 >= len(calendar):
        return None

    snapshot = entry_mode == "snapshot" and in_hours and calendar[i0] == w.date() and p["price"]
    if snapshot:
        entry = float(p["price"])
        b0 = {s: closes[s].get(calendar[i0 - 1]) for s in ("IWM", "SPY")} if i0 > 0 else None
    else:
        entry = px.get(calendar[i0])
        b0 = {s: closes[s].get(calendar[i0]) for s in ("IWM", "SPY")}
    if not entry or not b0 or not all(b0.values()):
        return None

    out = {}
    for k in SESSIONS:
        if k == 0 and not snapshot:
            continue                                        # t0 only means something intraday
        j = i0 + k
        if j >= len(calendar):
            break
        d = calendar[j]
        c = px.get(d)
        if c is None:
            continue
        out[k] = {"ret": (c / entry - 1) * 100,
                  **{s.lower(): (closes[s][d] / b0[s] - 1) * 100 for s in ("IWM", "SPY") if d in closes[s]}}
    return out


def summarize(results, k):
    rows = [r[k] for r in results if r and k in r and "iwm" in r[k]]
    if not rows:
        return {"n": 0}
    ex = [r["ret"] - r["iwm"] for r in rows]
    rets = [r["ret"] for r in rows]
    return {"n": len(rows),
            "median_ret": round(st.median(rets), 2),
            "median_excess_iwm": round(st.median(ex), 2),
            "mean_excess_iwm": round(st.mean(ex), 2),
            "beat_iwm_pct": round(100.0 * sum(e > 0 for e in ex) / len(ex), 1),
            "win_pct": round(100.0 * sum(r > 0 for r in rets) / len(rets), 1)}


def fmt(s):
    if not s.get("n"):
        return "%-24s" % "-"
    if s["n"] < 15:
        return "%-24s" % ("(n=%d, anecdote)" % s["n"])
    return "%-24s" % ("%+6.2f beat %2.0f%% n=%d" % (s["median_excess_iwm"], s["beat_iwm_pct"], s["n"]))


def breakdowns(key, picks, graded):
    """Board-specific cuts. Every cut is reported, whatever it shows."""
    pairs = [(p, g) for p, g in zip(picks, graded) if g]
    cuts = {"rank 1-5": lambda p: p["rank"] <= 5,
            "rank 6-10": lambda p: 6 <= p["rank"] <= 10,
            "rank 11+": lambda p: p["rank"] >= 11}
    scored = sorted(p["score"] for p, _ in pairs if isinstance(p["score"], (int, float)))
    if len(scored) >= 30:
        t1, t2 = scored[len(scored) // 3], scored[2 * len(scored) // 3]
        cuts["score: top third"] = lambda p, t2=t2: isinstance(p["score"], (int, float)) and p["score"] >= t2
        cuts["score: bottom third"] = lambda p, t1=t1: isinstance(p["score"], (int, float)) and p["score"] < t1
    if key == "insider":
        cuts["old model (< Aug 20)"] = lambda p: p["when"].date() < MODEL_REBUILD
        cuts["new model (>= Aug 20)"] = lambda p: p["when"].date() >= MODEL_REBUILD
        for tier in ("A", "B", "C"):
            cuts["tier %s" % tier] = lambda p, tier=tier: p["extra"].get("tier") == tier
    if key == "analyst":
        cuts["on 1 board"] = lambda p: p["extra"].get("families", 0) <= 1
        cuts["on 2+ boards"] = lambda p: p["extra"].get("families", 0) >= 2
    if key in ("movers_day", "highly_disc"):
        for lo, hi in ((-99, 10), (10, 20), (20, 999)):
            cuts["up %s on the day" % ("<10%" if lo < 0 else "%d%%+" % lo if hi > 900 else "%d-%d%%" % (lo, hi))] = \
                lambda p, lo=lo, hi=hi: isinstance(p["chg"], (int, float)) and lo <= p["chg"] < hi
    return {name: {k: summarize([g for p, g in pairs if f(p)], k) for k in SESSIONS} for name, f in cuts.items()}


# ── day-pick selection rules (fixed in advance) ──────────────────────────────

DAY_RULES = [
    ("current: highest score",       lambda c: True),
    ("skip names up more than 10%",  lambda c: isinstance(c[4], (int, float)) and c[4] <= 10),
    ("skip names up more than 15%",  lambda c: isinstance(c[4], (int, float)) and c[4] <= 15),
    ("only names up 2% to 8%",       lambda c: isinstance(c[4], (int, float)) and 2 <= c[4] <= 8),
]


def _bootstrap_median(xs, n=2000, seed=7):
    if len(xs) < 10:
        return None
    rnd = random.Random(seed)
    meds = sorted(st.median(rnd.choice(xs) for _ in xs) for _ in range(n))
    return round(meds[int(0.05 * n)], 2), round(meds[int(0.95 * n)], 2)


def day_rule_test(snapshots, closes, calendar):
    """One pick per trading day per rule: the highest-scoring eligible candidate
    at the first market-hours scan of the day that has one. Graded from the
    price the scan saw. 'every candidate' shows whether ranking helps at all."""
    by_day = defaultdict(list)
    for when, rows in snapshots:
        if when.weekday() < 5 and (9 * 60 + 30) <= when.hour * 60 + when.minute < 16 * 60 and rows:
            by_day[when.date()].append((when, rows))

    out = {}
    for name, ok in DAY_RULES:
        graded, days_with_pick = [], 0
        for day in sorted(by_day):
            for when, rows in sorted(by_day[day]):
                elig = [r for r in rows if ok(r) and isinstance(r[2], (int, float))]
                if elig:
                    best = max(elig, key=lambda r: r[2])
                    p = {"ticker": best[0], "when": when, "price": best[3], "rank": best[1],
                         "score": best[2], "chg": best[4], "extra": {}}
                    graded.append(grade_pick(p, "snapshot", closes, calendar))
                    days_with_pick += 1
                    break
        out[name] = {"days_with_pick": days_with_pick, "days_total": len(by_day),
                     "horizons": {k: summarize(graded, k) for k in (0, 1, 5, 20)},
                     "t1_median_ret_90ci": _bootstrap_median([g[1]["ret"] for g in graded if g and 1 in g])}

    everyone = []
    for day in sorted(by_day):
        when, rows = sorted(by_day[day])[0]
        for r in rows:
            everyone.append(grade_pick({"ticker": r[0], "when": when, "price": r[3], "rank": r[1],
                                        "score": r[2], "chg": r[4], "extra": {}},
                                       "snapshot", closes, calendar))
    out["reference: every candidate at the day's first scan"] = {
        "days_with_pick": len(by_day), "days_total": len(by_day),
        "horizons": {k: summarize(everyone, k) for k in (0, 1, 5, 20)},
        "t1_median_ret_90ci": _bootstrap_median([g[1]["ret"] for g in everyone if g and 1 in g])}
    return out


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-read git history instead of the cache")
    args = ap.parse_args()

    snaps = load_snapshots(args.refresh)
    picks = {b[0]: picks_from(snaps[b[0]]) for b in BOARDS}
    universe = {p["ticker"] for v in picks.values() for p in v} | {"IWM", "SPY"}
    closes, misses = load_prices(universe)
    if "IWM" not in closes or "SPY" not in closes:
        sys.exit("benchmark prices unavailable - refusing to grade anything")
    calendar = sorted(closes["IWM"])

    # 1. coverage
    print("\n=== 1. COVERAGE (priced / picks)  - read this before any result ===")
    graded = {}
    for key, label, _p, _l, _s, entry, _n in BOARDS:
        graded[key] = [grade_pick(p, entry, closes, calendar) for p in picks[key]]
        have = sum(1 for g in graded[key] if g is not None)
        print("  %-34s %5d / %-5d (%3.0f%%)" % (label, have, len(picks[key]),
                                               100.0 * have / max(len(picks[key]), 1)))
    written_off = sorted(t for t, n in misses.items() if n >= MAX_MISSES)
    print("  tickers written off after %d failed runs: %d %s" % (MAX_MISSES, len(written_off), written_off[:12]))

    # 2. benchmark sanity
    print("\n=== 2. BENCHMARK SANITY (IWM over graded windows) ===")
    allg = [g for v in graded.values() for g in v if g]
    for k in (1, 5, 20, 60):
        v = [g[k]["iwm"] for g in allg if k in g and "iwm" in g[k]]
        if v:
            print("  %2d sessions: IWM median %+5.2f%%  (n=%d)" % (k, st.median(v), len(v)))

    # 3. findings
    print("\n=== 3. BOARDS: median excess vs IWM, share beating it (native horizon in [ ]) ===")
    print("  %-34s %s" % ("", "".join("%-24s" % ("t%d" % k if k < 2 else "%d sess" % k) for k in SESSIONS)))
    card = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "method": "git-history first appearances; entry at the scan's price (intraday Movers lists) "
                      "or the next actionable close; excess vs IWM over the same sessions",
            "reentry_days": REENTRY_DAYS, "boards": {}}
    for key, label, path, list_key, _s, entry, native in BOARDS:
        hz = {k: summarize(graded[key], k) for k in SESSIONS}
        cells = "".join(("[%s]" % fmt(hz[k]).strip()).ljust(24) if k == native else fmt(hz[k]) for k in SESSIONS)
        print("  %-34s %s" % (label, cells))
        card["boards"][key] = {"label": label, "source": "%s:%s" % (path, list_key), "entry": entry,
                               "native_horizon": native, "picks": len(picks[key]),
                               "priced": sum(1 for g in graded[key] if g), "horizons": hz,
                               "breakdowns": breakdowns(key, picks[key], graded[key])}

    print("\n=== 4. CUTS at each board's native horizon ===")
    for key, label, *_rest, native in BOARDS:
        print("  %s (%s)" % (label, "t%d" % native if native < 2 else "%d sessions" % native))
        for cut, hz in card["boards"][key]["breakdowns"].items():
            print("      %-30s %s" % (cut, fmt(hz[native])))

    print("\n=== 5. DAY-PICK SELECTION RULES (fixed in advance; all reported) ===")
    rules = day_rule_test(snaps["movers_day"], closes, calendar)
    card["day_rules"] = rules
    print("  %-50s %-6s %s" % ("rule", "days", "".join("%-26s" % h for h in ("t0 (same day)", "t1", "5 sess", "20 sess"))))
    for name, r in rules.items():
        cells = ""
        for k in (0, 1, 5, 20):
            s = r["horizons"][k]
            cells += ("%-26s" % ("%+5.2f%% win %2.0f%% n=%d" % (s["median_ret"], s["win_pct"], s["n"]))
                      if s.get("n") else "%-26s" % "-")
        print("  %-50s %3d/%-3d %s" % (name, r["days_with_pick"], r["days_total"], cells))
        if r["t1_median_ret_90ci"]:
            print("  %-50s         t1 median, 90%% bootstrap interval: %s" % ("", r["t1_median_ret_90ci"]))

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(card, f, indent=1, allow_nan=False, default=str)
    print("\n[scorecard] written to %s" % os.path.relpath(OUT_FILE, REPO))


if __name__ == "__main__":
    main()
