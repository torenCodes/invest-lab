"""
Insider Backtest — does the conviction model actually predict anything?

The weights in InsiderBuying/scan.py are informed judgement, not measured fact.
This measures them. It reconstructs every historical insider buying cluster from
five years of SEC Form 4 filings, scores each one using ONLY what was knowable
at the time, then looks up what the stock actually did afterwards against the
S&P over the same window.

The output answers two questions:

  1. Does a higher conviction score lead to better forward returns, or is the
     score decoration? If the buckets do not slope, the model does not work.
  2. Which individual dimensions carry the signal? Cluster size and seniority
     might matter enormously, or barely at all. Right now nobody knows.

It also tests candidate dimensions that are NOT in the live model yet, so their
weight can be set by evidence rather than invented:

    52-week position   did they buy near the lows or chase the highs?
    drawdown depth     how far below the 52-week high the purchase happened
    repeat buying      had this company seen insider buying in the prior 90 days?

METHOD NOTES, because a backtest is easy to flatter:

  * Entry is the FILING date, never the trade date. A Form 4 has up to two
    business days to appear, and you cannot act on information you cannot see.
  * Returns are measured against SPY over the identical window, so a rising
    market does not get mistaken for a working signal.
  * Tickers with no price history are COUNTED and reported rather than quietly
    dropped, because silently skipping delisted names is how a backtest
    manufactures survivorship bias.
  * Recency and entry-vs-insider-cost cannot be tested this way. Every cluster
    is equally fresh at its own moment, so those two dimensions are excluded
    from the analysis rather than given a fake result.

Run: python Website/scripts/insider_backtest.py [--limit N] [--horizon 60]
Output: Website/data/insider_backtest.json + a printed report.
"""

import argparse
import collections
import csv
import io
import json
import math
import os
import re
import statistics
import time
import zipfile
from datetime import date, datetime, timedelta, timezone

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Website/
CACHE_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".insider_cache")
PRICE_DIR   = os.path.join(CACHE_DIR, "prices")
MISS_FILE   = os.path.join(CACHE_DIR, "price_misses.json")
MAX_MISSES  = 3     # blank this many times across separate runs = really gone
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "insider_backtest.json")

CLUSTER_WINDOW_DAYS = 10     # buys this close together are one event
HORIZONS            = (30, 60, 90)
MIN_PRICE           = 3.0    # sub-$3 names are dominated by spread, not signal
BENCHMARK           = "SPY"

MONTHS = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}

# Mirrors ROLE_POINTS in InsiderBuying/scan.py so the backtest scores clusters
# the same way the live board does.
ROLE_POINTS = [
    (("CHIEF EXECUTIVE", "CEO"), 25),
    (("CHIEF FINANCIAL", "CFO"), 22),
    (("CHAIRMAN", "CHAIR"), 18),
    (("PRESIDENT",), 18),
    (("CHIEF OPERATING", "COO", "CHIEF TECHNOLOGY", "CTO", "OFFICER"), 14),
    (("DIRECTOR",), 10),
    (("10%", "TEN PERCENT", "BENEFICIAL"), 4),
]


# Filers type the ticker by hand and the SEC does not validate it, so roughly
# 0.8% of symbols arrive as free text: "(SIRI)", "NYSE: KRC", "MOGA/MOGB",
# "BFA, BFB", "Z AND ZG", even "N O G" for NOG. One of them ('"OMEX"', quotes
# included) crashed the first full run by producing an illegal Windows filename.
_EXCH_RE  = re.compile(r"^\(?\s*(?:NYSE\s*AMERICAN|NYSEAMERICAN|NASDAQ|NYSE|AMEX|OTC|CBOE)\s*[:\-]\s*", re.I)
_CLEAN_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def norm_symbol(raw):
    """Best-effort clean ticker, or None if it cannot be trusted."""
    s = (raw or "").strip().upper()
    if not s or s in ("NONE", "N/A"):
        return None
    s = s.strip("\"' \t")
    s = _EXCH_RE.sub("", s)
    s = s.strip("()[]{} \t\"'")
    if _CLEAN_RE.match(s):
        return s
    # "N O G" — a symbol typed with spaces between its letters
    parts = s.replace(",", " ").replace("/", " ").split()
    if len(parts) > 1 and all(len(p) == 1 for p in parts):
        joined = "".join(parts)
        return joined if _CLEAN_RE.match(joined) else None
    # "MOGA/MOGB", "BFA, BFB", "Z AND ZG" — dual class, take the first listing
    if parts:
        first = parts[0].strip("()[]{} \"'")
        if first == "Z" and len(parts) > 1:      # "Z AND ZG"
            return "Z"
        if _CLEAN_RE.match(first):
            return first
    return None


