"""
Market Temperature Scan — proprietary live market-regime thermometer.

Composite score 0-100:
  0 = Cold (washed out, fear), 100 = Hot (euphoric, overheated)

Rebuilt July 2026 from a valuation gauge into a REGIME thermometer. The old
valuation anchors (Buffett Indicator, Shiller CAPE, Fed Model — 40% of weight)
move on quarters, not days, and in this era sit permanently at their ceilings,
which pinned the composite in the mid-70s for weeks. They're gone; ~75% of the
weight now moves day to day, and the gauge leans on the lab's own signals.

Components (each scored 0-100):
  - Risk posture (lab's Sector Rotation engine)   — 15%  cyclical vs defensive rel. strength
  - Trend heat (SPY vs 50-DMA + 10-day thrust)    — 15%  percentile over 3yr
  - Fear & Greed (CNN sentiment composite)        — 15%  used directly (already 0-100)
  - Fast breadth (% S&P 500 above 50-DMA)         — 10%  used directly
  - Net new highs (near 52wk high − near low)     — 10%  derived from breadth download
  - Credit spreads (ICE BofA HY OAS, FRED)        — 10%  inverted percentile over 10yr
  - Growth vs Value (IWF / IWD style ratio)       — 10%  level + momentum percentile, 3yr
  - Structural breadth (% S&P 500 above 200-DMA)  —  5%  fixed thresholds
  - Insider breadth (SEC Form 4, buying vs sell)  —  5%  INVERTED percentile over 5yr
  - Yield curve (10Y − 2Y, FRED)                  —  5%  fixed thresholds (cycle stage)

Insider breadth is the one contrarian input — executives buy weakness and go
quiet into strength, so it is inverted. It comes from insider_pulse_scan.py,
which must run BEFORE this scan. Weighted at only 5%: tested against forward
S&P returns the direction holds, but on ~19 independent observations.

Output: MarketDashboard/data/market_temperature.json
Invoked by GitHub Actions daily. Run locally: python scripts/market_temperature_scan.py
"""

import json
import os
import time
from bisect import bisect_left
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "MarketDashboard", "data", "market_temperature.json")

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_BASE    = "https://api.stlouisfed.org/fred/series/observations"

NEXT_SCAN_INFO = "Weekdays at 6:00am ET"
CALIB_YEARS    = 10

# Price and participation signals (trend, breadth_50, new_highs, breadth) were
# 55% of the gauge and are heavily correlated with one another. Trimmed two of
# them by 5 points each to make room for insider breadth, which is genuinely
# orthogonal: it is the revealed preference of the people who know their own
# companies best, and it moves on a different clock than price.
# Aug 2026 rebalance. Insider breadth drops 10 -> 5: testing it against forward
# S&P returns showed the contrarian direction is right (quiet insiders precede
# weaker markets) but the relationship is non-monotonic and rests on roughly 19
# INDEPENDENT observations once overlapping windows are accounted for. That is
# far too thin to carry a tenth of the gauge.
# Structural breadth also drops 10 -> 5, being the slowest-moving of the three
# participation measures and largely saying what Fast Breadth already says.
# The freed weight funds Growth vs Value, which adds a style dimension the gauge
# had no read on at all.
WEIGHTS = {
    "risk_posture": 0.15,
    "trend":        0.15,
    "fear_greed":   0.15,
    "breadth_50":   0.10,
    "new_highs":    0.10,
    "credit":       0.10,
    "growth_value": 0.10,
    "breadth":      0.05,
    "insider":      0.05,
    "yield_curve":  0.05,
}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


# ── Shared helpers ───────────────────────────────────────────────────────────

def percentile_rank(series, value):
    """Percentile 0-100 of `value` within `series` (unsorted ok).
    0 = value at or below minimum; 100 = value strictly above max."""
    if not series:
        return None
    arr = sorted(series)
    idx = bisect_left(arr, value)
    return round(min(100.0, 100.0 * idx / len(arr)), 1)


def label_for(score):
    if score is None:
        return "Unknown"
    if score < 20:  return "Cold"
    if score < 40:  return "Cool"
    if score < 60:  return "Neutral"
    if score < 80:  return "Warm"
    return "Hot"


