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
from datetime import datetime, timedelta, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "results.json")

FINNHUB_API_KEY = os.environ.get("FINNHUB_KEY", "d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70")
POLYGON_API_KEY = os.environ.get("POLYGON_KEY", "P9fRbZP9VAKhjwABMtvcS7tfcYGU6z1T")

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
    headers = {
        "User-Agent": "InvestLabScanner/1.0 (personal market research tool; non-commercial)",
        "Accept": "application/json",
    }
    ticker_pattern = re.compile(r"\b([A-Z]{2,5})\b")
    dollar_pattern = re.compile(r"\$([A-Z]{1,5})\b")
    url_pattern    = re.compile(r"https?://\S+")

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
        # Common 4-letter English words that slip through
        "THIS","WITH","FROM","THAT","HAVE","BEEN","THEY","WILL","MORE","THAN",
        "THEN","WHEN","WHAT","SOME","LIKE","INTO","JUST","OVER","ALSO","BACK",
        "ONLY","COME","WELL","EVEN","WANT","LOOK","GOOD","GIVE","MOST","TELL",
        "VERY","MUCH","NEED","TAKE","KNOW","MAKE","LAST","HERE","MANY","SAID",
        "SAME","DOES","EACH","BOTH","WENT","WERE","YOUR","YEAR","DAYS","WEEK",
        "LONG","TERM","TIME","REAL","EVER","NEXT","BEST","WORK","PLAY",
        "DOWN","MOON","NEWS","SHOW","PLAN","MOVE","KEEP","FIND","FEEL","DONE",
        "GOES","LETS","STAY","ONCE","NICE","HELP","THEM","USED",
        "CAME","GONE","LEFT","SEEN","GAVE","HELD","SOLD","FELL","RISE",
        "HITS","JUMP","TANK","DIPS","DROP","RUNS","GAPS",
        "HUGE","FAST","EASY","SAFE","HARD","DARK","FULL","FREE","LIVE",
        "TOLD","SENT","FELT","KNEW","ASKS",
        "BEAT","MISS","WARN","CUTS","HIKE","FADE","RIPS","LEGS",
        "ADDS","BUYS","SETS","GETS","PAYS","SAYS","TOPS","NEAR",
        "LATE","PAST","WONT","CANT","DONT","ISNT","AINT",
        "ABLE","AWAY","BLUE","BOOM","BUST","COOL","DATA","DEAL","DEEP",
        "EARN","ELSE","FILL","FIRM","FLIP","FLOW","FUND","GAME","GREW","GROW",
        "HALF","HASH","HEAR","HEAT","HINT","HOPE","HOUR","HURT","IDEA",
        "JOIN","KICK","KING","LAND","LEAD","LEAN","LEND","LESS","LINE","LIST",
        "LOSE","LOVE","MADE","MAIN","MARK","MASS","MEAN","MEET","MILD","MIND",
        "MINT","MUST","NAME","NOTE","OPTS","PACE","PAID","PASS","PICK","POLL",
        "POOL","POST","PUSH","RACE","RELY","REST","RICH","ROLE","ROLL","RULE",
        "RUSH","SALE","SAVE","SHOW","SIDE","SIGN","SIZE","SKIP","SLOW","SNAP",
        "SOAR","SORT","STEP","STOP","SWAP","TALK","TECH","TEST","TIED","TILL",
        "TIPS","TOOK","TYPE","VARY","VIEW","VOTE","WAIT","WALK","WEAK","WINS",
        "WORD","WRAP","BORN","BOLD","BUSY","COLD","DEAD","DEAR","DEBT","DENY",
        "DRAW","DREW","DUAL","EDGE","EPIC","EVEN","EXAM","FACE","FACT","FAIL",
        "FAIR","FAKE","FAME","FARM","FATE","FEAR","FEED","FEEL","FEET","FILE",
        "FINE","FIRE","FIVE","FLAG","FLAT","FLEW","FOLD","FORE","FORK","FORM",
        "FORT","FOUR","FUEL","FURY","FUSE","GATE","GAVE","GAZE","GEAR","GLOW",
        "GOAL","GOLD","GRAB","GRAY","GREY","GRID","GRIM","GRIP","GRIT","GULF",
        "GURU","GUYS","HALT","HANG","HARD","HARM","HATE","HAVE","HEAD","HEED",
        "HELD","HIRE","HITS","HOLE","HOME","HOOK","HORN","HOST","HUNT","ICON",
        "IDLE","INFO","IRON","ITEM","JOBS","JOHN","JUMP","KEEP","KILL","LACK",
        "LAID","LAKE","LAME","LAMP","LANE","LAPS","LASH","LAWN","LAZY","LEAD",
        "LEAK","LEAN","LEAP","LEND","LENS","LIEN","LIFT","LINK","LION","LIPS",
        "LOAD","LOCK","LOOM","LOOP","LORE","LOUD","LUCK","LURE","LURK","LUST",
        "MALL","MATH","MAZE","MILD","MILK","MILL","MOCK","MODE","MOOD","MORE",
        "MOOT","MOVE","MYTH","NAIL","NAVY","NEED","NODE","NORM","NOSE","NULL",
        "OATH","OBEY","ODDS","OKAY","ONES","ONTO","ORAL","OVER","OWNS","PACK",
        "PACT","PAGE","PAIN","PAIR","PALM","PATH","PEAK","PEER","PESO","PILL",
        "PIPE","PITS","PLOT","PLUG","PLUS","PODS","POKE","POLL","POND","POOR",
        "PORK","POSE","POUR","PREY","PROD","PROF","PROP","PROS","PULL","PURE",
        "PUTS","RACK","RAID","RAIL","RAIN","RAMP","RAND","RANK","RANT","RARE",
        "RAYS","READ","REAR","RELY","REPO","RICH","RIDE","RIFE","RING","RIOT",
        "ROAD","ROAM","ROAR","ROCK","RODE","ROOF","ROOM","ROOT","ROPE","ROSE",
        "RUIN","SALE","SALT","SAND","SAVE","SCAN","SEAL","SEED","SELF","SHED",
        "SHIP","SHOP","SHOT","SHUT","SILK","SING","SINK","SITE","SITS","SKEW",
        "SKIN","SLIM","SLIP","SLOT","SLOW","SLUM","SNAP","SOIL","SOLD","SOLE",
        "SOME","SOUL","SOUP","SPAN","SPIN","SPIT","SPOT","SPUN","STAR","STEM",
        "STIR","STUB","STUN","SUCH","SUIT","SUNK","SURE","SWIM","TALE","TALL",
        "TAPE","TAPS","TASK","TEAR","TEND","TENS","TEST","THAT","THEM","THEN",
        "TICK","TIER","TILT","TIRE","TOLL","TONE","TOOL","TOPS","TORE","TORN",
        "TOSS","TOUT","TOWN","TOYS","TRAP","TRIM","TRIO","TRIP","TROY","TUBE",
        "TUCK","TUNE","TURN","TWIN","TYING","UGLY","UNIT","UPON","URGE","VAIN",
        "VEIL","VERY","VEST","VETO","VIBE","VOID","WARY","WAYS","WEED","WELL",
        "WENT","WHOM","WIDE","WIFE","WIKI","WILD","WIPE","WIRE","WISE","WISH",
        "ZONE","ZOOM",
        # Common 5-letter English words that slip through
        "ABOUT","AFTER","AGAIN","AHEAD","ALLOW","ALONG","AMONG","APPLY","AVOID",
        "BASIC","BELOW","BLACK","BOARD","BREAK","BRING","BROAD","BUILD","BUYER",
        "CALLS","DAILY","EARLY","EMAIL","ENTER","EVERY","FALLS","FIRST","FIXED",
        "FLOOR","FOCUS","FORCE","GIVEN","GOING","GOODS","GREAT","GREEN","GROUP",
        "GROWN","HAPPY","HELLO","HOUSE","INDEX","INNER","ISSUE","LARGE","LATER",
        "LAYER","LEARN","LEVEL","LIGHT","LIMIT","LOWER","MAJOR","MAYBE","MEDIA",
        "MIGHT","MIXED","MODEL","MONTH","MOVED","MONEY","NOTES","OFFER","ORDER",
        "OTHER","OWNED","PAPER","PARTY","PLACE","POINT","POWER","PRESS","PRICE",
        "PRINT","QUITE","QUOTE","RAISE","RANGE","RAPID","RATIO","REACH","READY",
        "REPLY","RESET","RIGHT","ROUND","SCALE","SCORE","SETUP","SHARE","SHORT",
        "SHOWS","SIDES","SIGNS","SINCE","SMALL","SMART","SPACE","SPEAK","SPEND",
        "SPLIT","STAGE","START","STATE","STILL","STORE","STORM","STORY","STUDY",
        "STYLE","SUPER","SURGE","TABLE","TALKS","TAXES","TEAMS","THERE","THING",
        "THINK","THIRD","THOSE","THREE","THROW","TIGHT","TODAY","TOPIC","TOTAL",
        "TOUCH","TRACK","TRADE","TREND","TRIED","TRULY","TURNS","ULTRA","UNDER",
        "UNION","UNTIL","UPPER","USING","USUAL","VALUE","WATCH","WEEKS","WHERE",
        "WHICH","WHILE","WHITE","WHOLE","WHOSE","WIDER","WORLD","WORRY","WORSE",
        "WORST","WOULD","WRITE","WRONG","YEARS","YIELD","YOURS","STOCK","HTTPS",
        "AGAIN","CLOSE","COULD","DOING","DOING","DOING","EARLY","EIGHT","EVERY",
        "EXACT","FALLS","FILED","FINAL","FIRST","FLOOR","FLIES","FUNDS","GAINS",
        "GOING","GONNA","GROSS","HANDS","HAPPY","HEAVY","HOURS","IDEAS","KEEPS",
        "KNOWN","LEAST","LEGAL","LOCAL","LOOKS","MAKES","MARKS","MEANS","MEETS",
        "MICRO","MILES","MINUS","MOVES","NEEDS","NEVER","NIGHT","NORMS","NORTH",
        "NOWIT","OFTEN","ONSET","OPENS","PAGES","PANEL","PLANS","PLAYS","POSES",
        "PRIOR","PULLS","RATES","RATIO","RALLY","RANKS","READS","RISKS","ROLES",
        "RULES","SALES","SEEMS","SHALL","SHOWS","SIDED","SIDES","SITES","SIXTH",
        "SIZED","SLOWS","SOLID","SORTS","SOUTH","SPEND","SPINS","SPITE","SPOKE",
        "STEPS","STOCK","STOPS","SUITS","SUPER","TAKES","TALKS","TASKS","TENTH",
        "TERMS","TESTS","TEXTS","THEIR","THERE","THESE","THICK","THROW","TICKS",
        "TIMES","TIRED","TITLE","TODOS","TOOLS","TOWNS","TRACE","TRAIL","TRUST",
        "TRUTH","TWICE","TYPES","UNITS","UNTIL","USUAL","VALID","VIEWS","VIRAL",
        "VISIT","VOTES","WANTS","WASTE","WAVES","WELLS","WIDER","WINDS","WORKS",
        "WORSE","WORST","YARDS","ZEROS",
        # URL / tech terms (strip URLs first, but also add as safety net)
        "HTTPS","HTTP","HTML","JSON","REST","APIS","REPO","WIKI","BLOG","FEED",
        # TA / chart jargon
        "CHART","CHOCH","MACD","VWAP","OHLC","OHCL","WICK","WICKS","BULL","BEAR",
        # More common words confirmed slipping through
        "BEING","BASED","PART","LOTS","IRAN","DOESN","CANT","WONT","ISNT",
        "EVER","JUST","SOME","BACK","ALSO","ONLY","VERY","MUCH","MORE","MOST",
        "LESS","LIKE","WELL","EVEN","HERE","SOME","CAME","GONE","LEFT","FELL",
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
                if resp.status_code == 429:
                    print(f"[Reddit] Rate limited on r/{subreddit}, retrying after 15s...")
                    time.sleep(15)
                    resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    print(f"[Reddit] r/{subreddit}/{sort} returned {resp.status_code}, skipping")
                    continue
                if "json" not in resp.headers.get("content-type", ""):
                    print(f"[Reddit] r/{subreddit}/{sort} returned non-JSON, skipping")
                    continue
                posts = resp.json().get("data", {}).get("children", [])
                for post in posts:
                    pd = post.get("data", {})
                    post_id = pd.get("id", "")
                    hours_ago = (time.time() - pd.get("created_utc", 0)) / 3600
                    if hours_ago > 24:
                        continue
                    # Strip URLs before uppercasing to prevent URL fragments (e.g. HTTPS) scoring as tickers
                    raw = pd.get("title", "") + " " + pd.get("selftext", "")
                    text = url_pattern.sub(" ", raw).upper()
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


