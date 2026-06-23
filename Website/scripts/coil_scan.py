"""
Coil Scan — proprietary swing-setup engine ("Coil Score").

The swing-side mirror of the Cadence engine. Scores the broad liquid US market
on how wound-up and ready-to-break each name is: a tight consolidation, in an
uptrend, with relative strength and contracting volume. This is the
"buy a little and wait for the move" profile — the MRVL / DELL / NVDA-setting-up
setup, surfaced before it goes.

Coil Score (0-100):
  Trend stack    (30) — price > 10 > 20 > 50-day SMA (intermediate uptrend).
                        Below the 50-day zeroes it out — no coils in downtrends.
  Relative str   (25) — 3-month return percentile across the universe (leaders).
  Tightness      (25) — recent 10-day range narrow AND contracting vs the base
                        (the coil itself — energy building before the break).
  Volume dry-up  (20) — recent volume below its 50-day base (classic pre-breakout).

The detected chart pattern (Volatility squeeze / VCP / Bull flag / Coiled base)
is folded in: its characteristics drive the tightness + trend points, and the
label rides along on each card as a tag.

Reuses the Cadence grouped-daily pipeline + name map (shared local cache, same
Polygon key) — only the lookback and scoring differ.

Output: PatternScanner/data/coil.json. Run: python Website/scripts/coil_scan.py
"""

import bisect
import json
import os
import statistics
import sys
import time
from datetime import date, timedelta

# Reuse the proven data layer from the Cadence scan (shared cache + name map)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cadence_scan import fetch_grouped, build_series, fetch_name_map, clean_name, clamp  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Website/
OUTPUT_FILE = os.path.join(BASE_DIR, "PatternScanner", "data", "coil.json")

LOOKBACK_DAYS  = 70          # trading days of history to assemble
MIN_BARS       = 55          # need ~50 for the 50-DMA + base windows

MIN_PRICE      = 10.0
MAX_PRICE      = 1000.0      # swings run higher than day names (NVDA/AVGO/DELL)
MIN_DOLLAR_VOL = 20_000_000

# Names to spotlight in the sanity print (user's swing names + known leaders)
WATCH = ["MRVL", "DELL", "NVDA", "AVGO", "TQQQ", "AAPL", "MSFT",
         "PLTR", "ANET", "CRWD", "NFLX", "NBIS"]


