import os, json, math, time, threading, socket
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import yfinance as yf

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
app          = Flask(__name__)
RESULTS_FILE = os.path.join(BASE_DIR, "results.json")

PRESCAN_TICKERS = ["AAPL", "MSFT", "NVDA"]

# SEC EDGAR requires a descriptive User-Agent per their access policy
SEC_HEADERS = {"User-Agent": "TheInvestLab personal-research@example.com"}

POLYGON_API_KEY = os.environ.get("POLYGON_KEY", "P9fRbZP9VAKhjwABMtvcS7tfcYGU6z1T")

# Approximate sector-median trailing P/E benchmarks
SECTOR_PE = {
    "Technology":             28,
    "Healthcare":             22,
    "Financial Services":     14,
    "Consumer Cyclical":      22,
    "Consumer Defensive":     20,
    "Energy":                 12,
    "Industrials":            20,
    "Basic Materials":        16,
    "Real Estate":            30,
    "Utilities":              18,
    "Communication Services": 20,
}

_lock  = threading.Lock()
_state = {
    "prescan":        {},      # ticker → result dict
    "prescan_status": "idle",  # idle | scanning | done
}

# ── Result cache ───────────────────────────────────────────────────────────────
_cache     = {}    # ticker → (result_dict, timestamp)
_CACHE_TTL = 300   # seconds (5 min)


# ── SEC EDGAR helpers ──────────────────────────────────────────────────────────

def get_cik(ticker):
    """Return zero-padded CIK string for a ticker, or None."""
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=10)
        for entry in r.json().values():
            if entry["ticker"] == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        pass
    return None


def get_sec_filings(cik):
    """Return most-recent 10-K and 10-Q filing date + accession from SEC."""
    result = {"10-K": None, "10-Q": None}
    if not cik:
        return result
    try:
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=SEC_HEADERS, timeout=10
        )
        recent = r.json().get("filings", {}).get("recent", {})
        forms  = recent.get("form", [])
        dates  = recent.get("filingDate", [])
        accs   = recent.get("accessionNumber", [])
        for i, form in enumerate(forms):
            if form == "10-K"  and result["10-K"]  is None:
                result["10-K"]  = {"date": dates[i], "accession": accs[i]}
            if form == "10-Q"  and result["10-Q"]  is None:
                result["10-Q"]  = {"date": dates[i], "accession": accs[i]}
            if result["10-K"] and result["10-Q"]:
                break
    except Exception:
        pass
    return result


# ── Valuation scoring & commentary ────────────────────────────────────────────

