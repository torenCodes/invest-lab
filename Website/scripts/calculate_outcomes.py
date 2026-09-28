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

Graded result, every source. One result per pick on its own board's clock,
with the S&P 500 over the same sessions. This is what the homepage Track Record
publishes. See BOARD_CLOCKS.
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

# ── Each board on its own clock (Sep 2026) ───────────────────────────────────
# The 30-day outcome puts every board on one calendar clock, which is wrong at
# both ends: a day-trade pick is meant for a single session, and a deep-value or
# insider pick for months. 'graded' holds the one result the homepage
# publishes: the close a set number of TRADING SESSIONS after the last close
# before the flag, with SPY over exactly the same sessions. Like the short
# horizons it reads specific closes, so it cannot drift with the job's run
# date, and it is written once and never revised.
#   movers              1 session: out at the close of the session the pick was
#                       flagged in, or the next one when flagged after the close
#   patterns, chatter   20 sessions, about a month (a swing setup)
#   marathon, insider   60 sessions, about three months. The longest clock the
#                       archive can fill today; a 120-session read needs 2027.
BOARD_CLOCKS = {'movers': 1, 'patterns': 20, 'chatter': 20,
                'underdogs': 60, 'tried-true': 60, 'insider': 60}
MAX_GRADE_MISSES = 3


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
    if nominee.get('short') and not nominee.get('short_split_safe'):
        return True                                          # stored before splits were handled; redo once
    have = nominee.get('short') or {}
    return any(k not in have for k, _ in SHORT_HORIZONS)


# ── Prices, with splits handled ──────────────────────────────────────────────
# Yahoo rescales every close before a split by the split ratio. The archive
# keeps the entry price as it was seen that day. Compared directly, CRWD's
# 4-for-1 split read as a 75% one-day loss, APH's 2-for-1 as two 51% losses,
# and SVC's reverse split inside its window as a 575% gain. So every return is
# computed on Yahoo's basis, with the archived entry converted into it once, and
# prices are stored as they traded on the day.

def price_history(tickers, start, today):
    """{ticker: {'rows': [(date, close)], 'splits': [(date, ratio)]}} for
    completed sessions, closes on Yahoo's split-adjusted basis. A ticker missing
    from the result is a miss for this run, never 'no data'."""
    import math

    out = {}
    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        syms = [t.replace('.', '-') for t in chunk]           # filings write BRK.B, Yahoo wants BRK-B
        try:
            df = yf.download(syms, start=start, progress=False, auto_adjust=False,
                             actions=True, group_by='ticker', threads=True)
        except Exception as e:
            print(f'[prices] batch {i // 50 + 1} failed ({type(e).__name__}: {e}); will retry')
            continue
        for t, s in zip(chunk, syms):
            try:
                sub = df[s] if len(chunk) > 1 else df
                close = sub['Close']
                split_col = sub['Stock Splits'] if 'Stock Splits' in sub else None
            except Exception:
                continue                                     # absent from the batch -> a miss
            rows = [(d.date(), float(v)) for d, v in close.items()
                    if d.date() < today and math.isfinite(float(v)) and float(v) > 0]
            splits = []
            if split_col is not None:
                splits = [(d.date(), float(r)) for d, r in split_col.items()
                          if math.isfinite(float(r)) and float(r) > 0 and float(r) != 1]
            if rows:
                out[t] = {'rows': rows, 'splits': splits}
    return out


def _factor_after(splits, day):
    """Product of the split ratios that took effect after `day`, which is what
    Yahoo divided that day's price by."""
    f = 1.0
    for d, r in splits:
        if d > day:
            f *= r
    return f


def _entry_on_yahoo_basis(nominee, splits):
    flag = datetime.strptime(nominee['date_flagged'], '%Y-%m-%d').date()
    return float(nominee['entry_price']) / _factor_after(splits, flag)


def fill_short_horizons(nominees, today):
    """Fill t0 / t1 / t5 for Movers picks from historical closes.

    Works for any pick whose sessions have closed, however old, so the first
    run backfills the whole archive. Values stored before splits were handled
    (no short_split_safe flag) are recomputed once. That corrects split damage;
    it does not revise a result. Returns the number of horizon values set.
    """
    todo = [n for n in nominees if _needs_short(n)]
    if not todo:
        print('[short] Nothing to fill')
        return 0

    tickers = sorted({n['ticker'] for n in todo})
    earliest = min(n['date_flagged'] for n in todo)
    start = (datetime.strptime(earliest, '%Y-%m-%d') - timedelta(days=3)).strftime('%Y-%m-%d')
    print(f'[short] {len(todo)} pick(s) across {len(tickers)} ticker(s) need short horizons '
          f'(from {earliest})')
    hist = price_history(tickers, start, today)

    filled = 0
    for n in todo:
        h = hist.get(n['ticker'])
        if h is None:
            n['short_misses'] = n.get('short_misses', 0) + 1
            if n['short_misses'] >= MAX_SHORT_MISSES:
                n['short_unavailable'] = True
                print(f'[short] {n["ticker"]} flagged {n["date_flagged"]}: no price history after '
                      f'{MAX_SHORT_MISSES} runs, giving up')
            continue
        if not n.get('entry_price'):
            continue

        flag = datetime.strptime(n['date_flagged'], '%Y-%m-%d').date()
        sessions = [(d, px) for d, px in h['rows'] if d >= flag]
        entry = _entry_on_yahoo_basis(n, h['splits'])

        # A redo starts from scratch; a fill keeps what is already there.
        short = n.setdefault('short', {}) if n.get('short_split_safe') else {}
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
            short[key] = {
                'date':  d.strftime('%Y-%m-%d'),
                'price': round(px * _factor_after(h['splits'], d), 2),   # as it traded that day
                'pct':   round((px - entry) / entry * 100, 2),
            }
            filled += 1
        n['short'] = short
        n['short_split_safe'] = True
        n.pop('short_misses', None)                          # a success clears the ledger

    print(f'[short] Set {filled} horizon value(s); {len(tickers) - len(hist)} ticker(s) '
          f'returned no history this run')
    return filled