def collect_history(lookback):
    """Walk back from yesterday, collecting `lookback` trading days with data."""
    days = {}
    d = date.today() - timedelta(days=1)
    checks = 0
    while len(days) < lookback and checks < lookback * 2 + 20:
        checks += 1
        j = fetch_grouped(d)
        if j and j.get("results"):
            days[d.isoformat()] = j["results"]
        d -= timedelta(days=1)
    return days


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_ticker(ticker, bars):
    bars = [b for b in bars if b["c"] and b["h"] and b["l"] and b["v"]]
    if len(bars) < MIN_BARS:
        return None

    closes = [b["c"] for b in bars]
    highs  = [b["h"] for b in bars]
    lows   = [b["l"] for b in bars]
    vols   = [b["v"] for b in bars]
    price  = closes[-1]

    med_dollar_vol = statistics.median([closes[i] * vols[i] for i in range(len(closes))][-50:])
    if price < MIN_PRICE or price > MAX_PRICE:
        return None
    if med_dollar_vol < MIN_DOLLAR_VOL:
        return None

    ma10 = statistics.mean(closes[-10:])
    ma20 = statistics.mean(closes[-20:])
    ma50 = statistics.mean(closes[-50:])

    # ── Trend stack (30) — below the 50-day disqualifies (trend_pts = 0) ──
    if price <= ma50:
        trend_pts = 0.0
    else:
        trend_pts = 12.0
        if price > ma20: trend_pts += 6
        if ma10 > ma20:  trend_pts += 6
        if ma20 > ma50:  trend_pts += 6

    # ── Tightness (25) — narrow 10-day band that's contracting vs the base ──
    def rng(i):
        return (highs[i] - lows[i]) / closes[i] * 100 if closes[i] else 0.0
    recent  = [rng(i) for i in range(len(closes) - 10, len(closes))]
    earlier = [rng(i) for i in range(len(closes) - 40, len(closes) - 10)]
    recent_avg  = statistics.mean(recent)
    earlier_avg = statistics.mean(earlier) if earlier else recent_avg
    contraction = recent_avg / earlier_avg if earlier_avg else 1.0
    band = (max(highs[-10:]) - min(lows[-10:])) / price * 100   # consolidation width
    tight_factor = clamp((18.0 - band) / (18.0 - 6.0), 0.0, 1.0)       # <6% wide -> 1.0
    contr_factor = clamp((1.0 - contraction) / (1.0 - 0.6), 0.0, 1.0)  # <0.6 ratio -> 1.0
    tight_pts = (0.6 * tight_factor + 0.4 * contr_factor) * 25

    # ── Volume dry-up (20) — recent volume below the 50-day base ──
    recent_vol = statistics.mean(vols[-10:])
    base_vol   = statistics.mean(vols[-50:])
    vol_ratio  = recent_vol / base_vol if base_vol else 1.0
    vol_factor = clamp((1.1 - vol_ratio) / (1.1 - 0.7), 0.0, 1.0)      # <0.7 -> 1.0
    vol_pts    = vol_factor * 20

    # 63-day return (RS percentile assigned in a second pass)
    ref = closes[-63] if len(closes) >= 63 else closes[0]
    ret63 = (price / ref - 1.0) * 100 if ref else 0.0

    return {
        "ticker":       ticker,
        "price":        round(price, 2),
        "dollar_vol":   int(med_dollar_vol),
        "ret63":        ret63,
        "band_pct":     round(band, 1),
        "contraction":  round(contraction, 2),
        "vol_ratio":    round(vol_ratio, 2),
        "extension":    round((price - ma20) / ma20 * 100, 1) if ma20 else 0.0,
        "above_50dma":  price > ma50,
        "perfect_stack": price > ma10 > ma20 > ma50,
        "history":      [round(c, 2) for c in closes[-40:]],   # for the card sparkline
        "_trend": round(trend_pts, 1), "_tight": round(tight_pts, 1), "_vol": round(vol_pts, 1),
    }


def classify(s):
    """A descriptive pattern tag derived from the measured shape."""
    if not s["above_50dma"]:
        return "Below trend"
    if s["band_pct"] < 6:
        return "Volatility squeeze"
    if s["contraction"] < 0.75 and s["band_pct"] < 13:
        return "Tight base (VCP)"
    if s["ret63"] > 20 and s["band_pct"] < 16:
        return "Bull flag"
    return "Coiled base"


