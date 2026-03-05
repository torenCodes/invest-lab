"""
Market Scanner Dashboard - Flask Backend
Run: python app.py
Then open: http://localhost:5000
"""

from flask import Flask, jsonify, Response, send_file
import threading
import time
import json
import os
import re
import requests
from datetime import datetime
from collections import defaultdict

# ── Anchor everything to the folder this script lives in ─────────────────────
# This ensures scan_results.json and dashboard.html are always found
# regardless of which directory you run `python app.py` from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, "scan_results.json")

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
FINNHUB_API_KEY = "d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70"

# Day trades: lowered floor to $2 to catch small-cap runners like OSS/LPTH
DAY_TRADE_MIN_PRICE   = 2.0
DAY_TRADE_MAX_PRICE   = 100.0
# Swing trades: lowered floor to $2, cap threshold to $50M to catch micro-caps
SWING_TRADE_MIN_PRICE = 2.0
MIN_MARKET_CAP        = 20_000_000   # $20M min for day trades (filters true penny stocks)
MIN_MARKET_CAP_SWING  = 50_000_000   # $50M min for swing trades
MIN_DAY_SCORE         = 10
MIN_SWING_SCORE       = 8

REFRESH_INTERVAL_SECONDS = 900  # 15 minutes between full scans

# ── Shared state ──────────────────────────────────────────────────────────────
scan_state = {
    "status": "idle",
    "progress": 0,
    "progress_total": 0,
    "current_ticker": "",
    "last_scan": None,
    "next_scan": None,
    "reddit_feed": [],
}
state_lock = threading.Lock()


def set_state(**kwargs):
    with state_lock:
        scan_state.update(kwargs)


# ── Scanner logic ─────────────────────────────────────────────────────────────

