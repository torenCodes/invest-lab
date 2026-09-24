#!/usr/bin/env python3
"""
archive_nominee.py — Records the top nominee from a dashboard scan into
Website/data/nominees_archive.json.

Usage (called by GitHub Actions after each scan):
    python scripts/archive_nominee.py --source movers
    python scripts/archive_nominee.py --source underdogs
    python scripts/archive_nominee.py --source insider
    python scripts/archive_nominee.py --source tried-true
    python scripts/archive_nominee.py --source patterns   # top Coil pick (coil.json)

Dedup logic: the same ticker from the same source is skipped if it was
already archived within the last DEDUP_DAYS days.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

WEBSITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ARCHIVE_PATH = os.path.join(WEBSITE_DIR, 'MarketDashboard', 'data', 'nominees_archive.json')

RESULTS_PATHS = {
    'movers':      os.path.join(WEBSITE_DIR, 'MarketDashboard', 'data', 'results.json'),
    'underdogs':   os.path.join(WEBSITE_DIR, 'TheMarathon', 'data', 'deep_value.json'),
    'insider':     os.path.join(WEBSITE_DIR, 'InsiderBuying', 'data', 'results.json'),
    'tried-true':  os.path.join(WEBSITE_DIR, 'TheMarathon', 'data', 'consensus.json'),
    'patterns':    os.path.join(WEBSITE_DIR, 'PatternScanner', 'data', 'coil.json'),
    # Phase B (data-gathering): top accelerating-chatter pick from the Movers
    # scan — archived so its 30-day outcome builds a track record we can judge
    # before surfacing chatter velocity as a live trading flag.
    'chatter':     os.path.join(WEBSITE_DIR, 'MarketDashboard', 'data', 'results.json'),
}

DEDUP_DAYS = 14  # Don't re-archive the same ticker+source within N days


# ── Archive helpers ────────────────────────────────────────────────────────────

def load_archive():
    if os.path.exists(ARCHIVE_PATH):
        with open(ARCHIVE_PATH) as f:
            return json.load(f)
    return {'nominees': []}


def save_archive(data):
    os.makedirs(os.path.dirname(ARCHIVE_PATH), exist_ok=True)
    with open(ARCHIVE_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def is_duplicate(archive, source_key, ticker):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DEDUP_DAYS)).date()
    for n in archive['nominees']:
        if n['source_key'] == source_key and n['ticker'] == ticker:
            flagged = datetime.strptime(n['date_flagged'], '%Y-%m-%d').date()
            if flagged >= cutoff:
                return True
    return False


# ── Extractors — one per dashboard ────────────────────────────────────────────

def extract_movers(path):
    with open(path) as f:
        data = json.load(f)

    # Pick highest-scored nominee across day_trades and swing_trades
    candidates = []
    day_list   = data.get('day_trades', [])
    swing_list = data.get('swing_trades', [])
    if day_list:
        candidates.append(('Day Trade', day_list[0]))
    if swing_list:
        candidates.append(('Swing Trade', swing_list[0]))
    if not candidates:
        return None

    trade_type, pick = max(candidates, key=lambda x: x[1].get('score', 0))
    signals = pick.get('signals', [])
    reason  = trade_type + ' — ' + '; '.join(signals[:2]) if signals else trade_type + ' nominee'

    return {
        'source':      'Movers & Shakers',
        'source_key':  'movers',
        'ticker':      pick['ticker'],
        'name':        pick.get('name', pick['ticker']),
        'sector':      pick.get('sector', ''),
        'entry_price': pick.get('current_price'),
        'score':       pick.get('score'),
        'reason':      reason,
    }


def extract_underdogs(path):
    with open(path) as f:
        data = json.load(f)

    nominees = data.get('nominees', [])
    if not nominees:
        return None

    pick    = nominees[0]
    quality = pick.get('quality_signals', [])
    beaten  = pick.get('beaten_signals', [])
    parts   = quality[:1] + beaten[:1]
    detail  = '; '.join(parts) if parts else 'Top composite nominee'
    reason  = (f"Quality {pick.get('quality_score', 0)}, "
               f"Beaten-up {pick.get('beaten_up_score', 0)} — {detail}")

    return {
        'source':      'The Underdogs',
        'source_key':  'underdogs',
        'ticker':      pick['ticker'],
        'name':        pick.get('name', pick['ticker']),
        'sector':      pick.get('sector', ''),
        'entry_price': pick.get('price'),
        'score':       round(float(pick.get('composite_score', 0)), 1),
        'reason':      reason,
    }


def extract_insider(path):
    """Pick the top-conviction Insider nominee for the daily archive entry.
    The nominees list is already sorted by conviction score, so nominees[0]
    is the best representative across every dimension (cluster size +
    C-suite + dollar volume + recency) without the old cluster-then-csuite
    fallback dance."""
    with open(path) as f:
        data = json.load(f)

    nominees = data.get('nominees', [])
    if not nominees:
        return None

    pick    = nominees[0]
    count   = pick.get('insider_count', 1)
    value   = pick.get('value', 0)
    signals = pick.get('signals') or []

    # Reason string — prefer the conviction signal list since it's richer
    # than the legacy "N insiders bought" template
    if signals:
        reason = ' · '.join(signals[:3])
    elif count > 1:
        reason = f'{count} insiders bought open-market — ${value:,.0f} total'
    else:
        title = (pick.get('insiders') or [{}])[0].get('title', 'Insider')
        reason = f'{title} — ${value:,.0f} open-market purchase'

    # Entry price — top-level current_price, fall back to top insider's purchase
    price = pick.get('current_price') or (pick.get('insiders') or [{}])[0].get('price')

    return {
        'source':      'Insider Buying',
        'source_key':  'insider',
        'ticker':      pick['ticker'],
        'name':        pick.get('company', pick['ticker']),
        'sector':      pick.get('sector', ''),
        'entry_price': price,
        'score':       pick.get('conviction_score'),
        'reason':      reason,
    }


def extract_tried_true(path):
    with open(path) as f:
        data = json.load(f)

    top_10 = data.get('top_10', [])
    if not top_10:
        return None

    pick      = top_10[0]
    etf_count = pick.get('etf_count', 0)
    score     = pick.get('score', 0)
    reason    = f'Held in {etf_count} growth ETFs — consensus score {score:.0f}'

    return {
        'source':      'Tried and True',
        'source_key':  'tried-true',
        'ticker':      pick['ticker'],
        'name':        pick.get('full_name') or pick.get('name', pick['ticker']),
        'sector':      pick.get('sector', ''),
        'entry_price': pick.get('price'),
        'score':       score,
        'reason':      reason,
    }


def extract_patterns(path):
    """Top pick from the Pattern Scanner's Coil engine (coil.json). The
    'Coiled' list is the dashboard's headline tightness-ranked watchlist, so
    coiled[0] is the strongest setup of the day."""
    with open(path) as f:
        data = json.load(f)

    coiled = data.get('coiled', [])
    if not coiled:
        return None
    pick = coiled[0]

    bits = ['Coil ' + str(round(pick.get('coil_score', 0)))]
    if pick.get('rs_pct') is not None:
        bits.append('RS ' + str(pick['rs_pct']) + 'th')
    if pick.get('band_pct') is not None:
        bits.append(str(pick['band_pct']) + '% range')
    reason = pick.get('pattern', 'Coiled setup') + ' — ' + ', '.join(bits)

    return {
        'source':      'Pattern Scanner',
        'source_key':  'patterns',
        'ticker':      pick['ticker'],
        'name':        pick.get('name', pick['ticker']),
        'sector':      pick.get('sector', ''),
        'entry_price': pick.get('price'),
        'score':       round(float(pick.get('coil_score', 0)), 1),
        'reason':      reason,
    }


def extract_chatter(path):
    """Top accelerating-chatter pick from the Movers scan's `chatter_emerging`
    list (quiet yesterday, spiking today). Archived to measure whether the
    velocity signal precedes a move."""
    with open(path) as f:
        data = json.load(f)

    picks = data.get('chatter_emerging') or []
    if not picks:
        return None
    p = picks[0]
    trend = p.get('trend_pct')
    return {
        'source':      'Chatter Watch',
        'source_key':  'chatter',
        'ticker':      p['ticker'],
        'name':        p.get('name', p['ticker']),
        'sector':      p.get('sector', ''),
        'entry_price': p.get('current_price'),
        'score':       trend,
        'reason':      (f"Chatter accelerating — {p.get('mentions')} mentions, "
                        f"up {trend}% over 24h (from {p.get('prev')})"),
    }


EXTRACTORS = {
    'movers':     extract_movers,
    'underdogs':  extract_underdogs,
    'insider':    extract_insider,
    'tried-true': extract_tried_true,
    'patterns':   extract_patterns,
    'chatter':    extract_chatter,
}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Archive top scan nominee')
    parser.add_argument('--source', required=True, choices=RESULTS_PATHS.keys(),
                        help='Which dashboard scan is calling this')
    args = parser.parse_args()

    results_path = RESULTS_PATHS[args.source]
    if not os.path.exists(results_path):
        print(f'[archive] Results file not found: {results_path} — skipping')
        sys.exit(0)

    try:
        nominee = EXTRACTORS[args.source](results_path)
    except Exception as e:
        print(f'[archive] Failed to extract nominee from {results_path}: {e}')
        sys.exit(0)

    if not nominee:
        print(f'[archive] No nominee found in {results_path} — skipping')
        sys.exit(0)

    if nominee.get('entry_price') is None:
        print(f'[archive] No entry price for {nominee["ticker"]} — skipping')
        sys.exit(0)

    archive = load_archive()

    if is_duplicate(archive, nominee['source_key'], nominee['ticker']):
        print(f'[archive] Duplicate within {DEDUP_DAYS} days: '
              f'{nominee["ticker"]} ({nominee["source_key"]}) — skipping')
        sys.exit(0)

    today, flagged_at, session = _flag_stamp()
    entry = {
        'id':            f'{nominee["source_key"]}-{nominee["ticker"]}-{today}',
        'source':        nominee['source'],
        'source_key':    nominee['source_key'],
        'ticker':        nominee['ticker'],
        'name':          nominee['name'],
        'sector':        nominee.get('sector', ''),
        'date_flagged':  today,
        'flagged_at':    flagged_at,
        'flagged_session': session,
        'entry_price':   round(float(nominee['entry_price']), 2),
        'score':         nominee.get('score'),
        'reason':        nominee['reason'],
        'outcome_price': None,
        'outcome_pct':   None,
        'outcome_date':  None,
    }

    archive['nominees'].append(entry)
    save_archive(archive)
    print(f'[archive] Recorded: {entry["ticker"]} ({entry["source"]}) '
          f'at ${entry["entry_price"]} on {today}')


def _flag_stamp():
    """(date_flagged, flagged_at, flagged_session) for a pick recorded now.

    date_flagged is the US/Eastern trading date. It used to be the UTC date,
    so any run landing after 8pm ET was stamped with tomorrow's date - and
    GitHub's scheduler has been observed running hours late.

    flagged_session records WHERE in the trading day the entry price was taken.
    The archive used to hold only the date, and the entry price is whatever the
    scan saw at run time: intraday for most runs, but exactly the close for any
    run that landed after 4pm. 37 of 347 Movers picks had an entry equal to the
    day's close to the cent, which made a same-day outcome meaningless for them
    and was indistinguishable from the rest. calculate_outcomes skips the
    same-day read for 'after' and 'closed'.
    """
    now_utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_et = now_utc.astimezone(ZoneInfo('America/New_York'))
    except Exception:
        # No tz database (rare; the Actions runner has one). Fixed EDT offset is
        # wrong by an hour in winter, which only matters within an hour of the
        # open or close, so say so rather than fail.
        print('[archive] zoneinfo unavailable - using a fixed UTC-4 offset')
        now_et = now_utc - timedelta(hours=4)

    mins = now_et.hour * 60 + now_et.minute
    if now_et.weekday() >= 5:
        session = 'closed'
    elif mins < 9 * 60 + 30:
        session = 'pre'
    elif mins < 16 * 60:
        session = 'open'
    else:
        session = 'after'
    return now_et.strftime('%Y-%m-%d'), now_utc.isoformat(timespec='seconds'), session


if __name__ == '__main__':
    main()
