"""
Market Temperature Scan — proprietary composite market valuation gauge.

Composite score 0-100:
  0 = Cheap, 100 = Frothy

Components (each scored 0-100). Expanded June 2026 from a static valuation
gauge into a market-regime composite: valuation anchors were trimmed and
dynamic macro/internal inputs added so the reading actually moves with market
stress and euphoria instead of pinning near the top. VIX dropped (it lives in
the homepage's Trading Conditions panel now).
  - Buffett Indicator (Wilshire 5000 / GDP)       — 15%  percentile over 10yr
  - Shiller CAPE (10yr real P/E)                  — 15%  percentile over 10yr
  - Fed Model (S&P earnings yield − 10Y Treasury) — 10%  fixed thresholds
  - Credit spreads (ICE BofA HY OAS, FRED)        — 15%  inverted percentile over 10yr
  - Yield curve (10Y − 2Y, FRED)                  — 10%  fixed thresholds (cycle stage)
  - Breadth (% S&P 500 above 200-DMA)             — 15%  fixed thresholds
  - Net new highs (near 52wk high − near low)     — 10%  derived from breadth download
  - Fear & Greed (CNN sentiment composite)        — 10%  used directly (already 0-100)

Output: MarketDashboard/data/market_temperature.json
Invoked by GitHub Actions daily. Run locally: python scripts/market_temperature_scan.py
"""

import json
import os
import re
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