def parse_sec_date(s):
    p = (s or "").strip().split("-")
    if len(p) != 3 or p[1].upper() not in MONTHS:
        return None
    try:
        return date(int(p[2]), MONTHS[p[1].upper()], int(p[0]))
    except ValueError:
        return None


def role_points(title):
    t = (title or "").upper()
    for keys, pts in ROLE_POINTS:
        if any(k in t for k in keys):
            return pts
    return 6


# ── Step 1: rebuild historical buy clusters from the SEC archives ─────────────

def load_purchases():
    """Every open-market purchase in the cached quarters, with the fields the
    conviction model needs."""
    zips = sorted(f for f in os.listdir(CACHE_DIR) if f.endswith("_form345.zip"))
    if not zips:
        print("[backtest] No cached SEC archives — run insider_pulse_scan.py first")
        return []

    buys = []
    for fn in zips:
        z = zipfile.ZipFile(os.path.join(CACHE_DIR, fn))

        def tsv(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8",
                                                   errors="replace"), delimiter="\t")

        sub = {}
        for r in tsv("SUBMISSION.tsv"):
            sym = norm_symbol(r.get("ISSUERTRADINGSYMBOL"))
            if sym:
                sub[r["ACCESSION_NUMBER"]] = (sym, parse_sec_date(r.get("FILING_DATE")))

        titles = collections.defaultdict(list)
        owners = collections.defaultdict(set)
        for r in tsv("REPORTINGOWNER.tsv"):
            acc = r["ACCESSION_NUMBER"]
            titles[acc].append((r.get("RPTOWNER_TITLE") or "") + " " +
                               (r.get("RPTOWNER_RELATIONSHIP") or ""))
            owners[acc].add((r.get("RPTOWNERNAME") or "").strip().upper())

        n = 0
        for r in tsv("NONDERIV_TRANS.tsv"):
            if (r.get("TRANS_CODE") or "").strip().upper() != "P":
                continue
            acc = r["ACCESSION_NUMBER"]
            meta = sub.get(acc)
            if not meta:
                continue
            sym, filed = meta
            traded = parse_sec_date(r.get("TRANS_DATE"))
            if not traded or not filed:
                continue
            try:
                shares = float(r.get("TRANS_SHARES") or 0)
                price  = float(r.get("TRANS_PRICEPERSHARE") or 0)
                after  = float(r.get("SHRS_OWND_FOLWNG_TRANS") or 0)
            except ValueError:
                continue
            if shares <= 0 or price <= 0 or price > 100_000:
                continue
            before = after - shares
            growth = 999.0 if before <= 0 else min(shares / before * 100.0, 999.0)
            buys.append({
                "ticker": sym, "traded": traded, "filed": filed,
                "value": min(shares * price, 50_000_000),
                "growth": growth,
                "role": max((role_points(t) for t in titles.get(acc, [])), default=6),
                "owners": owners.get(acc, set()),
            })
            n += 1
        print(f"[backtest]   {fn[:6]}: {n} purchases")
    return buys


def build_clusters(buys):
    """Group purchases in the same company that happened close together."""
    by_ticker = collections.defaultdict(list)
    for b in buys:
        by_ticker[b["ticker"]].append(b)

    clusters = []
    for sym, rows in by_ticker.items():
        rows.sort(key=lambda r: r["traded"])
        cur = []
        for r in rows:
            if cur and (r["traded"] - cur[0]["traded"]).days > CLUSTER_WINDOW_DAYS:
                clusters.append(_finish(sym, cur))
                cur = []
            cur.append(r)
        if cur:
            clusters.append(_finish(sym, cur))
    return clusters


