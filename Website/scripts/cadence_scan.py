"""
Cadence Scan — proprietary day-trade "tradeable rhythm" engine.

Scores the broad liquid US market on how good each name is as a repeatable
day-trade vehicle, the way BE / AAOI behave. Built entirely from daily OHLCV
bars pulled from Polygon's grouped-daily endpoint (one call = whole market
for one trading day), so it scales to ~12k tickers cheaply.

Cadence Score (0-100):
  ADR%         (45) — Average Daily Range. The literal "movement to trade."
                      Floor 3%, full credit by 8%, plateaus above (high range
                      is never penalized — chaos is caught by Consistency).
  Consistency  (25) — is the daily range dependable or erratic? Low coefficient
                      of variation = steady rhythm = high score. This is what
                      separates BE's learnable cadence from a one-off news pop.
  Liquidity    (20) — median daily dollar volume; must absorb real position size.
  Price-band   (10) — $20-300 ideal day range; $300-500 tagged "leans swing";
                      $10-20 allowed (quality gate applied at integration).

This is the standalone validation build. It prints where the user's known
names land so we can eyeball the ranking before wiring it into M&S.
Run: python scripts/cadence_scan.py
"""

import json
import os
import statistics
import re
import time
from collections import defaultdict
from datetime import date, timedelta

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Website/
OUTPUT_FILE = os.path.join(BASE_DIR, "MarketDashboard", "data", "cadence.json")
CACHE_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cadence_cache")

# `or` (not get's default): an unset GitHub Actions secret expands to an empty
# string, which would otherwise override the hardcoded key with "" and 401 every
# call. `or` falls back when the env var is missing OR empty.
POLYGON_KEY = os.environ.get("POLYGON_KEY") or "P9fRbZP9VAKhjwABMtvcS7tfcYGU6z1T"

LOOKBACK_DAYS = 22          # trading days of history to assemble
SCORE_WINDOW  = 20          # use the most recent N bars for scoring
MIN_BARS      = 18          # skip names without enough history

# Filters
MIN_PRICE       = 10.0
MAX_PRICE       = 500.0
MIN_DOLLAR_VOL  = 25_000_000   # median daily $ volume floor (tradeable)
MIN_ADR         = 3.0          # % — enough range to bother

# Names to spotlight in the sanity print
WATCH = ["BE", "AAOI", "TE", "NVDA", "DELL", "MRVL", "AVGO", "TQQQ", "SOXL", "PLTR"]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


# Trim verbose share-class boilerplate Polygon appends to company names
# ("Common Stock", "Class A Common Stock", "Ordinary Shares", etc.) so the
# watchlist shows "Hut 8 Corp." instead of "Hut 8 Corp. Common Stock".
_NAME_SUFFIX_RE = re.compile(
    r"\s+(Class\s+[A-Z]\s+)?(Common Stock|Common Shares|Ordinary Shares?|"
    r"Ordinary Share|American Depositary Shares?|ADS)\b.*$",
    re.IGNORECASE,
)

def clean_name(nm):
    return _NAME_SUFFIX_RE.sub("", (nm or "").strip()).strip()


# ── Data: Polygon grouped daily (one call = whole market for one day) ─────────

