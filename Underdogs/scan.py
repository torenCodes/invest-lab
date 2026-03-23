"""
Underdogs — Standalone Scanner
Identifies high-quality companies with temporarily beaten-up stocks.
Writes results to data/results.json.

Run locally: python scan.py
Invoked by GitHub Actions weekly (Mondays 9am ET).
"""

import json
import os
import time
from datetime import datetime, timezone

try:
    import requests
    import yfinance as yf
except ImportError:
    raise SystemExit("Required packages missing. Run: pip install yfinance requests")

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE    = os.path.join(BASE_DIR, "data", "results.json")
INSIDER_FILE   = os.path.join(BASE_DIR, "..", "InsiderBuying", "data", "results.json")
NEXT_SCAN_INFO = "Mondays 9am ET"

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70")

ETF_UNIVERSE = [
    {'symbol': 'QUAL', 'name': 'MSCI USA Quality Factor', 'provider': 'iShares', 'category': 'Quality'},
    {'symbol': 'MOAT', 'name': 'Morningstar Wide Moat',   'provider': 'VanEck',  'category': 'Quality'},
    {'symbol': 'COWZ', 'name': 'US Cash Cows 100',         'provider': 'Pacer',   'category': 'Cash Flow'},
    {'symbol': 'QQQ',  'name': 'Nasdaq-100',               'provider': 'Invesco', 'category': 'Nasdaq Growth'},
]

# Sectors that use financial scoring path
FINANCIAL_SECTORS = {'financial services', 'financials', 'finance', 'banks', 'insurance'}

# Minimum thresholds to qualify
MIN_QUALITY_SCORE   = 30
MIN_BEATEN_UP_SCORE = 20
TOP_N               = 10


# ── ETF Holdings ──────────────────────────────────────────────────────────────

def get_holdings(symbol):
    """
    Fetch top ETF holdings via yfinance.
    Returns list of {'ticker', 'name', 'weight'} sorted by weight desc.
    Weight is expressed as a percentage (e.g. 7.2 means 7.2%).
    """
    try:
        t = yf.Ticker(symbol)

        # Primary: funds_data.top_holdings (yfinance >= 0.2.x)
        try:
            fd = t.funds_data
            if fd is not None:
                df = fd.top_holdings
                if df is not None and not df.empty:
                    result = []
                    for idx, row in df.iterrows():
                        # yfinance column is 'Holding Percent' (decimal); also
                        # accept legacy camelCase key in case API changes again
                        raw = row.get('Holding Percent', row.get('holdingPercent', 0))
                        try:
                            pct = float(raw) * 100
                        except (TypeError, ValueError):
                            continue
                        sym = str(idx).strip()
                        if not sym or len(sym) > 6:
                            continue
                        result.append({
                            'ticker': sym,
                            'name':   str(row.get('Name', row.get('holdingName', sym))).strip(),
                            'weight': round(pct, 2),
                        })
                    if result:
                        return sorted(result, key=lambda x: x['weight'], reverse=True)[:60]
        except Exception as e:
            print(f"  [{symbol}] funds_data err: {e}")

        # Fallback: info dict
        try:
            info     = t.info
            raw_list = info.get('holdings', [])
            if raw_list:
                result = []
                for h in raw_list[:60]:
                    raw = h.get('holdingPercent', 0)
                    try:
                        pct = float(raw) * 100
                    except (TypeError, ValueError):
                        continue
                    sym = str(h.get('symbol', '')).strip()
                    if not sym:
                        continue
                    result.append({
                        'ticker': sym,
                        'name':   str(h.get('holdingName', sym)).strip(),
                        'weight': round(pct, 2),
                    })
                if result:
                    return sorted(result, key=lambda x: x['weight'], reverse=True)
        except Exception as e:
            print(f"  [{symbol}] info fallback err: {e}")

        return []

    except Exception as e:
        print(f"[{symbol}] get_holdings outer err: {e}")
        return []


# ── Quality Scoring ───────────────────────────────────────────────────────────