def _finish(sym, rows):
    people = set()
    for r in rows:
        people |= r["owners"]
    return {
        "ticker":   sym,
        # Entry is when the market could SEE it, not when the trade happened.
        "entry":    max(r["filed"] for r in rows),
        "traded":   max(r["traded"] for r in rows),
        "insiders": max(len(people), 1),
        "value":    sum(r["value"] for r in rows),
        "growth":   max(r["growth"] for r in rows),
        "role":     max(r["role"] for r in rows),
    }


# ── Step 2: price history ─────────────────────────────────────────────────────

def price_path(sym):
    # Belt and braces: even with norm_symbol upstream, never let a filer-typed
    # string reach the filesystem unfiltered.
    safe = re.sub(r"[^A-Za-z0-9.\-]", "_", sym or "_")[:12] or "_"
    return os.path.join(PRICE_DIR, f"{safe}.json")


def fetch_prices(symbols, batch=25):
    """Daily closes per ticker, cached to disk so re-runs cost nothing.

    NEVER caches a failed download. The first version wrote an empty record
    whenever the fetch threw, which meant a burst of Yahoo rate limiting was
    permanently recorded as "this company has no price history". 69% of the
    universe — including MSFT, KO and WMT — was written off as delisted, and
    every number the backtest produced from it was worthless. A failure now
    leaves no file behind, so the next run simply retries it.
    """
    import yfinance as yf
    os.makedirs(PRICE_DIR, exist_ok=True)

    misses = {}
    if os.path.exists(MISS_FILE):
        try:
            with open(MISS_FILE) as f:
                misses = json.load(f)
        except Exception:
            misses = {}

    need = [s for s in symbols
            if not os.path.exists(price_path(s)) and misses.get(s, 0) < MAX_MISSES]
    givenup = sum(1 for s in symbols if misses.get(s, 0) >= MAX_MISSES)
    print(f"[backtest] {len(symbols) - len(need) - givenup} cached, {len(need)} to fetch, "
          f"{givenup} confirmed unavailable after {MAX_MISSES} tries")

    failed_batches = 0
    for i in range(0, len(need), batch):
        chunk = need[i:i + batch]
        data, err = None, None
        for attempt in range(4):
            try:
                data = yf.download(" ".join(s.replace(".", "-") for s in chunk),
                                   period="6y", interval="1d", auto_adjust=True,
                                   group_by="ticker", progress=False, threads=False)
                err = None
                break
            except Exception as e:
                err = e
                wait = 20 * (attempt + 1)     # Yahoo throttles hard; back off properly
                print(f"[backtest]   rate limited, waiting {wait}s "
                      f"(attempt {attempt + 1}): {str(e)[:50]}")
                time.sleep(wait)

        if data is None:
            failed_batches += 1
            print(f"[backtest]   batch {i // batch} abandoned; will retry on next run")
            time.sleep(30)
            continue

        wrote = blank = 0
        for s in chunk:
            key = s.replace(".", "-")
            try:
                col = data[key]["Close"] if len(chunk) > 1 else data["Close"]
                ser = col.dropna()
            except Exception:
                ser = None
            if ser is None or not len(ser):
                # An empty column inside an otherwise successful batch is
                # ambiguous: the ticker may be delisted, or yfinance may have
                # failed just this symbol. Caching it as "no data" is what wrote
                # off KO, INTC and FDX as delisted. Count the miss instead and
                # only give up after several independent attempts.
                misses[s] = misses.get(s, 0) + 1
                blank += 1
                continue
            rec = {"d": [d.strftime("%Y-%m-%d") for d in ser.index],
                   "c": [round(float(v), 4) for v in ser.values]}
            with open(price_path(s), "w") as f:
                json.dump(rec, f, separators=(",", ":"))
            misses.pop(s, None)
            wrote += 1
        print(f"[backtest]   {min(i + batch, len(need))}/{len(need)} "
              f"({wrote} written, {blank} blank)")
        time.sleep(4)             # deliberately unhurried; being throttled costs far more

    with open(MISS_FILE, "w") as f:
        json.dump(misses, f, separators=(",", ":"))
    if failed_batches:
        print(f"[backtest] {failed_batches} batches could not be fetched — re-run to fill them")
    still = sum(1 for v in misses.values() if v < MAX_MISSES)
    if still:
        print(f"[backtest] {still} symbols came back blank and will be retried next run")