# ── Polygon.io news buzz ────────────────────────────────────────────────────────

def get_polygon_news_buzz(api_key):
    """
    Returns (lookup_dict, feed_list) using Polygon.io news article ticker mentions.
    Tickers are pre-extracted by Polygon.io — no regex needed.
    feed_list items use the same keys as Reddit feed items (subreddit, ups, etc.)
    so renderRedditFeed() in the frontend works unchanged.
    """
    if not api_key:
        return {}, []

    counts = defaultdict(int)
    feed = []

    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"https://api.polygon.io/v2/reference/news"
        f"?limit=1000&published_utc.gte={yesterday}"
        f"&sort=published_utc&order=desc&apiKey={api_key}"
    )
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"[PolygonNews] HTTP {resp.status_code}")
            return {}, []

        articles = resp.json().get("results", [])
        print(f"[PolygonNews] {len(articles)} articles in last 24h")

        for article in articles:
            tickers = [t for t in article.get("tickers", []) if 2 <= len(t) <= 5 and t.isalpha()]
            for t in tickers:
                counts[t] += 1

            if tickers:
                pub_utc = article.get("published_utc", "")
                hours_ago = 0.0
                if pub_utc:
                    try:
                        pub_dt = datetime.fromisoformat(pub_utc.replace("Z", "+00:00"))
                        hours_ago = round(
                            (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600, 1
                        )
                    except Exception:
                        pass
                feed.append({
                    "id":        article.get("id", ""),
                    "title":     article.get("title", "")[:120],
                    "subreddit": article.get("publisher", {}).get("name", "News"),
                    "ups":       0,
                    "tickers":   tickers[:5],
                    "hours_ago": hours_ago,
                    "url":       article.get("article_url", ""),
                    "is_news":   True,
                })

        feed.sort(key=lambda x: x["hours_ago"])
        lookup = {t: c for t, c in counts.items() if c >= 2}
        return lookup, feed[:40]

    except Exception as e:
        print(f"[PolygonNews] Error: {e}")
        return {}, []


# ── Yahoo Trending ─────────────────────────────────────────────────────────────

def get_yahoo_trending():
    """Returns {ticker: rank} for Yahoo Finance trending tickers (rank 1 = most trending)."""
    try:
        url  = "https://finance.yahoo.com/trending-tickers"
        hdrs = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = requests.get(url, headers=hdrs, timeout=8)
        if resp.status_code != 200:
            print(f"[YahooTrending] HTTP {resp.status_code}")
            return {}
        raw     = re.findall(r'"symbol":"([A-Z]{1,5})"', resp.text)
        # Deduplicate preserving order
        seen    = set()
        symbols = [t for t in raw if not (t in seen or seen.add(t))][:20]
        result  = {ticker: i + 1 for i, ticker in enumerate(symbols)}
        print(f"[YahooTrending] {len(result)} trending tickers: {list(result.keys())[:8]}")
        return result
    except Exception as e:
        print(f"[YahooTrending] Error: {e}")
        return {}


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

def analyze_stock(ticker, yahoo_cats, buzz_lookup, yahoo_trending=None, buzz_label="Reddit"):
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

    reddit_mentions = buzz_lookup.get(ticker, 0)
    if reddit_mentions >= 20:
        score += 15
        signals.append(f"High {buzz_label} buzz ({reddit_mentions})")
    elif reddit_mentions >= 10:
        score += 10
        signals.append(f"{buzz_label} buzz ({reddit_mentions})")
    elif reddit_mentions >= 5:
        score += 5
        signals.append(f"{buzz_label} activity ({reddit_mentions})")

    st_rank = (yahoo_trending or {}).get(ticker, 0)
    if st_rank:
        bonus = 12 if st_rank <= 10 else 8
        score += bonus
        signals.append(f"Yahoo trending (#{st_rank})")

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
        "is_active":          is_active,
        "logo":               profile.get("logo", ""),
        "weburl":             profile.get("weburl", ""),
        "yahoo_trending_rank": st_rank if st_rank else None,
    }