WEIGHTS = {
    "buffett":     0.15,
    "shiller":     0.15,
    "fed_model":   0.10,
    "credit":      0.15,
    "yield_curve": 0.10,
    "breadth":     0.15,
    "new_highs":   0.10,
    "fear_greed":  0.10,
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
    if score < 20:  return "Cheap"
    if score < 40:  return "Fair"
    if score < 60:  return "Elevated"
    if score < 80:  return "Frothy"
    return "Extreme"


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


def ffill_to_dates(sparse, target_dates):
    """Forward-fill a sparse series (quarterly GDP, etc.) onto target daily dates.
    Both inputs must be sorted ascending by date. Returns dict of date_str → value."""
    out = {}
    i = 0
    last = None
    for d in target_dates:
        while i < len(sparse) and sparse[i][0] <= d:
            last = sparse[i][1]
            i += 1
        if last is not None:
            out[d] = last
    return out


# ── Component 1: Buffett Indicator ───────────────────────────────────────────

def compute_buffett():
    """Buffett Indicator: total US market cap vs GDP.

    Data sources:
      - Wilshire 5000 (^W5000) via yfinance — FRED discontinued its WILL5000*
        series on June 3, 2024, so we go straight to Yahoo Finance for the
        same index.
      - GDP via FRED (GDP series) — quarterly, forward-filled onto monthly
        Wilshire dates.

    Score = percentile rank of the current Wilshire/GDP ratio over the
    prior ~10 years of monthly observations, so structurally elevated
    readings don't dominate.
    """
    print("[market-temp] Buffett Indicator...")
    try:
        import yfinance as yf
    except ImportError:
        print("[market-temp] yfinance unavailable")
        return None

    try:
        hist = yf.Ticker("^W5000").history(
            period=f"{CALIB_YEARS + 1}y", interval="1mo", auto_adjust=False
        )
    except Exception as e:
        print(f"[market-temp] Wilshire 5000 fetch failed: {e}")
        return None
    if hist is None or len(hist) < 24:
        print("[market-temp] Wilshire 5000: insufficient history")
        return None

    wilshire = [
        (d.strftime("%Y-%m-%d"), float(c))
        for d, c in zip(hist.index, hist["Close"].values)
        if c == c  # filter NaN
    ]
    wilshire.sort(key=lambda x: x[0])

    gdp = fred_series("GDP", CALIB_YEARS + 2)
    if not gdp:
        return None

    dates       = [d for d, _ in wilshire]
    gdp_aligned = ffill_to_dates(gdp, dates)

    ratios = [(d, w / gdp_aligned[d]) for d, w in wilshire if d in gdp_aligned]
    if len(ratios) < 24:
        print("[market-temp] Buffett: not enough overlapping history")
        return None

    current    = ratios[-1][1]
    historical = [v for _, v in ratios[:-1]]
    pct        = percentile_rank(historical, current)

    return {
        "raw":         round(current, 3),
        "raw_label":   f"{current:.1f} (W5000/GDP)",
        "percentile":  pct,
        "score":       pct,
        "label":       label_for(pct),
        "description": "Total US market cap (Wilshire 5000) vs GDP — Warren Buffett's \"best single measure.\" "
                       f"Percentile-ranked over the last {CALIB_YEARS} years.",
    }


# ── Component 2: Shiller CAPE ────────────────────────────────────────────────

def _parse_multpl_table(html):
    """multpl.com table parser — rows are (date, value)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="datatable")
    if not table:
        return []
    out = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        date_str = cells[0].get_text(strip=True)
        val_str  = cells[1].get_text(strip=True).replace(",", "").replace("†", "").strip()
        date = None
        for fmt in ("%b %d, %Y", "%b %Y", "%B %d, %Y", "%B %Y"):
            try:
                date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        if not date:
            continue
        try:
            out.append((date, float(val_str)))
        except ValueError:
            continue
    return out


def compute_shiller():
    print("[market-temp] Shiller CAPE...")
    try:
        r = requests.get("https://www.multpl.com/shiller-pe/table/by-month",
                         headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[market-temp] Shiller fetch failed: {e}")
        return None

    values = _parse_multpl_table(r.text)
    values.sort(key=lambda x: x[0])
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=CALIB_YEARS * 365 + 60)
    window = [v for d, v in values if d >= cutoff]

    if len(window) < 50:
        return None

    current    = window[-1]
    historical = window[:-1]
    pct        = percentile_rank(historical, current)

    return {
        "raw":         round(current, 2),
        "raw_label":   f"{current:.1f}x CAPE",
        "percentile":  pct,
        "score":       pct,
        "label":       label_for(pct),
        "description": "S&P 500 price divided by 10-year inflation-adjusted earnings. "
                       f"Percentile-ranked over the last {CALIB_YEARS} years.",
    }


# ── Component 3: Fed Model (fixed thresholds) ────────────────────────────────

def _fetch_sp500_pe():
    """Scrape current S&P 500 P/E from multpl.com.

    Page markup: <div id="current"><b>Current S&P 500 PE Ratio:</b> 30.35 <span>...</span></div>
    We want the text node immediately after <b>, not a regex on the whole element
    (which would greedily match "500" from the label).
    """
    try:
        r = requests.get("https://www.multpl.com/s-p-500-pe-ratio",
                         headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        current_el = soup.find("div", id="current")
        if not current_el or not current_el.b:
            return None
        value_text = (current_el.b.next_sibling or "")
        m = re.search(r"([0-9]+\.?[0-9]*)", str(value_text))
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f"[market-temp] S&P 500 PE fetch failed: {e}")
        return None


def compute_fed_model():
    print("[market-temp] Fed Model...")
    pe = _fetch_sp500_pe()
    if not pe or pe <= 0:
        return None

    earnings_yield = 100.0 / pe
    dgs10 = fred_series("DGS10", 0.3)
    if not dgs10:
        return None
    treasury_10y = dgs10[-1][1]

    spread = earnings_yield - treasury_10y

    if   spread >  3.0:  score = 10
    elif spread >  2.0:  score = 25
    elif spread >  1.0:  score = 40
    elif spread >  0.0:  score = 55
    elif spread > -1.0:  score = 70
    elif spread > -2.0:  score = 85
    else:                score = 95

    return {
        "raw":            round(spread, 2),
        "raw_label":      f"{spread:+.2f}% spread",
        "earnings_yield": round(earnings_yield, 2),
        "treasury_10y":   round(treasury_10y, 2),
        "pe":             round(pe, 2),
        "score":          score,
        "label":          label_for(score),
        "description":    f"S&P earnings yield {earnings_yield:.2f}% vs 10Y Treasury {treasury_10y:.2f}%. "
                          "Positive spread means stocks are relatively cheap vs bonds.",
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
        "description": "Extra yield demanded to hold high-yield (junk) bonds over Treasuries. "
                       "Tight spreads signal risk-on complacency; wide spreads signal stress. "
                       f"Inverted percentile over {CALIB_YEARS} years.",
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
        "description": "10-year minus 2-year Treasury yield. A steep curve is early-cycle and "
                       "healthy; a flat or inverted curve marks a late-cycle market that is "
                       "historically more stretched and froth-prone.",
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
    """Downloads the S&P 500 once and derives TWO components:
      - breadth:   % of stocks above their 200-day MA (trend participation)
      - new_highs: net % near a 52-week high minus near a 52-week low (the
                   euphoria/stress extreme — a fast-moving internal)
    Returns {"breadth": {...}|None, "new_highs": {...}|None}."""
    print("[market-temp] Market internals (breadth + new highs)...")
    out = {"breadth": None, "new_highs": None}
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

    above, total = 0, 0
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
            hi, lo = closes.max(), closes.min()
            if   hi and last >= 0.95 * hi:  near_high += 1   # within 5% of 52wk high
            elif lo and last <= 1.05 * lo:  near_low  += 1   # within 5% of 52wk low
        except Exception:
            continue

    if total == 0:
        return out

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
        "description":  f"{above} of {total} S&P 500 stocks trading above their 200-day moving average. "
                        "Healthy markets see 50–75%; above 90% signals euphoric participation.",
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
        "description": f"{near_high} stocks near a 52-week high vs {near_low} near a 52-week low "
                       "(within 5%). A surge of new highs signals euphoria; a wave of new lows signals stress.",
    }
    return out


# ── Component 5: Fear & Greed (CNN) ──────────────────────────────────────────

def compute_fear_greed():
    """CNN's Fear & Greed Index — composite of 7 short-term sentiment signals.
    The published score is already 0-100 (0 = Extreme Fear, 100 = Extreme
    Greed) and aligns directly with our Cheap → Frothy framing, so we use
    it without transformation."""
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
        "description": "CNN's composite of 7 short-term sentiment signals (momentum, "
                       "breadth, put/call ratio, junk-bond demand, volatility, etc.). "
                       "High readings reflect investor euphoria — historically a "
                       "contrarian sell signal.",
    }


# ── Composite ────────────────────────────────────────────────────────────────

COMPONENT_META = {
    "buffett":     {"title": "Buffett Indicator", "subtitle": "Market Cap / GDP"},
    "shiller":     {"title": "Shiller CAPE",      "subtitle": "10-Year Real P/E"},
    "fed_model":   {"title": "Fed Model",         "subtitle": "Earnings Yield − 10Y"},
    "credit":      {"title": "Credit Spreads",    "subtitle": "High-Yield OAS"},
    "yield_curve": {"title": "Yield Curve",       "subtitle": "10Y − 2Y Treasury"},
    "breadth":     {"title": "Breadth",           "subtitle": "% S&P 500 > 200-DMA"},
    "new_highs":   {"title": "Net New Highs",     "subtitle": "52wk highs − lows"},
    "fear_greed":  {"title": "Fear & Greed",      "subtitle": "CNN Sentiment Index"},
}


def run():
    start = datetime.now(timezone.utc)
    print(f"[market-temp] Starting scan at {start.isoformat()}")

    internals = compute_internals()
    components = {
        "buffett":     compute_buffett(),
        "shiller":     compute_shiller(),
        "fed_model":   compute_fed_model(),
        "credit":      compute_credit_spreads(),
        "yield_curve": compute_yield_curve(),
        "breadth":     internals.get("breadth"),
        "new_highs":   internals.get("new_highs"),
        "fear_greed":  compute_fear_greed(),
    }

    weighted_sum, total_weight = 0.0, 0.0
    for k, comp in components.items():
        if comp and comp.get("score") is not None:
            weighted_sum += comp["score"] * WEIGHTS[k]
            total_weight += WEIGHTS[k]

    composite_score = round(weighted_sum / total_weight, 1) if total_weight > 0 else None
    composite_label = label_for(composite_score)

    # Merge meta (title/subtitle) into each component for frontend convenience
    for k, comp in components.items():
        if comp:
            comp.update(COMPONENT_META[k])
            comp["weight"] = WEIGHTS[k]

    output = {
        "scan_time":        start.isoformat(),
        "next_scan_info":   NEXT_SCAN_INFO,
        "composite_score":  composite_score,
        "composite_label":  composite_label,
        "components":       components,
        "coverage":         round(total_weight, 2),
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[market-temp] Done in {elapsed}s — composite {composite_score} ({composite_label}), "
          f"coverage {total_weight:.2f}")
    print(f"[market-temp] Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
