#!/usr/bin/env python3
"""
PatternScanner — Daily technical pattern scanner for S&P 500 stocks.
Detects 6 classic chart patterns and grades each setup A / B / Watch.
Cross-references insider buying and ETF consensus data from other dashboards.

Run locally:  python PatternScanner/scan.py
GitHub Actions: pattern-scanner.yml runs this daily at ~9:40am ET.
"""

import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(BASE_DIR)
OUTPUT_FILE  = os.path.join(BASE_DIR, 'data', 'results.json')
INSIDER_FILE = os.path.join(REPO_ROOT, 'InsiderBuying', 'data', 'results.json')
ETF_FILE     = os.path.join(REPO_ROOT, 'TriedAndTrue',  'data', 'results.json')

MIN_PRICE      = 5.0   # skip penny stocks
MIN_DATA_DAYS  = 60    # minimum days of history for pattern detection
GRADE_A_SCORE  = 65
GRADE_B_SCORE  = 45
GRADE_W_SCORE  = 30    # minimum to appear in output

NEXT_SCAN_INFO = 'Weekdays ~9:40am ET'


# ── Universe ───────────────────────────────────────────────────────────────────

def get_sp500_universe():
    """Fetch S&P 500 tickers, names, and sectors from Wikipedia."""
    try:
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        df = tables[0]
        names   = {}
        sectors = {}
        tickers = []
        for _, row in df.iterrows():
            raw_t = str(row.get('Symbol', '')).strip()
            t = raw_t.replace('.', '-')   # BRK.B → BRK-B for yfinance
            tickers.append(t)
            names[t]   = str(row.get('Security', t)).strip()
            sectors[t] = str(row.get('GICS Sector', '')).strip()
        print(f"[scan] Universe: {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers, names, sectors
    except Exception as e:
        print(f"[scan] Wikipedia fetch failed ({e}) — using fallback list")
        fallback = [
            'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','BRK-B','AVGO','JPM',
            'LLY','V','MA','XOM','COST','UNH','PG','HD','WMT','JNJ','MRK','ORCL',
            'ABBV','KO','CVX','BAC','CRM','PEP','TMO','NFLX','AMD','DIS','ADBE',
            'IBM','MCD','GE','ACN','CSCO','ABT','AXP','TXN','PM','CAT','GS','SPGI',
            'INTU','VZ','LMT','MS','RTX','HON','AMAT','NOW','QCOM','SYK','UPS',
            'AMGN','ELV','BLK','DE','ISRG','MO','MMM','SCHW','PLD','MDLZ','C',
            'ADI','GILD','VRTX','BMY','CI','ETN','SO','DUK','ITW','PNC','AON',
            'BSX','SHW','CL','APD','ZTS','CME','MCO','TJX','MU','INTC','REGN',
            'FCX','NUE','CLF','WFC','USB','TFC','COF','F','GM','WBA','PARA',
        ]
        return fallback, {}, {}


# ── Data Fetching ──────────────────────────────────────────────────────────────

def fetch_price_history(tickers):
    """Batch download 1 year of daily OHLCV. Returns raw MultiIndex DataFrame."""
    print(f"[scan] Downloading 1-year history for {len(tickers)} tickers (this takes ~2 min)...")
    try:
        raw = yf.download(
            tickers,
            period='1y',
            group_by='ticker',
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        print(f"[scan] Download complete — shape: {raw.shape}")
        return raw
    except Exception as e:
        print(f"[scan] Batch download error: {e}")
        return None


def get_ticker_df(raw, ticker):
    """Extract a single ticker's OHLCV DataFrame from the batch result."""
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            df = raw[ticker].copy()
        else:
            df = raw.copy()
        df = df.dropna(how='all')
        if len(df) < MIN_DATA_DAYS:
            return None
        if df['Close'].iloc[-1] < MIN_PRICE:
            return None
        return df
    except (KeyError, Exception):
        return None


# ── Technical Indicators ───────────────────────────────────────────────────────

def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def _sma(series, window):
    return series.rolling(window).mean()

def _rsi(close, period=14):
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))

