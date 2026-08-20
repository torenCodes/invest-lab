"""
Insider Pulse — a market-wide read on what corporate insiders are doing.

The question this answers: "how healthy does the market look based on how much
buying executives are doing?" Insiders sell constantly because they are paid in
equity, so the raw buy/sell ratio is always low and means little on its own.
What carries information is BREADTH — the share of companies with insider
activity where that activity was buying — measured against its own history.

    breadth = companies with >=1 open-market BUY
              ---------------------------------------------------
              companies with a BUY  +  companies with a SELL

WHY BREADTH AND NOT DOLLARS (learned the hard way):
A dollar-weighted ratio is one fat-finger away from nonsense. In Q4 2025 a
single filer reported 15,000,000 shares at a price of $15,000,000 PER SHARE,
having put the total value in the price field. That one typo produced $225
trillion and accounted for 69% of the entire quarter's purchase value. Counting
companies is immune to price errors, so breadth is the headline metric and
dollars are only ever reported as a capped, secondary figure.

DATA SOURCES
  History : SEC quarterly "Form 345" structured datasets — every Form 3/4/5 as
            TSV, authoritative and free. Published a quarter in arrears.
  Current : OpenInsider's screener, because the SEC bulk files lag by months and
            a market-regime gauge has to be current. Same metric definition on
            both sides, and the overlap is compared so any source bias is
            visible rather than silent.

Output: MarketDashboard/data/insider_pulse.json (+ a committed history file so
CI never re-downloads five years of archives).
Run: python Website/scripts/insider_pulse_scan.py [--backfill N_QUARTERS]
"""

import argparse
import collections
import csv
import io
import json
import os
import re
import statistics
import time
import urllib.request
import zipfile
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Website/
OUTPUT_FILE  = os.path.join(BASE_DIR, "MarketDashboard", "data", "insider_pulse.json")
HISTORY_FILE = os.path.join(BASE_DIR, "data", "insider_history.json")
CACHE_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".insider_cache")

# SEC requires a descriptive User-Agent with contact info on every request.
SEC_UA  = {"User-Agent": "TheInvestLab Research toren5@gmail.com"}
SEC_ZIP = ("https://www.sec.gov/files/structureddata/data/"
           "insider-transactions-data-sets/{q}_form345.zip")

OI_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
OI_URL = ("http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd={days}&fdr=&td=0&tdr="
          "&fdlyl=&fdlyh=&daysago=&x{side}=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999"
          "&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=5000&page=1")

WINDOW_DAYS   = 30        # trailing window for one breadth reading
SAMPLE_EVERY  = 7         # history is sampled weekly — ~260 points over 5 years
MAX_PX        = 100_000   # a per-share price above this is a filing error
MAX_TXN_VALUE = 50_000_000  # cap any single transaction before summing dollars

MONTHS = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}

TOP_TITLES = ("CEO", "CHIEF EXECUTIVE", "CFO", "CHIEF FINANCIAL",
              "PRESIDENT", "CHAIRMAN", "COO", "CHIEF OPERATING")


# ── Helpers ───────────────────────────────────────────────────────────────────

def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def percentile_rank(series, value):
    """Percentile 0-100 of `value` within `series`."""
    if not series:
        return None
    arr = sorted(series)
    return round(min(100.0, 100.0 * bisect_left(arr, value) / len(arr)), 1)


def parse_sec_date(s):
    """SEC bulk dates look like '29-DEC-2025'."""
    p = (s or "").strip().split("-")
    if len(p) != 3 or p[1].upper() not in MONTHS:
        return None
    try:
        return date(int(p[2]), MONTHS[p[1].upper()], int(p[0]))
    except ValueError:
        return None


def recent_quarters(n):
    """The n most recent completed quarters, newest first, as '2025q4' strings."""
    today = date.today()
    q = (today.month - 1) // 3 + 1
    y = today.year
    out = []
    for _ in range(n + 1):
        q -= 1
        if q == 0:
            q, y = 4, y - 1
        out.append("%dq%d" % (y, q))
    return out[:n]