def compute_verdict(info, price, graham):
    """
    Score the stock from -100 (very overpriced) to +100 (very undervalued).
    Returns (verdict_label, score, commentary_string).
    """
    sector      = info.get("sector", "Unknown")
    ticker      = info.get("symbol", "")
    company     = info.get("longName") or info.get("shortName", ticker)
    pe_trail    = info.get("trailingPE")
    pe_fwd      = info.get("forwardPE")
    peg         = info.get("pegRatio")
    rev_growth  = info.get("revenueGrowth")
    earn_growth = info.get("earningsGrowth")
    net_margin  = info.get("profitMargins")
    roe         = info.get("returnOnEquity")
    debt_eq     = info.get("debtToEquity")
    eps_trail   = info.get("trailingEps")
    fcf         = info.get("freeCashflow")        # absolute $ — can be negative
    mkt_cap     = info.get("marketCap")
    revenue     = info.get("totalRevenue")

    sector_pe  = SECTOR_PE.get(sector, 20)
    pe         = pe_fwd or pe_trail
    score      = 0
    signals    = []   # bullish observations
    cautions   = []   # bearish observations

    # ── P/E vs sector
    if pe:
        if   pe < sector_pe * 0.70:
            score += 25
            signals.append(
                f"Forward P/E of {pe:.1f}x is well below the {sector} sector median "
                f"(~{sector_pe}x), pricing in limited growth expectations"
            )
        elif pe < sector_pe:
            score += 10
            signals.append(
                f"P/E of {pe:.1f}x sits below the {sector} sector median (~{sector_pe}x)"
            )
        elif pe > sector_pe * 1.80:
            score -= 25
            cautions.append(
                f"P/E of {pe:.1f}x represents a steep premium to the {sector} sector "
                f"(~{sector_pe}x) — significant growth must materialise to justify the multiple"
            )
        elif pe > sector_pe * 1.25:
            score -= 12
            cautions.append(
                f"P/E of {pe:.1f}x carries a meaningful premium to the {sector} sector "
                f"(~{sector_pe}x)"
            )

    # ── PEG ratio
    if peg:
        if   peg < 1.0:
            score += 20
            signals.append(
                f"PEG ratio of {peg:.2f} is below 1.0 — growth may be underpriced "
                f"relative to the earnings trajectory"
            )
        elif peg < 1.5:
            score += 8
        elif peg > 2.5:
            score -= 15
            cautions.append(
                f"PEG of {peg:.2f} signals the market is pricing in very optimistic "
                f"future growth"
            )

    # ── Revenue growth
    if rev_growth is not None:
        if   rev_growth > 0.20:
            score += 15
            signals.append(
                f"Revenue expanding at {rev_growth*100:.1f}% YoY — robust top-line momentum"
            )
        elif rev_growth > 0.08:
            score += 8
            signals.append(f"Revenue growth of {rev_growth*100:.1f}% YoY is healthy")
        elif rev_growth < 0:
            score -= 15
            cautions.append(
                f"Revenue declined {abs(rev_growth)*100:.1f}% YoY — top-line contraction "
                f"demands explanation"
            )
        elif rev_growth < 0.03:
            score -= 5
            cautions.append(
                f"Revenue growth of {rev_growth*100:.1f}% YoY is below inflation — "
                f"organic growth is stalling"
            )

    # ── Net margin
    if net_margin is not None:
        if   net_margin > 0.20:
            score += 10
            signals.append(
                f"Net margin of {net_margin*100:.1f}% reflects exceptional pricing power "
                f"and operational leverage"
            )
        elif net_margin > 0.10:
            score += 5
        elif net_margin < 0:
            score -= 20
            cautions.append(
                f"Negative net margin ({net_margin*100:.1f}%) — the company is currently "
                f"burning cash at the operating level"
            )

    # ── Free cash flow (yield + margin). FCF is the cash left after capex —
    # actual money available for buybacks, dividends, R&D, or debt paydown.
    # Harder to massage with accounting choices than reported earnings.
    fcf_yield  = fcf / mkt_cap if (fcf is not None and mkt_cap)         else None
    fcf_margin = fcf / revenue if (fcf is not None and revenue)         else None

    if fcf_yield is not None:
        if   fcf_yield > 0.08:
            score += 12
            signals.append(
                f"Free cash flow yield of {fcf_yield*100:.1f}% reflects strong cash "
                f"generation at an attractive price"
            )
        elif fcf_yield > 0.04:
            score += 6
            signals.append(
                f"Free cash flow yield of {fcf_yield*100:.1f}% — cash returns to "
                f"shareholders are well-supported"
            )
        elif fcf_yield < 0:
            score -= 15
            cautions.append(
                f"Free cash flow is negative — the company is currently consuming cash "
                f"at the corporate level after capex, which limits flexibility for "
                f"buybacks, dividends, or debt paydown"
            )

    # FCF margin bonus only when FCF is positive — capital-efficiency signal
    if fcf_margin is not None and fcf_margin > 0.20 and (fcf_yield is None or fcf_yield > 0):
        score += 5
        signals.append(
            f"FCF margin of {fcf_margin*100:.1f}% — the business converts a high "
            f"share of revenue into actual cash"
        )

    # ── Graham Number
    if graham and price:
        ratio = price / graham
        if   ratio < 0.80:
            score += 20
            signals.append(
                f"At ${price:.2f}, the stock trades {(1-ratio)*100:.0f}% below its "
                f"Graham Number of ${graham:.2f} — a classic value margin of safety"
            )
        elif ratio < 1.0:
            score += 10
            signals.append(
                f"Price of ${price:.2f} is below the Graham Number of ${graham:.2f}, "
                f"suggesting the market has not yet fully priced intrinsic book value"
            )
        elif ratio > 2.0:
            score -= 15
            cautions.append(
                f"Trading at {ratio:.1f}x the Graham Number of ${graham:.2f} — the market "
                f"assigns a large franchise premium above tangible asset value"
            )

    # ── ROE
    if roe:
        if   roe > 0.25:
            score += 8
            signals.append(
                f"Return on equity of {roe*100:.1f}% demonstrates best-in-class "
                f"capital efficiency"
            )
        elif roe < 0:
            score -= 10
            cautions.append(
                f"Negative ROE indicates the business is currently eroding shareholder equity"
            )

    # ── Leverage
    if debt_eq is not None and debt_eq > 200:
        score -= 12
        cautions.append(
            f"Debt/equity ratio of {debt_eq:.0f}% is elevated — financial leverage "
            f"amplifies downside risk in a higher-rate environment"
        )

    # ── Verdict label
    if eps_trail and eps_trail < 0 and rev_growth and rev_growth > 0.15:
        verdict = "SPECULATIVE"
    elif score >= 25:
        verdict = "UNDERVALUED"
    elif score >= -15:
        verdict = "FAIRLY VALUED"
    else:
        verdict = "OVERPRICED"

    # ── Narrative paragraph
    pe_str  = f"{pe:.1f}x"    if pe        else "N/A"
    gr_str  = f"{rev_growth*100:.1f}%" if rev_growth is not None else "N/A"
    mg_str  = f"{net_margin*100:.1f}%" if net_margin is not None else "N/A"

    openers = {
        "UNDERVALUED":   f"{company} ({ticker}) appears undervalued relative to its fundamentals.",
        "FAIRLY VALUED": f"{company} ({ticker}) appears fairly valued at current levels.",
        "OVERPRICED":    f"{company} ({ticker}) looks richly priced relative to its underlying fundamentals.",
        "SPECULATIVE":   f"{company} ({ticker}) is a pre-profitability growth story where traditional valuation metrics are secondary to the revenue trajectory.",
    }

    closers = {
        "UNDERVALUED":   f"At a forward P/E of {pe_str} with {gr_str} revenue growth, the risk/reward skews favourably for patient long-term investors.",
        "FAIRLY VALUED": f"The current valuation appears to reflect near-term earnings. Accumulating on market-wide pullbacks would improve the entry risk/reward.",
        "OVERPRICED":    f"While the business quality may be high, current pricing offers limited margin of safety — position sizing and a disciplined entry point are important.",
        "SPECULATIVE":   f"Investors should size positions to reflect execution risk and monitor quarterly revenue cadence and the timeline to profitability.",
    }

    parts = [openers[verdict]]
    if signals:   parts.append(signals[0] + ".")
    if len(signals) > 1: parts.append(signals[1] + ".")
    if cautions:  parts.append(cautions[0] + ".")
    parts.append(closers[verdict])

    commentary = " ".join(parts)
    return verdict, score, commentary


