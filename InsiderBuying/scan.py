"""
InsiderBuying -- Standalone Scanner
Scrapes Finviz insider trading page for recent open-market purchases >= $25k.
Groups results into cluster buys, C-suite buys, big money, and a recent feed.
Writes results to data/results.json.

Run locally: python scan.py
Invoked by GitHub Actions on schedule (weekdays, matches MarketDashboard cadence).
"""

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "results.json")
MIN_VALUE   = 25_000

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

C_SUITE_KEYWORDS = {
    "ceo", "cfo", "coo", "cto", "president", "chairman",
    "chief executive", "chief financial", "chief operating",
    "chief technology", "chief revenue", "chief strategy", "chief investment",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_int(s):
    """'$1,234,567' or '1,234,567' -> 1234567"""
    return int(re.sub(r"[^\d]", "", s or "0") or "0")


def parse_float(s):
    """'38.00' -> 38.0"""
    try:
        return float(re.sub(r"[^\d.]", "", s or "0"))
    except ValueError:
        return 0.0


def is_csuite(title):
    t = title.lower()
    return any(k in t for k in C_SUITE_KEYWORDS)


# ── Fetch transactions ────────────────────────────────────────────────────────

def fetch_transactions():
    """Scrape Finviz insider trading page and return list of purchase transactions."""
    url = (
        "https://finviz.com/insidertrading.ashx"
        "?or=-10&tv=25000&tc=1&o=-filedate&cnt=500"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[Finviz] HTTP {resp.status_code}")
            return []

        soup   = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")

        # Find the data table (has 'Ticker' as first header)
        data_table = None
        for t in tables:
            headers = [th.get_text(strip=True) for th in t.find_all(["th", "td"])[:3]]
            if headers and headers[0] == "Ticker":
                data_table = t
                break

        if not data_table:
            print("[Finviz] Data table not found")
            return []

        rows = data_table.find_all("tr")[1:]  # skip header row
        transactions = []

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 9:
                continue
            try:
                ticker   = cols[0].get_text(strip=True).upper()
                insider  = cols[1].get_text(strip=True)
                title    = cols[2].get_text(strip=True)
                date     = cols[3].get_text(strip=True)
                txn_type = cols[4].get_text(strip=True)
                price    = parse_float(cols[5].get_text(strip=True))
                qty      = parse_int(cols[6].get_text(strip=True))
                value    = parse_int(cols[7].get_text(strip=True))
                filing   = cols[9].get_text(strip=True) if len(cols) > 9 else ""

                # Only open-market purchases above minimum
                if txn_type.lower() not in ("buy", "purchase"):
                    continue
                if value < MIN_VALUE:
                    continue
                if not ticker or not insider:
                    continue

                transactions.append({
                    "ticker":    ticker,
                    "insider":   insider,
                    "title":     title,
                    "date":      date,
                    "price":     price,
                    "qty":       qty,
                    "value":     value,
                    "filing":    filing,
                    "is_csuite": is_csuite(title),
                })
            except Exception:
                continue

        print(f"[Finviz] {len(transactions)} purchase transactions (>= ${MIN_VALUE:,})")
        return transactions

    except Exception as e:
        print(f"[Finviz] Error: {e}")
        return []


# ── Enrich tickers ────────────────────────────────────────────────────────────

def enrich_tickers(tickers):
    """Fetch current price, change%, market cap, sector via yfinance."""
    import yfinance as yf

    enriched = {}
    batch_size = 20

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.Tickers(" ".join(batch))
            for ticker in batch:
                try:
                    info = data.tickers[ticker].info
                    change_pct = info.get("regularMarketChangePercent", 0) or 0
                    enriched[ticker] = {
                        "current_price": info.get("currentPrice") or info.get("regularMarketPrice") or 0,
                        "change_pct":    round(change_pct, 2),
                        "market_cap":    info.get("marketCap") or 0,
                        "sector":        info.get("sector") or "Unknown",
                        "industry":      info.get("industry") or "",
                        "name":          info.get("longName") or info.get("shortName") or ticker,
                    }
                except Exception:
                    enriched[ticker] = {
                        "current_price": 0, "change_pct": 0,
                        "market_cap": 0, "sector": "Unknown",
                        "industry": "", "name": ticker,
                    }
        except Exception as e:
            print(f"[yfinance] Batch error: {e}")
            for ticker in batch:
                enriched[ticker] = {
                    "current_price": 0, "change_pct": 0,
                    "market_cap": 0, "sector": "Unknown",
                    "industry": "", "name": ticker,
                }
        time.sleep(0.5)

    return enriched


# ── Build panels ──────────────────────────────────────────────────────────────

def build_cluster_buys(transactions, enrichment):
    """Stocks where 2+ distinct insiders bought. Ranked by insider count, then total value."""
    groups = defaultdict(list)
    for t in transactions:
        groups[t["ticker"]].append(t)

    clusters = []
    for ticker, txns in groups.items():
        distinct = len({t["insider"] for t in txns})
        if distinct < 2:
            continue

        total_value = sum(t["value"] for t in txns)
        enr = enrichment.get(ticker, {})

        clusters.append({
            "ticker":         ticker,
            "company":        enr.get("name", ticker),
            "sector":         enr.get("sector", "Unknown"),
            "industry":       enr.get("industry", ""),
            "current_price":  enr.get("current_price", 0),
            "change_pct":     enr.get("change_pct", 0),
            "market_cap":     enr.get("market_cap", 0),
            "insider_count":  distinct,
            "total_value":    total_value,
            "insiders": sorted(
                [{"name": t["insider"], "title": t["title"],
                  "value": t["value"], "price": t["price"],
                  "qty": t["qty"], "date": t["date"]}
                 for t in txns],
                key=lambda x: x["value"], reverse=True
            ),
        })

    clusters.sort(key=lambda x: (x["insider_count"], x["total_value"]), reverse=True)
    return clusters[:10]


def build_csuite_buys(transactions, enrichment):
    """Top C-suite purchases, deduplicated per person+ticker, ranked by total value."""
    # Merge multiple transactions by same insider at same ticker
    groups = defaultdict(lambda: {"value": 0, "qty": 0, "txns": []})
    for t in transactions:
        if not t["is_csuite"]:
            continue
        key = (t["ticker"], t["insider"])
        groups[key]["value"] += t["value"]
        groups[key]["qty"]   += t["qty"]
        groups[key]["txns"].append(t)

    merged = []
    for (ticker, insider), g in groups.items():
        base = g["txns"][0]
        enr  = enrichment.get(ticker, {})
        merged.append({
            "ticker":        ticker,
            "insider":       insider,
            "title":         base["title"],
            "date":          base["date"],
            "price":         base["price"],
            "qty":           g["qty"],
            "value":         g["value"],
            "txn_count":     len(g["txns"]),
            "is_csuite":     True,
            "company":       enr.get("name", ticker),
            "sector":        enr.get("sector", "Unknown"),
            "current_price": enr.get("current_price", 0),
            "change_pct":    enr.get("change_pct", 0),
            "market_cap":    enr.get("market_cap", 0),
        })

    merged.sort(key=lambda x: x["value"], reverse=True)
    return merged[:10]


def build_big_money(transactions, enrichment):
    """Top 10 purchases by dollar value, deduplicated per person+ticker."""
    groups = defaultdict(lambda: {"value": 0, "qty": 0, "txns": []})
    for t in transactions:
        key = (t["ticker"], t["insider"])
        groups[key]["value"] += t["value"]
        groups[key]["qty"]   += t["qty"]
        groups[key]["txns"].append(t)

    merged = []
    for (ticker, insider), g in groups.items():
        base = g["txns"][0]
        enr  = enrichment.get(ticker, {})
        merged.append({
            "ticker":        ticker,
            "insider":       insider,
            "title":         base["title"],
            "date":          base["date"],
            "price":         base["price"],
            "qty":           g["qty"],
            "value":         g["value"],
            "txn_count":     len(g["txns"]),
            "company":       enr.get("name", ticker),
            "sector":        enr.get("sector", "Unknown"),
            "current_price": enr.get("current_price", 0),
            "change_pct":    enr.get("change_pct", 0),
            "market_cap":    enr.get("market_cap", 0),
        })

    merged.sort(key=lambda x: x["value"], reverse=True)
    return merged[:10]


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("[scan.py] Starting insider buying scan...")
    start = datetime.now()

    transactions = fetch_transactions()
    if not transactions:
        print("[scan.py] No transactions fetched — aborting.")
        return

    unique_tickers = list({t["ticker"] for t in transactions})
    print(f"[scan.py] Enriching {len(unique_tickers)} unique tickers via yfinance...")
    enrichment = enrich_tickers(unique_tickers)

    cluster_buys = build_cluster_buys(transactions, enrichment)
    csuite_buys  = build_csuite_buys(transactions, enrichment)
    big_money    = build_big_money(transactions, enrichment)
    recent_feed  = transactions[:40]

    # Date range from data
    dates = [t["date"] for t in transactions if t.get("date")]
    date_range = f"{dates[-1]} – {dates[0]}" if dates else "Unknown"

    output = {
        "scan_time":          start.isoformat(),
        "total_transactions": len(transactions),
        "date_range":         date_range,
        "min_value":          MIN_VALUE,
        "cluster_buys":       cluster_buys,
        "csuite_buys":        csuite_buys,
        "big_money":          big_money,
        "recent_feed":        recent_feed,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now() - start).seconds
    print(f"[scan.py] Done in {elapsed}s — "
          f"{len(cluster_buys)} clusters, {len(csuite_buys)} C-suite, "
          f"{len(big_money)} big money, {len(recent_feed)} feed items")
    print(f"[scan.py] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