def _bb_width(close, window=20, std=2):
    mid = close.rolling(window).mean()
    dev = close.rolling(window).std()
    upper = mid + std * dev
    lower = mid - std * dev
    return (upper - lower) / mid.replace(0, float('nan'))

def _atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()

def add_indicators(df):
    c = df['Close']
    df = df.copy()
    df['EMA_20']    = _ema(c, 20)
    df['EMA_50']    = _ema(c, 50)
    df['EMA_200']   = _ema(c, 200)
    df['Vol_MA_20'] = _sma(df['Volume'], 20)
    df['RSI']       = _rsi(c)
    df['BB_width']  = _bb_width(c)
    df['ATR']       = _atr(df['High'], df['Low'], c)
    return df


# ── Pattern Detectors ──────────────────────────────────────────────────────────
# Each returns None (no pattern) or a dict:
#   { pattern, pattern_key, signals: [...], score_bonus }

def detect_bull_flag(df):
    """Strong uptrend (pole) followed by tight consolidation (flag) near the top."""
    c = df['Close']
    v = df['Volume']

    if c.iloc[-1] < df['EMA_20'].iloc[-1]:   # must be above short-term trend
        return None

    recent_c = c.iloc[-50:]
    recent_v = v.iloc[-50:]

    # Find the flagpole peak (not in the last 3 bars — needs some flag formed)
    peak_loc = int(recent_c.iloc[:-3].values.argmax())
    if peak_loc < 5 or peak_loc > len(recent_c) - 5:
        return None

    # Flagpole: find the trough before the peak
    pre_peak  = recent_c.iloc[:peak_loc + 1]
    trough_loc = int(pre_peak.values.argmin())
    if trough_loc >= peak_loc - 2:
        return None

    pole_low  = float(pre_peak.iloc[trough_loc])
    pole_high = float(recent_c.iloc[peak_loc])
    pole_gain = (pole_high - pole_low) / pole_low * 100
    pole_days = peak_loc - trough_loc

    if pole_gain < 12 or pole_days < 3 or pole_days > 25:
        return None

    # Flag: consolidation since the pole top
    flag_c    = recent_c.iloc[peak_loc:]
    if len(flag_c) < 4:
        return None

    flag_high = float(flag_c.max())
    flag_low  = float(flag_c.min())
    flag_depth = (flag_high - flag_low) / pole_high * 100

    if flag_depth > 20:   # too wide — not a tight flag
        return None

    # Price near top of flag (approaching breakout)
    flag_range = flag_high - flag_low
    flag_pos   = (float(c.iloc[-1]) - flag_low) / flag_range if flag_range > 0 else 1.0
    if flag_pos < 0.5:
        return None

    # Volume: flag volume should be lighter than pole volume
    pole_vol = float(recent_v.iloc[trough_loc:peak_loc + 1].mean())
    flag_vol = float(recent_v.iloc[peak_loc:].mean())
    vol_ok   = flag_vol < pole_vol * 0.85

    signals = [
        f"Flagpole +{pole_gain:.1f}% in {pole_days}d",
        f"Flag depth {flag_depth:.1f}% — tight consolidation",
    ]
    if vol_ok:
        signals.append("Volume contracting in flag")
    if c.iloc[-1] > df['EMA_200'].iloc[-1]:
        signals.append("Above 200-day EMA")

    return {'pattern': 'Bull Flag', 'pattern_key': 'bull_flag',
            'signals': signals, 'score_bonus': min(int(pole_gain), 25)}