def _last_close_before_flag(nominee, calendar, traded_close):
    """The session whose close was the last one completed when the pick was
    flagged. After-close flags count their own day. Picks archived before
    flagged_session existed are read from the price: an entry equal to the flag
    day's close was taken at or after that close (48 early Movers picks were)."""
    flag = datetime.strptime(nominee['date_flagged'], '%Y-%m-%d').date()
    when = nominee.get('flagged_session')
    on_or_before = [d for d in calendar if d <= flag]
    before = [d for d in calendar if d < flag]
    if when in ('after', 'closed'):
        return on_or_before[-1] if on_or_before else None
    if when is None and on_or_before and on_or_before[-1] == flag:
        px = traded_close(flag)
        if px and abs(px - float(nominee['entry_price'])) < 0.015:
            return flag
    return before[-1] if before else None


def fill_graded(nominees, today):
    """Grade each pick on its board's clock. Returns (graded, other records
    changed), the second being miss counters, so the caller knows to save."""
    todo = [n for n in nominees if n.get('source_key') in BOARD_CLOCKS and 'graded' not in n
            and not n.get('graded_unavailable') and n.get('entry_price')]
    if not todo:
        print('[graded] Nothing to grade')
        return 0, 0
    earliest = min(n['date_flagged'] for n in todo)
    start = (datetime.strptime(earliest, '%Y-%m-%d') - timedelta(days=10)).strftime('%Y-%m-%d')
    hist = price_history(sorted({n['ticker'] for n in todo} | {'SPY'}), start, today)
    if 'SPY' not in hist:
        print('[graded] SPY history unavailable - grading nothing this run')
        return 0, 0
    calendar = [d for d, _ in hist['SPY']['rows']]
    spy = dict(hist['SPY']['rows'])
    pos = {d: i for i, d in enumerate(calendar)}

    def miss(n):
        n['graded_misses'] = n.get('graded_misses', 0) + 1
        if n['graded_misses'] >= MAX_GRADE_MISSES:
            n['graded_unavailable'] = True
            print(f'[graded] {n["ticker"]} ({n["source_key"]}, {n["date_flagged"]}): '
                  f'no usable price after {MAX_GRADE_MISSES} runs, giving up')

    graded = pending = touched = 0
    for n in todo:
        h = hist.get(n['ticker'])
        if h is None:
            miss(n)
            touched += 1
            continue
        closes, splits = dict(h['rows']), h['splits']
        traded = lambda d: closes[d] * _factor_after(splits, d) if d in closes else None
        ref = _last_close_before_flag(n, calendar, traded)
        if ref is None:
            continue
        k = BOARD_CLOCKS[n['source_key']]
        j = pos[ref] + k
        if j >= len(calendar):
            pending += 1                                     # its clock has not run out yet
            continue
        exit_day = calendar[j]
        entry = _entry_on_yahoo_basis(n, splits)
        result = {'sessions': k, 'from': ref.strftime('%Y-%m-%d'), 'date': exit_day.strftime('%Y-%m-%d')}

        px = closes.get(exit_day)
        if px is None:
            # No bar on the exit day. A stock that stopped trading before it (a
            # buyout or a delisting, no bars for a week or more since) is graded
            # at its last close. Anything else is a gap: retried, never guessed.
            last_day = h['rows'][-1][0]
            stopped = ref < last_day < exit_day and pos.get(last_day, len(calendar)) <= len(calendar) - 6
            if not stopped:
                miss(n)
                touched += 1
                continue
            exit_day, px = h['rows'][-1]
            result['ended_early'] = exit_day.strftime('%Y-%m-%d')
        result['price'] = round(px * _factor_after(splits, exit_day), 2)   # as it traded that day
        result['pct'] = round((px - entry) / entry * 100, 2)
        result['spy_pct'] = round((spy[exit_day] - spy[ref]) / spy[ref] * 100, 2)
        n['graded'] = result
        n.pop('graded_misses', None)
        graded += 1
    print(f'[graded] Graded {graded} pick(s); {pending} still inside their clock')
    return graded, touched


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
    graded, touched = fill_graded(archive['nominees'], today)

    if updated or short_filled or graded or touched:
        with open(ARCHIVE_PATH, 'w') as f:
            json.dump(archive, f, indent=2)
        print(f'[outcomes] Done — resolved {updated} 30-day outcome(s), '
              f'{short_filled} short-horizon value(s), {graded} graded on their clock')
    else:
        print('[outcomes] No nominees needed updating')


if __name__ == '__main__':
    main()
