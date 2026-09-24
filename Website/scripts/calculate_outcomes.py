#!/usr/bin/env python3
"""
calculate_outcomes.py — Fills in outcomes for archived nominees.

Usage (called by the weekday outcomes-calc GitHub Actions workflow):
    python scripts/calculate_outcomes.py

Two measurements:

30-day outcome, every source. For each nominee that is OUTCOME_DAYS old and
still has outcome_price=null, fetches the current price and records the %
change from entry. Written once and never revisited. Because it takes the price
on whatever day the job runs, the true window drifts past 30 days when a run is
missed; the published values are frozen, so that is documented rather than
recomputed.

Short horizons, Movers picks only. t0 / t1 / t5 sessions after the flag, each
read from the close of a specific session. See SHORT_HORIZONS.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
except ImportError:
    print('[outcomes] yfinance not installed — run: pip install yfinance')
    sys.exit(1)

WEBSITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_PATH = os.path.join(WEBSITE_DIR, 'MarketDashboard', 'data', 'nominees_archive.json')
OUTCOME_DAYS = 30

# ── Short horizons for the Movers board (Sep 2026) ───────────────────────────
# A day-trade pick is a same-day idea, but until now the only thing ever
# recorded for it was a 30-day outcome. Benchmarked, those day picks trailed
# SPY by 6.4 points at the median over their 30-day windows, which says
# holding them for a month loses and says nothing about whether they work as
# day trades. These horizons make that answerable.
#
# Counted in TRADING SESSIONS from the flag date, each read off the close of a
# specific session, so unlike the 30-day figure they cannot drift with the
# job's run date:
#   t0 - close of the flag day itself. The scans run intraday, so this is the
#        pure day-trade read: entry at the scan's price, out at that close.
#   t1 - close of the next session.
#   t5 - close five sessions later, roughly one trading week.
# Only today's bar is excluded; a session counts once it has closed.
SHORT_HORIZONS = (('t0', 0), ('t1', 1), ('t5', 5))
SHORT_SOURCES = {'movers'}

# A failed price fetch is never written down as a result. It increments a miss
# counter and the pick is retried next run; only after this many separate runs
# is it given up on. The insider backtest once cached rate-limit failures as
# "no data" and wrote off MSFT, KO and WMT as delisted.
MAX_SHORT_MISSES = 3


def fetch_price(ticker):
    """Return the most recent closing price for a ticker, or None on failure."""
    try:
        hist = yf.Ticker(ticker).history(period='2d')
        if hist.empty:
            return None
        return round(float(hist['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f'[outcomes] Could not fetch price for {ticker}: {e}')
        return None


def pick_kind(nominee):
    """'day' or 'swing' for a Movers pick, read from the reason prefix."""
    reason = (nominee.get('reason') or '').lower()
    if reason.startswith('day'):
        return 'day'
    if reason.startswith('swing'):
        return 'swing'
    return None


def _needs_short(nominee):
    if nominee.get('source_key') not in SHORT_SOURCES:
        return False
    if nominee.get('short_unavailable'):
        return False
    have = nominee.get('short') or {}
    return any(k not in have for k, _ in SHORT_HORIZONS)


def fill_short_horizons(nominees, today):
    """Fill t0 / t1 / t5 for Movers picks from historical closes.

    Works for any pick whose sessions have closed, however old, so the first
    run backfills the whole archive. Returns the number of horizon values set.
    """
    import math

    todo = [n for n in nominees if _needs_short(n)]
    if not todo:
        print('[short] Nothing to fill')
        return 0

    by_ticker = {}
    for n in todo:
        by_ticker.setdefault(n['ticker'], []).append(n)
    tickers = sorted(by_ticker)
    earliest = min(n['date_flagged'] for n in todo)
    start = (datetime.strptime(earliest, '%Y-%m-%d') - timedelta(days=3)).strftime('%Y-%m-%d')
    print(f'[short] {len(todo)} pick(s) across {len(tickers)} ticker(s) need short horizons '
          f'(from {earliest})')

    closes = {}
    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        try:
            df = yf.download(chunk, start=start, progress=False, auto_adjust=False,
                             group_by='ticker', threads=True)
        except Exception as e:
            # The whole batch failed - record nothing, retry next run.
            print(f'[short] batch {i // 50 + 1} failed ({type(e).__name__}: {e}); will retry')
            continue
        for t in chunk:
            try:
                s = (df[t]['Close'] if len(chunk) > 1 else df['Close']).dropna()
                s = s[s.index.date < today]                 # completed sessions only
                if len(s):
                    closes[t] = s
            except Exception:
                pass                                         # absent from batch -> a miss

    filled = 0
    for n in todo:
        s = closes.get(n['ticker'])
        if s is None:
            n['short_misses'] = n.get('short_misses', 0) + 1
            if n['short_misses'] >= MAX_SHORT_MISSES:
                n['short_unavailable'] = True
                print(f'[short] {n["ticker"]} flagged {n["date_flagged"]}: no price history after '
                      f'{MAX_SHORT_MISSES} runs, giving up')
            continue

        flag = datetime.strptime(n['date_flagged'], '%Y-%m-%d').date()
        sessions = [(d, float(v)) for d, v in zip(s.index.date, s.values) if d >= flag]
        entry = n.get('entry_price')
        if not entry:
            continue

        short = n.setdefault('short', {})
        for key, k in SHORT_HORIZONS:
            if key in short or k >= len(sessions):
                continue                                     # already set, or not closed yet
            if key == 't0' and n.get('flagged_session') in ('after', 'closed'):
                # Entry was taken at or after the close, so entry -> close is
                # zero by construction. Recorded as None (a considered blank,
                # not a miss) so it is neither retried nor averaged in.
                # Picks archived before flagged_session existed have no field
                # and keep a t0 - some of those are after-close entries too.
                short[key] = None
                continue
            d, px = sessions[k]
            if not math.isfinite(px) or px <= 0:
                continue
            short[key] = {
                'date':  d.strftime('%Y-%m-%d'),
                'price': round(px, 2),
                'pct':   round((px - entry) / entry * 100, 2),
            }
            filled += 1
        n.pop('short_misses', None)                          # a success clears the ledger

    print(f'[short] Set {filled} horizon value(s); {len(tickers) - len(closes)} ticker(s) '
          f'returned no history this run')
    return filled


def main():
    if not os.path.exists(ARCHIVE_PATH):
        print('[outcomes] Archive not found — nothing to do')
        sys.exit(0)

    with open(ARCHIVE_PATH) as f:
        archive = json.load(f)

    today   = datetime.now(timezone.utc).date()
    cutoff  = today - timedelta(days=OUTCOME_DAYS)
    updated = 0

    for nominee in archive['nominees']:
        # Skip already resolved
        if nominee.get('outcome_price') is not None:
            continue

        flagged = datetime.strptime(nominee['date_flagged'], '%Y-%m-%d').date()

        # Skip nominees not yet old enough
        if flagged > cutoff:
            print(f'[outcomes] {nominee["ticker"]} ({nominee["source_key"]}) '
                  f'flagged {nominee["date_flagged"]} — not 30 days old yet, skipping')
            continue

        current_price = fetch_price(nominee['ticker'])
        if current_price is None:
            print(f'[outcomes] Could not get price for {nominee["ticker"]} — skipping')
            continue

        entry_price  = nominee['entry_price']
        outcome_pct  = round((current_price - entry_price) / entry_price * 100, 2)

        nominee['outcome_price'] = current_price
        nominee['outcome_pct']   = outcome_pct
        nominee['outcome_date']  = today.strftime('%Y-%m-%d')

        arrow = '▲' if outcome_pct >= 0 else '▼'
        print(f'[outcomes] {nominee["ticker"]:6s} ({nominee["source_key"]}): '
              f'${entry_price} → ${current_price}  {arrow} {outcome_pct:+.2f}%  '
              f'[flagged {nominee["date_flagged"]}]')
        updated += 1

    short_filled = fill_short_horizons(archive['nominees'], today)

    if updated or short_filled:
        with open(ARCHIVE_PATH, 'w') as f:
            json.dump(archive, f, indent=2)
        print(f'[outcomes] Done — resolved {updated} 30-day outcome(s), '
              f'{short_filled} short-horizon value(s)')
    else:
        print('[outcomes] No nominees needed updating')


if __name__ == '__main__':
    main()