def score_quality(info, etf_count):
    """Standard quality score for non-financial companies (0-100)."""
    pts = 0

    # Gross margin (20 pts)
    gm = info.get('grossMargins')
    if gm is not None:
        if gm >= 0.60:   pts += 20
        elif gm >= 0.40: pts += 12
        elif gm >= 0.25: pts += 6

    # Operating margin (20 pts)
    om = info.get('operatingMargins')
    if om is not None:
        if om >= 0.20:   pts += 20
        elif om >= 0.12: pts += 12
        elif om >= 0.05: pts += 6

    # ROE — yfinance returnOnEquity is a decimal (15 pts)
    roe = info.get('returnOnEquity')
    if roe is not None:
        if roe >= 0.20:   pts += 15
        elif roe >= 0.12: pts += 8

    # Revenue growth YoY (12 pts)
    rg = info.get('revenueGrowth')
    if rg is not None:
        if rg >= 0.15:   pts += 12
        elif rg >= 0.08: pts += 7
        elif rg >= 0.03: pts += 3

    # Free cash flow positive (10 pts)
    fcf = info.get('freeCashflow')
    if fcf is not None and fcf > 0:
        pts += 10

    # Debt to equity — yfinance returns as ratio×100 (e.g. 50 = 0.5×) (8 pts)
    de = info.get('debtToEquity')
    if de is not None:
        if de < 50:    pts += 8   # < 0.5×
        elif de < 150: pts += 4   # < 1.5×

    # ETF consensus (15 pts)
    if etf_count >= 3:   pts += 15
    elif etf_count == 2: pts += 10
    elif etf_count == 1: pts += 5

    return min(pts, 100)


def score_quality_financial(info, etf_count):
    """Quality score for financial-sector companies — ROE-primary path (0-100)."""
    pts = 0

    # ROE — primary signal for financials (30 pts)
    roe = info.get('returnOnEquity')
    if roe is not None:
        if roe >= 0.15:   pts += 30
        elif roe >= 0.10: pts += 18
        elif roe >= 0.06: pts += 8

    # Price-to-book ratio (20 pts)
    pb = info.get('priceToBook')
    if pb is not None:
        if 1.0 <= pb <= 3.0:  pts += 20   # fair value range
        elif pb < 1.0:         pts += 12   # below book — deeply discounted
        elif pb <= 5.0:        pts += 8

    # Revenue growth (20 pts)
    rg = info.get('revenueGrowth')
    if rg is not None:
        if rg >= 0.10:   pts += 20
        elif rg >= 0.05: pts += 12
        elif rg >= 0.0:  pts += 5

    # Net income positive (15 pts)
    ni = info.get('netIncomeToCommon')
    if ni is not None and ni > 0:
        pts += 15

    # FCF positive (5 pts)
    fcf = info.get('freeCashflow')
    if fcf is not None and fcf > 0:
        pts += 5

    # ETF consensus (10 pts)
    if etf_count >= 3:   pts += 10
    elif etf_count == 2: pts += 7
    elif etf_count == 1: pts += 3

    return min(pts, 100)


# ── Beaten-Up Scoring ────────────────────────────────────────────────────────

def calc_rsi(closes, period=14):
    """Calculate RSI from a list of closing prices using Wilder's smoothing."""
    if len(closes) < period + 1:
        return None
    try:
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains  = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)
    except Exception:
        return None


def score_beaten_up(ticker_sym):
    """
    Fetch 1-year price history and compute beaten-up score (0-100).
    Returns (score, signals_dict) with raw values for the frontend.
    """
    pts     = 0
    signals = {}

    try:
        hist = yf.Ticker(ticker_sym).history(period='1y', auto_adjust=True)
        if hist.empty:
            return 0, signals

        closes  = list(hist['Close'])
        current = closes[-1]

        # 52-week high drawdown (30 pts)
        high_52w = max(closes)
        drawdown = (high_52w - current) / high_52w * 100
        signals['drawdown_pct'] = round(drawdown, 1)
        signals['high_52w']     = round(high_52w, 2)
        if drawdown >= 30:   pts += 30
        elif drawdown >= 20: pts += 20
        elif drawdown >= 10: pts += 10

        # YTD change — first close of current calendar year (25 pts)
        this_year    = hist.index[-1].year
        year_slice   = hist[hist.index.year == this_year]
        if not year_slice.empty:
            ytd_start = float(year_slice['Close'].iloc[0])
            ytd_pct   = (current - ytd_start) / ytd_start * 100
        else:
            ytd_pct = 0.0
        signals['ytd_pct'] = round(ytd_pct, 1)
        if ytd_pct <= -20:   pts += 25
        elif ytd_pct <= -10: pts += 15
        elif ytd_pct <= -5:  pts += 8
        elif ytd_pct <= 0:   pts += 3

        # RSI 14-day (25 pts)
        rsi = calc_rsi(closes)
        signals['rsi'] = rsi
        if rsi is not None:
            if rsi < 30:   pts += 25
            elif rsi < 40: pts += 15
            elif rsi < 50: pts += 5

        # Price below 200-day MA (20 pts); fallback to 50-day for shorter histories
        if len(closes) >= 200:
            ma200 = sum(closes[-200:]) / 200
            signals['ma200'] = round(ma200, 2)
            if current < ma200:
                pts += 20
        elif len(closes) >= 50:
            ma50 = sum(closes[-50:]) / 50
            signals['ma200'] = None
            if current < ma50:
                pts += 10   # partial credit

    except Exception as e:
        print(f"  [{ticker_sym}] beaten_up err: {e}")

    return min(pts, 100), signals