def detect_vcp(df):
    """Volatility Contraction Pattern: progressively tighter ranges, declining volume."""
    c = df['Close']

    if len(c) < 60:
        return None

    # Within 25% of 52-week high (base condition — stock in a proper base)
    high_52w = float(c.iloc[-min(252, len(c)):].max())
    dist_from_high = (high_52w - float(c.iloc[-1])) / high_52w * 100
    if dist_from_high > 25:
        return None

    # Above 50-day EMA (in an uptrend)
    if c.iloc[-1] < df['EMA_50'].iloc[-1]:
        return None

    # Compare 3 rolling 15-day windows (oldest → newest)
    def rng(start, end):
        seg = c.iloc[start:end]
        return (float(seg.max()) - float(seg.min())) / float(seg.mean()) * 100

    def avg_vol(start, end):
        return float(df['Volume'].iloc[start:end].mean())

    r1 = rng(-15, None)     # most recent 15 days
    r2 = rng(-30, -15)      # 15–30 days ago
    r3 = rng(-45, -30)      # 30–45 days ago

    if not (r1 < r2 < r3):  # must be progressively tightening
        return None

    if r1 / r3 > 0.7:       # needs at least 30% overall contraction
        return None

    v1 = avg_vol(-15, None)
    v2 = avg_vol(-30, -15)
    vol_contracting = v1 < v2 * 0.9

    signals = [
        f"3 tightening windows: {r3:.1f}% → {r2:.1f}% → {r1:.1f}%",
        f"{dist_from_high:.1f}% below 52w high — near breakout zone",
    ]
    if vol_contracting:
        signals.append("Volume declining with each contraction")
    if c.iloc[-1] > df['EMA_200'].iloc[-1]:
        signals.append("Above 200-day EMA")

    return {'pattern': 'VCP', 'pattern_key': 'vcp',
            'signals': signals, 'score_bonus': 15}


def detect_bb_squeeze(df):
    """Bollinger Band squeeze: volatility compressed to 6-month low."""
    bb = df['BB_width'].dropna()
    if len(bb) < 130:
        return None

    current_w = float(bb.iloc[-1])
    min_6mo   = float(bb.iloc[-126:].min())
    avg_6mo   = float(bb.iloc[-126:].mean())

    # Must be at or near 6-month minimum, and genuinely compressed vs average
    if current_w > min_6mo * 1.15:
        return None
    if current_w > avg_6mo * 0.55:  # must be well below average width
        return None

    c       = df['Close']
    rsi_val = float(df['RSI'].iloc[-1]) if not pd.isna(df['RSI'].iloc[-1]) else 50
    above_200 = float(c.iloc[-1]) > float(df['EMA_200'].iloc[-1])
    rsi_ok    = 35 <= rsi_val <= 65

    signals = [f"BB width at 6-month low ({current_w:.3f}) — energy compressing"]
    if rsi_ok:
        signals.append(f"RSI neutral at {rsi_val:.0f} — coiling before move")
    if above_200:
        signals.append("Above 200-day EMA — bullish bias on breakout")
    else:
        signals.append("Below 200-day EMA — direction of move uncertain")

    return {'pattern': 'BB Squeeze', 'pattern_key': 'bb_squeeze',
            'signals': signals, 'score_bonus': 12}


def detect_ma_crossover(df):
    """EMA 20 crossed above EMA 50 within the last 5 trading days."""
    e20 = df['EMA_20']
    e50 = df['EMA_50']

    if len(e20) < 55:
        return None

    crossed    = False
    days_ago   = None
    for i in range(1, 6):
        was_below = float(e20.iloc[-(i + 1)]) < float(e50.iloc[-(i + 1)])
        now_above = float(e20.iloc[-i])        > float(e50.iloc[-i])
        if was_below and now_above:
            crossed  = True
            days_ago = i - 1
            break

    if not crossed:
        return None

    c         = df['Close']
    above_200 = float(c.iloc[-1]) > float(df['EMA_200'].iloc[-1])

    cross_vol_ratio = 1.0
    try:
        cross_idx = -(days_ago + 1)
        vol_ma    = float(df['Vol_MA_20'].iloc[cross_idx])
        if vol_ma > 0:
            cross_vol_ratio = float(df['Volume'].iloc[cross_idx]) / vol_ma
    except Exception:
        pass

    label = "today" if days_ago == 0 else f"{days_ago}d ago"
    signals = [f"EMA 20 crossed above EMA 50 ({label})"]
    if cross_vol_ratio >= 1.2:
        signals.append(f"Volume {cross_vol_ratio:.1f}x average on cross day")
    if above_200:
        signals.append("Above 200-day EMA — confirmed uptrend")
    else:
        signals.append("Below 200-day EMA — watch for overhead resistance")

    return {'pattern': 'MA Crossover', 'pattern_key': 'ma_crossover',
            'signals': signals, 'score_bonus': 10}