def fred_series(series_id, years_back):
    """Fetch a FRED series as list of (date_str, float), oldest first."""
    if not FRED_API_KEY:
        print(f"[market-temp] FRED_API_KEY missing, skipping {series_id}")
        return []
    start = (datetime.now(timezone.utc) - timedelta(days=int(years_back * 365.25))).date().isoformat()
    params = {
        "series_id":        series_id,
        "api_key":          FRED_API_KEY,
        "file_type":        "json",
        "observation_start": start,
    }
    try:
        r = requests.get(FRED_BASE, params=params, timeout=20)
        r.raise_for_status()
        obs = r.json().get("observations", [])
    except Exception as e:
        print(f"[market-temp] FRED {series_id} failed: {e}")
        return []
    out = []
    for o in obs:
        v = o.get("value", ".")
        if v in (".", ""):
            continue
        try:
            out.append((o["date"], float(v)))
        except (ValueError, KeyError):
            continue
    return out


# ── Component: Risk posture (the lab's own Sector Rotation read) ─────────────

def compute_risk_posture():
    """Cyclical vs defensive leadership from the Movers scan's Sector Rotation
    engine — the average 1-month relative strength (vs SPY) of cyclical sectors
    minus defensives, read straight from results.json in this repo. Cyclicals
    leading = risk appetite (hot); defensives leading = de-risking (cold).
    A ±8pt spread saturates the scale. Updated 6x/day by the market scan, so
    this component moves every session."""
    print("[market-temp] Risk posture (sector rotation)...")
    path = os.path.join(BASE_DIR, "MarketDashboard", "data", "results.json")
    try:
        with open(path) as f:
            posture = (json.load(f).get("sector_rotation") or {}).get("posture")
    except Exception as e:
        print(f"[market-temp] results.json unavailable: {e}")
        return None
    if not posture or posture.get("spread") is None:
        print("[market-temp] Risk posture: no posture in results.json yet")
        return None

    spread = float(posture["spread"])
    score  = round(clamp(50.0 + spread * 6.0, 0.0, 100.0), 1)
    leaders = ", ".join(posture.get("leaders") or []) or "n/a"
    return {
        "raw":         spread,
        "raw_label":   f"{spread:+.1f}pt {posture.get('label', '')}".strip(),
        "score":       score,
        "label":       label_for(score),
        "description": "Cyclical sectors' 1-month strength against defensives, from the lab's own "
                       "Sector Rotation engine. Cyclicals leading means risk appetite is on.",
    }


# ── Component: Insider breadth (corporate insiders' revealed preference) ─────

def compute_insider_breadth():
    """Share of companies with insider activity where that activity was BUYING,
    percentile-ranked against five years of its own history. Produced by
    insider_pulse_scan.py from SEC Form 345 data.

    INVERTED on purpose. Insiders buy their own stock when it looks cheap to the
    people who know it best, which happens in washed-out markets, and they stop
    buying when things feel expensive. So heavy insider buying is a COLD reading
    and an absence of buying is a HOT one. That makes this the only genuinely
    contrarian input in the gauge.

    Counts companies rather than dollars, because a single mis-keyed filing can
    otherwise dominate an entire quarter (see the scan's header for the case
    that motivated it)."""
    print("[market-temp] Insider breadth...")
    path = os.path.join(BASE_DIR, "MarketDashboard", "data", "insider_pulse.json")
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception as e:
        print(f"[market-temp] insider_pulse.json unavailable: {e}")
        return None

    pct = d.get("percentile")
    cur = d.get("current") or {}
    if pct is None or not cur:
        return None

    score = round(clamp(100.0 - float(pct), 0.0, 100.0), 1)   # invert
    return {
        "raw":         cur.get("breadth"),
        "raw_label":   ("Quiet" if pct is not None and pct < 40 else
                        "Active" if pct is not None and pct > 60 else "Middling")
                       + f" · {cur.get('buy_cos')} of {(cur.get('buy_cos') or 0) + (cur.get('sell_cos') or 0):,} buying",
        "percentile":  pct,
        "score":       score,
        "label":       label_for(score),
        # No counts here — raw_label already carries "529 of 1,962 buying". This
        # explains the inversion instead, which is the part that is not obvious.
        "description": "Share of Form 4 filers that were buying, ranked against five years. "
                       "Inverted: insiders buy weakness and go quiet into strength, so a "
                       "quiet tape reads hot.",
    }


# ── Component: Growth vs Value (which style the market is paying for) ────────