# ── Categorize ─────────────────────────────────────────────────────────────────

def categorize(results, buzz_lookup, universe, yahoo_cats=None, buzz_label="Reddit"):
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
    reddit_candidates = sorted(buzz_lookup.items(), key=lambda x: x[1], reverse=True)

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
                "signals":         [f"{buzz_label} buzz ({mentions} mentions)"],
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
        tickers = re.findall(r'quote\.ashx\?t=([A-Z]{1,5})[&\"]', resp.text)[:20]
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

    print("[scan.py] Fetching Polygon.io news buzz...")
    news_lookup, news_feed = get_polygon_news_buzz(POLYGON_API_KEY)
    print(f"[scan.py] News: {len(news_lookup)} tickers in news")

    if len(reddit_lookup) >= 3:
        buzz_lookup, buzz_feed, buzz_source, buzz_label = reddit_lookup, reddit_feed, "reddit", "Reddit"
    elif news_lookup:
        buzz_lookup, buzz_feed, buzz_source, buzz_label = news_lookup, news_feed, "news", "News"
    else:
        buzz_lookup, buzz_feed, buzz_source, buzz_label = {}, [], "none", "Reddit"
    print(f"[scan.py] Buzz source: {buzz_source} ({len(buzz_lookup)} tickers)")

    print("[scan.py] Fetching Yahoo trending tickers...")
    yahoo_trending = get_yahoo_trending()

    results = []
    for i, ticker in enumerate(universe, 1):
        if i % 10 == 0:
            print(f"[scan.py] Analyzing {i}/{len(universe)}: {ticker}")
        result = analyze_stock(ticker, yahoo_cats, buzz_lookup, yahoo_trending, buzz_label)
        if result:
            results.append(result)
        time.sleep(1.1)

    day_trades, swing_trades, reddit_cards = categorize(results, buzz_lookup, universe, yahoo_cats, buzz_label)
    sector_flow = build_sector_flow(results)

    print("[scan.py] Fetching Fear & Greed, news, earnings, Finviz...")
    fear_greed     = get_fear_greed()
    market_news    = get_market_news()
    earnings_cal   = get_earnings_calendar()
    finviz_unusual = get_finviz_movers()

    confirmed = {card["ticker"] for card in reddit_cards}
    filtered_feed = []
    for item in buzz_feed:
        matched = [t for t in item.get("tickers", []) if t in confirmed]
        if matched:
            enriched = dict(item)
            enriched["confirmed_tickers"] = matched
            filtered_feed.append(enriched)
    display_feed = filtered_feed if filtered_feed else buzz_feed[:20]

    output = {
        "scan_time":      start.isoformat(),
        "next_scan_info": NEXT_SCAN_INFO,
        "total_scanned":  len(universe),
        "day_trades":     day_trades,
        "swing_trades":   swing_trades,
        "buzz_source":    buzz_source,
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