def fetch_grouped(d):
    """Grouped-daily OHLCV for a single date, cached locally so re-runs are
    instant. Returns the parsed JSON dict or None."""
    # One-time key diagnostic (a blank key in CI is the classic "No data" cause)
    if not getattr(fetch_grouped, "_announced", False):
        fetch_grouped._announced = True
        k = POLYGON_KEY or ""
        print(f"[fetch] Polygon key: {'EMPTY!' if not k else 'len ' + str(len(k)) + ' …' + k[-4:]}")

    cache_path = os.path.join(CACHE_DIR, f"{d.isoformat()}.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{d.isoformat()}"
    for attempt in range(6):
        try:
            r = requests.get(url, params={"adjusted": "true", "apiKey": POLYGON_KEY}, timeout=30)
        except Exception as e:
            print(f"   {d} request error: {e}")
            time.sleep(5)
            continue
        if r.status_code == 429:
            time.sleep(15)
            continue
        if r.status_code != 200:
            # Surface the first few failures so a broken key / blocked IP / quota
            # shows up in the log instead of a silent "No data".
            fetch_grouped._fails = getattr(fetch_grouped, "_fails", 0) + 1
            if fetch_grouped._fails <= 4:
                print(f"[fetch] {d} -> HTTP {r.status_code}: {r.text[:140]}")
            return None
        j = r.json()
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(j, f)
        time.sleep(2)   # be polite to the free tier
        return j
    return None


def collect_history():
    """Walk back from yesterday, collecting LOOKBACK_DAYS trading days that
    actually return data (skips weekends/holidays automatically)."""
    days = {}
    d = date.today() - timedelta(days=1)
    checks = 0
    while len(days) < LOOKBACK_DAYS and checks < LOOKBACK_DAYS * 2 + 15:
        checks += 1
        j = fetch_grouped(d)
        if j and j.get("results"):
            days[d.isoformat()] = j["results"]
        d -= timedelta(days=1)
    return days


def build_series(days):
    """{ticker: [bar, ...]} sorted by date ascending."""
    series = defaultdict(list)
    for dstr in sorted(days.keys()):
        for bar in days[dstr]:
            t = bar.get("T")
            if not t:
                continue
            series[t].append({
                "d": dstr,
                "h": bar.get("h"), "l": bar.get("l"),
                "c": bar.get("c"), "v": bar.get("v"),
            })
    return series


def fetch_name_map():
    """Build a {ticker: company name} map from Polygon's tickers reference
    (paginated, ~12 calls for the whole market). Grouped-daily bars give us
    OHLCV but no names, so this is how the watchlist gets 'DigitalOcean'
    under 'DOCN'. Cached locally for 7 days since names rarely change."""
    cache_path = os.path.join(CACHE_DIR, "name_map.json")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path)) < 7 * 86400:
        with open(cache_path) as f:
            return json.load(f)

    print("[cadence] Building ticker -> name map...")
    names = {}
    url = "https://api.polygon.io/v3/reference/tickers"
    params = {"market": "stocks", "active": "true", "limit": 1000, "apiKey": POLYGON_KEY}
    pages = 0
    while url and pages < 25:
        pages += 1
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(15)
                continue
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            print(f"[cadence] name map page {pages} failed: {e}")
            break
        for row in (j.get("results") or []):
            t, nm = row.get("ticker"), row.get("name")
            if t and nm:
                names[t] = nm
        url = j.get("next_url")
        params = {"apiKey": POLYGON_KEY}   # next_url already carries the cursor/filters
        if url:
            time.sleep(2)

    if names:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(names, f)
    print(f"[cadence] Name map: {len(names)} tickers across {pages} pages")
    return names


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_ticker(ticker, bars):
    bars = [b for b in bars if b["c"] and b["h"] and b["l"]]
    if len(bars) < MIN_BARS:
        return None
    recent = bars[-SCORE_WINDOW:]

    ranges      = [(b["h"] - b["l"]) / b["c"] * 100 for b in recent if b["c"]]
    dollar_vols = [b["c"] * b["v"] for b in recent if b["c"] and b["v"]]
    if not ranges or not dollar_vols:
        return None

    price          = recent[-1]["c"]
    adr            = statistics.mean(ranges)
    med_dollar_vol = statistics.median(dollar_vols)

    # ── Filters ──
    if price < MIN_PRICE or price > MAX_PRICE:
        return None
    if med_dollar_vol < MIN_DOLLAR_VOL:
        return None
    if adr < MIN_ADR:
        return None

    # ── ADR component (45): floor 3%, full by 8%, plateau above (no penalty) ──
    adr_factor = clamp((adr - 3.0) / (8.0 - 3.0), 0.0, 1.0)
    adr_pts    = adr_factor * 45

    # ── Consistency (25): low coefficient of variation = steady rhythm ──
    rmean = statistics.mean(ranges)
    rstd  = statistics.pstdev(ranges)
    cv    = (rstd / rmean) if rmean else 1.0
    consistency = clamp((0.7 - cv) / (0.7 - 0.2), 0.0, 1.0)
    cons_pts    = consistency * 25

    # ── Liquidity (20): tiered on median daily dollar volume ──
    if   med_dollar_vol >= 200e6: liq = 1.0
    elif med_dollar_vol >= 50e6:  liq = 0.7
    else:                         liq = 0.4
    liq_pts = liq * 20

    # ── Price-band fit (10) ──
    if   20 <= price <= 300: pb = 1.0
    elif 300 < price <= 500: pb = 0.5
    elif 10 <= price < 20:   pb = 0.7
    else:                    pb = 0.0
    pb_pts = pb * 10

    score = round(adr_pts + cons_pts + liq_pts + pb_pts, 1)
    return {
        "ticker":        ticker,
        "price":         round(price, 2),
        "adr_pct":       round(adr, 1),
        "consistency":   round(consistency, 2),
        "dollar_vol":    int(med_dollar_vol),
        "cadence_score": score,
        "tag":           "leans-swing" if price > 300 else "day",
        "_components":   {"adr": round(adr_pts, 1), "cons": round(cons_pts, 1),
                          "liq": round(liq_pts, 1), "pb": round(pb_pts, 1)},
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("[cadence] Collecting grouped-daily history...")
    days = collect_history()
    print(f"[cadence] Got {len(days)} trading days: "
          f"{min(days)} -> {max(days)}" if days else "[cadence] No data")
    if not days:
        return

    series = build_series(days)
    print(f"[cadence] Built series for {len(series)} tickers")

    scored = []
    for t, bars in series.items():
        s = score_ticker(t, bars)
        if s:
            scored.append(s)
    scored.sort(key=lambda x: x["cadence_score"], reverse=True)
    print(f"[cadence] {len(scored)} names passed filters\n")

    # ── Sanity print ──
    by_ticker = {s["ticker"]: (i + 1, s) for i, s in enumerate(scored)}

    print("=== WATCHLIST NAMES (where your known names land) ===")
    print(f"{'Tkr':6} {'Rank':>5} {'Score':>6} {'ADR%':>5} {'Cons':>5} "
          f"{'$Vol':>7} {'Price':>8} {'Tag':12} components")
    for w in WATCH:
        if w in by_ticker:
            rank, s = by_ticker[w]
            c = s["_components"]
            dv = f"${s['dollar_vol']/1e6:.0f}M"
            print(f"{w:6} {rank:>5} {s['cadence_score']:>6} {s['adr_pct']:>5} "
                  f"{s['consistency']:>5} {dv:>7} ${s['price']:>7} {s['tag']:12} "
                  f"adr={c['adr']} cons={c['cons']} liq={c['liq']} pb={c['pb']}")
        else:
            print(f"{w:6}   —   (filtered out or not in universe)")

    print("\n=== TOP 25 BY CADENCE SCORE ===")
    print(f"{'Rank':>4} {'Tkr':6} {'Score':>6} {'ADR%':>5} {'Cons':>5} {'$Vol':>7} {'Price':>8} {'Tag'}")
    for i, s in enumerate(scored[:25], 1):
        dv = f"${s['dollar_vol']/1e6:.0f}M"
        print(f"{i:>4} {s['ticker']:6} {s['cadence_score']:>6} {s['adr_pct']:>5} "
              f"{s['consistency']:>5} {dv:>7} ${s['price']:>7} {s['tag']}")

    # Enrich the top 60 with company names (grouped-daily bars carry none)
    name_map = fetch_name_map()

    out = []
    for s in scored[:60]:
        s2 = {k: v for k, v in s.items() if k != "_components"}
        s2["name"] = clean_name(name_map.get(s2["ticker"], ""))
        out.append(s2)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"generated": max(days), "count": len(scored), "names": out}, f, indent=2)
    print(f"\n[cadence] Wrote top {len(out)} to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
