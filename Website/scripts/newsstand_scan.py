"""
Newsstand Scanner — Standalone
Fetches market context data (earnings calendar, news, unusual volume)
and writes to MarketDashboard/data/newsstand.json for the homepage.

Invoked by GitHub Actions on schedule.
Run locally: python scripts/newsstand_scan.py
"""

import csv
import io
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "MarketDashboard", "data", "newsstand.json")

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70")
POLYGON_KEY = os.environ.get("POLYGON_KEY", "P9fRbZP9VAKhjwABMtvcS7tfcYGU6z1T")

NEXT_SCAN_INFO = "Weekdays at 10:30am, 1pm, 4pm ET"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


# ── Russell 3000 universe (for earnings calendar filter) ─────────────────────

IWV_URL = ("https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/"
           "1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund")


def fetch_russell3000_universe():
    """Fetch the iShares IWV (Russell 3000) holdings CSV and return a set of
    equity tickers. The Russell 3000 ≈ top ~3000 US stocks by market cap,
    covering S&P 500, Russell 2000, and mid-cap contenders.

    Returns an empty set on failure (callers should treat that as "no filter").
    """
    print("[newsstand] Fetching Russell 3000 universe from iShares IWV...")
    try:
        r = requests.get(IWV_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[newsstand] IWV fetch failed: {e}")
        return set()

    tickers = set()
    reader = csv.reader(io.StringIO(r.text))
    in_holdings = False
    for row in reader:
        if not row:
            continue
        if not in_holdings:
            # Header row — first cell is exactly "Ticker"
            if row[0].strip().lower() == "ticker":
                in_holdings = True
            continue
        # Data row — only keep Equity rows with a real ticker
        if len(row) < 4:
            continue
        ticker    = row[0].strip().upper()
        asset_cls = row[3].strip() if len(row) > 3 else ""
        if not ticker or asset_cls.lower() != "equity":
            continue
        # Normalize away punctuation — iShares/Finnhub/Yahoo disagree on
        # share-class formatting (BRKB vs BRK.B vs BRK-B). Strip on both
        # sides of the comparison.
        tickers.add(_norm_ticker(ticker))

    print(f"[newsstand] Universe: {len(tickers)} tickers loaded")
    return tickers


def _norm_ticker(t):
    """Canonicalize a ticker for set membership: uppercase, strip . and -."""
    return (t or "").upper().replace(".", "").replace("-", "").strip()


# ── Finnhub Earnings Calendar ────────────────────────────────────────────────

def fetch_earnings(days_ahead=14, universe=None):
    """Fetch upcoming earnings from Finnhub for the next N days.

    If `universe` is a non-empty set, entries whose symbol is not in that set
    are dropped — used to cap the calendar at the Russell 3000 so small-cap
    earnings don't overwhelm the homepage card.

    Implementation note: Finnhub's calendar endpoint caps a multi-day response
    at ~1500 entries and serves later dates first when the cap is hit, silently
    dropping the earliest 1-2 days from the result. Workaround: query day by
    day so each request returns a complete single-day list.
    """
    print("[newsstand] Fetching earnings calendar (day-by-day)...")
    today = datetime.now(timezone.utc).date()

    url = "https://finnhub.io/api/v1/calendar/earnings"

    raw_total = 0
    notable = []
    dropped_universe = 0
    dropped_reported = 0
    fetch_failures = 0

    for offset in range(days_ahead + 1):
        day = (today + timedelta(days=offset)).isoformat()
        try:
            r = requests.get(url, params={
                "from": day, "to": day, "token": FINNHUB_KEY,
            }, timeout=15)
            r.raise_for_status()
            day_raw = r.json().get("earningsCalendar", [])
        except Exception as e:
            fetch_failures += 1
            print(f"[newsstand] Earnings fetch failed for {day}: {e}")
            continue

        raw_total += len(day_raw)
        for e in day_raw:
            # Require an EPS estimate (filters out analyst-less micro-caps)
            if e.get("epsEstimate") is None:
                continue
            # Skip entries that have already reported (epsActual filled in).
            # Today's pre-market names accumulate actuals after ~9am ET, so
            # the scan picks them up as "already happened" not "upcoming".
            if e.get("epsActual") is not None:
                dropped_reported += 1
                continue
            symbol = (e.get("symbol") or "").upper().strip()
            # Russell 3000 filter (skip if caller didn't supply a universe).
            # Normalize both sides: iShares IWV uses "BRKB", Finnhub uses "BRK.B".
            if universe and _norm_ticker(symbol) not in universe:
                dropped_universe += 1
                continue
            notable.append({
                "date":             e.get("date"),
                "symbol":           symbol,
                "eps_estimate":     e.get("epsEstimate"),
                "eps_actual":       e.get("epsActual"),
                "revenue_estimate": e.get("revenueEstimate"),
                "revenue_actual":   e.get("revenueActual"),
                "hour":             e.get("hour", ""),  # bmo = before market open, amc = after market close
                "quarter":          e.get("quarter"),
                "year":             e.get("year"),
            })

        # Stay well under Finnhub's free-tier 60 req/min limit
        time.sleep(0.2)

    print(f"[newsstand] Earnings: scanned {days_ahead + 1} days, "
          f"{raw_total} raw entries from Finnhub, {fetch_failures} day(s) failed")
    if universe:
        print(f"[newsstand] Earnings: dropped {dropped_universe} outside Russell 3000, "
              f"{dropped_reported} already reported")

    # Group by date so we can spread coverage across days instead of letting
    # a single heavy day (50+ reports) eat the whole 50-entry cap.
    PER_DAY_CAP   = 8
    DAYS_TO_SHOW  = 7   # first 7 calendar days that actually have entries

    by_date = {}
    for x in notable:
        by_date.setdefault(x["date"], []).append(x)

    # Within each day, surface larger companies first (revenue estimate desc),
    # then alphabetical. Larger companies tend to be the recognizable names
    # users want to see — keeps obscure micro-caps off the top of each day.
    for date_key in by_date:
        by_date[date_key].sort(
            key=lambda x: (-(x.get("revenue_estimate") or 0), x["symbol"])
        )
        by_date[date_key] = by_date[date_key][:PER_DAY_CAP]

    notable = []
    for date_key in sorted(by_date.keys())[:DAYS_TO_SHOW]:
        notable.extend(by_date[date_key])

    print(f"[newsstand] Earnings: {len(notable)} notable entries across "
          f"{min(len(by_date), DAYS_TO_SHOW)} days")
    return notable


# ── Polygon.io Market News ───────────────────────────────────────────────────

def fetch_news(limit=15, retries=3):
    """Fetch latest market news from Polygon.io with retry logic."""
    print("[newsstand] Fetching market news...")
    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
        "apiKey": POLYGON_KEY,
    }

    results = []
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                wait = 15 * attempt
                print(f"[newsstand] Polygon rate-limited (429), waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            print(f"[newsstand] News: {len(results)} articles from Polygon.io")
            break
        except Exception as e:
            print(f"[newsstand] News fetch attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(5 * attempt)

    if not results:
        print("[newsstand] News: falling back to Finnhub general news")
        results = _fetch_news_finnhub(limit)

    articles = []
    for a in results:
        # Normalize — Polygon and Finnhub have different field names
        tickers = a.get("tickers") or a.get("related", "").split(",") if a.get("related") else []
        tickers = [t.strip() for t in tickers if t.strip()][:5]
        publisher = a.get("publisher", {})
        source = publisher.get("name", "") if isinstance(publisher, dict) else (a.get("source", "") or str(publisher))
        articles.append({
            "title":     a.get("title") or a.get("headline", ""),
            "url":       a.get("article_url") or a.get("url", ""),
            "source":    source,
            "published": a.get("published_utc") or a.get("datetime", ""),
            "tickers":   tickers,
            "snippet":   (a.get("description") or a.get("summary", "") or "")[:200],
        })

    return articles


def _fetch_news_finnhub(limit=15):
    """Fallback: fetch general news from Finnhub."""
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": FINNHUB_KEY}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        items = r.json()
        print(f"[newsstand] Finnhub fallback: {len(items)} articles")
        return items[:limit]
    except Exception as e:
        print(f"[newsstand] Finnhub news fallback also failed: {e}")
        return []


# ── Finviz Unusual Volume ────────────────────────────────────────────────────

MIN_UNUSUAL_VOLUME_PRICE = 7.00  # Filter out penny stocks ($7 floor)


def fetch_unusual_volume(limit=10):
    """Scrape Finviz unusual volume screener. Positive movers only.
    Filters out stocks priced under MIN_UNUSUAL_VOLUME_PRICE to avoid penny-stock noise."""
    print("[newsstand] Fetching unusual volume...")
    # f=sh_price_o5  → pre-filter at Finviz to price > $5 so we don't burn
    # the 20-row budget on penny stocks. Python post-filter below raises to $7.
    url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&o=-volume&f=sh_price_o5"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[newsstand] Finviz fetch failed: {e}")
        return []

    tickers = []

    # Finviz screener table: find the main results table
    # The data rows are in a table with class "screener_table" or similar
    table = soup.find("table", class_="screener_table")
    if not table:
        # Fallback: try finding by ID or broader search
        tables = soup.find_all("table")
        for t in tables:
            if t.find("td", class_="screener-body-table-nw"):
                table = t
                break

    if not table:
        print("[newsstand] Finviz: could not find screener table")
        return []

    rows = table.find_all("tr")[1:]  # Skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        ticker_cell = cells[1]
        ticker_link = ticker_cell.find("a")
        ticker = ticker_link.text.strip() if ticker_link else ""

        name_cell = cells[2]
        name_link = name_cell.find("a")
        name = name_link.text.strip() if name_link else ""

        # Price is in column index 8 (0-based), change in 9
        try:
            price_text = cells[8].text.strip().replace(",", "")
            price = float(price_text) if price_text else None
        except (ValueError, IndexError):
            price = None

        try:
            change_text = cells[9].text.strip().replace("%", "")
            change_pct = float(change_text) if change_text else None
        except (ValueError, IndexError):
            change_pct = None

        # Volume in column 6
        volume_text = cells[6].text.strip() if len(cells) > 6 else ""

        if (ticker
                and change_pct is not None and change_pct > 0
                and price is not None and price >= MIN_UNUSUAL_VOLUME_PRICE):
            tickers.append({
                "ticker":     ticker,
                "name":       name,
                "price":      price,
                "change_pct": change_pct,
                "volume":     volume_text,
            })
            if len(tickers) >= limit:
                break

    print(f"[newsstand] Unusual volume: {len(tickers)} positive tickers "
          f"(price >= ${MIN_UNUSUAL_VOLUME_PRICE:.2f})")
    return tickers


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    start = datetime.now(timezone.utc)
    print(f"[newsstand] Starting scan at {start.isoformat()}")

    universe = fetch_russell3000_universe()
    earnings = fetch_earnings(days_ahead=14, universe=universe)

    # Respect Polygon rate limit (5 calls/min on free tier)
    time.sleep(1)
    news = fetch_news(limit=15)

    time.sleep(1)
    unusual_volume = fetch_unusual_volume(limit=15)

    output = {
        "scan_time":       start.isoformat(),
        "next_scan_info":  NEXT_SCAN_INFO,
        "earnings":        earnings,
        "news":            news,
        "unusual_volume":  unusual_volume,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[newsstand] Done in {elapsed}s — "
          f"{len(earnings)} earnings, {len(news)} news, {len(unusual_volume)} volume")
    print(f"[newsstand] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
