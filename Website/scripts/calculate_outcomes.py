#!/usr/bin/env python3
"""
calculate_outcomes.py — Fills in 30-day outcome prices for archived nominees.

Usage (called by weekly GitHub Actions workflow):
    python scripts/calculate_outcomes.py

For each nominee that is OUTCOME_DAYS old and still has outcome_price=null,
fetches the current market price via yfinance and records the % change from
the original entry price.
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

    if updated:
        with open(ARCHIVE_PATH, 'w') as f:
            json.dump(archive, f, indent=2)
        print(f'[outcomes] Done — resolved {updated} nominee(s)')
    else:
        print('[outcomes] No nominees needed updating')


if __name__ == '__main__':
    main()