# ── Polygon.io news ────────────────────────────────────────────────────────────

def get_polygon_news(ticker):
    """Return up to 5 recent news items for a ticker from Polygon.io."""
    if not POLYGON_API_KEY:
        return []
    try:
        from datetime import timezone, timedelta
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"https://api.polygon.io/v2/reference/news"
            f"?ticker={ticker}&limit=5&published_utc.gte={week_ago}"
            f"&sort=published_utc&order=desc&apiKey={POLYGON_API_KEY}"
        )
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return []
        articles = r.json().get("results", [])
        news = []
        for a in articles:
            pub = a.get("published_utc", "")
            hours_ago = None
            if pub:
                try:
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    hours_ago = round(
                        (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600, 1
                    )
                except Exception:
                    pass
            news.append({
                "title":     a.get("title", ""),
                "source":    a.get("publisher", {}).get("name", ""),
                "url":       a.get("article_url", ""),
                "hours_ago": hours_ago,
            })
        return news
    except Exception:
        return []


# ── yfinance fetch with retry ──────────────────────────────────────────────────

def _yf_fetch(ticker):
    """
    Fetch yfinance .info with exponential-backoff retry on rate-limit errors.
    Raises the last exception if all attempts fail.
    """
    delays = [5, 15, 30]
    last_exc = None
    for attempt, delay in enumerate(delays, 1):
        try:
            info = yf.Ticker(ticker).info
            if not info or len(info) < 5:
                raise ValueError("Empty response — ticker may be invalid")
            return info
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = any(k in msg for k in ("429", "too many", "rate limit", "rate-limit"))
            if is_rate_limit and attempt < len(delays):
                time.sleep(delay)
                last_exc = e
            else:
                raise
    raise last_exc


# ── Core analysis function ─────────────────────────────────────────────────────

def analyze_ticker(ticker):
    ticker = ticker.upper().strip()

    # Return cached result if still fresh
    cached = _cache.get(ticker)
    if cached:
        result, ts = cached
        if time.time() - ts < _CACHE_TTL:
            return result

    try:
        info = _yf_fetch(ticker)
    except Exception as e:
        return {"error": f"Could not fetch data for {ticker}: {e}", "ticker": ticker}

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not price:
        return {"error": f"No price data found for '{ticker}'. Check the ticker symbol.", "ticker": ticker}

    prev_close = info.get("previousClose", price)
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

    # Graham Number: √(22.5 × EPS × Book Value per Share)
    eps_trail  = info.get("trailingEps")
    book_val   = info.get("bookValue")
    graham     = None
    if eps_trail and eps_trail > 0 and book_val and book_val > 0:
        graham = round(math.sqrt(22.5 * eps_trail * book_val), 2)

    verdict, score, commentary = compute_verdict(info, price, graham)

    # SEC EDGAR
    cik         = get_cik(ticker)
    sec_filings = get_sec_filings(cik)

    def pct(v):
        return round(v * 100, 1) if v is not None else None

    def r2(v):
        return round(v, 2) if v is not None else None

    def r1(v):
        return round(v, 1) if v is not None else None

    result = {
        "ticker":       ticker,
        "company":      info.get("longName") or info.get("shortName", ticker),
        "sector":       info.get("sector", "Unknown"),
        "industry":     info.get("industry", "Unknown"),
        "price":        round(price, 2),
        "change_pct":   round(change_pct, 2),
        "mkt_cap":      info.get("marketCap"),
        "week52_low":   info.get("fiftyTwoWeekLow"),
        "week52_high":  info.get("fiftyTwoWeekHigh"),
        # Valuation
        "pe_trailing":  r1(info.get("trailingPE")),
        "pe_forward":   r1(info.get("forwardPE")),
        "peg":          r2(info.get("pegRatio")),
        "pb":           r2(info.get("priceToBook")),
        "ps":           r2(info.get("priceToSalesTrailing12Months")),
        "ev_ebitda":    r1(info.get("enterpriseToEbitda")),
        "eps_trailing": r2(eps_trail),
        "eps_forward":  r2(info.get("forwardEps")),
        "graham":       graham,
        # Growth & profitability
        "rev_growth":   pct(info.get("revenueGrowth")),
        "earn_growth":  pct(info.get("earningsGrowth")),
        "gross_margin": pct(info.get("grossMargins")),
        "op_margin":    pct(info.get("operatingMargins")),
        "net_margin":   pct(info.get("profitMargins")),
        "roe":          pct(info.get("returnOnEquity")),
        "roa":          pct(info.get("returnOnAssets")),
        # Free cash flow
        "fcf":          info.get("freeCashflow"),  # absolute $, can be negative
        "fcf_yield":    pct((info.get("freeCashflow") or 0) / info.get("marketCap"))
                            if info.get("freeCashflow") is not None and info.get("marketCap")
                            else None,
        "fcf_margin":   pct((info.get("freeCashflow") or 0) / info.get("totalRevenue"))
                            if info.get("freeCashflow") is not None and info.get("totalRevenue")
                            else None,
        # Balance sheet
        "debt_equity":   r1(info.get("debtToEquity")),
        "current_ratio": r2(info.get("currentRatio")),
        "book_val_ps":   r2(book_val),
        # Analyst output
        "verdict":       verdict,   # UNDERVALUED | FAIRLY VALUED | OVERPRICED | SPECULATIVE
        "score":         score,
        "commentary":    commentary,
        # SEC
        "sec_filings":  sec_filings,
        "cik":          cik,
        # Meta
        "summary_short": (info.get("longBusinessSummary") or "")[:280],
        "scanned_at":    datetime.now().isoformat(),
    }

    result["recent_news"] = get_polygon_news(ticker)
    _cache[ticker] = (result, time.time())
    return result


# ── Pre-scan thread ────────────────────────────────────────────────────────────

def run_prescan():
    with _lock:
        _state["prescan_status"] = "scanning"

    results = {}
    for t in PRESCAN_TICKERS:
        try:
            results[t] = analyze_ticker(t)
        except Exception as e:
            results[t] = {"error": str(e), "ticker": t}
        time.sleep(4)

    with _lock:
        _state["prescan"]        = results
        _state["prescan_status"] = "done"

    try:
        with open(RESULTS_FILE, "w") as f:
            json.dump(results, f, indent=2, default=str)
    except Exception:
        pass


# ── Flask routes ───────────────────────────────────────────────────────────────

WEBSITE_IMAGES = os.path.join(BASE_DIR, "..", "images")

@app.route("/images/<path:filename>")
def serve_images(filename):
    return send_file(os.path.join(WEBSITE_IMAGES, filename))

@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "dashboard.html"))


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data   = request.get_json() or {}
    ticker = data.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
    return jsonify(analyze_ticker(ticker))


