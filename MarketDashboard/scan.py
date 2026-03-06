"""
MarketDashboard — Standalone Scanner
Runs once, writes results to data/results.json, then exits.
Invoked by GitHub Actions on a schedule (weekdays 8am & 1pm ET).
Run locally: python scan.py
"""

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "results.json")

FINNHUB_API_KEY = os.environ.get("FINNHUB_KEY", "d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70")

DAY_TRADE_MIN_PRICE   = 2.0
DAY_TRADE_MAX_PRICE   = 100.0
SWING_TRADE_MIN_PRICE = 2.0
MIN_MARKET_CAP        = 20_000_000
MIN_MARKET_CAP_SWING  = 50_000_000
MIN_DAY_SCORE         = 10
MIN_SWING_SCORE       = 8

NEXT_SCAN_INFO = "weekdays 8am & 1pm ET"

# ── Yahoo Finance movers ───────────────────────────────────────────────────────

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


# ── Reddit buzz ────────────────────────────────────────────────────────────────

def get_reddit_buzz():
    """Returns (lookup_dict, feed_list)"""
    counts = defaultdict(float)
    post_counts = defaultdict(set)   # ticker -> set of distinct post IDs mentioning it
    feed = []
    subreddits = ["wallstreetbets", "stocks", "StockMarket", "options", "daytrading"]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    ticker_pattern = re.compile(r"\b([A-Z]{2,5})\b")
    dollar_pattern = re.compile(r"\$([A-Z]{1,5})\b")

    NOISE = {
        # Articles / conjunctions / prepositions / pronouns (2-3 chars)
        "THE","AND","FOR","ARE","BUT","NOT","YOU","ALL","CAN","HER","WAS","ONE",
        "OUR","OUT","HAD","HIS","HOW","ITS","WHO","DID","GET","HAS","HIM",
        "GOT","TOO","SEE","TWO","WAY","BOY","OWN","SAY","SHE","MAY","USE","NEW",
        "NOW","OLD","ANY","TRY","FEW","CAR","MAN","SET","PUT","END","WHY","LET",
        "BIG","FAR","OFF","ADD","YET","TOP","SIT","ACT","AGO","AIM","AGE",
        # Common 2-3 char words that look like tickers
        "OR","GO","IT","DO","SO","UP","ON","IN","AT","BY","TO","AS","BE","AN",
        "OF","IS","IF","NO","MY","WE","HE","ME","US","OK","OH","HI","VS","RE",
        "AM","PM","ER","EX","II","IV","VI","IX","XI","XL","XX",
        # Finance / market jargon (abbreviations)
        "USD","EUR","GBP","ETF","IPO","CEO","CFO","CTO","COO","EPS","ATH","ATL",
        "IMO","WSB","EOM","EOD","YTD","AUM","NAV","OTC","SEC","FED","GDP","CPI",
        "APR","APY","DCA","FDIC","FOMC","YOLO","FOMO","BTFD","HODL","PUMP","DUMP",
        "BEAR","BULL","CALL","PUTS","GAIN","LOSS","DEBT","CASH","BOND",
        "LOAN","RATE","RISK","SELL","HOLD","LONG","HIGH","LOWS","STOP","OPEN",
        "DUE","TAX","IRA","ROTH","REITS","REIT","SPAC","LOT","BUY","OTM","ITM",
        "ATM","SPY","QQQ","IWM","DIA","VIX","WSJ","CNBC","TWTR",
        # Common 4-5 char English words that slip through
        "THIS","WITH","FROM","THAT","HAVE","BEEN","THEY","WILL","MORE","THAN",
        "THEN","WHEN","WHAT","SOME","LIKE","INTO","JUST","OVER","ALSO","BACK",
        "ONLY","COME","WELL","EVEN","WANT","LOOK","GOOD","GIVE","MOST","TELL",
        "VERY","MUCH","NEED","TAKE","KNOW","MAKE","LAST","HERE","MANY","SAID",
        "SAME","DOES","EACH","BOTH","WENT","WERE","YOUR","YEAR","DAYS","WEEK",
        "LONG","TERM","TIME","REAL","EVER","NEXT","BEST","WORK","PLAY",
        "DOWN","MOON","NEWS","SHOW","PLAN","MOVE","KEEP","FIND","FEEL","DONE",
        "WENT","GOES","LETS","STAY","ONCE","NICE","HELP","THEM","THEN","USED",
        "CAME","GONE","LEFT","SEEN","GAVE","HELD","SOLD","HIGH","FELL","RISE",
        "FELL","HITS","JUMP","PUMP","DUMP","TANK","DIPS","DROP","RUNS","GAPS",
        "HUGE","FAST","EASY","SAFE","HARD","DARK","FULL","FREE","OPEN","LIVE",
        "SAID","TOLD","SENT","FEEL","FELT","KNEW","SEEN","PUTS","CALL","ASKS",
        "BEAT","MISS","MISS","WARN","CUTS","HIKE","HOLD","FADE","RIPS","LEGS",
        "ADDS","BUYS","SETS","GETS","HITS","PAYS","SAYS","RUNS","TOPS","NEAR",
        "LATE","PAST","DAYS","WONT","CANT","DONT","ISNT","AINT","DONT",
        # Reddit slang
        "LMAO","LMFAO","LOL","OMG","WTF","SMH","TBH","IMO","IMHO","NGL","IRL",
        "AMA","TIL","ELI","AFAIK","IIRC","TLDR","YMMV","RIP","GG","GJ",
        "BRB","AFK","FYI","DIY","BTW","IDK","TBF","FUD","SHILL","APE","APES",
        # Country/currency codes
        "USA","JPY","CAD","AUD","CHF","CNY","INR",
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
                    post_id = pd.get("id", "")
                    hours_ago = (time.time() - pd.get("created_utc", 0)) / 3600
                    if hours_ago > 24:
                        continue
                    text = (pd.get("title", "") + " " + pd.get("selftext", "")).upper()
                    recency = 2.0 if hours_ago < 6 else (1.5 if hours_ago < 12 else 1.0)
                    weight = recency * min(1 + pd.get("ups", 1) // 200, 4)

                    mentioned = set()

                    # $-prefixed: strong intentional signal — allow 2-5 chars
                    for t in dollar_pattern.findall(text):
                        if t not in NOISE and 2 <= len(t) <= 5 and t.isalpha():
                            counts[t] += weight * 3
                            post_counts[t].add(post_id)
                            mentioned.add(t)

                    # Plain caps: require 4+ chars to avoid catching OR/GO/IT/DAY etc.
                    for t in ticker_pattern.findall(text):
                        if t not in NOISE and 4 <= len(t) <= 5 and t.isalpha():
                            counts[t] += weight
                            post_counts[t].add(post_id)
                            mentioned.add(t)

                    if mentioned and pd.get("ups", 0) > 50:
                        feed.append({
                            "id":        post_id,
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

    seen_ids = set()
    unique_feed = []
    for item in feed:
        post_id = item.get("id") or item.get("url", "")
        if post_id not in seen_ids:
            seen_ids.add(post_id)
            unique_feed.append(item)
    unique_feed.sort(key=lambda x: x["ups"], reverse=True)

    # Require both a minimum weighted score AND mentions across ≥2 distinct posts.
    # The post diversity check is the key guard against one viral post with a
    # common word (e.g. "or", "go") artificially inflating a count.
    lookup = {t: int(c) for t, c in counts.items()
              if c >= 8 and len(post_counts[t]) >= 2}
    return lookup, unique_feed[:40]


# ── Finnhub ────────────────────────────────────────────────────────────────────

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


# ── Stock analysis ─────────────────────────────────────────────────────────────

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


# ── Categorize ─────────────────────────────────────────────────────────────────

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

    result_map = {r["ticker"]: r for r in results if r}
    reddit_candidates = sorted(reddit_lookup.items(), key=lambda x: x[1], reverse=True)

    reddit_cards    = []
    reddit_fallback = []
    checked = 0
    for ticker, mentions in reddit_candidates:
        if len(reddit_cards) >= 3:
            break
        if checked >= 40:
            break
        checked += 1

        if ticker in result_map:
            card = dict(result_map[ticker])
            card["mentions"] = mentions
            if card.get("change_pct", 0) > 0:
                reddit_cards.append(card)
            elif len(reddit_fallback) < 3:
                reddit_fallback.append(card)
            continue

        try:
            quote   = get_stock_quote(ticker)
            profile = get_company_profile(ticker)
            if not quote or not profile or not profile.get("name"):
                continue
            change_pct = quote.get("dp", 0)
            market_cap = profile.get("marketCapitalization", 0) * 1_000_000
            if market_cap < MIN_MARKET_CAP:
                continue
            card = {
                "ticker":          ticker,
                "mentions":        mentions,
                "name":            profile.get("name", ticker),
                "sector":          profile.get("finnhubIndustry", "Unknown"),
                "current_price":   quote.get("c", 0),
                "change_pct":      change_pct,
                "high":            quote.get("h", 0),
                "low":             quote.get("l", 0),
                "open":            quote.get("o", 0),
                "prev_close":      quote.get("pc", 0),
                "market_cap":      market_cap,
                "score":           0,
                "signals":         [f"Reddit buzz ({mentions} mentions)"],
                "reddit_mentions": mentions,
                "is_gainer":       False,
                "is_active":       False,
            }
            if change_pct > 0:
                reddit_cards.append(card)
            elif len(reddit_fallback) < 3:
                reddit_fallback.append(card)
            time.sleep(1.1)
        except Exception:
            continue

    while len(reddit_cards) < 3 and reddit_fallback:
        reddit_cards.append(reddit_fallback.pop(0))

    return day_cands[:3], swing_cands[:3], reddit_cards


# ── Sector flow ────────────────────────────────────────────────────────────────

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


# ── Supplemental data ─────────────────────────────────────────────────────────

def get_fear_greed():
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
    try:
        from datetime import timedelta
        today    = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={tomorrow}&token={FINNHUB_API_KEY}"
        resp = requests.get(url, timeout=8)
        items = resp.json().get("earningsCalendar", [])[:15]
        earnings = []
        for item in items:
            earnings.append({
                "ticker":  item.get("symbol", ""),
                "date":    item.get("date", ""),
                "hour":    item.get("hour", ""),
                "eps_est": item.get("epsEstimate"),
                "rev_est": item.get("revenueEstimate"),
            })
        return earnings
    except Exception as e:
        print(f"[Earnings] Error: {e}")
        return []


def get_finviz_movers():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&o=-volume"
        resp = requests.get(url, headers=headers, timeout=10)
        tickers = re.findall(r'quote\.ashx\?t=([A-Z]{1,5})"', resp.text)[:20]
        return list(dict.fromkeys(tickers))
    except Exception as e:
        print(f"[Finviz] Error: {e}")
        return []


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("[scan.py] Starting market scan...")
    start = datetime.now()

    yahoo_cats = get_yahoo_movers_categorized()
    universe   = sorted(set().union(*yahoo_cats.values()))
    print(f"[scan.py] Universe: {len(universe)} tickers")

    print("[scan.py] Fetching Reddit buzz...")
    reddit_lookup, reddit_feed = get_reddit_buzz()
    print(f"[scan.py] Reddit: {len(reddit_lookup)} tickers with buzz")

    results = []
    for i, ticker in enumerate(universe, 1):
        if i % 10 == 0:
            print(f"[scan.py] Analyzing {i}/{len(universe)}: {ticker}")
        result = analyze_stock(ticker, yahoo_cats, reddit_lookup)
        if result:
            results.append(result)
        time.sleep(1.1)

    day_trades, swing_trades, reddit_cards = categorize(results, reddit_lookup, universe, yahoo_cats)
    sector_flow = build_sector_flow(results)

    print("[scan.py] Fetching Fear & Greed, news, earnings, Finviz...")
    fear_greed     = get_fear_greed()
    market_news    = get_market_news()
    earnings_cal   = get_earnings_calendar()
    finviz_unusual = get_finviz_movers()

    confirmed = {card["ticker"] for card in reddit_cards}
    filtered_feed = []
    for item in reddit_feed:
        matched = [t for t in item.get("tickers", []) if t in confirmed]
        if matched:
            enriched = dict(item)
            enriched["confirmed_tickers"] = matched
            filtered_feed.append(enriched)
    display_feed = filtered_feed if filtered_feed else reddit_feed[:20]

    output = {
        "scan_time":      start.isoformat(),
        "next_scan_info": NEXT_SCAN_INFO,
        "total_scanned":  len(universe),
        "day_trades":     day_trades,
        "swing_trades":   swing_trades,
        "reddit_cards":   reddit_cards,
        "sector_flow":    sector_flow,
        "reddit_feed":    display_feed,
        "fear_greed":     fear_greed,
        "market_news":    market_news,
        "earnings_cal":   earnings_cal,
        "finviz_unusual": finviz_unusual,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now() - start).seconds
    print(f"[scan.py] Done in {elapsed}s — {len(day_trades)}D {len(swing_trades)}S {len(reddit_cards)}R")
    print(f"[scan.py] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