def get_yahoo_movers_categorized():
    categorized = {"gainers": set(), "losers": set(), "active": set()}
    urls = {
        "gainers": "https://finance.yahoo.com/screener/predefined/day_gainers",
        "losers":  "https://finance.yahoo.com/screener/predefined/day_losers",
        "active":  "https://finance.yahoo.com/screener/predefined/most_actives",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    for cat, url in urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            found = set(re.findall(r'"symbol":"([A-Z]{1,5})"', resp.text)[:60])
            categorized[cat] = found
        except Exception:
            pass
    return categorized


def get_reddit_buzz():
    """Returns (lookup_dict, feed_list)"""
    counts = defaultdict(float)
    feed = []
    subreddits = ["wallstreetbets", "stocks", "StockMarket", "options", "daytrading"]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    ticker_pattern = re.compile(r"\b([A-Z]{2,5})\b")
    dollar_pattern = re.compile(r"\$([A-Z]{1,5})\b")

    # Comprehensive noise list: common English words, finance jargon, subreddit slang
    # that regex catches as "tickers" but are definitely not stock symbols
    NOISE = {
        # Articles / conjunctions / prepositions
        "THE","AND","FOR","ARE","BUT","NOT","YOU","ALL","CAN","HER","WAS","ONE",
        "OUR","OUT","HAD","HIS","HOW","ITS","WHO","DID","GET","HAS","HIM","HIS",
        "GOT","TOO","SEE","TWO","WAY","BOY","OWN","SAY","SHE","MAY","USE","NEW",
        "NOW","OLD","ANY","TRY","FEW","CAR","MAN","SET","PUT","END","WHY","LET",
        "BIG","FAR","OFF","ADD","YET","TOP","SIT","ACT","AGO","AIM","AGE",
        # Finance/market jargon (not real tickers)
        "USD","EUR","GBP","ETF","IPO","CEO","CFO","CTO","COO","EPS","ATH","ATL",
        "IMO","WSB","EOM","EOD","YTD","AUM","NAV","OTC","SEC","FED","GDP","CPI",
        "APR","APY","DCA","FDIC","FOMC","YOLO","FOMO","BTFD","HODL","PUMP","DUMP",
        "BEAR","BULL","CALL","PUTS","PUTS","GAIN","LOSS","DEBT","CASH","BOND",
        "LOAN","RATE","RISK","SELL","HOLD","LONG","HIGH","LOWS","STOP","OPEN",
        "DUE","TAX","IRA","ROTH","REITS","REIT","SPAC","LOT","BUY","OTM","ITM",
        "ATM","SPY","QQQ","IWM","DIA","VIX","WSJ","CNBC","TWTR",
        # Common words regex mistakes for tickers
        "THIS","WITH","FROM","THAT","HAVE","BEEN","THEY","WILL","MORE","THAN",
        "THEN","WHEN","WHAT","SOME","LIKE","INTO","JUST","OVER","ALSO","BACK",
        "ONLY","COME","WELL","EVEN","WANT","LOOK","GOOD","GIVE","MOST","TELL",
        "VERY","MUCH","NEED","TAKE","KNOW","MAKE","LAST","HERE","MANY","SAID",
        "SAME","DOES","EACH","BOTH","WENT","WERE","YOUR","YEAR","DAYS","WEEK",
        "LONG","TERM","TIME","REAL","THAN","EVER","NEXT","BEST","WORK","PLAY",
        # Reddit slang
        "LMAO","LMFAO","LOL","OMG","WTF","SMH","TBH","IMO","IMHO","NGL","IRL",
        "AMA","TIL","ELI","AFAIK","IIRC","TLDR","YMMV","RIP","GG","GG","GJ",
        "BRB","AFK","FYI","DIY","BTW","IDK","TBF","FUD","SHILL","APE","APES",
        # Country/currency codes
        "USA","USD","EUR","GBP","JPY","CAD","AUD","CHF","CNY","INR",
    }

    for subreddit in subreddits:
        for sort in ["hot", "new"]:
            try:
                url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit=50"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    continue
                posts = resp.json().get("data", {}).get("children", [])
                for post in posts:
                    pd = post.get("data", {})
                    hours_ago = (time.time() - pd.get("created_utc", 0)) / 3600
                    if hours_ago > 24:
                        continue
                    text = (pd.get("title", "") + " " + pd.get("selftext", "")).upper()
                    recency = 2.0 if hours_ago < 6 else (1.5 if hours_ago < 12 else 1.0)
                    weight = recency * min(1 + pd.get("ups", 1) // 200, 4)

                    mentioned = set()
                    for t in dollar_pattern.findall(text):
                        # $ prefix is strong signal — still filter noise but weight heavily
                        if t not in NOISE and 2 <= len(t) <= 5 and t.isalpha():
                            counts[t] += weight * 3
                            mentioned.add(t)
                    for t in ticker_pattern.findall(text):
                        # Plain word — only count if 2-5 alpha chars and not noise
                        if t not in NOISE and 2 <= len(t) <= 5 and t.isalpha():
                            counts[t] += weight
                            mentioned.add(t)

                    if mentioned and pd.get("ups", 0) > 50:
                        feed.append({
                            "id":        pd.get("id", ""),          # stable unique post ID
                            "title":     pd.get("title", "")[:120],
                            "subreddit": subreddit,
                            "ups":       pd.get("ups", 0),
                            "tickers":   sorted(mentioned - NOISE)[:5],
                            "hours_ago": round(hours_ago, 1),
                            "url":       f"https://reddit.com{pd.get('permalink', '')}",
                        })
                time.sleep(1.2)
            except Exception:
                continue

    # Deduplicate by post ID — more reliable than URL which can vary in trailing slashes
    seen_ids = set()
    unique_feed = []
    for item in feed:
        post_id = item.get("id") or item.get("url", "")
        if post_id not in seen_ids:
            seen_ids.add(post_id)
            unique_feed.append(item)
    unique_feed.sort(key=lambda x: x["ups"], reverse=True)

    lookup = {t: int(c) for t, c in counts.items() if c >= 8}
    return lookup, unique_feed[:40]


def get_stock_quote(ticker):
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}"
    try:
        return requests.get(url, timeout=5).json()
    except Exception:
        return None


def get_company_profile(ticker):
    url = f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}"
    try:
        return requests.get(url, timeout=5).json()
    except Exception:
        return None