@app.route("/api/prescan")
def api_prescan():
    with _lock:
        return jsonify({
            "status":  _state["prescan_status"],
            "results": _state["prescan"],
        })


@app.route("/ping")
def ping():
    return "pong"


@app.route("/api/retry-prescan", methods=["POST"])
def api_retry_prescan():
    with _lock:
        _state["prescan_status"] = "idle"
        _state["prescan"]        = {}
    threading.Thread(target=run_prescan, daemon=True).start()
    return jsonify({"status": "started"})


# ── Startup ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Load cached prescan results if available
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                cached = json.load(f)
            with _lock:
                _state["prescan"]        = cached
                _state["prescan_status"] = "done"
            print("Loaded cached prescan results.")
        except Exception:
            pass

    # Kick off prescan if cache is absent, incomplete, or has errors
    with _lock:
        ready = (
            _state["prescan_status"] == "done"
            and len(_state["prescan"]) >= len(PRESCAN_TICKERS)
            and all("error" not in v for v in _state["prescan"].values())
        )
    if not ready:
        threading.Thread(target=run_prescan, daemon=True).start()

    # On Render (and other cloud platforms) PORT is injected as an env var.
    # Locally, find a free port from the candidate list.
    if os.environ.get("PORT"):
        port = int(os.environ["PORT"])
        print(f"The Analyst running on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)
    else:
        port = 8095
        for p in [8095, 8096, 8097, 9095, 9096]:
            try:
                s = socket.socket()
                s.bind(("", p))
                s.close()
                port = p
                break
            except OSError:
                continue
        print(f"The Analyst running at http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=False)
