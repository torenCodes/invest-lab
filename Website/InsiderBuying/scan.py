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
LOOKBACK_DAYS = 30

# Purchases only (xp=1). cnt must be large: the default page size truncates.
OPENINSIDER_URL = (
    "http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd={days}&fdr=&td=0&tdr="
    "&fdlyl=&fdlyh=&daysago=&xp=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0"
    "&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=5000&page=1")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

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

def _cell(html):
    """Strip tags from one table cell."""
    return re.sub(r"<[^>]+>", "", html).replace(" ", " ").strip()


def _money(s):
    """'+$86,500' -> 86500.0"""
    try:
        return abs(float(re.sub(r"[^0-9.\-]", "", s or "") or 0))
    except ValueError:
        return 0.0


def _pct_own(s):
    """OpenInsider's delta-own column: '+9%', '>999%', 'New'. Returns a float
    percent, treating a brand new position as the strongest possible signal."""
    t = (s or "").strip()
    if not t:
        return None
    if "new" in t.lower():
        return 999.0
    try:
        return abs(float(re.sub(r"[^0-9.\-]", "", t) or 0))
    except ValueError:
        return None


def fetch_transactions():
    """Open-market insider PURCHASES from OpenInsider's screener.

    Replaced the Finviz scrape in Aug 2026. Both ultimately serve SEC Form 4
    data, but this source carries two fields Finviz does not, and they are the
    ones that separate a token purchase from real conviction:

        Owned  - shares the insider holds after the trade
        <Own   - how much that trade INCREASED their position

    A director adding $50k to a $10m stake is noise. A CFO increasing their
    holding by 80% is a statement, and only the second column can tell them
    apart. The ticker is read from the link href rather than the cell text,
    because the cell wraps a JS tooltip whose payload contains angle brackets
    and defeats tag-stripping (the same trap that had Finviz reporting AATMU
    for ATMU).
    """
    url = OPENINSIDER_URL.format(days=LOOKBACK_DAYS)
    html = None
    for attempt in range(4):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=90)
            if resp.status_code == 200:
                html = resp.text
                break
            print(f"[OpenInsider] HTTP {resp.status_code} (attempt {attempt + 1})")
        except Exception as e:
            print(f"[OpenInsider] attempt {attempt + 1} failed: {str(e)[:70]}")
        time.sleep(5 * (attempt + 1))

    if not html:
        print("[OpenInsider] No data after retries")
        return []

    transactions = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 13:
            continue
        m = re.search(r'href="/([A-Z][A-Z0-9.\-]{0,6})"', cells[3])
        if not m:
            continue
        try:
            ticker  = m.group(1).upper()
            trade   = _cell(cells[2])                       # already ISO: 2026-08-18
            insider = _cell(cells[5])
            title   = _cell(cells[6])
            ttype   = _cell(cells[7])
            if not ttype.upper().startswith("P"):           # purchases only
                continue
            price = _money(_cell(cells[8]))
            qty   = int(_money(_cell(cells[9])))
            owned = int(_money(_cell(cells[10])))
            value = _money(_cell(cells[12]))
            if value < MIN_VALUE or price <= 0:
                continue
            transactions.append({
                "ticker":     ticker,
                "company":    _cell(cells[4]),
                "insider":    insider,
                "title":      title,
                "date":       trade,
                "price":      price,
                "qty":        qty,
                "owned":      owned,
                "delta_own":  _pct_own(_cell(cells[11])),
                "value":      value,
                "filing":     _cell(cells[1])[:10],
                "is_csuite":  is_csuite(title),
            })
        except Exception:
            continue

    if not transactions:
        print("[OpenInsider] Parsed 0 transactions - the markup may have changed")
    else:
        print(f"[OpenInsider] {len(transactions)} purchases >= ${MIN_VALUE:,} "
              f"over {LOOKBACK_DAYS} days")
    return transactions


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
                "owned":     base.get("owned"),
                "delta_own": max((t.get("delta_own") or 0) for t in sub["txns"]) or None,
            })
        insiders.sort(key=lambda x: x["value"], reverse=True)
        top = insiders[0]
        enr = enrichment.get(ticker, {})

        # Volume-weighted price the insiders actually paid, and where the stock
        # trades against it. Buying below their cost is a genuinely useful edge:
        # the people with the best information paid MORE than you would today.
        spent  = sum(t["value"] for t in g["txns"])
        shares = sum(t["qty"] for t in g["txns"]) or 0
        avg_cost = round(spent / shares, 2) if shares else None
        cur = enr.get("current_price") or 0
        vs_insider = round((cur - avg_cost) / avg_cost * 100, 1) if (avg_cost and cur) else None
        # The source's own company name, used when yfinance returns nothing usable
        # (its fallback is the bare ticker, which reads as a broken card).
        fv_name = next((t.get("company") for t in g["txns"] if t.get("company")), "")

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
            "company":        (enr.get("name") if enr.get("name") and enr.get("name") != ticker
                               else (fv_name or ticker)),
            "sector":         enr.get("sector", "Unknown"),
            "current_price":  enr.get("current_price", 0),
            "change_pct":     enr.get("change_pct", 0),
            "market_cap":     enr.get("market_cap", 0),
            "insider_avg_cost": avg_cost,
            "vs_insider_pct":   vs_insider,
            "max_delta_own":    max((i.get("delta_own") or 0) for i in insiders) or None,
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