def compute_growth_value():
    """Russell 1000 Growth against Russell 1000 Value (IWF / IWD).

    The gauge had no read on STYLE. Growth leading value is the signature of a
    market paying up for future earnings and tolerating long duration risk,
    which is a hot condition; value leading is the market retreating to cash
    flows it can see today. Scored on both where the ratio sits against its own
    three-year history and how it has moved over the last quarter, because a
    stretched ratio that is already rolling over says something different from
    one still climbing.

    Not a duplicate of Risk Posture, which measures cyclical versus defensive
    SECTORS. The two genuinely diverge — at the time of writing sector rotation
    reads risk-on while growth is down double digits against value."""
    print("[market-temp] Growth vs Value...")
    try:
        import yfinance as yf
        d = yf.download("IWF IWD", period="3y", interval="1d", auto_adjust=True,
                        group_by="ticker", progress=False, threads=False)
        g = d["IWF"]["Close"].dropna()
        v = d["IWD"]["Close"].dropna()
    except Exception as e:
        print(f"[market-temp] Growth/Value fetch failed: {e}")
        return None

    ratio = (g / v.reindex(g.index)).dropna()
    if len(ratio) < 200:
        print("[market-temp] Growth/Value: insufficient history")
        return None

    vals = [float(x) for x in ratio.values]
    cur  = vals[-1]
    level_pct = percentile_rank(vals[:-1], cur)

    lookback = 63 if len(vals) > 63 else len(vals) - 1
    chg = (cur / vals[-1 - lookback] - 1.0) * 100.0
    changes = [(vals[i] / vals[i - lookback] - 1.0) * 100.0
               for i in range(lookback, len(vals))]
    mom_pct = percentile_rank(changes[:-1], chg)

    if level_pct is None or mom_pct is None:
        return None
    score = round(clamp((level_pct + mom_pct) / 2.0, 0.0, 100.0), 1)
    leader = "Growth" if chg > 0 else "Value"
    return {
        "raw":         round(cur, 4),
        "raw_label":   f"{leader} leading, {chg:+.1f}% in 3mo",
        "percentile":  level_pct,
        "score":       score,
        "label":       label_for(score),
        "description": f"Russell 1000 Growth against Value: {level_pct}th percentile of three years, "
                       f"{chg:+.1f}% this quarter. Growth leading means investors are paying up "
                       f"for future earnings.",
    }


# ── Component: Trend heat (S&P 500 price structure) ──────────────────────────

def compute_trend_heat():
    """Where the S&P sits vs its 50-day average plus the strength of the last
    two weeks' move, each percentile-ranked against ~3 years of daily history
    and averaged. The fastest-moving component — built to make the gauge
    breathe day to day."""
    print("[market-temp] Trend heat (SPY)...")
    try:
        import yfinance as yf
        hist = yf.Ticker("SPY").history(period="3y", interval="1d", auto_adjust=True)
    except Exception as e:
        print(f"[market-temp] SPY fetch failed: {e}")
        return None
    if hist is None or len(hist) < 300:
        print("[market-temp] Trend heat: insufficient SPY history")
        return None

    close = hist["Close"].dropna()
    dist  = ((close / close.rolling(50).mean()) - 1.0).dropna() * 100   # % vs 50-DMA
    roc10 = (close.pct_change(10).dropna()) * 100                       # 10-day thrust
    if len(dist) < 250 or len(roc10) < 250:
        return None

    d_now, r_now = float(dist.iloc[-1]), float(roc10.iloc[-1])
    d_pct = percentile_rank([float(v) for v in dist.iloc[:-1]], d_now)
    r_pct = percentile_rank([float(v) for v in roc10.iloc[:-1]], r_now)
    if d_pct is None or r_pct is None:
        return None

    score = round((d_pct + r_pct) / 2.0, 1)
    return {
        "raw":         round(d_now, 2),
        "raw_label":   f"{d_now:+.1f}% vs 50-DMA",
        "score":       score,
        "label":       label_for(score),
        "description": "The S&P against its 50-day average plus the last two weeks' thrust, "
                       "percentile-ranked over three years.",
    }


# ── Component: Credit spreads (ICE BofA US High Yield OAS) ───────────────────

