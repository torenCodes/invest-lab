"""
cadence_theme_backtest.py — would knowing direction make the Cadence list better?

Why
---
The Cadence Score measures how far a stock moves and never which way. In a
rotation (Nov 2026: Health Care and Staples up 12-13% in a month, Technology down
12%) the list stays full of the falling sector, because falling stocks have wide
ranges too. short_term_backtest.py showed the range promise holds, and
list_backtest.py showed the names drift down against the market. This asks whether
a direction check keeps the movement and improves the outcome.

How (no hindsight in the rules)
-------------------------------
- Universe: common stocks that traded $8-600 with a median $15M+ a day over the 20
  sessions to 2026-06-22 (loose, so names can drift into the live filters), plus
  every ticker that ever appeared on the live list. Funds and leveraged products
  are excluded.
- Every session from 2026-07-01, the live score_ticker() runs on the 20 sessions
  through that day, exactly as the scan does, and each rule below builds its top
  60. Control: the simulated BASE list is compared with what the live scan
  actually published that day.
- The list is acted on the next session. Outcomes: open to close that day, the best
  and worst move from the open, the day's range, and the return from that open to
  the close 5 and 20 sessions later, all against SPY over the same stretch.
- Sector = Yahoo's, on the 11 SPDR funds used by Sector Rotation, with bitcoin
  miners turned data-center hosts moved from Financials to Technology.
- Everything a rule uses comes from the same 22 sessions of bars the live scan
  already downloads, so anything that passes can ship without new data.

Rules, fixed before any result was seen. Each is the Cadence Score order after the
filter, top 60:
  BASE   the live list.
  A      Trend: closed above its own 20-day average.
  B      Relative strength: 20-day return beats SPY's.
  C      Sector tailwind: its sector fund's 20-day return beats SPY's.
  D      Trend + sector: A and C.
  E      Strength + sector: B and C.
  F      Sector cap: no filter, at most 12 names from any one sector.

Adoption test, also fixed in advance. A rule becomes the default order only if, on
the daily list averages:
  1. its 5-session return vs SPY beats BASE, with a 90% interval on the difference
     entirely above zero (5-day block bootstrap, since lists overlap day to day);
  2. it beats BASE in BOTH halves of the window;
  3. next-session open-to-close is no worse than BASE;
  4. next-session range stays at least 85% of BASE's, because movement is the
     list's whole job.
Six rules on one market regime, so a single marginal win is not a finding.

Usage:  python Website/scripts/cadence_theme_backtest.py
Needs:  Website/scripts/.cadence_cache/ (local) and yfinance
Output: Website/data/cadence_theme_scorecard.json  (research output, not served)
"""

import datetime as dt
import json
import os
import re
import statistics as st
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cadence_scan as cs                                # noqa: E402
import early_signal_backtest as esb                      # noqa: E402  (grouped cache, fund regex, OHLCV fetch)
import list_backtest as lb                               # noqa: E402  (git history)
import short_term_backtest as stb                        # noqa: E402  (day-cached loader)

REPO      = lb.REPO
CACHE_DIR = lb.CACHE_DIR
OUT_FILE  = os.path.join(REPO, "Website", "data", "cadence_theme_scorecard.json")

PRICE_START = "2026-03-20"
TEST_START  = dt.date(2026, 7, 1)
TOP_N       = 60
SECTOR_CAP  = 12
WINDOW      = 20          # sessions of relative strength and trend
MAX_MISSES  = 3

FUND_OF = {"Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Energy": "XLE",
           "Industrials": "XLI", "Communication Services": "XLC", "Consumer Cyclical": "XLY",
           "Consumer Defensive": "XLP", "Real Estate": "XLRE", "Basic Materials": "XLB", "Utilities": "XLU"}