def analyze_stock(ticker, yahoo_cats, reddit_lookup):
    quote = get_stock_quote(ticker)
    if not quote or quote.get("c", 0) == 0:
        return None

    profile = get_company_profile(ticker)
    if not profile or not profile.get("name"):
        return None

    current_price = quote.get("c", 0)
    change_pct    = quote.get("dp", 0)
    high          = quote.get("h", 0)
    low           = quote.get("l", 0)
    open_         = quote.get("o", 0)
    prev_close    = quote.get("pc", 0)

    # Green-only filter
    if change_pct <= 0:
        return None

    score   = 0
    signals = []

    is_gainer = ticker in yahoo_cats["gainers"]
    is_active = ticker in yahoo_cats["active"]

    if is_gainer:
        score += 15
        signals.append(f"Top gainer ({change_pct:+.1f}%)")

    if is_active:
        score += 5
        signals.append("High volume")

    if change_pct >= 5.0:
        score += 15
        signals.append(f"Strong move ({change_pct:+.1f}%)")
    elif change_pct >= 3.0:
        score += 10
        signals.append(f"Good move ({change_pct:+.1f}%)")
    elif change_pct >= 1.5:
        score += 5
        signals.append(f"Moderate move ({change_pct:+.1f}%)")

    reddit_mentions = reddit_lookup.get(ticker, 0)
    if reddit_mentions >= 20:
        score += 15
        signals.append(f"High Reddit buzz ({reddit_mentions})")
    elif reddit_mentions >= 10:
        score += 10
        signals.append(f"Reddit buzz ({reddit_mentions})")
    elif reddit_mentions >= 5:
        score += 5
        signals.append(f"Reddit activity ({reddit_mentions})")

    market_cap = profile.get("marketCapitalization", 0) * 1_000_000
    sector     = profile.get("finnhubIndustry", "Unknown")

    return {
        "ticker":          ticker,
        "name":            profile.get("name", ticker),
        "sector":          sector,
        "current_price":   current_price,
        "change_pct":      change_pct,
        "high":            high,
        "low":             low,
        "open":            open_,
        "prev_close":      prev_close,
        "score":           score,
        "signals":         signals,
        "reddit_mentions": reddit_mentions,
        "market_cap":      market_cap,
        "is_gainer":       is_gainer,
        "is_active":       is_active,
        "logo":            profile.get("logo", ""),
        "weburl":          profile.get("weburl", ""),
    }


def categorize(results, reddit_lookup, universe, yahoo_cats=None):
    day_cands   = []
    swing_cands = []

    for r in results:
        if not r:
            continue
        price      = r["current_price"]
        market_cap = r["market_cap"]

        if (DAY_TRADE_MIN_PRICE <= price <= DAY_TRADE_MAX_PRICE
                and market_cap >= MIN_MARKET_CAP
                and r["change_pct"] >= 1.5
                and r["score"] >= MIN_DAY_SCORE):
            day_cands.append(r)

        if (price >= SWING_TRADE_MIN_PRICE
                and market_cap >= MIN_MARKET_CAP_SWING
                and r["change_pct"] >= 1.0
                and r["score"] >= MIN_SWING_SCORE):
            if r["is_gainer"]:
                r["score"] += 5
            swing_cands.append(r)

    day_cands.sort(key=lambda x: x["score"], reverse=True)
    swing_cands.sort(key=lambda x: x["score"], reverse=True)

    day_tickers = {c["ticker"] for c in day_cands[:3]}
    swing_cands = [c for c in swing_cands if c["ticker"] not in day_tickers]

    # Reddit buzz: pull top mentioned tickers independently of Yahoo universe.
    # Sort by mention count, then fetch a live quote for each to confirm green.
    result_map = {r["ticker"]: r for r in results if r}
    reddit_candidates = sorted(reddit_lookup.items(), key=lambda x: x[1], reverse=True)

    reddit_cards = []
    checked = 0
    for ticker, mentions in reddit_candidates:
        if len(reddit_cards) >= 3:
            break
        if checked >= 20:  # cap API calls — don't check the entire list
            break
        checked += 1

        # If we already have a result from the main scan, reuse it
        if ticker in result_map:
            card = dict(result_map[ticker])
            card["mentions"] = mentions
            if card.get("change_pct", 0) > 0:
                reddit_cards.append(card)
            continue

        # Otherwise fetch a fresh quote for this reddit-only ticker
        try:
            quote   = get_stock_quote(ticker)
            profile = get_company_profile(ticker)
            if not quote or not profile or not profile.get("name"):
                continue
            change_pct = quote.get("dp", 0)
            if change_pct <= 0:
                continue  # green only
            market_cap = profile.get("marketCapitalization", 0) * 1_000_000
            if market_cap < MIN_MARKET_CAP:
                continue  # skip true micro-pennies
            reddit_cards.append({
                "ticker":        ticker,
                "mentions":      mentions,
                "name":          profile.get("name", ticker),
                "sector":        profile.get("finnhubIndustry", "Unknown"),
                "current_price": quote.get("c", 0),
                "change_pct":    change_pct,
                "high":          quote.get("h", 0),
                "low":           quote.get("l", 0),
                "open":          quote.get("o", 0),
                "prev_close":    quote.get("pc", 0),
                "market_cap":    market_cap,
                "score":         0,
                "signals":       [f"Reddit buzz ({mentions} mentions)"],
                "reddit_mentions": mentions,
                "is_gainer":     ticker in yahoo_cats.get("gainers", set()) if False else False,
                "is_active":     False,
            })
            time.sleep(1.1)  # respect Finnhub rate limit
        except Exception:
            continue

    return day_cands[:3], swing_cands[:3], reddit_cards