def compute_credit_spreads():
    """High-yield credit spread — the extra yield investors demand to hold junk
    bonds over Treasuries. TIGHT spreads = risk-on complacency (frothy); WIDE
    spreads = stress/fear (cheap). Percentile-ranked over ~10yr then INVERTED so
    a tight spread maps to a high (hot) score. A genuinely dynamic risk-appetite
    read — it widens fast in selloffs."""
    print("[market-temp] Credit spreads (HY OAS)...")
    series = fred_series("BAMLH0A0HYM2", CALIB_YEARS)
    if len(series) < 250:
        print("[market-temp] Credit spreads: insufficient history")
        return None
    current    = series[-1][1]
    historical = [v for _, v in series[:-1]]
    pct = percentile_rank(historical, current)   # high pct = wide spread = fear
    if pct is None:
        return None
    score = round(clamp(100.0 - pct, 0.0, 100.0), 1)   # invert: tight → hot
    return {
        "raw":         round(current, 2),
        "raw_label":   f"{current:.2f}% HY OAS",
        "percentile":  pct,
        "score":       score,
        "label":       label_for(score),
        "description": "Extra yield demanded to hold junk bonds over Treasuries. Tight means "
                       "complacency, wide means stress. Inverted, so tight scores hot.",
    }


# ── Component: Yield curve (10Y − 2Y Treasury) ───────────────────────────────

def compute_yield_curve():
    """10-year minus 2-year Treasury spread. A steep positive curve is
    early-cycle and healthy (cooler); a flat-to-inverted curve marks a late-cycle
    market — historically stretched and prone to froth before a downturn (hotter).
    Mapped via fixed thresholds; cycle-stage context rather than a valuation."""
    print("[market-temp] Yield curve (10Y-2Y)...")
    series = fred_series("T10Y2Y", 0.5)
    if not series:
        return None
    spread = series[-1][1]
    if   spread >  1.5:  score = 30   # steep — early cycle
    elif spread >  0.75: score = 42
    elif spread >  0.25: score = 52
    elif spread >  0.0:  score = 60   # flat — mid/late cycle
    elif spread > -0.5:  score = 72   # mildly inverted — late cycle
    else:                score = 85   # deeply inverted
    return {
        "raw":         round(spread, 2),
        "raw_label":   f"{spread:+.2f}% (10Y−2Y)",
        "score":       score,
        "label":       label_for(score),
        "description": "10-year minus 2-year Treasury. A steep curve is early-cycle and healthy; "
                       "flat or inverted marks a late-cycle market.",
    }


# ── Component 4: Breadth (% above 200-DMA) ───────────────────────────────────

def _fetch_sp500_tickers():
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                         headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[market-temp] SP500 tickers fetch failed: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", id="constituents")
    if not table:
        return []
    tickers = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if cells:
            t = cells[0].get_text(strip=True).replace(".", "-")
            if t:
                tickers.append(t)
    return tickers