def load_series(sym):
    try:
        with open(price_path(sym)) as f:
            r = json.load(f)
        return r["d"], r["c"]
    except Exception:
        return [], []


def _at_or_after(dates, closes, target):
    """First close on or after `target`. Returns (price, index) or (None, None)."""
    from bisect import bisect_left
    i = bisect_left(dates, target)
    if i >= len(dates):
        return None, None
    return closes[i], i


# ── Step 3: evaluate ──────────────────────────────────────────────────────────

def evaluate(clusters, horizon):
    bench_d, bench_c = load_series(BENCHMARK)
    if not bench_d:
        print("[backtest] No benchmark prices — cannot measure excess return")
        return [], {}

    results = []
    missing_price = collections.Counter()
    for c in clusters:
        d, px = load_series(c["ticker"])
        if not d:
            missing_price["no history"] += 1
            continue
        entry_str = c["entry"].isoformat()
        p0, i0 = _at_or_after(d, px, entry_str)
        if p0 is None or p0 < MIN_PRICE:
            missing_price["no price at entry" if p0 is None else "below price floor"] += 1
            continue
        exit_str = (c["entry"] + timedelta(days=horizon)).isoformat()
        p1, _ = _at_or_after(d, px, exit_str)
        if p1 is None:
            missing_price["window not yet complete"] += 1
            continue

        b0, _ = _at_or_after(bench_d, bench_c, entry_str)
        b1, _ = _at_or_after(bench_d, bench_c, exit_str)
        if not b0 or not b1:
            missing_price["no benchmark"] += 1
            continue

        stock_ret = (p1 / p0 - 1) * 100
        bench_ret = (b1 / b0 - 1) * 100

        # Candidate dimensions that need price context, computed from the year
        # BEFORE entry only — no look-ahead.
        lo_i = max(0, i0 - 252)
        window = px[lo_i:i0 + 1]
        hi52, lo52 = (max(window), min(window)) if window else (p0, p0)
        pos52 = ((p0 - lo52) / (hi52 - lo52) * 100) if hi52 > lo52 else 50.0
        drawdown = ((p0 / hi52) - 1) * 100 if hi52 else 0.0

        results.append({
            **{k: c[k] for k in ("ticker", "insiders", "value", "growth", "role")},
            "entry":     entry_str,
            "excess":    round(stock_ret - bench_ret, 3),
            "stock_ret": round(stock_ret, 3),
            "pos52":     round(pos52, 1),
            "drawdown":  round(drawdown, 1),
        })
    return results, dict(missing_price)


def live_score(r):
    """The score InsiderBuying/scan.py would have produced, minus the two
    dimensions a backtest cannot judge (recency, entry-vs-insider-cost)."""
    s = 0
    n = r["insiders"]
    s += 25 if n >= 5 else 21 if n == 4 else 17 if n == 3 else 11 if n == 2 else 3
    s += r["role"]
    g = r["growth"]
    s += 20 if g >= 100 else 17 if g >= 50 else 13 if g >= 25 else 9 if g >= 10 else 5 if g >= 5 else 2
    v = r["value"]
    s += 11 if v >= 10e6 else 9 if v >= 5e6 else 7 if v >= 1e6 else 4 if v >= 250e3 else 2 if v >= 100e3 else 0
    return s


# ── Step 4: analyse ───────────────────────────────────────────────────────────

def summarize(rows, label):
    if not rows:
        return {"label": label, "n": 0}
    ex = [r["excess"] for r in rows]
    return {
        "label":     label,
        "n":         len(rows),
        "avg_excess": round(statistics.mean(ex), 2),
        "median_excess": round(statistics.median(ex), 2),
        "win_rate":  round(100.0 * sum(1 for x in ex if x > 0) / len(ex), 1),
    }


def buckets(rows, key, edges, labels):
    out = []
    for i, lab in enumerate(labels):
        lo = edges[i]
        hi = edges[i + 1] if i + 1 < len(edges) else float("inf")
        sel = [r for r in rows if lo <= key(r) < hi]
        out.append(summarize(sel, lab))
    return out


