"""
Tried and True — Growth Stock Overlap Dashboard

Identifies the top 10 stocks with the highest consensus across top growth ETFs
that have outperformed SPY. The more ETFs that hold a stock — and the higher
their average allocation — the stronger the conviction signal.

Run:   python app.py
Needs: pip install flask yfinance
"""

import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, jsonify, send_file

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("yfinance not installed.  Run: pip install yfinance")

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, 'results.json')

# ── ETF Universe ──────────────────────────────────────────────────────────────
# Growth-oriented ETFs and funds selected for long-term S&P 500 outperformance.
# Covers multiple providers and investment styles to ensure the overlap signal
# reflects genuine multi-source conviction, not just index-tracking overlap.

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

SPY = 'SPY'

app    = Flask(__name__)
_lock  = threading.Lock()
_state = {
    'status':    'idle',   # 'idle' | 'scanning' | 'error'
    'progress':  0,
    'current':   '',
    'last_scan': None,
    'results':   None,
}


# ── Data helpers ──────────────────────────────────────────────────────────────

def calc_return(ticker_obj, years):
    """Total % return over N years from daily close history. Returns None on failure."""
    try:
        hist = ticker_obj.history(period=f'{years + 1}y', auto_adjust=True)
        if hist.empty or len(hist) < 10:
            return None
        cutoff = hist.index[-1] - timedelta(days=years * 365)
        window  = hist[hist.index >= cutoff]
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
    Weight is expressed as a percentage (e.g. 7.2 means 7.2 %).
    """
    try:
        t = yf.Ticker(symbol)

        # Primary path: funds_data.top_holdings (yfinance ≥ 0.2.x)
        try:
            fd = t.funds_data
            if fd is not None:
                df = fd.top_holdings
                if df is not None and not df.empty:
                    result = []
                    for idx, row in df.iterrows():
                        raw = row.get('holdingPercent', 0)
                        try:
                            pct = float(raw) * 100      # fraction → percent
                        except (TypeError, ValueError):
                            continue
                        sym = str(idx).strip()
                        if not sym or len(sym) > 6:
                            continue
                        result.append({
                            'ticker': sym,
                            'name':   str(row.get('holdingName', sym)).strip(),
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


# ── Scanner ───────────────────────────────────────────────────────────────────

def _set(progress, current):
    with _lock:
        _state['progress'] = progress
        _state['current']  = current


def run_scan():
    with _lock:
        if _state['status'] == 'scanning':
            return
        _state['status']   = 'scanning'
        _state['progress'] = 0
    try:
        _do_scan()
    except Exception as e:
        print(f"[Tried & True] Fatal scan error: {e}")
        with _lock:
            _state['status']  = 'error'
            _state['current'] = f'Error: {e}'


def _do_scan():
    # ── SPY baseline ──────────────────────────────────────────────────────────
    _set(2, 'Fetching SPY benchmark…')
    spy_t    = yf.Ticker(SPY)
    spy_perf = {
        '1yr': calc_return(spy_t, 1),
        '3yr': calc_return(spy_t, 3),
        '5yr': calc_return(spy_t, 5),
    }
    print(f"[Tried & True] SPY benchmark → {spy_perf}")

    # ── ETF loop ──────────────────────────────────────────────────────────────
    etf_results = []
    stock_map   = {}        # symbol → aggregation dict
    total       = len(ETF_UNIVERSE)

    for i, etf in enumerate(ETF_UNIVERSE):
        sym = etf['symbol']
        _set(5 + int(i / total * 60), f'Scanning {sym} — {etf["provider"]} {etf["name"]}…')
        print(f"[Tried & True] Scanning {sym}…")

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
            'performance':           perf,
            'spy_perf':              spy_perf,
            'beats_spy_3yr':         (p3 is not None and spy3 is not None and p3 > spy3),
            'beats_spy_5yr':         (p5 is not None and spy5 is not None and p5 > spy5),
            'delta_3yr':             round(p3 - spy3, 1) if (p3 is not None and spy3 is not None) else None,
            'delta_5yr':             round(p5 - spy5, 1) if (p5 is not None and spy5 is not None) else None,
            'top_holdings_display':  holdings[:8],
            'holdings_count':        len(holdings),
        })

        # Aggregate holdings into stock_map
        for h in holdings:
            sym_h = h['ticker']
            # Skip non-equity entries (bonds, cash, ETFs-within-ETFs, etc.)
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
            stock_map[sym_h]['etf_count']    += 1
            stock_map[sym_h]['total_weight']  = round(stock_map[sym_h]['total_weight'] + h['weight'], 2)
            stock_map[sym_h]['etfs_holding'].append({
                'symbol':   etf['symbol'],
                'provider': etf['provider'],
                'weight':   h['weight'],
            })

        time.sleep(1.0)     # gentle rate limiting on Yahoo Finance

    # ── Score and rank candidates ──────────────────────────────────────────────
    _set(68, 'Ranking nominees…')

    for entry in stock_map.values():
        count = entry['etf_count']
        avg_w = entry['total_weight'] / count if count else 0.0
        entry['avg_weight'] = round(avg_w, 2)
        # Score: breadth of consensus (count × 10) + depth of conviction (avg weight)
        entry['score'] = round((count * 10) + avg_w, 2)

    candidates = sorted(
        [v for v in stock_map.values() if v['etf_count'] >= 2],
        key=lambda x: x['score'],
        reverse=True
    )
    top_10 = candidates[:10]

    # ── Enrich top 10 with fundamentals ───────────────────────────────────────
    _set(72, 'Enriching top nominees with fundamentals…')

    for rank, stock in enumerate(top_10, 1):
        stock['rank'] = rank
        _set(72 + rank * 2, f'Fetching data for {stock["ticker"]}…')
        info = get_stock_info(stock['ticker'])
        stock.update(info)
        t = yf.Ticker(stock['ticker'])
        stock['performance'] = {
            '1yr': calc_return(t, 1),
            '3yr': calc_return(t, 3),
        }
        time.sleep(0.5)

    # ── Persist ───────────────────────────────────────────────────────────────
    _set(98, 'Saving results…')

    results = {
        'scanned_at': datetime.now().isoformat(),
        'spy_perf':   spy_perf,
        'top_10':     top_10,
        'etfs':       etf_results,
        'meta': {
            'etfs_scanned':       len(etf_results),
            'total_stocks_found': len(stock_map),
            'candidates_2plus':   len(candidates),
        },
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    with _lock:
        _state['results']   = results
        _state['status']    = 'idle'
        _state['progress']  = 100
        _state['current']   = 'Scan complete'
        _state['last_scan'] = datetime.now().isoformat()

    print(
        f"[Tried & True] Scan complete — "
        f"{len(top_10)} nominees from {len(etf_results)} ETFs "
        f"({len(stock_map)} unique stocks found)"
    )


# ── Flask routes ──────────────────────────────────────────────────────────────

WEBSITE_IMAGES = os.path.join(BASE_DIR, '..', 'Website', 'images')

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_file(os.path.join(WEBSITE_IMAGES, filename))

@app.route('/')
def index():
    return send_file(os.path.join(BASE_DIR, 'dashboard.html'))


@app.route('/api/status')
def api_status():
    with _lock:
        return jsonify({
            'status':    _state['status'],
            'progress':  _state['progress'],
            'current':   _state['current'],
            'last_scan': _state['last_scan'],
        })


@app.route('/api/results')
def api_results():
    with _lock:
        data = _state['results']
    if data:
        return jsonify(data)
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return jsonify(json.load(f))
    return jsonify({'error': 'No results yet — scan in progress.'}), 404


@app.route('/api/rescan', methods=['POST'])
def api_rescan():
    with _lock:
        if _state['status'] == 'scanning':
            return jsonify({'error': 'Already scanning'}), 409
    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/ping')
def ping():
    return 'ok'


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Load any cached results so the UI isn't blank on restart
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            _state['results'] = json.load(f)
        print('[Tried & True] Loaded cached results.')
    else:
        print('[Tried & True] No cache — launching initial scan…')
        threading.Thread(target=run_scan, daemon=True).start()

    # On Render (and other cloud platforms) PORT is injected as an env var.
    # Locally, find a free port from the candidate list.
    if os.environ.get('PORT'):
        port = int(os.environ['PORT'])
        print(f'[Tried & True] → running on port {port}')
        app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
    else:
        for port in [8090, 8091, 8092, 9090, 9091]:
            try:
                with socket.socket() as s:
                    s.bind(('', port))
                print(f'[Tried & True] → http://localhost:{port}')
                app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
                break
            except OSError:
                continue
