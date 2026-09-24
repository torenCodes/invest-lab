"""
Capitol Flow — what members of Congress are actually trading.

Built from the House Clerk's own filings, which are free and authoritative:

  1. https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.ZIP
     A per-year index of every financial disclosure. FilingType "P" marks a
     Periodic Transaction Report, which is the one that lists actual trades.
  2. https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{YEAR}/{DocID}.pdf
     The filing itself. Nearly all are machine-readable, so pypdf can extract
     the table without OCR.

READ THIS BEFORE TRUSTING THE NUMBERS.

*Disclosure is slow.* The STOCK Act allows 30 to 45 days between a trade and
its disclosure, so this is not a timing signal and nothing here should be read
as "buy what they bought". By the time a filing appears the move has usually
happened. Its value is thematic: which sectors and names are accumulating
attention among people with unusual visibility into policy. The scan reports
the median disclosure lag on every run so the staleness is stated, not hidden.

*Amounts are ranges, not figures.* Members disclose a band such as
"$1,001 - $15,000". Aggregates here use the midpoint of the band, which is an
estimate and nothing more. A member trading at the top of a band and one at the
bottom look identical in this data.

*The Senate is not included.* Its disclosure portal sits behind a session
agreement rather than a bulk download, so this covers the House only.

Output: InsiderBuying/data/capitol_flow.json (read same-origin by the
Politician tab on the Insider Buying dashboard).
Run: python Website/scripts/capitol_flow_scan.py [--years 1] [--limit N]
"""

import argparse
import collections
import io
import json
import os
import re
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Website/
OUTPUT_FILE = os.path.join(BASE_DIR, "InsiderBuying", "data", "capitol_flow.json")
# Parsed filings are kept OUT of the published payload. Every PTR ever parsed
# would push the browser download past half a megabyte, and none of it is
# needed to render the tab — it exists so CI never re-fetches a filing.
CACHE_FILE  = os.path.join(BASE_DIR, "data", "capitol_cache.json")

UA = {"User-Agent": "TheInvestLab Research toren5@gmail.com"}
INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.ZIP"
PTR_URL   = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"

# The asset line carries the ticker and an instrument tag; the transaction line
# that follows carries the code, both dates and the disclosed band. They are
# separate lines, so transactions are paired to the nearest ticker ABOVE them.
ASSET_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})\)\s*\[(ST|OP|CS|EF|OT|MF|CT)\]")
TXN_RE   = re.compile(r"\b([PSE])\s*(?:\(partial\))?\s*"
                      r"(\d{2}/\d{2}/\d{4})\s*(\d{2}/\d{2}/\d{4})\s*"
                      r"\$([\d,]+)\s*-\s*\$([\d,]+)")

ASSET_LABEL = {"ST": "Stock", "OP": "Options", "CS": "Corporate bond", "EF": "ETF",
               "MF": "Fund", "CT": "Corporate", "OT": "Other"}
CODE_LABEL  = {"P": "Purchase", "S": "Sale", "E": "Exchange"}

RECENT_TXNS = 120   # how many individual trades to publish for the feed


def fetch(url, timeout=90):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def load_index(year):
    """Every Periodic Transaction Report filed in `year`."""
    try:
        raw = fetch(INDEX_URL.format(year=year))
    except Exception as e:
        print(f"[capitol] {year} index unavailable: {e}")
        return []
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in z.namelist() if n.lower().endswith(".txt")), None)
    if not name:
        return []
    lines = z.read(name).decode("utf-8-sig", "replace").splitlines()
    out = []
    for line in lines[1:]:
        p = line.split("\t")
        if len(p) < 9 or p[4].strip() != "P":
            continue
        out.append({
            "doc":    p[8].strip(),
            "member": " ".join(x for x in (p[2].strip(), p[1].strip()) if x),
            "state":  p[5].strip(),
            "filed":  p[7].strip(),
            "year":   year,
        })
    print(f"[capitol] {year}: {len(out)} periodic transaction reports")
    return out


def parse_ptr(text):
    """Pair each transaction with the ticker that precedes it in the document."""
    events = []
    for m in ASSET_RE.finditer(text):
        events.append((m.start(), "A", m.group(1), m.group(2)))
    for m in TXN_RE.finditer(text):
        events.append((m.start(), "T", m.groups(), None))
    events.sort(key=lambda e: e[0])

    rows, ticker, kind = [], None, None
    for _, typ, a, b in events:
        if typ == "A":
            ticker, kind = a, b
            continue
        if not ticker:
            continue          # a transaction with no tickered asset above it
        code, td, nd, lo, hi = a
        try:
            lo_v, hi_v = int(lo.replace(",", "")), int(hi.replace(",", ""))
        except ValueError:
            continue
        rows.append({
            "ticker":     ticker,
            "asset_type": kind,
            "code":       code,
            "trade_date": td,
            "notify_date": nd,
            "amount_low":  lo_v,
            "amount_high": hi_v,
            # Members disclose a band, so every aggregate below is an estimate
            "amount_mid":  (lo_v + hi_v) // 2,
        })
    return rows