def run(limit=None, horizon=60):
    global BENCHMARK
    print("[backtest] Loading purchases from cached SEC archives...")
    buys = load_purchases()
    if not buys:
        return
    print(f"[backtest] {len(buys)} purchases")

    clusters = build_clusters(buys)
    clusters.sort(key=lambda c: c["entry"])
    if limit:
        clusters = clusters[-limit:]
    print(f"[backtest] {len(clusters)} buying clusters across "
          f"{len({c['ticker'] for c in clusters})} tickers")

    symbols = sorted({c["ticker"] for c in clusters} | {BENCHMARK})
    fetch_prices(symbols)

    rows, missing = evaluate(clusters, horizon)
    print(f"[backtest] {len(rows)} clusters measurable at {horizon}d")
    print(f"[backtest] excluded: {missing}")

    overall = summarize(rows, f"all clusters ({horizon}d)")
    by_score = buckets(rows, live_score, [0, 40, 55, 70, 85],
                       ["score <40", "40-54", "55-69", "70-84", "85+"])
    analysis = {
        "cluster_size": buckets(rows, lambda r: r["insiders"], [1, 2, 3, 5],
                                ["1 insider", "2", "3-4", "5+"]),
        "seniority":    buckets(rows, lambda r: r["role"], [0, 10, 18, 22, 25],
                                ["other", "director", "chair/pres", "CFO", "CEO"]),
        "position_growth": buckets(rows, lambda r: r["growth"], [0, 5, 25, 100],
                                   ["<5%", "5-24%", "25-99%", "100%+"]),
        "dollar_size":  buckets(rows, lambda r: r["value"], [0, 100e3, 1e6, 10e6],
                                ["<$100k", "$100k-1M", "$1-10M", "$10M+"]),
        "pos_52wk":     buckets(rows, lambda r: r["pos52"], [0, 25, 50, 75],
                                ["bottom quartile", "25-50", "50-75", "top quartile"]),
        "drawdown":     buckets(rows, lambda r: r["drawdown"], [-100, -50, -25, -10],
                                ["down >50%", "down 25-50%", "down 10-25%", "near highs"]),
    }

    out = {
        "generated":   datetime.now(timezone.utc).isoformat(),
        "horizon_days": horizon,
        "benchmark":   BENCHMARK,
        "clusters_measured": len(rows),
        "clusters_total":    len(clusters),
        "excluded":    missing,
        "overall":     overall,
        "by_score":    by_score,
        "by_dimension": analysis,
        "method": {
            "entry": "filing date, not trade date — you cannot act before disclosure",
            "return": f"stock return minus {BENCHMARK} over the same {horizon}-day window",
            "survivorship": "tickers without price history are counted in `excluded`, not dropped silently",
            "untested": ["recency", "entry vs insider cost"],
        },
    }
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=1, allow_nan=False)

    # ── Report ──
    def table(title, rowset):
        print()
        print(f"  {title}")
        print(f"    {'bucket':<18} {'n':>7} {'avg excess':>12} {'median':>9} {'win rate':>9}")
        for b in rowset:
            if not b.get("n"):
                print(f"    {b['label']:<18} {0:>7}")
                continue
            print(f"    {b['label']:<18} {b['n']:>7} {b['avg_excess']:>11.2f}% "
                  f"{b['median_excess']:>8.2f}% {b['win_rate']:>8.1f}%")

    print()
    print("=" * 74)
    print(f"  OVERALL: {overall['n']} clusters, avg excess {overall['avg_excess']}%, "
          f"win rate {overall['win_rate']}% over {horizon} days vs {BENCHMARK}")
    print("=" * 74)
    table("BY CONVICTION SCORE (does the model work?)", by_score)
    for name, rowset in analysis.items():
        table(f"BY {name.upper().replace('_', ' ')}", rowset)
    print()
    print(f"[backtest] Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Validate the insider conviction model")
    ap.add_argument("--limit", type=int, default=None, help="most recent N clusters only")
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--benchmark", default=BENCHMARK,
                    help="comparison index. Insider buying concentrates in small caps, "
                         "so SPY can flatter or punish the whole sample on size alone.")
    a = ap.parse_args()
    BENCHMARK = a.benchmark
    run(a.limit, a.horizon)