# ── Recovery Bonus ────────────────────────────────────────────────────────────

def load_insider_tickers():
    """Return set of tickers with recent insider buying from InsiderBuying results.json."""
    try:
        path = os.path.abspath(INSIDER_FILE)
        if not os.path.exists(path):
            print("[insider] File not found — skipping cross-reference")
            return set()
        with open(path, 'r') as f:
            data = json.load(f)
        tickers = set()
        for key in ('cluster_buys', 'csuite_buys', 'big_money', 'recent_feed'):
            for entry in data.get(key, []):
                t = entry.get('ticker', '')
                if t:
                    tickers.add(t.upper())
        print(f"  Loaded {len(tickers)} insider tickers")
        return tickers
    except Exception as e:
        print(f"[insider] load err: {e}")
        return set()


def get_finnhub_earnings_surprise(ticker_sym):
    """Fetch most recent quarterly earnings surprise from Finnhub. Returns % surprise or None."""
    try:
        url = (
            f"https://finnhub.io/api/v1/stock/earnings"
            f"?symbol={ticker_sym}&limit=4&token={FINNHUB_KEY}"
        )
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        recent   = data[0]
        actual   = recent.get('actual')
        estimate = recent.get('estimate')
        if actual is None or estimate is None or estimate == 0:
            return None
        return round((actual - estimate) / abs(estimate) * 100, 1)
    except Exception:
        return None


def score_recovery_bonus(ticker_sym, insider_tickers):
    """
    Compute recovery bonus (0-30, capped).
    Returns (bonus_pts, signals_list).
    """
    pts     = 0
    signals = []

    # Insider buying cross-reference (15 pts)
    if ticker_sym.upper() in insider_tickers:
        pts += 15
        signals.append('Insider buying detected')

    # Finnhub earnings surprise (10 pts)
    surprise = get_finnhub_earnings_surprise(ticker_sym)
    if surprise is not None and surprise > 0:
        pts += 10
        signals.append(f'Earnings beat +{surprise}%')

    # Price stabilization: 30-day range < 10% of low (5 pts)
    try:
        hist = yf.Ticker(ticker_sym).history(period='1mo', auto_adjust=True)
        if not hist.empty and len(hist) >= 15:
            lo = float(hist['Low'].min())
            hi = float(hist['High'].max())
            if lo > 0:
                range_pct = (hi - lo) / lo * 100
                if range_pct < 10:
                    pts += 5
                    signals.append('Price stabilizing')
    except Exception:
        pass

    return min(pts, 30), signals


# ── Composite Score ───────────────────────────────────────────────────────────