def compute_internals():
    """Downloads the S&P 500 once and derives THREE components:
      - breadth_50: % of stocks above their 50-day MA (the FAST participation
                    read — swings hard with every pullback and rally)
      - breadth:    % of stocks above their 200-day MA (structural trend health)
      - new_highs:  net % near a 52-week high minus near a 52-week low (the
                    euphoria/stress extreme)
    Returns {"breadth_50": ..., "breadth": ..., "new_highs": ...} (each dict|None)."""
    print("[market-temp] Market internals (breadth + new highs)...")
    out = {"breadth_50": None, "breadth": None, "new_highs": None}
    try:
        import yfinance as yf
    except ImportError:
        print("[market-temp] yfinance not available")
        return out

    tickers = _fetch_sp500_tickers()
    if not tickers:
        return out
    print(f"[market-temp] Got {len(tickers)} S&P 500 tickers")

    try:
        data = yf.download(" ".join(tickers), period="1y", interval="1d",
                           group_by="ticker", progress=False,
                           threads=True, auto_adjust=True)
    except Exception as e:
        print(f"[market-temp] yfinance download failed: {e}")
        return out

    above, above50, total = 0, 0, 0
    near_high, near_low = 0, 0
    for t in tickers:
        try:
            closes = data[t]["Close"].dropna()
            if len(closes) < 200:
                continue
            total += 1
            last  = closes.iloc[-1]
            if last > closes.iloc[-200:].mean():
                above += 1
            if last > closes.iloc[-50:].mean():
                above50 += 1
            hi, lo = closes.max(), closes.min()
            if   hi and last >= 0.95 * hi:  near_high += 1   # within 5% of 52wk high
            elif lo and last <= 1.05 * lo:  near_low  += 1   # within 5% of 52wk low
        except Exception:
            continue

    if total == 0:
        return out

    pct50 = round(100.0 * above50 / total, 1)
    out["breadth_50"] = {
        "raw":         pct50,
        "raw_label":   f"{pct50}% above 50-DMA",
        "above_50dma": above50,
        "total":       total,
        "score":       round(clamp(pct50, 0.0, 100.0), 1),   # the % IS the score
        "label":       label_for(pct50),
        "description": f"{above50} of {total} S&P 500 stocks above their 50-day average — the fast "
                       "participation read, which swings with every dip and rally.",
    }

    pct = round(100.0 * above / total, 1)
    if   pct <= 30:  b_score = 15
    elif pct <= 45:  b_score = 30
    elif pct <= 60:  b_score = 45
    elif pct <= 75:  b_score = 60
    elif pct <= 85:  b_score = 75
    elif pct <= 92:  b_score = 87
    else:            b_score = 95
    out["breadth"] = {
        "raw":          pct,
        "raw_label":    f"{pct}% above 200-DMA",
        "above_200dma": above,
        "total":        total,
        "score":        b_score,
        "label":        label_for(b_score),
        "description": f"{above} of {total} S&P 500 stocks above their 200-day average. Healthy "
                        "markets run 50–75%; above 90% is euphoric.",
    }

    net = round(100.0 * (near_high - near_low) / total, 1)   # −100 (all at lows) .. +100 (all at highs)
    nh_score = round(clamp(50.0 + net, 0.0, 100.0), 1)       # net 0 → 50 neutral
    out["new_highs"] = {
        "raw":        net,
        "raw_label":  f"{near_high} hi / {near_low} lo",
        "near_high":  near_high,
        "near_low":   near_low,
        "total":      total,
        "score":      nh_score,
        "label":      label_for(nh_score),
        "description": f"{near_high} stocks near a 52-week high vs {near_low} near a low, within 5%. "
                       "A surge of highs signals euphoria, a wave of lows signals stress.",
    }
    return out


# ── Component 5: Fear & Greed (CNN) ──────────────────────────────────────────

def compute_fear_greed():
    """CNN's Fear & Greed Index — composite of 7 short-term sentiment signals.
    The published score is already 0-100 (0 = Extreme Fear, 100 = Extreme
    Greed) and aligns directly with our Cold → Hot framing, so we use it
    without transformation."""
    print("[market-temp] Fear & Greed...")
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/125.0.0.0 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[market-temp] Fear & Greed fetch failed: {e}")
        return None

    fg = data.get("fear_and_greed", {}) or {}
    try:
        score = float(fg.get("score", 0) or 0)
    except (TypeError, ValueError):
        return None
    if score <= 0:
        return None
    rating = (fg.get("rating") or "Unknown").replace("_", " ").title()

    return {
        "raw":         round(score, 1),
        "raw_label":   f"{round(score)} ({rating})",
        "score":       round(score, 1),
        "label":       label_for(score),
        "description": "CNN's composite of seven short-term sentiment signals — momentum, breadth, "
                       "put/call, junk demand and volatility.",
    }


# ── Composite ────────────────────────────────────────────────────────────────

COMPONENT_META = {
    "risk_posture": {"title": "Risk Posture",       "subtitle": "Cyclicals vs Defensives"},
    "trend":        {"title": "Trend Heat",         "subtitle": "S&P vs 50-DMA + thrust"},
    "insider":      {"title": "Insider Breadth",    "subtitle": "Buying vs selling companies"},
    "growth_value": {"title": "Growth vs Value",    "subtitle": "IWF / IWD style ratio"},
    "breadth_50":   {"title": "Fast Breadth",       "subtitle": "% S&P 500 > 50-DMA"},
    "new_highs":    {"title": "Net New Highs",      "subtitle": "52wk highs − lows"},
    "fear_greed":   {"title": "Fear & Greed",       "subtitle": "CNN Sentiment Index"},
    "breadth":      {"title": "Structural Breadth", "subtitle": "% S&P 500 > 200-DMA"},
    "credit":       {"title": "Credit Spreads",     "subtitle": "High-Yield OAS"},
    "yield_curve":  {"title": "Yield Curve",        "subtitle": "10Y − 2Y Treasury"},
}

