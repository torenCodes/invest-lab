"""
Tried and True — Standalone Scanner
Runs once, writes results to data/results.json, then exits.
Invoked by GitHub Actions on a weekly schedule (Mondays 9am ET).
Run locally: python scan.py
"""

import json
import os
import time
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("yfinance not installed. Run: pip install yfinance")

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE  = os.path.join(BASE_DIR, "..", "TheMarathon", "data", "consensus.json")

NEXT_SCAN_INFO = "Mondays 9am ET"

ETF_UNIVERSE = [
    {'symbol': 'QQQ',   'name': 'Nasdaq-100',             'provider': 'Invesco',  'category': 'Nasdaq Growth'},
    {'symbol': 'SCHG',  'name': 'US Large-Cap Growth',    'provider': 'Schwab',   'category': 'Large-Cap Growth'},
    {'symbol': 'VUG',   'name': 'Growth ETF',             'provider': 'Vanguard', 'category': 'Large-Cap Growth'},
    {'symbol': 'IWF',   'name': 'Russell 1000 Growth',    'provider': 'iShares',  'category': 'Large-Cap Growth'},
    {'symbol': 'VGT',   'name': 'Information Technology', 'provider': 'Vanguard', 'category': 'Sector — Tech'},
    {'symbol': 'XLK',   'name': 'Technology Select',      'provider': 'SPDR',     'category': 'Sector — Tech'},
    {'symbol': 'MGK',   'name': 'Mega Cap Growth',        'provider': 'Vanguard', 'category': 'Mega-Cap Growth'},
    {'symbol': 'FTEC',  'name': 'MSCI Info Technology',   'provider': 'Fidelity', 'category': 'Sector — Tech'},
    {'symbol': 'SPYG',  'name': 'S&P 500 Growth',         'provider': 'SPDR',     'category': 'S&P 500 Growth'},
    {'symbol': 'BGRWX', 'name': 'Growth Fund',            'provider': 'Baron',    'category': 'Active Growth'},
]

# Comparison-only ETFs: shown in the scorecard table but NOT used for stock overlap scoring.
ETF_COMPARISON = [
    {'symbol': 'SCHD',  'name': 'US Dividend Equity',     'provider': 'Schwab',   'category': 'Dividend'},
    {'symbol': 'DGRO',  'name': 'Dividend Growth',        'provider': 'iShares',  'category': 'Dividend Growth'},
    {'symbol': 'VIG',   'name': 'Dividend Appreciation',  'provider': 'Vanguard', 'category': 'Dividend Growth'},
    {'symbol': 'VTV',   'name': 'Value ETF',              'provider': 'Vanguard', 'category': 'Large-Cap Value'},
    {'symbol': 'VXUS',  'name': 'Total Intl Stock',       'provider': 'Vanguard', 'category': 'International'},
    {'symbol': 'VTI',   'name': 'Total Stock Market',     'provider': 'Vanguard', 'category': 'Total Market'},
    {'symbol': 'ARKK',  'name': 'Innovation ETF',         'provider': 'ARK',      'category': 'Thematic Growth'},
    {'symbol': 'VOO',   'name': 'S&P 500 ETF',            'provider': 'Vanguard', 'category': 'S&P 500'},
    {'symbol': 'DIA',   'name': 'Dow Jones Industrial',   'provider': 'SPDR',     'category': 'Blue Chip'},
    {'symbol': 'JEPI',  'name': 'Equity Premium Income',  'provider': 'JPMorgan', 'category': 'Income'},
    {'symbol': 'JEPQ',  'name': 'Nasdaq Equity Premium',  'provider': 'JPMorgan', 'category': 'Income Growth'},
    {'symbol': 'RSP',   'name': 'S&P 500 Equal Weight',   'provider': 'Invesco',  'category': 'Equal Weight'},
]

SPY = 'SPY'


# ── Data helpers ───────────────────────────────────────────────────────────────