LABEL_OF = {"XLK": "Technology", "XLF": "Financials", "XLV": "Health Care", "XLE": "Energy",
            "XLI": "Industrials", "XLC": "Comm. Services", "XLY": "Cons. Discretionary",
            "XLP": "Cons. Staples", "XLRE": "Real Estate", "XLB": "Materials", "XLU": "Utilities"}


# ── universe + data ───────────────────────────────────────────────────────────

def build_universe():
    days = esb._grouped_days()
    if len(days) < 40:
        sys.exit("need the Cadence scan's cached daily bars in %s" % esb.GROUPED)
    names = json.load(open(os.path.join(esb.GROUPED, "name_map.json")))
    order = sorted(days)
    last20 = order[-20:]
    uni = set()
    for tk in days[order[-1]]:
        name = names.get(tk, "")
        if not name or esb._FUND.search(name) or cs.is_leveraged_product(name) or not re.fullmatch(r"[A-Z]{1,5}", tk):
            continue
        bars = [days[d][tk] for d in last20 if tk in days[d]]
        if len(bars) < 18:
            continue
        if 8 <= st.median(b["c"] for b in bars) <= 600 and st.median(b["c"] * b["v"] for b in bars) >= 15e6:
            uni.add(tk)
    seen_live, live = 0, {}
    for when, data in lb.versions("Website/MarketDashboard/data/cadence.json"):
        rows = data.get("names") or []
        live[data.get("generated") or when.date().isoformat()] = [r["ticker"] for r in rows]
        for r in rows:
            nm = r.get("name") or names.get(r["ticker"], "")
            if not (nm and (esb._FUND.search(nm) or cs.is_leveraged_product(nm))) and re.fullmatch(r"[A-Z]{1,5}", r["ticker"]):
                if r["ticker"] not in uni:
                    seen_live += 1
                uni.add(r["ticker"])
    print("[universe] %d stocks (%d added from the live list's history)" % (len(uni), seen_live))
    return sorted(uni), live


def load_sectors(tickers):
    """{ticker: (yahoo sector, industry)}, cached across runs. A failed lookup is
    a miss, retried on the next run, never recorded as 'no sector'."""
    import yfinance as yf
    path = os.path.join(CACHE_DIR, "sector_info.json")
    miss_path = os.path.join(CACHE_DIR, "sector_misses.json")
    info = json.load(open(path)) if os.path.exists(path) else {}
    misses = json.load(open(miss_path)) if os.path.exists(miss_path) else {}
    need = [t for t in tickers if t not in info and misses.get(t, 0) < MAX_MISSES]
    print("[sector] %d known, %d to look up" % (len(info), len(need)))

    def one(t):
        for attempt in (1, 2, 3):
            try:
                i = yf.Ticker(t.replace(".", "-")).info
                if i and i.get("sector"):
                    return t, [i["sector"], i.get("industry")]
                return t, None
            except Exception:
                time.sleep(4 * attempt)
        return t, None

    for start in range(0, len(need), 40):
        with ThreadPoolExecutor(4) as ex:
            for t, v in ex.map(one, need[start:start + 40]):
                if v:
                    info[t] = v
                    misses.pop(t, None)
                else:
                    misses[t] = misses.get(t, 0) + 1
        json.dump(info, open(path, "w"))
        json.dump(misses, open(miss_path, "w"))
        print("[sector] %d / %d" % (min(start + 40, len(need)), len(need)), flush=True)
    return info


def sector_fund(tk, info):
    if tk in cs.MINER_HOSTS:
        return "XLK"
    v = info.get(tk)
    return FUND_OF.get(v[0]) if v else None


# ── simulation ────────────────────────────────────────────────────────────────