# ── Grouping (Aug 2026) ──────────────────────────────────────────────────────
# The gauge moved from the wide main column into the 420px Market Reading
# sidebar. Ten components at ~180px each stacked to roughly 2,100px of expanded
# card there, so they now roll up into four themes. The weights bucket exactly:
# 40 / 25 / 20 / 15 = 100, no fudging. Group order is display order.
GROUPS = [
    ("trend_participation", "Trend & Participation",
     "Is the market rising, and are enough stocks taking part?",
     ["trend", "breadth_50", "new_highs", "breadth"]),
    ("risk_appetite", "Risk Appetite",
     "Where money is positioned — offense or defense.",
     ["risk_posture", "growth_value"]),
    ("sentiment", "Sentiment",
     "What investors feel, and what insiders are quietly doing.",
     ["fear_greed", "insider"]),
    ("credit_rates", "Credit & Rates",
     "The slower backdrop: funding stress and cycle stage.",
     ["credit", "yield_curve"]),
]


def build_groups(components):
    """Roll the components into their four themes.

    A group's score is the weighted mean of whichever of its members returned
    data, and its weight is the sum of those members' weights — so a group
    degrades the same way the composite does when a feed is down, rather than
    silently scoring a missing input as zero.
    """
    out = []
    for key, title, blurb, members in GROUPS:
        wsum = tsum = 0.0
        live, missing = [], []
        for m in members:
            comp = components.get(m)
            if comp and comp.get("score") is not None:
                wsum += comp["score"] * WEIGHTS[m]
                tsum += WEIGHTS[m]
                live.append(m)
            else:
                missing.append(m)
        out.append({
            "key":      key,
            "title":    title,
            "blurb":    blurb,
            "score":    round(wsum / tsum, 1) if tsum > 0 else None,
            "label":    label_for(round(wsum / tsum, 1)) if tsum > 0 else None,
            # Nominal weight is what this group is WORTH; live weight is what
            # actually contributed. They differ only when a feed failed.
            "weight":         round(sum(WEIGHTS[m] for m in members), 2),
            "weight_live":    round(tsum, 2),
            "members":        members,
            "members_live":   live,
            "members_missing": missing,
        })
    return out


def run():
    start = datetime.now(timezone.utc)
    print(f"[market-temp] Starting scan at {start.isoformat()}")

    internals = compute_internals()
    # Fast movers first — this dict order is the display order on the homepage.
    components = {
        "risk_posture": compute_risk_posture(),
        "trend":        compute_trend_heat(),
        "insider":      compute_insider_breadth(),
        "growth_value": compute_growth_value(),
        "breadth_50":   internals.get("breadth_50"),
        "new_highs":    internals.get("new_highs"),
        "fear_greed":   compute_fear_greed(),
        "breadth":      internals.get("breadth"),
        "credit":       compute_credit_spreads(),
        "yield_curve":  compute_yield_curve(),
    }

    weighted_sum, total_weight = 0.0, 0.0
    for k, comp in components.items():
        if comp and comp.get("score") is not None:
            weighted_sum += comp["score"] * WEIGHTS[k]
            total_weight += WEIGHTS[k]

    composite_score = round(weighted_sum / total_weight, 1) if total_weight > 0 else None
    composite_label = label_for(composite_score)

    # Merge meta (title/subtitle) into each component for frontend convenience,
    # plus the group it belongs to so the sidebar can nest it without needing
    # its own copy of the mapping.
    group_of = {m: key for key, _t, _b, members in GROUPS for m in members}
    for k, comp in components.items():
        if comp:
            comp.update(COMPONENT_META[k])
            comp["weight"] = WEIGHTS[k]
            comp["group"]  = group_of.get(k)

    groups = build_groups(components)

    output = {
        "scan_time":        start.isoformat(),
        "next_scan_info":   NEXT_SCAN_INFO,
        "composite_score":  composite_score,
        "composite_label":  composite_label,
        "components":       components,
        "groups":           groups,
        "coverage":         round(total_weight, 2),
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[market-temp] Done in {elapsed}s — composite {composite_score} ({composite_label}), "
          f"coverage {total_weight:.2f}")
    for g in groups:
        gap = (" [missing: " + ", ".join(g["members_missing"]) + "]") if g["members_missing"] else ""
        print(f"[market-temp]   {g['title']:<24} {str(g['score']):>6} "
              f"{str(g['label'] or '-'):<8} w={g['weight']:.2f}{gap}")
    print(f"[market-temp] Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