def detect_cup_handle(df):
    """Simplified cup-with-handle: rounded base recovery + shallow handle near prior high."""
    c = df['Close']

    if len(c) < 120:
        return None

    # Must be within 15% of 52-week high
    high_52w   = float(c.iloc[-min(252, len(c)):].max())
    pct_from_high = (high_52w - float(c.iloc[-1])) / high_52w * 100
    if pct_from_high > 15:
        return None

    # Cup: significant trough in the 20–120 days ago window
    cup_seg    = c.iloc[-120:-20]
    if len(cup_seg) < 20:
        return None

    cup_start  = float(cup_seg.iloc[0])
    cup_low    = float(cup_seg.min())
    cup_depth  = (cup_start - cup_low) / cup_start * 100

    if cup_depth < 12 or cup_depth > 45:  # cup too shallow or too deep
        return None

    # Recovery: price near the top of the cup again
    cup_end       = float(c.iloc[-20])
    recovery_pct  = (cup_end - cup_low) / (cup_start - cup_low) * 100 if cup_start > cup_low else 0
    if recovery_pct < 70:
        return None

    # Handle: mild pullback in last 5–20 days
    handle     = c.iloc[-20:]
    handle_hi  = float(handle.max())
    handle_lo  = float(handle.min())
    handle_dep = (handle_hi - handle_lo) / handle_hi * 100 if handle_hi > 0 else 0

    if handle_dep < 2 or handle_dep > 18:
        return None

    # Price in upper half of handle (near pivot)
    h_range  = handle_hi - handle_lo
    h_pos    = (float(c.iloc[-1]) - handle_lo) / h_range if h_range > 0 else 1.0
    if h_pos < 0.5:
        return None

    signals = [
        f"Cup depth {cup_depth:.1f}% — {pct_from_high:.1f}% from 52w high",
        f"Handle depth {handle_dep:.1f}% — near pivot breakout point",
    ]
    if c.iloc[-1] > df['EMA_200'].iloc[-1]:
        signals.append("Above 200-day EMA")

    return {'pattern': 'Cup & Handle', 'pattern_key': 'cup_handle',
            'signals': signals, 'score_bonus': 18}


def detect_hv_gap(df):
    """High-volume gap-up held above gap level — earnings reaction or catalyst breakout."""
    c  = df['Close']
    v  = df['Volume']
    vm = df['Vol_MA_20']

    if len(c) < 25:
        return None

    for i in range(1, 21):    # look back up to 20 days
        prev_close = float(c.iloc[-(i + 1)])
        gap_close  = float(c.iloc[-i])
        if prev_close <= 0:
            continue

        gap_pct   = (gap_close - prev_close) / prev_close * 100
        vol_ma_val = float(vm.iloc[-i]) if not pd.isna(vm.iloc[-i]) else 1
        vol_ratio  = float(v.iloc[-i]) / vol_ma_val if vol_ma_val > 0 else 1

        if gap_pct >= 5 and vol_ratio >= 2.5:
            # Confirm: still holding at or above the gap-up close
            if float(c.iloc[-1]) >= gap_close * 0.97:
                ago_label = f"{i}d ago" if i > 1 else "today"
                signals = [
                    f"+{gap_pct:.1f}% gap-up {ago_label} on {vol_ratio:.1f}x average volume",
                    f"Holding above gap level (${gap_close:.2f})",
                ]
                if float(c.iloc[-1]) > float(df['EMA_50'].iloc[-1]):
                    signals.append("Above 50-day EMA")
                if float(c.iloc[-1]) > float(df['EMA_200'].iloc[-1]):
                    signals.append("Above 200-day EMA")
                return {'pattern': 'High-Vol Gap', 'pattern_key': 'hv_gap',
                        'signals': signals, 'score_bonus': 20}
    return None