def _iso(us_date):
    try:
        m, d, y = us_date.split("/")
        return f"{y}-{m}-{d}"
    except ValueError:
        return None


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return {t["doc"]: t for t in json.load(f).get("docs", [])}
        except Exception:
            pass
    return {}


def save_cache(parsed):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(),
                   "docs": list(parsed.values())}, f, separators=(",", ":"))


def run(years=1, limit=None):
    start = datetime.now(timezone.utc)
    this_year = date.today().year
    filings = []
    for y in range(this_year, this_year - years, -1):
        filings.extend(load_index(y))
    if not filings:
        print("[capitol] No filings found — aborting")
        return

    cache = load_cache()
    todo = [f for f in filings if f["doc"] not in cache]
    if limit:
        todo = todo[:limit]
    print(f"[capitol] {len(cache)} already parsed, {len(todo)} to fetch")

    try:
        from pypdf import PdfReader
    except ImportError:
        print("[capitol] pypdf not installed (pip install pypdf)")
        return

    parsed = dict(cache)
    failures = 0
    for i, f in enumerate(todo, 1):
        url = PTR_URL.format(year=f["year"], doc=f["doc"])
        try:
            raw = fetch(url, timeout=60)
            text = "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
            rows = parse_ptr(text)
        except Exception as e:
            failures += 1
            if failures <= 5:
                print(f"[capitol]   {f['doc']} failed: {str(e)[:60]}")
            rows = []
        parsed[f["doc"]] = {**f, "txns": rows}
        if i % 40 == 0:
            print(f"[capitol]   {i}/{len(todo)} filings...")
        time.sleep(0.25)          # be polite to house.gov

    # ── Flatten ──
    txns = []
    lags = []
    for doc in parsed.values():
        for t in doc.get("txns", []):
            td, nd = _iso(t["trade_date"]), _iso(t["notify_date"])
            if not td:
                continue
            if td and nd:
                try:
                    lags.append((datetime.fromisoformat(nd) - datetime.fromisoformat(td)).days)
                except ValueError:
                    pass
            txns.append({**t, "trade_date": td, "notify_date": nd,
                         "member": doc["member"], "state": doc["state"], "doc": doc["doc"]})

    txns.sort(key=lambda t: t["trade_date"], reverse=True)
    scanned = sum(1 for d in parsed.values() if d.get("txns"))
    print(f"[capitol] {len(txns)} transactions from {scanned} filings with tickered assets")

    # ── Aggregates over the last 90 days of TRADE dates ──
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    recent = [t for t in txns if t["trade_date"] >= cutoff]

    def agg(code):
        by = collections.defaultdict(lambda: {"n": 0, "amount": 0, "members": set()})
        for t in recent:
            if t["code"] != code:
                continue
            g = by[t["ticker"]]
            g["n"] += 1
            g["amount"] += t["amount_mid"]
            g["members"].add(t["member"])
        rows = [{"ticker": k, "trades": v["n"], "est_amount": v["amount"],
                 "members": len(v["members"]), "member_names": sorted(v["members"])[:6]}
                for k, v in by.items()]
        rows.sort(key=lambda r: (r["members"], r["est_amount"]), reverse=True)
        return rows[:25]

    top_bought, top_sold = agg("P"), agg("S")

    member_activity = collections.Counter(t["member"] for t in recent)
    by_type = collections.Counter(ASSET_LABEL.get(t["asset_type"], t["asset_type"]) for t in recent)

    median_lag = sorted(lags)[len(lags) // 2] if lags else None

    out = {
        "scan_time":     start.isoformat(),
        "source":        "US House Clerk (Periodic Transaction Reports)",
        "filings_total": len(parsed),
        "filings_with_trades": scanned,
        "transactions":  len(txns),
        "window_days":   90,
        "median_disclosure_lag_days": median_lag,
        "caveats": {
            "lag": "The STOCK Act allows 30-45 days between a trade and its "
                   "disclosure, so this is a thematic read rather than a timing signal.",
            "amounts": "Members disclose a range, not a figure. Totals use the "
                       "midpoint of each band and are estimates only.",
            "coverage": "House of Representatives only. The Senate portal has no "
                        "bulk download.",
        },
        "top_bought":    top_bought,
        "top_sold":      top_sold,
        "most_active":   [{"member": m, "trades": n} for m, n in member_activity.most_common(12)],
        "asset_mix":     [{"type": k, "trades": v} for k, v in by_type.most_common()],
        "recent":        txns[:RECENT_TXNS],
    }
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=1, allow_nan=False)
    save_cache(parsed)

    print()
    print(f"[capitol] median disclosure lag: {median_lag} days")
    print(f"[capitol] most-bought (last 90d): " +
          ", ".join(f"{r['ticker']}({r['members']})" for r in top_bought[:8]))
    print(f"[capitol] Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="House congressional trading scan")
    ap.add_argument("--years", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None, help="cap filings fetched this run")
    a = ap.parse_args()
    run(a.years, a.limit)