def leader_score(s, rs_factor):
    """Strength-weighted score for the 'Leaders' list: constructive strong
    leaders. Relative strength and trend dominate, but a hard constructive
    gate excludes anything in a downtrend, parabolic above its 20-day, or
    actively blowing out (range expanding on a volume surge). Returns 0 for
    names that fail the gate, so the Leaders list is constructive-only —
    names you could buy and wait on, not ones that already ran."""
    if not s["above_50dma"]:
        return 0.0
    if s["extension"] > 20:                                      # parabolic above the 20-day
        return 0.0
    if s["extension"] < -15:                                     # sharp break below the 20-day
        return 0.0
    if s["band_pct"] > 25:                                       # wide, wild range — not orderly
        return 0.0
    if s["contraction"] > 1.25 and s["vol_ratio"] > 1.25:        # mid-breakout, already running
        return 0.0

    rs_pts    = rs_factor * 50
    trend_pts = (s["_trend"] / 30.0) * 25
    # Constructive (25): orderly, basing action with a sensible entry near the 20-day
    tight_factor = clamp((22.0 - s["band_pct"]) / (22.0 - 8.0), 0.0, 1.0)     # <8% band -> 1.0
    calm_factor  = clamp((1.2 - s["contraction"]) / (1.2 - 0.85), 0.0, 1.0)   # contracting -> 1.0
    near_factor  = clamp((12.0 - abs(s["extension"])) / 12.0, 0.0, 1.0)       # near 20-day -> 1.0
    constructive = (0.45 * tight_factor + 0.30 * calm_factor + 0.25 * near_factor) * 25
    return round(rs_pts + trend_pts + constructive, 1)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"[coil] Collecting {LOOKBACK_DAYS} trading days...")
    days = collect_history(LOOKBACK_DAYS)
    print(f"[coil] Got {len(days)} trading days: {min(days)} -> {max(days)}" if days else "[coil] No data")
    if not days:
        return

    series = build_series(days)
    print(f"[coil] Built series for {len(series)} tickers")

    scored = []
    for t, bars in series.items():
        s = score_ticker(t, bars)
        if s:
            scored.append(s)

    # ── Relative-strength percentile (rank 3-month returns across the field) ──
    rets = sorted(s["ret63"] for s in scored)
    n = len(rets)
    for s in scored:
        p = (bisect.bisect_left(rets, s["ret63"]) / n) if n else 0.0
        rs_factor = clamp((p - 0.3) / 0.7, 0.0, 1.0)
        s["rs_pct"]       = round(p * 100)
        s["coil_score"]   = round(s["_trend"] + s["_tight"] + s["_vol"] + rs_factor * 25, 1)
        s["pattern"]      = classify(s)
        s["leader_score"] = leader_score(s, rs_factor)

    # ── Two complementary lists ──
    coiled  = sorted(scored, key=lambda x: x["coil_score"], reverse=True)
    leaders = sorted([s for s in scored if s["leader_score"] > 0],
                     key=lambda x: x["leader_score"], reverse=True)
    print(f"[coil] {len(scored)} scored | {len(leaders)} pass the constructive-leader gate\n")

    coiled_rank  = {s["ticker"]: i + 1 for i, s in enumerate(coiled)}
    leader_rank  = {s["ticker"]: i + 1 for i, s in enumerate(leaders)}
    by_ticker    = {s["ticker"]: s for s in scored}

    print("=== WATCHLIST NAMES (your swing names + leaders) ===")
    print(f"{'Tkr':6} {'CoilRk':>6} {'Coil':>5} | {'LeadRk':>6} {'Lead':>5} | "
          f"{'RS%':>4} {'Band':>5} {'Ext%':>5} {'Contr':>6} {'Pattern'}")
    for w in WATCH:
        if w in by_ticker:
            s  = by_ticker[w]
            cr = coiled_rank.get(w, "-")
            lr = leader_rank.get(w, "-")
            print(f"{w:6} {str(cr):>6} {s['coil_score']:>5} | {str(lr):>6} {s['leader_score']:>5} | "
                  f"{s['rs_pct']:>4} {s['band_pct']:>5} {s['extension']:>5} {s['contraction']:>6} {s['pattern']}")
        else:
            print(f"{w:6}   —   (filtered out / not in universe)")

    def show(title, rows, key):
        print(f"\n=== TOP 18 — {title} ===")
        print(f"{'Rk':>3} {'Tkr':6} {'Score':>6} {'RS%':>4} {'Band':>5} {'Ext%':>5} {'VolR':>5} {'Price':>8} {'Pattern'}")
        for i, s in enumerate(rows[:18], 1):
            print(f"{i:>3} {s['ticker']:6} {s[key]:>6} {s['rs_pct']:>4} {s['band_pct']:>5} "
                  f"{s['extension']:>5} {s['vol_ratio']:>5} ${s['price']:>7} {s['pattern']}")
    show("COILED (tightness-weighted)", coiled, "coil_score")
    show("LEADERS (constructive strength)", leaders, "leader_score")

    # ── Output: enrich top 40 of each list with company names ──
    name_map = fetch_name_map()
    def enrich(rows):
        out = []
        for s in rows[:40]:
            s2 = {k: v for k, v in s.items() if not k.startswith("_")}
            s2["name"] = clean_name(name_map.get(s2["ticker"], ""))
            out.append(s2)
        return out

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"generated": max(days),
                   "universe": len(scored),
                   "coiled":  enrich(coiled),
                   "leaders": enrich(leaders)}, f, indent=2)
    print(f"\n[coil] Wrote {OUTPUT_FILE} (coiled + leaders)")


if __name__ == "__main__":
    run()