DETECTORS = [
    detect_bull_flag,
    detect_vcp,
    detect_bb_squeeze,
    detect_ma_crossover,
    detect_cup_handle,
    detect_hv_gap,
]


# ── Grading ────────────────────────────────────────────────────────────────────

def grade_setup(df, result, insider_tickers, etf_tickers, ticker):
    """
    Score a detected pattern setup and assign a grade.
    Mutates result['signals'] in place (appends cross-ref signals).
    Returns (score, grade, rs_pct, insider_hit, etf_hit, etf_count).
    """
    c = df['Close']
    v = df['Volume']

    score = 30  # base: any detected pattern earns 30 pts
    score += result.get('score_bonus', 0)

    # Trend: above 200-day EMA
    if not pd.isna(df['EMA_200'].iloc[-1]) and float(c.iloc[-1]) > float(df['EMA_200'].iloc[-1]):
        score += 10

    # Relative strength: position within 52-week range
    c_window = c.iloc[-min(252, len(c)):]
    high_52w = float(c_window.max())
    low_52w  = float(c_window.min())
    rs_pct   = (float(c.iloc[-1]) - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50.0
    if rs_pct >= 70:
        score += 10
    elif rs_pct >= 50:
        score += 5

    # RSI health
    rsi_val = df['RSI'].iloc[-1]
    if not pd.isna(rsi_val) and 45 <= float(rsi_val) <= 70:
        score += 5

    # Volume trend: recent 10-day avg vs prior 20-day avg
    if len(v) >= 30:
        vol_recent = float(v.iloc[-10:].mean())
        vol_older  = float(v.iloc[-30:-10].mean())
        if vol_older > 0 and vol_recent > vol_older * 1.1:
            score += 5

    # Cross-reference bonuses
    insider_hit = ticker in insider_tickers
    etf_count   = etf_tickers.get(ticker, 0)
    etf_hit     = etf_count > 0

    if insider_hit:
        score += 15
        result['signals'].append("Insider buying confirmed (cross-reference)")
    if etf_hit:
        score += 10
        result['signals'].append(f"Held in {etf_count} growth ETFs (TriedAndTrue)")

    # Assign grade
    if score >= GRADE_A_SCORE:
        grade = 'A'
    elif score >= GRADE_B_SCORE:
        grade = 'B'
    else:
        grade = 'Watch'

    return score, grade, round(rs_pct, 1), insider_hit, etf_hit, etf_count


# ── Cross-reference Loaders ────────────────────────────────────────────────────

def load_insider_tickers():
    """Return set of tickers with recent insider buying."""
    try:
        with open(INSIDER_FILE) as f:
            data = json.load(f)
        tickers = set()
        for item in data.get('cluster_buys', []) + data.get('csuite_buys', []):
            t = item.get('ticker', '').strip()
            if t:
                tickers.add(t)
        print(f"[scan] Insider cross-ref: {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"[scan] Insider file not found or unreadable ({e}) — skipping cross-ref")
        return set()


def load_etf_tickers():
    """Return dict of ticker → etf_count from TriedAndTrue top_10."""
    try:
        with open(ETF_FILE) as f:
            data = json.load(f)
        result = {item['ticker']: item.get('etf_count', 1) for item in data.get('top_10', [])}
        print(f"[scan] ETF cross-ref: {len(result)} tickers")
        return result
    except Exception as e:
        print(f"[scan] ETF file not found or unreadable ({e}) — skipping cross-ref")
        return {}


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("[scan] PatternScanner starting...")
    start = datetime.now(timezone.utc)

    tickers, names, sectors = get_sp500_universe()

    raw = fetch_price_history(tickers)
    if raw is None or raw.empty:
        print("[scan] Download returned no data — aborting")
        return

    insider_tickers = load_insider_tickers()
    etf_tickers     = load_etf_tickers()

    matches   = []   # (ticker, df, best_result)
    skipped   = 0
    processed = 0

    for ticker in tickers:
        df = get_ticker_df(raw, ticker)
        if df is None:
            skipped += 1
            continue

        try:
            df = add_indicators(df)
        except Exception as e:
            print(f"[scan] Indicator error {ticker}: {e}")
            skipped += 1
            continue

        processed += 1

        # Run all detectors; keep only the highest-scoring match per ticker
        best = None
        for detector in DETECTORS:
            try:
                result = detector(df)
                if result is None:
                    continue

                score, grade, rs_pct, i_hit, e_hit, e_cnt = grade_setup(
                    df, result, insider_tickers, etf_tickers, ticker
                )

                if score < GRADE_W_SCORE:
                    continue

                if best is None or score > best['_score']:
                    result.update({
                        '_score':     score,
                        '_grade':     grade,
                        '_rs_pct':    rs_pct,
                        '_insider':   i_hit,
                        '_etf':       e_hit,
                        '_etf_count': e_cnt,
                    })
                    best = result

            except Exception as e:
                print(f"[scan] Pattern error {ticker}/{detector.__name__}: {e}")

        if best:
            matches.append((ticker, df, best))

    print(f"[scan] Processed {processed} tickers — {len(matches)} setups found (skipped {skipped})")

    # Build output records
    output_setups = []
    for ticker, df, best in matches:
        c = df['Close']
        try:
            change_pct   = round((float(c.iloc[-1]) - float(c.iloc[-2])) / float(c.iloc[-2]) * 100, 2)
            week_chg_pct = round((float(c.iloc[-1]) - float(c.iloc[-6])) / float(c.iloc[-6]) * 100, 2) if len(c) >= 6 else None
        except Exception:
            change_pct   = None
            week_chg_pct = None

        output_setups.append({
            'ticker':          ticker,
            'name':            names.get(ticker, ticker),
            'sector':          sectors.get(ticker, ''),
            'pattern':         best['pattern'],
            'pattern_key':     best['pattern_key'],
            'grade':           best['_grade'],
            'score':           best['_score'],
            'signals':         best['signals'],
            'current_price':   round(float(c.iloc[-1]), 2),
            'change_pct':      change_pct,
            'week_change_pct': week_chg_pct,
            'rs_pct':          best['_rs_pct'],
            'chart_url':       f'https://www.tradingview.com/chart/?symbol={ticker}',
            'insider_flag':    best['_insider'],
            'etf_flag':        best['_etf'],
            'etf_count':       best['_etf_count'],
        })

    # Sort: A → B → Watch, then by score descending within each grade
    grade_order = {'A': 0, 'B': 1, 'Watch': 2}
    output_setups.sort(key=lambda x: (grade_order.get(x['grade'], 3), -x['score']))

    # Grade counts for summary
    grade_counts = {'A': 0, 'B': 0, 'Watch': 0}
    for s in output_setups:
        grade_counts[s['grade']] = grade_counts.get(s['grade'], 0) + 1

    output = {
        'scan_time':      start.isoformat(),
        'next_scan_info': NEXT_SCAN_INFO,
        'total_scanned':  processed,
        'setups_found':   len(output_setups),
        'grade_counts':   grade_counts,
        'setups':         output_setups,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[scan] Done in {elapsed}s — "
          f"{grade_counts['A']}A  {grade_counts['B']}B  {grade_counts['Watch']}W")
    print(f"[scan] Output → {OUTPUT_FILE}")


if __name__ == '__main__':
    run()
