"""
InsiderBuying -- Standalone Scanner
Scrapes Finviz insider trading page for recent open-market purchases >= $25k.
Builds a single ranked nominees list with conviction tier (A / B / Watch)
plus a 'standouts' top-3 callout. Writes results to data/results.json.

Conviction score combines four dimensions: distinct insider count, C-suite
presence, dollar volume tier, and recency. See build_nominees() below.

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

# Word-boundary regex — substring matching was incorrectly flagging titles
# like "Director" as C-suite because the substring "cto" appears in
# "director". \b ensures whole-word matches only.
_CSUITE_RE = re.compile(
    r"\b(ceo|cfo|coo|cto|president|chairman|"
    r"chief\s+(executive|financial|operating|technology|revenue|strategy|investment))\b",
    re.IGNORECASE,
)


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
    """True if the title is a true C-suite role (CEO, CFO, COO, CTO,
    President, Chairman, or any 'Chief X' role). Uses word boundaries to
    avoid the 'cto in director' substring trap."""
    return bool(_CSUITE_RE.search(title or ""))


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


# ── Build nominees ────────────────────────────────────────────────────────────
# Legacy three-panel builders (build_cluster_buys / build_csuite_buys /
# build_big_money) were removed once the unified conviction-tier nominees
# schema replaced them and all downstream consumers (archive_nominee.py,
# analyst_scan.py) migrated. The single `nominees` list now captures
# every angle (cluster size, C-suite presence, dollar volume, recency)
# in one ranked output.


def _roll_up_by_ticker(transactions, enrichment):
    """Helper — group transactions by ticker (not by ticker+insider), summing
    dollar value across every insider at that company. Each row carries an
    `insiders` list with the per-insider breakdown for the expanded view.
    The top-level `insider` / `title` / `date` / `price` fields surface the
    single largest buyer so cards still have one face to display."""
    groups = defaultdict(lambda: {"value": 0, "qty": 0, "txns": []})
    for t in transactions:
        groups[t["ticker"]]["value"] += t["value"]
        groups[t["ticker"]]["qty"]   += t["qty"]
        groups[t["ticker"]]["txns"].append(t)

    rows = []
    for ticker, g in groups.items():
        # Per-insider rollup within the ticker (one row per unique insider)
        per_insider = defaultdict(lambda: {"value": 0, "qty": 0, "txns": []})
        for t in g["txns"]:
            per_insider[t["insider"]]["value"] += t["value"]
            per_insider[t["insider"]]["qty"]   += t["qty"]
            per_insider[t["insider"]]["txns"].append(t)

        insiders = []
        for name, sub in per_insider.items():
            base = sub["txns"][0]
            insiders.append({
                "name":      name,
                "title":     base["title"],
                "date":      base["date"],
                "price":     base["price"],
                "qty":       sub["qty"],
                "value":     sub["value"],
                "is_csuite": base["is_csuite"],
            })
        insiders.sort(key=lambda x: x["value"], reverse=True)
        top = insiders[0]
        enr = enrichment.get(ticker, {})

        rows.append({
            "ticker":         ticker,
            "insider":        top["name"],
            "title":          top["title"],
            "date":           top["date"],
            "price":          top["price"],
            "qty":            g["qty"],
            "value":          g["value"],          # total across every insider at this ticker
            "txn_count":      len(g["txns"]),
            "insider_count":  len(insiders),
            "is_csuite":      any(i["is_csuite"] for i in insiders),
            "company":        enr.get("name", ticker),
            "sector":         enr.get("sector", "Unknown"),
            "current_price":  enr.get("current_price", 0),
            "change_pct":     enr.get("change_pct", 0),
            "market_cap":     enr.get("market_cap", 0),
            "insiders":       insiders,
        })
    return rows


# ── Phase B: conviction scoring + nominees ────────────────────────────────────
#
# Replaces the three separate panels (cluster / csuite / big money) — which
# always overlapped on top names — with one ranked list of unique tickers.
# Each nominee gets a conviction score combining insider count, C-suite
# presence, dollar volume, and recency. Tier A / B / Watch grades mirror the
# Pattern Scanner UX so users get one coherent leaderboard with a sidebar
# filter chip per tier.

TIER_A_CUTOFF = 50
TIER_B_CUTOFF = 25
TIER_W_CUTOFF = 10


def _parse_finviz_date(s):
    """'Apr 28 '26' or 'May 02 '26' -> datetime. Used for recency checks."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%b %d '%y")
    except ValueError:
        return None