RULES = [
    ("BASE: live list",            lambda f: True, None),
    ("A: above 20-day average",    lambda f: f["above_ma20"], None),
    ("B: beats SPY over 20 days",  lambda f: f["rs20"] is not None and f["rs20"] > 0, None),
    ("C: sector beats SPY",        lambda f: f["fund_rs20"] is not None and f["fund_rs20"] > 0, None),
    ("D: trend + sector",          lambda f: f["above_ma20"] and f["fund_rs20"] is not None and f["fund_rs20"] > 0, None),
    ("E: strength + sector",       lambda f: f["rs20"] is not None and f["rs20"] > 0 and f["fund_rs20"] is not None and f["fund_rs20"] > 0, None),
    ("F: max 12 per sector",       lambda f: True, SECTOR_CAP),
]
METRICS = ("day", "best", "worst", "range", "t5", "t20")


def simulate(universe, frames, sectors):
    spy = frames["SPY"]
    cal = [d.date() for d in spy.index]
    pos = {d: i for i, d in enumerate(cal)}
    spy_o, spy_c = spy["Open"].to_numpy(), spy["Close"].to_numpy()

    arrays = {}
    for t, f in frames.items():
        a = {k: np.full(len(cal), np.nan) for k in ("o", "h", "l", "c", "v")}
        for d, o, h, l, c, v in zip(f.index, f["Open"], f["High"], f["Low"], f["Close"], f["Volume"]):
            i = pos.get(d.date())
            if i is not None:
                a["o"][i], a["h"][i], a["l"][i], a["c"][i], a["v"][i] = o, h, l, c, v
        arrays[t] = a

    def ret20(a, i):
        c0, c1 = a["c"][i - WINDOW], a["c"][i]
        return (c1 / c0 - 1) * 100 if c0 and c0 == c0 and c1 == c1 else None

    daily = {name: defaultdict(list) for name, *_ in RULES}
    lists = {name: {} for name, *_ in RULES}
    eligible_by_day = {}
    test_days = [i for i, d in enumerate(cal) if d >= TEST_START and i + 1 < len(cal) and i >= 22]
    for n, i in enumerate(test_days):
        spy20 = ret20(arrays["SPY"], i)
        fund_rs = {}
        for fund in LABEL_OF:
            r = ret20(arrays[fund], i) if fund in arrays else None
            fund_rs[fund] = r - spy20 if r is not None and spy20 is not None else None
        feats = []
        for t in universe:
            a = arrays.get(t)
            if a is None or a["c"][i] != a["c"][i]:
                continue
            idx = range(i - 21, i + 1)
            bars = [{"c": a["c"][j], "h": a["h"][j], "l": a["l"][j], "v": a["v"][j]} for j in idx if a["c"][j] == a["c"][j]]
            s = cs.score_ticker(t, bars)
            if not s:
                continue
            closes = [b["c"] for b in bars[-WINDOW:]]
            r = ret20(a, i)
            fund = sector_fund(t, sectors)
            feats.append({"ticker": t, "score": s["cadence_score"], "adr": s["adr_pct"], "fund": fund,
                          "above_ma20": a["c"][i] > sum(closes) / len(closes),
                          "rs20": r - spy20 if r is not None and spy20 is not None else None,
                          "fund_rs20": fund_rs.get(fund) if fund else None, "i": i})
        feats.sort(key=lambda f: f["score"], reverse=True)
        eligible_by_day[cal[i]] = feats

        def outcome(f):
            a = arrays[f["ticker"]]
            o1, h1, l1, c1 = a["o"][i + 1], a["h"][i + 1], a["l"][i + 1], a["c"][i + 1]
            if not (o1 == o1 and c1 == c1 and o1 > 0):
                return None
            spy_day = (spy_c[i + 1] / spy_o[i + 1] - 1) * 100
            out = {"day": (c1 / o1 - 1) * 100 - spy_day, "best": (h1 / o1 - 1) * 100, "worst": (l1 / o1 - 1) * 100,
                   "range": (h1 - l1) / c1 * 100}
            for key, k in (("t5", 5), ("t20", 20)):
                if i + k < len(cal) and a["c"][i + k] == a["c"][i + k]:
                    out[key] = (a["c"][i + k] / o1 - 1) * 100 - (spy_c[i + k] / spy_o[i + 1] - 1) * 100
            return out

        cache = {}
        for name, ok, cap in RULES:
            picked, per = [], Counter()
            for f in feats:
                if not ok(f):
                    continue
                if cap and f["fund"] and per[f["fund"]] >= cap:
                    continue
                picked.append(f)
                per[f["fund"]] += 1
                if len(picked) == TOP_N:
                    break
            lists[name][cal[i]] = picked
            outs = []
            for f in picked:
                if f["ticker"] not in cache:
                    cache[f["ticker"]] = outcome(f)
                if cache[f["ticker"]]:
                    outs.append(cache[f["ticker"]])
            for m in METRICS:
                vals = [o[m] for o in outs if m in o]
                daily[name][m].append(float(np.mean(vals)) if len(vals) >= 10 else np.nan)
            daily[name]["n"].append(len(picked))
        if n % 20 == 0:
            print("[sim] %s  eligible %d" % (cal[i], len(feats)), flush=True)
    return daily, lists, eligible_by_day, [cal[i] for i in test_days]