def is_top_officer(titles):
    t = (titles or "").upper()
    return any(k in t for k in TOP_TITLES)


# ── SEC bulk history ──────────────────────────────────────────────────────────

def fetch_quarter(qtr):
    """Download (and cache) one quarterly Form 345 archive. Returns bytes|None."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "%s_form345.zip" % qtr)
    if os.path.exists(path) and os.path.getsize(path) > 100_000:
        return open(path, "rb").read()
    url = SEC_ZIP.format(q=qtr)
    try:
        req = urllib.request.Request(url, headers=SEC_UA)
        data = urllib.request.urlopen(req, timeout=120).read()
    except Exception as e:
        print("[insider] %s unavailable (%s)" % (qtr, e))
        return None
    if len(data) < 100_000:
        print("[insider] %s looks empty, skipping" % qtr)
        return None
    with open(path, "wb") as f:
        f.write(data)
    time.sleep(0.4)   # stay well inside SEC's rate limit
    return data


def transactions_from_zip(raw):
    """Yield (trade_date, ticker, code, value, is_top_officer) from one archive."""
    z = zipfile.ZipFile(io.BytesIO(raw))

    def rows(name):
        with z.open(name) as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                                    delimiter="\t"):
                yield r

    issuer = {}
    for r in rows("SUBMISSION.tsv"):
        sym = (r.get("ISSUERTRADINGSYMBOL") or "").strip().upper()
        if sym and sym not in ("NONE", "N/A"):
            issuer[r["ACCESSION_NUMBER"]] = sym

    titles = collections.defaultdict(list)
    for r in rows("REPORTINGOWNER.tsv"):
        titles[r["ACCESSION_NUMBER"]].append(
            (r.get("RPTOWNER_TITLE") or "") + " " + (r.get("RPTOWNER_RELATIONSHIP") or ""))

    for r in rows("NONDERIV_TRANS.tsv"):
        code = (r.get("TRANS_CODE") or "").strip().upper()
        if code not in ("P", "S"):          # only discretionary open-market trades
            continue
        acc = r["ACCESSION_NUMBER"]
        sym = issuer.get(acc)
        if not sym:
            continue
        d = parse_sec_date(r.get("TRANS_DATE"))
        if not d:
            continue
        try:
            shares = float(r.get("TRANS_SHARES") or 0)
            price  = float(r.get("TRANS_PRICEPERSHARE") or 0)
        except ValueError:
            continue
        if shares <= 0 or price <= 0 or price > MAX_PX:
            continue                         # the fat-finger gate
        yield d, sym, code, min(shares * price, MAX_TXN_VALUE), is_top_officer(" ".join(titles.get(acc, [])))


def build_history(n_quarters):
    """Assemble the weekly trailing-30-day breadth series from SEC archives."""
    print("[insider] Backfilling %d quarters of SEC Form 345 data..." % n_quarters)
    txns = []
    for qtr in recent_quarters(n_quarters):
        raw = fetch_quarter(qtr)
        if not raw:
            continue
        n = 0
        for t in transactions_from_zip(raw):
            txns.append(t)
            n += 1
        print("[insider]   %s -> %d open-market transactions" % (qtr, n))

    if not txns:
        return []

    # Date sanity. Filings routinely carry stray trade dates far outside their
    # own quarter (this run saw one dated 2002), which would otherwise stretch
    # the series back two decades over a mostly empty range.
    today  = date.today()
    oldest = today - timedelta(days=int(366 * (n_quarters / 4.0 + 0.5)))
    before = len(txns)
    txns = [t for t in txns if oldest <= t[0] <= today]
    if before != len(txns):
        print("[insider] Dropped %d transactions dated outside %s..%s"
              % (before - len(txns), oldest, today))

    txns.sort(key=lambda t: t[0])
    dates = [t[0] for t in txns]
    start, end = dates[0] + timedelta(days=WINDOW_DAYS), dates[-1]
    print("[insider] Transactions span %s -> %s (%d rows)" % (dates[0], end, len(txns)))

    series, cur = [], start
    while cur <= end:
        lo = bisect_left(dates, cur - timedelta(days=WINDOW_DAYS))
        hi = bisect_left(dates, cur)
        window = txns[lo:hi]
        pt = window_breadth(window, cur)
        if pt:
            series.append(pt)
        cur += timedelta(days=SAMPLE_EVERY)

    # Coverage gate. Each quarterly archive holds filings FILED in that quarter,
    # so windows at the very start of the oldest quarter (and the very end of the
    # newest) see only late filings — a small, unrepresentative subset. Those
    # thin windows produced the highest breadth readings in the whole series
    # purely as an artifact: 64 companies versus a normal 1,500. Drop anything
    # covering less than half the typical company count, self-calibrating so the
    # threshold keeps working as filing volumes drift.
    if series:
        coverage = [p["buy_cos"] + p["sell_cos"] for p in series]
        floor = statistics.median(coverage) * 0.5
        kept = [p for p in series if (p["buy_cos"] + p["sell_cos"]) >= floor]
        if len(kept) != len(series):
            print("[insider] Dropped %d thin windows below %.0f companies (artifact of "
                  "partial quarter coverage)" % (len(series) - len(kept), floor))
        series = kept

    print("[insider] Built %d weekly history points" % len(series))
    return series


def window_breadth(window, as_of):
    """One breadth reading from a list of (date, sym, code, value, is_top)."""
    buy_cos, sell_cos, top_cos = set(), set(), set()
    buy_val = sell_val = 0.0
    n_buy = n_sell = 0
    for _, sym, code, val, top in window:
        if code == "P":
            buy_cos.add(sym); buy_val += val; n_buy += 1
            if top:
                top_cos.add(sym)
        else:
            sell_cos.add(sym); sell_val += val; n_sell += 1
    total_cos = len(buy_cos) + len(sell_cos)
    if total_cos < 40:            # too thin to mean anything
        return None
    return {
        "date":        as_of.isoformat(),
        "breadth":     round(len(buy_cos) / total_cos, 4),
        "buy_cos":     len(buy_cos),
        "sell_cos":    len(sell_cos),
        "top_buy_cos": len(top_cos),
        "n_buy":       n_buy,
        "n_sell":      n_sell,
        "buy_val":     round(buy_val),
        "sell_val":    round(sell_val),
    }


# ── OpenInsider: the current window ───────────────────────────────────────────

# The ticker cell wraps the symbol in a JS tooltip whose payload contains both
# '<' and '>', so stripping tags leaves garbage. The href carries the clean
# symbol — the same lesson the Finviz scrapers taught: read the attribute.
_TICKER_RE = re.compile(r'href="/([A-Z][A-Z0-9.\-]{0,6})"')


def _cell_text(html):
    return re.sub(r"<[^>]+>", "", html).replace("\xa0", " ").strip()


def fetch_openinsider(side, days=WINDOW_DAYS):
    """side 'p' = purchases, 's' = sales. Returns [(ticker, title, value)]."""
    url = OI_URL.format(days=days, side=side)
    html = None
    for attempt in range(4):          # the host rate-limits bursts; back off and retry
        try:
            req = urllib.request.Request(url, headers=OI_UA)
            html = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
            break
        except Exception as e:
            wait = 5 * (attempt + 1)
            print("[insider] OpenInsider %s attempt %d failed (%s) — retrying in %ds"
                  % (side, attempt + 1, str(e)[:60], wait))
            time.sleep(wait)
    if not html:
        print("[insider] OpenInsider %s unavailable after retries" % side)
        return []

    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 13:
            continue
        m = _TICKER_RE.search(cells[3])
        if not m:
            continue
        tk = m.group(1).upper()
        title = _cell_text(cells[6])
        val   = _cell_text(cells[12]).replace("$", "").replace(",", "").replace("+", "")
        try:
            value = abs(float(val))
        except ValueError:
            value = 0.0
        out.append((tk, title, min(value, MAX_TXN_VALUE)))
    print("[insider] OpenInsider %s: %d rows" % ("purchases" if side == "p" else "sales", len(out)))
    return out


def current_window():
    buys  = fetch_openinsider("p")
    sells = fetch_openinsider("s")
    if not buys or not sells:
        return None
    buy_cos  = {t for t, _, _ in buys}
    sell_cos = {t for t, _, _ in sells}
    top_cos  = {t for t, ti, _ in buys if is_top_officer(ti)}
    total    = len(buy_cos) + len(sell_cos)
    if total < 40:
        return None
    return {
        "date":        date.today().isoformat(),
        "breadth":     round(len(buy_cos) / total, 4),
        "buy_cos":     len(buy_cos),
        "sell_cos":    len(sell_cos),
        "top_buy_cos": len(top_cos),
        "n_buy":       len(buys),
        "n_sell":      len(sells),
        "buy_val":     round(sum(v for _, _, v in buys)),
        "sell_val":    round(sum(v for _, _, v in sells)),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                d = json.load(f)
            return d.get("series", []), d.get("quarters", 0)
        except Exception:
            pass
    return [], 0


def save_history(series, quarters):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump({"built": datetime.now(timezone.utc).isoformat(),
                   "quarters": quarters,
                   "window_days": WINDOW_DAYS,
                   "series": series}, f, indent=1)
    print("[insider] Wrote %d history points to %s" % (len(series), HISTORY_FILE))


def label_for(score):
    if score is None:      return "Unknown"
    if score < 20:         return "Heavy selling"
    if score < 40:         return "Net selling"
    if score < 60:         return "Typical"
    if score < 80:         return "Accumulating"
    return "Heavy buying"


def run(backfill_quarters=20, force=False):
    series, have = load_history()
    if force or len(series) < 30 or have < backfill_quarters:
        series = build_history(backfill_quarters)
        if series:
            save_history(series, backfill_quarters)
    else:
        print("[insider] Reusing %d cached history points (%d quarters)" % (len(series), have))

    cur = current_window()
    if not cur:
        print("[insider] No current reading available — aborting")
        return

    hist_breadth = [p["breadth"] for p in series]
    pct = percentile_rank(hist_breadth, cur["breadth"])
    top_hist = [p["top_buy_cos"] for p in series]
    top_pct  = percentile_rank(top_hist, cur["top_buy_cos"])

    # Source-bias check: the history is SEC, the current point is OpenInsider.
    # Report the historical spread so a reader can see whether today's reading
    # sits inside the normal range rather than trusting the percentile blindly.
    med = statistics.median(hist_breadth) if hist_breadth else None

    out = {
        "scan_time":       datetime.now(timezone.utc).isoformat(),
        "window_days":     WINDOW_DAYS,
        "current":         cur,
        "percentile":      pct,
        "top_percentile":  top_pct,
        "label":           label_for(pct),
        "history_points":  len(series),
        "history_median":  round(med, 4) if med is not None else None,
        "history_min":     round(min(hist_breadth), 4) if hist_breadth else None,
        "history_max":     round(max(hist_breadth), 4) if hist_breadth else None,
        "sources": {
            "history": "SEC Form 345 quarterly datasets",
            "current": "OpenInsider screener (SEC bulk lags ~1 quarter)",
            "note":    "Breadth counts companies, not dollars, so a single "
                       "mis-keyed filing cannot distort it.",
        },
        "series": series[-120:],   # ~2 years of weekly points for the sparkline
    }
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2, allow_nan=False)

    print()
    print("[insider] breadth %.3f  (%d buying / %d selling companies)"
          % (cur["breadth"], cur["buy_cos"], cur["sell_cos"]))
    print("[insider] percentile %s -> %s   | history median %.3f, range %.3f-%.3f"
          % (pct, label_for(pct), med, min(hist_breadth), max(hist_breadth)))
    print("[insider] top-officer buying at %d companies (percentile %s)"
          % (cur["top_buy_cos"], top_pct))
    print("[insider] Wrote %s" % OUTPUT_FILE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Market-wide insider breadth gauge")
    ap.add_argument("--backfill", type=int, default=20, help="quarters of history (default 20 = 5yr)")
    ap.add_argument("--force", action="store_true", help="rebuild history even if cached")
    a = ap.parse_args()
    run(a.backfill, a.force)