def _conviction_score(row, today=None):
    """Score a deduped ticker row across four dimensions. Returns
    (score, list_of_signal_tags). Tunable; keep weights conservative so
    Tier A really means high-conviction (multi-dimensional)."""
    today = today or datetime.now()
    signals = []
    score   = 0

    # Distinct insiders — multi-insider buying is the strongest cluster signal
    n_ins = row["insider_count"]
    if   n_ins >= 5: score += 35; signals.append(f"{n_ins} insiders buying")
    elif n_ins == 4: score += 28; signals.append("4 insiders buying")
    elif n_ins == 3: score += 20; signals.append("3 insiders buying")
    elif n_ins == 2: score += 12; signals.append("2 insiders buying")
    # 1 insider = no cluster bonus (still in pool via other signals)

    # C-suite presence
    if row["is_csuite"]:
        # Identify the top C-suite buyer for the signal label
        top_csuite = next((i for i in row["insiders"] if i["is_csuite"]), None)
        if top_csuite:
            score += 15
            title = top_csuite["title"]
            signals.append(f"{title} bought")

    # Dollar volume tier
    v = row["value"]
    if   v >= 10_000_000: score += 30; signals.append(f"${v/1e6:.1f}M total")
    elif v >=  5_000_000: score += 22; signals.append(f"${v/1e6:.1f}M total")
    elif v >=  1_000_000: score += 15; signals.append(f"${v/1e6:.1f}M total")
    elif v >=    500_000: score += 10; signals.append(f"${v/1e3:.0f}K total")
    elif v >=    100_000: score +=  5; signals.append(f"${v/1e3:.0f}K total")

    # Recency — most-recent insider buy within last 3 days
    dates = [_parse_finviz_date(i["date"]) for i in row["insiders"]]
    dates = [d for d in dates if d]
    if dates:
        most_recent = max(dates)
        age_days = (today - most_recent).days
        if age_days <= 3:
            score += 5
            signals.append("Activity in last 3 days")

    return score, signals


def _build_story(row, signals):
    """One-sentence narrative for the Standouts callout. Reads naturally
    rather than as a list of badges. Falls back to the signal list if we
    don't have enough material for a full sentence."""
    ticker  = row["ticker"]
    n_ins   = row["insider_count"]
    has_cs  = row["is_csuite"]
    v       = row["value"]
    csuite_titles = [i["title"] for i in row["insiders"] if i["is_csuite"]]

    parts = []
    if n_ins >= 3:
        if csuite_titles:
            roles = " and ".join(sorted(set(csuite_titles[:2])))
            parts.append(f"Cluster of {n_ins} buyers including the {roles}")
        else:
            parts.append(f"Cluster of {n_ins} insiders")
    elif n_ins == 2:
        if csuite_titles:
            parts.append(f"Two insiders bought including the {csuite_titles[0]}")
        else:
            parts.append("Two insiders bought")
    else:
        # Single buyer
        i0 = row["insiders"][0]
        if has_cs:
            parts.append(f"The {i0['title']} bought")
        else:
            parts.append(f"{i0['name']} ({i0['title']}) bought")

    # Dollar magnitude
    if   v >= 1_000_000: parts.append(f"${v/1e6:.1f}M total")
    elif v >=   100_000: parts.append(f"${v/1e3:.0f}K total")

    return f"{ticker} — " + ", ".join(parts) + "."


def build_nominees(transactions, enrichment):
    """Single ranked list of unique tickers with conviction tier (A/B/Watch),
    plus a 'standouts' top-3 for the homepage callout, plus tier_counts for
    sidebar badges."""
    rows = _roll_up_by_ticker(transactions, enrichment)

    today = datetime.now()
    scored = []
    for r in rows:
        score, signals = _conviction_score(r, today=today)
        if score < TIER_W_CUTOFF:
            continue
        if   score >= TIER_A_CUTOFF: tier = "A"
        elif score >= TIER_B_CUTOFF: tier = "B"
        else:                         tier = "W"
        r["conviction_score"] = score
        r["tier"]              = tier
        r["signals"]           = signals
        r["story"]             = _build_story(r, signals)
        scored.append(r)

    scored.sort(key=lambda x: x["conviction_score"], reverse=True)

    standouts = scored[:3]
    tier_counts = {
        "A":     sum(1 for r in scored if r["tier"] == "A"),
        "B":     sum(1 for r in scored if r["tier"] == "B"),
        "W":     sum(1 for r in scored if r["tier"] == "W"),
        "total": len(scored),
    }
    return scored, standouts, tier_counts


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

    nominees, standouts, tier_counts = build_nominees(transactions, enrichment)
    recent_feed = transactions[:40]

    # Date range from data
    dates = [t["date"] for t in transactions if t.get("date")]
    date_range = f"{dates[-1]} – {dates[0]}" if dates else "Unknown"

    output = {
        "scan_time":          start.isoformat(),
        "total_transactions": len(transactions),
        "date_range":         date_range,
        "min_value":          MIN_VALUE,
        "nominees":           nominees,
        "standouts":          standouts,
        "tier_counts":        tier_counts,
        "recent_feed":        recent_feed,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now() - start).seconds
    print(f"[scan.py] Done in {elapsed}s — "
          f"{tier_counts['total']} nominees ({tier_counts['A']}A / {tier_counts['B']}B / {tier_counts['W']}W), "
          f"{len(recent_feed)} feed items")
    print(f"[scan.py] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