def composite_score(quality, beaten_up, recovery):
    """Weighted composite: quality 45% + beaten-up 40% + recovery bonus (capped 30pts)."""
    return round(quality * 0.45 + beaten_up * 0.40 + recovery, 2)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("[scan.py] Starting Underdogs scan...")
    start = datetime.now(timezone.utc)

    # Step 1: Collect ETF holdings universe
    print("[scan.py] Fetching ETF holdings...")
    stock_map = {}  # ticker -> {name, etf_count, total_weight, etfs_holding}

    for etf in ETF_UNIVERSE:
        sym = etf['symbol']
        print(f"  Fetching {sym}...")
        holdings = get_holdings(sym)
        print(f"  {sym}: {len(holdings)} holdings")

        for h in holdings:
            t_sym = h['ticker']
            # Skip non-standard symbols
            if not t_sym or len(t_sym) > 6 or not t_sym.replace('-', '').replace('.', '').isalpha():
                continue
            if t_sym not in stock_map:
                stock_map[t_sym] = {
                    'ticker':       t_sym,
                    'name':         h['name'],
                    'etf_count':    0,
                    'total_weight': 0.0,
                    'etfs_holding': [],
                }
            stock_map[t_sym]['etf_count']   += 1
            stock_map[t_sym]['total_weight']  = round(stock_map[t_sym]['total_weight'] + h['weight'], 2)
            stock_map[t_sym]['etfs_holding'].append({
                'symbol':   sym,
                'provider': etf['provider'],
                'weight':   h['weight'],
            })

        time.sleep(1.5)

    total_tickers = len(stock_map)
    print(f"[scan.py] Universe: {total_tickers} unique tickers across {len(ETF_UNIVERSE)} ETFs")

    # Step 2: Load insider tickers for recovery bonus
    print("[scan.py] Loading insider buying data...")
    insider_tickers = load_insider_tickers()

    # Step 3: Score all candidates
    print("[scan.py] Scoring candidates (quality + beaten-up + recovery)...")
    candidates = []

    for i, (t_sym, entry) in enumerate(stock_map.items()):
        if (i + 1) % 25 == 0:
            print(f"  Progress: {i+1}/{total_tickers}...")
        try:
            ticker_obj = yf.Ticker(t_sym)
            info       = ticker_obj.info

            price  = info.get('currentPrice') or info.get('regularMarketPrice')
            mktcap = info.get('marketCap')

            # Skip if no price / market cap
            if not price or price <= 0 or not mktcap:
                continue

            # Sector-aware quality scoring
            sector       = info.get('sector', '') or ''
            is_financial = sector.lower() in FINANCIAL_SECTORS

            q_score = (
                score_quality_financial(info, entry['etf_count'])
                if is_financial
                else score_quality(info, entry['etf_count'])
            )

            if q_score < MIN_QUALITY_SCORE:
                continue

            # Beaten-up score
            b_score, b_signals = score_beaten_up(t_sym)

            if b_score < MIN_BEATEN_UP_SCORE:
                continue

            # Recovery bonus
            r_bonus, r_signals = score_recovery_bonus(t_sym, insider_tickers)
            time.sleep(0.3)  # Finnhub rate limit buffer

            c_score = composite_score(q_score, b_score, r_bonus)

            # Build human-readable signal strings for display
            quality_signals = []
            if is_financial:
                roe = info.get('returnOnEquity')
                if roe is not None:
                    quality_signals.append(f'ROE {round(roe * 100, 1)}%')
                pb = info.get('priceToBook')
                if pb is not None:
                    quality_signals.append(f'P/B {round(pb, 1)}×')
            else:
                gm = info.get('grossMargins')
                if gm is not None:
                    quality_signals.append(f'Gross margin {round(gm * 100, 0):.0f}%')
                roe = info.get('returnOnEquity')
                if roe is not None:
                    quality_signals.append(f'ROE {round(roe * 100, 1)}%')
            rg = info.get('revenueGrowth')
            if rg is not None:
                quality_signals.append(f'Rev growth {rg * 100:+.1f}%')

            beaten_signals = []
            dp = b_signals.get('drawdown_pct')
            if dp is not None:
                beaten_signals.append(f'{dp}% off 52w high')
            yp = b_signals.get('ytd_pct')
            if yp is not None:
                beaten_signals.append(f'YTD {yp:+.1f}%')
            rsi_val = b_signals.get('rsi')
            if rsi_val is not None:
                beaten_signals.append(f'RSI {rsi_val}')

            candidates.append({
                'ticker':           t_sym,
                'name':             info.get('longName') or info.get('shortName') or entry['name'],
                'sector':           sector,
                'industry':         info.get('industry', ''),
                'price':            round(float(price), 2),
                'market_cap':       mktcap,
                'pe':               info.get('trailingPE'),
                'pb':               info.get('priceToBook'),
                'roe':              info.get('returnOnEquity'),
                'gross_margin':     info.get('grossMargins'),
                'revenue_growth':   info.get('revenueGrowth'),
                'is_financial':     is_financial,
                'quality_score':    q_score,
                'beaten_up_score':  b_score,
                'recovery_bonus':   r_bonus,
                'composite_score':  c_score,
                'quality_signals':  quality_signals,
                'beaten_signals':   beaten_signals,
                'recovery_signals': r_signals,
                'rsi':              b_signals.get('rsi'),
                'drawdown_pct':     b_signals.get('drawdown_pct'),
                'ytd_pct':          b_signals.get('ytd_pct'),
                'high_52w':         b_signals.get('high_52w'),
                'etf_count':        entry['etf_count'],
                'total_weight':     entry['total_weight'],
                'etfs_holding':     entry['etfs_holding'],
            })

        except Exception as e:
            print(f"  [{t_sym}] scoring err: {e}")

        time.sleep(0.5)

    # Step 4: Rank by composite score, take top N
    candidates.sort(key=lambda x: x['composite_score'], reverse=True)
    top = candidates[:TOP_N]
    for i, c in enumerate(top):
        c['rank'] = i + 1

    print(f"[scan.py] {len(candidates)} candidates qualified → top {len(top)} selected")

    results = {
        'scanned_at':    start.isoformat(),
        'next_scan_info': NEXT_SCAN_INFO,
        'nominees':      top,
        'meta': {
            'etfs_scanned':         len(ETF_UNIVERSE),
            'total_tickers_found':  total_tickers,
            'candidates_qualified': len(candidates),
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[scan.py] Done in {elapsed}s — {len(top)} nominees written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
