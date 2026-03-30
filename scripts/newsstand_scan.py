"""
Newsstand Scanner — Standalone
Fetches market context data (earnings calendar, news, unusual volume)
and writes to MarketDashboard/data/newsstand.json for the homepage.

Invoked by GitHub Actions on schedule.
Run locally: python scripts/newsstand_scan.py
"""

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

NEXT_SCAN_INFO = "Weekdays at 9:00am ET"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


# ── Finnhub Earnings Calendar ────────────────────────────────────────────────

def fetch_earnings(days_ahead=14):
    """Fetch upcoming earnings from Finnhub for the next N days."""
    print("[newsstand] Fetching earnings calendar...")
    today = datetime.now(timezone.utc).date()
    from_date = today.isoformat()
    to_date = (today + timedelta(days=days_ahead)).isoformat()

    url = "https://finnhub.io/api/v1/calendar/earnings"
    params = {
        "from": from_date,
        "to": to_date,
        "token": FINNHUB_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        raw = data.get("earningsCalendar", [])
        print(f"[newsstand] Earnings: {len(raw)} total entries from Finnhub")
    except Exception as e:
        print(f"[newsstand] Earnings fetch failed: {e}")
        return []

    # Filter to notable stocks: require an EPS estimate (filters out micro-caps)
    # and sort by date, then by symbol
    notable = []
    for e in raw:
        if e.get("epsEstimate") is None:
            continue
        notable.append({
            "date":             e.get("date"),
            "symbol":           e.get("symbol", ""),
            "eps_estimate":     e.get("epsEstimate"),
            "eps_actual":       e.get("epsActual"),
            "revenue_estimate": e.get("revenueEstimate"),
            "revenue_actual":   e.get("revenueActual"),
            "hour":             e.get("hour", ""),  # bmo = before market open, amc = after market close
            "quarter":          e.get("quarter"),
            "year":             e.get("year"),
        })

    # Sort by date, then symbol
    notable.sort(key=lambda x: (x["date"] or "", x["symbol"]))

    # Cap at 50 to keep the JSON reasonable
    notable = notable[:50]
    print(f"[newsstand] Earnings: {len(notable)} notable entries after filtering")
    return notable


# ── Polygon.io Market News ───────────────────────────────────────────────────

def fetch_news(limit=15):
    """Fetch latest market news from Polygon.io."""
    print("[newsstand] Fetching market news...")
    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
        "apiKey": POLYGON_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        print(f"[newsstand] News: {len(results)} articles from Polygon.io")
    except Exception as e:
        print(f"[newsstand] News fetch failed: {e}")
        return []

    articles = []
    for a in results:
        tickers = a.get("tickers", [])
        publisher = a.get("publisher", {})
        articles.append({
            "title":     a.get("title", ""),
            "url":       a.get("article_url", ""),
            "source":    publisher.get("name", "") if isinstance(publisher, dict) else str(publisher),
            "published": a.get("published_utc", ""),
            "tickers":   tickers[:5],  # Cap ticker list
            "snippet":   (a.get("description", "") or "")[:200],
        })

    return articles


# ── Finviz Unusual Volume ────────────────────────────────────────────────────

def fetch_unusual_volume(limit=15):
    """Scrape Finviz unusual volume screener."""
    print("[newsstand] Fetching unusual volume...")
    url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&o=-volume"

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
    for row in rows[:limit]:
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

        if ticker:
            tickers.append({
                "ticker":     ticker,
                "name":       name,
                "price":      price,
                "change_pct": change_pct,
                "volume":     volume_text,
            })

    print(f"[newsstand] Unusual volume: {len(tickers)} tickers")
    return tickers


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    start = datetime.now(timezone.utc)
    print(f"[newsstand] Starting scan at {start.isoformat()}")

    earnings = fetch_earnings(days_ahead=14)

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