def build_sector_flow(results):
    sector_data = defaultdict(list)
    for r in results:
        if r and r["change_pct"] > 0:
            sector_data[r["sector"]].append(r["change_pct"])

    flow = []
    for sector, changes in sector_data.items():
        flow.append({
            "sector":     sector,
            "avg_change": round(sum(changes) / len(changes), 2),
            "count":      len(changes),
        })
    flow.sort(key=lambda x: x["avg_change"], reverse=True)
    return flow



def get_fear_greed():
    """CNN Fear & Greed Index — free, no API key."""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json()
        fg = data.get("fear_and_greed", {})
        score = round(float(fg.get("score", 0)), 1)
        rating = fg.get("rating", "Unknown").replace("_", " ").title()
        prev = round(float(fg.get("previous_close", score)), 1)
        week_ago = None
        history = data.get("fear_and_greed_historical", {}).get("data", [])
        if len(history) >= 5:
            week_ago = round(float(history[-5].get("y", score)), 1)
        return {"score": score, "rating": rating, "prev_close": prev, "week_ago": week_ago}
    except Exception as e:
        print(f"[F&G] Error: {e}")
        return None


def get_market_news():
    """Finnhub general market news — free tier, no extra cost."""
    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
        resp = requests.get(url, timeout=8)
        items = resp.json()[:12]
        news = []
        seen = set()
        for item in items:
            headline = item.get("headline", "")[:140]
            if not headline or headline in seen:
                continue
            seen.add(headline)
            news.append({
                "headline": headline,
                "source":   item.get("source", ""),
                "url":      item.get("url", ""),
                "summary":  item.get("summary", "")[:200],
                "datetime": item.get("datetime", 0),
            })
        return news
    except Exception as e:
        print(f"[News] Error: {e}")
        return []


def get_earnings_calendar():
    """Upcoming earnings for today + tomorrow from Finnhub — free tier."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        from datetime import timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={tomorrow}&token={FINNHUB_API_KEY}"
        resp = requests.get(url, timeout=8)
        items = resp.json().get("earningsCalendar", [])[:15]
        earnings = []
        for item in items:
            earnings.append({
                "ticker":     item.get("symbol", ""),
                "date":       item.get("date", ""),
                "hour":       item.get("hour", ""),   # bmo = before market, amc = after market
                "eps_est":    item.get("epsEstimate"),
                "rev_est":    item.get("revenueEstimate"),
            })
        return earnings
    except Exception as e:
        print(f"[Earnings] Error: {e}")
        return []


def get_finviz_movers():
    """Scrape Finviz top volume / unusual volume page — no API key needed."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&o=-volume"
        resp = requests.get(url, headers=headers, timeout=10)
        # Extract tickers from the screener table
        tickers = re.findall(r'quote\.ashx\?t=([A-Z]{1,5})"', resp.text)[:20]
        return list(dict.fromkeys(tickers))  # preserve order, dedupe
    except Exception as e:
        print(f"[Finviz] Error: {e}")
        return []

# ── Background scan loop ──────────────────────────────────────────────────────