# Role hierarchy. A CEO putting their own money in is the strongest single
# voice; a 10% holder is often a fund rebalancing and says little about the
# business, so it earns almost nothing here.
ROLE_POINTS = [
    (("CHIEF EXECUTIVE", "CEO"),                       25, "CEO"),
    (("CHIEF FINANCIAL", "CFO"),                       22, "CFO"),
    (("CHAIRMAN", "CHAIR"),                            18, "Chairman"),
    (("PRESIDENT",),                                   18, "President"),
    (("CHIEF OPERATING", "COO", "CHIEF TECHNOLOGY",
      "CTO", "CHIEF MEDICAL", "CHIEF SCIENTIFIC",
      "CHIEF BANKING", "CHIEF ACCOUNTING", "OFFICER"), 14, "Officer"),
    (("DIRECTOR",),                                    10, "Director"),
    (("10%", "TEN PERCENT", "BENEFICIAL"),              4, "10% owner"),
]


def _role_points(title):
    t = (title or "").upper()
    for keys, pts, label in ROLE_POINTS:
        if any(k in t for k in keys):
            return pts, label
    return 6, "Insider"


def _parse_trade_date(s):
    """OpenInsider supplies ISO dates. The old Finviz format is still accepted
    so a cached or hand-edited file does not break the scan."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%b %d '%y"):
        try:
            return datetime.strptime(s.strip()[:10] if fmt == "%Y-%m-%d" else s.strip(), fmt)
        except ValueError:
            continue
    return None


def _conviction_score(row, today=None):
    """Score a deduped ticker row 0-100 and return (score, signal tags).

    Six dimensions, weighted by how much each has historically distinguished
    an informative purchase from a routine one:

        cluster      25   several insiders acting together
        role         25   who bought, CEO down to 10% holder
        conviction   20   how much they grew their OWN position
        size         15   dollars, scaled against company size
        recency      10   how fresh the signal is
        entry         5   whether the stock is still near their price

    The position-growth dimension is the one the previous Finviz-based version
    could not see at all, and it is often the most telling: a director adding
    $50k to a $10m stake is noise next to a CFO lifting their holding by 80%.
    """
    today = today or datetime.now()
    signals = []
    score = 0.0

    # ── Cluster (25) ──
    n_ins = row["insider_count"]
    if   n_ins >= 5: score += 25; signals.append(f"{n_ins} insiders buying")
    elif n_ins == 4: score += 21; signals.append("4 insiders buying")
    elif n_ins == 3: score += 17; signals.append("3 insiders buying")
    elif n_ins == 2: score += 11; signals.append("2 insiders buying")
    else:            score += 3

    # ── Role quality (25), taking the most senior buyer ──
    best_pts, best_label, best_title = 0, "", ""
    for i in row["insiders"]:
        pts, label = _role_points(i.get("title"))
        if pts > best_pts:
            best_pts, best_label, best_title = pts, label, (i.get("title") or "")
    score += best_pts
    # Titles arrive already well-formed ("CEO", "CFO, Treasurer", "COB, CEO"),
    # so leave the casing alone — .title() turned CEO into "Ceo". Keep only the
    # primary role, since some insiders list four of them.
    primary = (best_title.split(",")[0].strip() if best_title else "")
    if best_pts >= 18:
        signals.append(f"{primary} bought" if primary else f"{best_label} bought")
    elif best_pts >= 10:
        signals.append(f"{best_label} bought")
    # Both of the top two seats buying is a distinct, stronger message
    titles_all = " ".join((i.get("title") or "") for i in row["insiders"]).upper()
    if any(k in titles_all for k in ("CEO", "CHIEF EXECUTIVE")) and        any(k in titles_all for k in ("CFO", "CHIEF FINANCIAL")):
        score += 4
        signals.append("CEO and CFO both buying")

    # ── Position growth (20) — the new dimension ──
    deltas = [i.get("delta_own") for i in row["insiders"] if i.get("delta_own") is not None]
    max_delta = max(deltas) if deltas else None
    if max_delta is not None:
        if   max_delta >= 100: score += 20; signals.append("Insider more than doubled their stake")
        elif max_delta >=  50: score += 17; signals.append(f"Position up {max_delta:.0f}%")
        elif max_delta >=  25: score += 13; signals.append(f"Position up {max_delta:.0f}%")
        elif max_delta >=  10: score += 9;  signals.append(f"Position up {max_delta:.0f}%")
        elif max_delta >=   5: score += 5
        else:                  score += 2

    # ── Size (15), judged against market cap where we know it ──
    v = row["value"]
    cap = row.get("market_cap") or 0
    if   v >= 10_000_000: score += 11; signals.append(f"${v/1e6:.1f}M total")
    elif v >=  5_000_000: score += 9;  signals.append(f"${v/1e6:.1f}M total")
    elif v >=  1_000_000: score += 7;  signals.append(f"${v/1e6:.1f}M total")
    elif v >=    250_000: score += 4;  signals.append(f"${v/1e3:.0f}K total")
    elif v >=    100_000: score += 2
    if cap > 0:
        # Relative to company size a modest cheque can still be a big statement
        rel = v / cap
        if   rel >= 0.01:  score += 4; signals.append("Large relative to market cap")
        elif rel >= 0.003: score += 2

    # ── Recency (10) ──
    dates = [_parse_trade_date(i.get("date")) for i in row["insiders"]]
    dates = [d for d in dates if d]
    if dates:
        age = (today - max(dates)).days
        if   age <= 2:  score += 10; signals.append("Bought in the last 2 days")
        elif age <= 5:  score += 8;  signals.append("Bought this week")
        elif age <= 10: score += 5
        elif age <= 20: score += 2

    # ── Entry advantage (5) — can you still buy near their price? ──
    vs = row.get("vs_insider_pct")
    if vs is not None:
        if   vs <= -5: score += 5; signals.append(f"Trading {abs(vs):.0f}% below insider cost")
        elif vs <= 0:  score += 4; signals.append("Still below insider cost")
        elif vs <= 8:  score += 2

    return round(min(score, 100.0), 1), signals


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