def block_ci(diff, block=5, reps=4000, seed=11):
    d = np.asarray([x for x in diff if x == x])
    if len(d) < 15:
        return None
    rnd = np.random.default_rng(seed)
    n_blocks = int(np.ceil(len(d) / block))
    means = []
    for _ in range(reps):
        starts = rnd.integers(0, len(d) - block + 1, n_blocks)
        means.append(np.concatenate([d[s:s + block] for s in starts])[:len(d)].mean())
    return round(float(np.percentile(means, 5)), 3), round(float(np.percentile(means, 95)), 3)


def main():
    universe, live = build_universe()
    tickers = sorted(set(universe) | {"SPY"} | set(LABEL_OF))
    frames = stb._load("cadencedaily", tickers, lambda c: esb._yf_ohlcv(c, start=PRICE_START, interval="1d"))
    if "SPY" not in frames:
        sys.exit("SPY unavailable - refusing to run without the benchmark")
    print("[data] prices for %d of %d" % (sum(1 for t in universe if t in frames), len(universe)))

    # Sectors only matter for names that can reach the list, so a first pass finds them.
    sectors = load_sectors([t for t in universe if t in frames and frames[t]["Close"].iloc[-30:].median() >= 8])
    daily, lists, elig, days = simulate(universe, frames, sectors)

    base = RULES[0][0]
    print("\n=== 1. COVERAGE ===")
    print("  %d sessions tested, %s to %s; eligible names per day: median %d" % (
        len(days), days[0], days[-1], st.median(len(v) for v in elig.values())))
    known = sum(1 for t in universe if sector_fund(t, sectors))
    print("  sector known for %d of %d universe names" % (known, len(universe)))
    for name, *_ in RULES:
        ns = daily[name]["n"]
        print("  %-28s list size median %d, min %d" % (name, st.median(ns), min(ns)))

    print("\n=== 2. CONTROL: simulated BASE vs the list the live scan published ===")
    overlaps = []
    for d in days:
        pub = live.get(d.isoformat())
        if pub:
            sim = {f["ticker"] for f in lists[base][d]}
            cut = [t for t in pub if not cs.is_leveraged_product(t)]
            if d >= dt.date(2026, 9, 25):       # the live list held leveraged funds before this
                overlaps.append(len(sim & set(cut)) / max(len(cut), 1))
    if overlaps:
        print("  %d comparable days since the leveraged-fund fix: median overlap %.0f%%" % (len(overlaps), 100 * st.median(overlaps)))

    half = len(days) // 2
    card = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "window": [str(days[0]), str(days[-1])], "sessions": len(days), "rules": {}}
    print("\n=== 3. RESULTS (daily list averages; returns vs SPY, points) ===")
    print("  %-28s %8s %7s %7s %7s %8s %8s" % ("", "next day", "best", "worst", "range", "5 sess", "20 sess"))
    for name, *_ in RULES:
        d = daily[name]
        s = {m: round(float(np.nanmean(d[m])), 3) for m in METRICS}
        card["rules"][name] = s
        print("  %-28s %+8.2f %+7.2f %+7.2f %7.2f %+8.2f %+8.2f" % (name, s["day"], s["best"], s["worst"], s["range"], s["t5"], s["t20"]))

    print("\n=== 4. ADOPTION TEST (fixed in advance) ===")
    print("  %-28s %-24s %-22s %-10s %-8s %s" % ("", "5-sess edge (90% CI)", "1st half / 2nd half", "next day", "range", "verdict"))
    b = daily[base]
    for name, *_ in RULES[1:]:
        d = daily[name]
        diff = np.array(d["t5"]) - np.array(b["t5"])
        ci = block_ci(diff)
        h1, h2 = float(np.nanmean(diff[:half])), float(np.nanmean(diff[half:]))
        day_edge = float(np.nanmean(np.array(d["day"]) - np.array(b["day"])))
        rng = float(np.nanmean(d["range"]) / np.nanmean(b["range"]))
        ok = bool(ci and ci[0] > 0 and h1 > 0 and h2 > 0 and day_edge >= 0 and rng >= 0.85)
        card["rules"][name].update({"t5_edge": round(float(np.nanmean(diff)), 3), "t5_edge_90ci": ci, "t5_edge_h1": round(h1, 3),
                                    "t5_edge_h2": round(h2, 3), "day_edge": round(day_edge, 3), "range_ratio": round(rng, 3), "adopt": ok})
        print("  %-28s %+6.2f %-17s %+6.2f / %+6.2f %12s %+8.3f %7.0f%%  %s" % (
            name, float(np.nanmean(diff)), str(ci), h1, h2, "", day_edge, 100 * rng, "PASS" if ok else "fail"))

    print("\n=== 5. YOUR QUESTION: where is the rhythm, by sector? (latest session) ===")
    last = days[-1]
    feats = elig[last]
    by = defaultdict(list)
    for f in feats:
        by[f["fund"]].append(f)
    spy_row = {}
    top60 = Counter(f["fund"] for f in lists[base][last])
    print("  %-22s %8s %9s %11s %s" % ("sector", "fund rs20", "eligible", "in top 60", "highest-scoring names"))
    order = sorted(LABEL_OF, key=lambda x: -(next((f["fund_rs20"] for f in feats if f["fund"] == x and f["fund_rs20"] is not None), -999)))
    for fund in order:
        rows = by.get(fund, [])
        rs = next((f["fund_rs20"] for f in rows if f["fund_rs20"] is not None), None)
        print("  %-22s %+8.1f %9d %11d %s" % (LABEL_OF[fund], rs if rs is not None else 0, len(rows), top60.get(fund, 0),
                                              ", ".join("%s %.0f" % (f["ticker"], f["score"]) for f in rows[:5])))
    print("  no sector: %d" % len(by.get(None, [])))
    card["latest_by_sector"] = {LABEL_OF[f]: {"eligible": len(by.get(f, [])), "in_top_60": top60.get(f, 0)} for f in LABEL_OF}

    print("\n=== 6. Sector share of the BASE list over time ===")
    months = defaultdict(Counter)
    for d in days:
        months[d.strftime("%Y-%m")].update(f["fund"] for f in lists[base][d])
    for m in sorted(months):
        tot = sum(months[m].values())
        print("  %s  %s" % (m, "  ".join("%s %2.0f%%" % (LABEL_OF.get(k, "none")[:10], 100.0 * v / tot) for k, v in months[m].most_common(5))))

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(card, f, indent=1, allow_nan=False, default=str)
    print("\n[scorecard] written to %s" % os.path.relpath(OUT_FILE, REPO))


if __name__ == "__main__":
    main()
