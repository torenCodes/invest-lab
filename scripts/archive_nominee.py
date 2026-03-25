#!/usr/bin/env python3
"""
archive_nominee.py — Records the top nominee from a dashboard scan into
Website/data/nominees_archive.json.

Usage (called by GitHub Actions after each scan):
    python scripts/archive_nominee.py --source movers
    python scripts/archive_nominee.py --source underdogs
    python scripts/archive_nominee.py --source insider
    python scripts/archive_nominee.py --source tried-true

Dedup logic: the same ticker from the same source is skipped if it was
already archived within the last DEDUP_DAYS days.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

ARCHIVE_PATH = 'MarketDashboard/data/nominees_archive.json'

RESULTS_PATHS = {
    'movers':      'MarketDashboard/data/results.json',
    'underdogs':   'Underdogs/data/results.json',
    'insider':     'InsiderBuying/data/results.json',
    'tried-true':  'TriedAndTrue/data/results.json',
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
    with open(path) as f:
        data = json.load(f)

    # Prefer cluster buys (multiple insiders buying the same stock)
    cluster = data.get('cluster_buys', [])
    csuite  = data.get('csuite_buys', [])

    if cluster:
        pick    = cluster[0]
        count   = pick.get('insider_count', 1)
        value   = pick.get('total_value', 0)
        reason  = f'{count} insiders bought open-market — ${value:,.0f} total'
        score   = count
        price   = pick.get('current_price')
        name    = pick.get('company', pick['ticker'])
    elif csuite:
        pick    = csuite[0]
        title   = pick.get('title', 'Insider')
        value   = pick.get('value', 0)
        reason  = f'{title} — ${value:,.0f} open-market purchase'
        score   = None
        price   = pick.get('price')   # purchase price
        name    = pick.get('company', pick['ticker'])
    else:
        return None

    return {
        'source':      'Insider Buying',
        'source_key':  'insider',
        'ticker':      pick['ticker'],
        'name':        name,
        'sector':      pick.get('sector', ''),
        'entry_price': price,
        'score':       score,
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


EXTRACTORS = {
    'movers':     extract_movers,
    'underdogs':  extract_underdogs,
    'insider':    extract_insider,
    'tried-true': extract_tried_true,
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

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    entry = {
        'id':            f'{nominee["source_key"]}-{nominee["ticker"]}-{today}',
        'source':        nominee['source'],
        'source_key':    nominee['source_key'],
        'ticker':        nominee['ticker'],
        'name':          nominee['name'],
        'sector':        nominee.get('sector', ''),
        'date_flagged':  today,
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


if __name__ == '__main__':
    main()