def run_scan():
    while True:
        set_state(status="scanning", progress=0, current_ticker="")
        try:
            print("[Scanner] Starting scan...")
            yahoo_cats = get_yahoo_movers_categorized()
            universe   = sorted(set().union(*yahoo_cats.values()))
            print(f"[Scanner] Universe: {len(universe)} tickers")

            set_state(progress_total=len(universe))

            print("[Scanner] Fetching Reddit...")
            reddit_lookup, reddit_feed = get_reddit_buzz()
            set_state(reddit_feed=reddit_feed)

            results = []
            for i, ticker in enumerate(universe, 1):
                set_state(progress=i, current_ticker=ticker)
                result = analyze_stock(ticker, yahoo_cats, reddit_lookup)
                if result:
                    results.append(result)
                time.sleep(1.1)

            day_trades, swing_trades, reddit_cards = categorize(results, reddit_lookup, universe, yahoo_cats)
            sector_flow = build_sector_flow(results)

            # Fetch supplemental data (non-blocking — failures don't abort scan)
            print("[Scanner] Fetching Fear & Greed, news, earnings, Finviz...")
            fear_greed      = get_fear_greed()
            market_news     = get_market_news()
            earnings_cal    = get_earnings_calendar()
            finviz_unusual  = get_finviz_movers()

            output = {
                "scan_time":      datetime.now().isoformat(),
                "total_scanned":  len(universe),
                "day_trades":     day_trades,
                "swing_trades":   swing_trades,
                "reddit_cards":   reddit_cards,
                "sector_flow":    sector_flow,
                "reddit_feed":    reddit_feed,
                "fear_greed":     fear_greed,
                "market_news":    market_news,
                "earnings_cal":   earnings_cal,
                "finviz_unusual": finviz_unusual,
            }

            with open(RESULTS_FILE, "w") as f:
                json.dump(output, f, indent=2)

            print(f"[Scanner] Saved results to {RESULTS_FILE}")
            set_state(
                status="done",
                last_scan=datetime.now().isoformat(),
                next_scan=(time.time() + REFRESH_INTERVAL_SECONDS),
            )
            print(f"[Scanner] Done. {len(day_trades)}D {len(swing_trades)}S {len(reddit_cards)}R")

        except Exception as e:
            print(f"[Scanner] Error: {e}")
            import traceback; traceback.print_exc()
            set_state(status="error")

        time.sleep(REFRESH_INTERVAL_SECONDS)


# ── Routes ────────────────────────────────────────────────────────────────────

WEBSITE_IMAGES = os.path.join(BASE_DIR, "..", "Website", "images")

@app.route("/images/<path:filename>")
def serve_images(filename):
    return send_file(os.path.join(WEBSITE_IMAGES, filename))

@app.route("/")
def index():
    # Read and return the HTML file directly — no static folder needed
    html_path = os.path.join(BASE_DIR, "dashboard.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.route("/api/status")
def api_status():
    with state_lock:
        s = dict(scan_state)
    s.pop("reddit_feed", None)
    return jsonify(s)


@app.route("/api/results")
def api_results():
    if not os.path.exists(RESULTS_FILE):
        return jsonify({"error": "No results yet — scan still running"}), 404
    with open(RESULTS_FILE) as f:
        return jsonify(json.load(f))


@app.route("/api/reddit_feed")
def api_reddit_feed():
    with state_lock:
        feed = scan_state.get("reddit_feed", [])
    return jsonify(feed)


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import socket

    print(f"[Startup] Script directory : {BASE_DIR}")
    print(f"[Startup] Results file     : {RESULTS_FILE}")
    print(f"[Startup] Dashboard file   : {os.path.join(BASE_DIR, 'dashboard.html')}")

    # Find an available port — port 5000 is blocked on Macs by AirPlay Receiver
    def find_free_port(candidates):
        for port in candidates:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            in_use = s.connect_ex(('127.0.0.1', port)) == 0
            s.close()
            if not in_use:
                return port
        return None

    PORT = find_free_port([8080, 8081, 8888, 9000, 3000])
    if PORT is None:
        print("[Startup] ERROR: Could not find a free port. Close some applications and retry.")
        exit(1)

    t = threading.Thread(target=run_scan, daemon=True)
    t.start()

    # On Render (and other cloud platforms) PORT is injected as an env var.
    # Locally, fall back to the free-port detection below.
    if os.environ.get("PORT"):
        PORT = int(os.environ["PORT"])
        print(f"[Startup] ✅ Running on port {PORT}")
        app.run(debug=False, host="0.0.0.0", port=PORT)
    else:
        PORT = find_free_port([8080, 8081, 8888, 9000, 3000])
        if PORT is None:
            print("[Startup] ERROR: Could not find a free port. Close some applications and retry.")
            exit(1)
        print(f"[Startup] ✅ Dashboard running at http://localhost:{PORT}")
        print(f"[Startup]    Open that URL in Chrome or Firefox (Safari can block localhost)")
        app.run(debug=False, host="0.0.0.0", port=PORT)


# ── Quick health check (visit http://localhost:5000/ping to confirm Flask works) ──
@app.route("/ping")
def ping():
    return Response("Flask is alive! Now go to http://localhost:5000", mimetype="text/plain")