def calc_return(ticker_obj, years):
    """Total % return over N years from daily close history. Returns None on failure."""
    try:
        hist = ticker_obj.history(period=f'{years + 1}y', auto_adjust=True)
        if hist.empty or len(hist) < 10:
            return None
        cutoff = hist.index[-1] - timedelta(days=years * 365)
        window = hist[hist.index >= cutoff]
        if len(window) < 5:
            return None
        start = float(window['Close'].iloc[0])
        end   = float(window['Close'].iloc[-1])
        return round((end / start - 1) * 100, 1)
    except Exception:
        return None


def get_holdings(symbol):
    """
    Fetch top ETF / mutual-fund holdings via yfinance.
    Returns a list of {'ticker', 'name', 'weight'} sorted by weight descending.
    Weight is expressed as a percentage (e.g. 7.2 means 7.2%).
    """
    try:
        t = yf.Ticker(symbol)

        # Primary path: funds_data.top_holdings (yfinance >= 0.2.x)
        try:
            fd = t.funds_data
            if fd is not None:
                df = fd.top_holdings
                if df is not None and not df.empty:
                    result = []
                    for idx, row in df.iterrows():
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
                        return sorted(result, key=lambda x: x['weight'], reverse=True)[:25]
        except Exception as e:
            print(f"  [{symbol}] funds_data err: {e}")

        # Fallback path: info dict
        try:
            info     = t.info
            raw_list = info.get('holdings', [])
            if raw_list:
                result = []
                for h in raw_list[:25]:
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


def get_stock_info(symbol):
    """Fetch basic fundamentals for a stock ticker."""
    try:
        info = yf.Ticker(symbol).info
        return {
            'full_name':  info.get('longName') or info.get('shortName', symbol),
            'sector':     info.get('sector', ''),
            'industry':   info.get('industry', ''),
            'market_cap': info.get('marketCap'),
            'price':      info.get('currentPrice') or info.get('regularMarketPrice'),
            'pe':         info.get('trailingPE'),
        }
    except Exception:
        return {}


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("[scan.py] Starting Tried & True scan...")
    start = datetime.now()

    # SPY baseline
    print("[scan.py] Fetching SPY benchmark...")
    spy_t    = yf.Ticker(SPY)
    spy_perf = {
        '1yr': calc_return(spy_t, 1),
        '3yr': calc_return(spy_t, 3),
        '5yr': calc_return(spy_t, 5),
    }
    print(f"[scan.py] SPY → {spy_perf}")

    # ETF loop
    etf_results = []
    stock_map   = {}
    total       = len(ETF_UNIVERSE)

    for i, etf in enumerate(ETF_UNIVERSE):
        sym = etf['symbol']
        print(f"[scan.py] Scanning {sym} ({i+1}/{total})...")

        t    = yf.Ticker(sym)
        perf = {
            '1yr': calc_return(t, 1),
            '3yr': calc_return(t, 3),
            '5yr': calc_return(t, 5),
        }
        holdings = get_holdings(sym)
        print(f"  {sym}: {len(holdings)} holdings | 3yr={perf.get('3yr')}%")

        spy3 = spy_perf.get('3yr')
        spy5 = spy_perf.get('5yr')
        p3   = perf.get('3yr')
        p5   = perf.get('5yr')

        etf_results.append({
            **etf,
            'performance':          perf,
            'spy_perf':             spy_perf,
            'beats_spy_3yr':        (p3 is not None and spy3 is not None and p3 > spy3),
            'beats_spy_5yr':        (p5 is not None and spy5 is not None and p5 > spy5),
            'delta_3yr':            round(p3 - spy3, 1) if (p3 is not None and spy3 is not None) else None,
            'delta_5yr':            round(p5 - spy5, 1) if (p5 is not None and spy5 is not None) else None,
            'top_holdings_display': holdings[:8],
            'holdings_count':       len(holdings),
        })

        for h in holdings:
            sym_h = h['ticker']
            if not sym_h or len(sym_h) > 6 or not sym_h.replace('-', '').isalpha():
                continue
            if sym_h not in stock_map:
                stock_map[sym_h] = {
                    'ticker':       sym_h,
                    'name':         h['name'],
                    'etf_count':    0,
                    'total_weight': 0.0,
                    'etfs_holding': [],
                }
            stock_map[sym_h]['etf_count']   += 1
            stock_map[sym_h]['total_weight']  = round(stock_map[sym_h]['total_weight'] + h['weight'], 2)
            stock_map[sym_h]['etfs_holding'].append({
                'symbol':   etf['symbol'],
                'provider': etf['provider'],
                'weight':   h['weight'],
            })

        time.sleep(1.0)

    # Comparison ETFs (scorecard only — no stock overlap)
    print("[scan.py] Scanning comparison ETFs for scorecard...")
    comparison_results = []
    for i, etf in enumerate(ETF_COMPARISON):
        sym = etf['symbol']
        print(f"[scan.py] Comparison {sym} ({i+1}/{len(ETF_COMPARISON)})...")
        t    = yf.Ticker(sym)
        perf = {
            '1yr': calc_return(t, 1),
            '3yr': calc_return(t, 3),
            '5yr': calc_return(t, 5),
        }
        spy3 = spy_perf.get('3yr')
        spy5 = spy_perf.get('5yr')
        p3   = perf.get('3yr')
        p5   = perf.get('5yr')
        comparison_results.append({
            **etf,
            'comparison_only':      True,
            'performance':          perf,
            'spy_perf':             spy_perf,
            'beats_spy_3yr':        (p3 is not None and spy3 is not None and p3 > spy3),
            'beats_spy_5yr':        (p5 is not None and spy5 is not None and p5 > spy5),
            'delta_3yr':            round(p3 - spy3, 1) if (p3 is not None and spy3 is not None) else None,
            'delta_5yr':            round(p5 - spy5, 1) if (p5 is not None and spy5 is not None) else None,
            'top_holdings_display': [],
            'holdings_count':       0,
        })
        time.sleep(1.0)

    # Score and rank
    print("[scan.py] Ranking nominees...")
    for entry in stock_map.values():
        count = entry['etf_count']
        avg_w = entry['total_weight'] / count if count else 0.0
        entry['avg_weight'] = round(avg_w, 2)
        entry['score']      = round((count * 10) + avg_w, 2)

    candidates = sorted(
        [v for v in stock_map.values() if v['etf_count'] >= 2],
        key=lambda x: x['score'],
        reverse=True
    )
    top_12 = candidates[:12]

    # Normalize scores to 0-100 scale
    # Max possible raw score: 10 ETFs * 10 + ~20% avg weight = ~120
    max_raw = max((s['score'] for s in top_12), default=1)
    for stock in top_12:
        stock['score_normalized'] = round(min(stock['score'] / max_raw * 100, 100), 1)

    # Enrich top 12 with fundamentals
    print("[scan.py] Enriching top nominees with fundamentals...")
    for rank, stock in enumerate(top_12, 1):
        stock['rank'] = rank
        print(f"  [{rank}] {stock['ticker']}")
        info = get_stock_info(stock['ticker'])
        stock.update(info)
        t = yf.Ticker(stock['ticker'])
        stock['performance'] = {
            '1yr': calc_return(t, 1),
            '3yr': calc_return(t, 3),
        }
        time.sleep(0.5)

    results = {
        'scanned_at':    start.isoformat(),
        'next_scan_info': NEXT_SCAN_INFO,
        'spy_perf':      spy_perf,
        'top_10':        top_12,
        'etfs':          etf_results,
        'etfs_comparison': comparison_results,
        'meta': {
            'etfs_scanned':       len(etf_results),
            'comparison_etfs':    len(comparison_results),
            'total_stocks_found': len(stock_map),
            'candidates_2plus':   len(candidates),
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    elapsed = (datetime.now() - start).seconds
    print(f"[scan.py] Done in {elapsed}s — {len(top_12)} nominees from {len(etf_results)} ETFs")
    print(f"[scan.py] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
