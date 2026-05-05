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
import yfinance as yf

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "results.json")

FINNHUB_API_KEY = os.environ.get("FINNHUB_KEY", "d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70")
POLYGON_API_KEY = os.environ.get("POLYGON_KEY", "P9fRbZP9VAKhjwABMtvcS7tfcYGU6z1T")

DAY_TRADE_MIN_PRICE   = 5.0
DAY_TRADE_MAX_PRICE   = 150.0
SWING_TRADE_MIN_PRICE = 20.0
MIN_MARKET_CAP        = 20_000_000
MIN_MARKET_CAP_SWING  = 50_000_000
MIN_DAY_SCORE         = 10
MIN_SWING_SCORE       = 8
MAX_POSSIBLE_SCORE    = 63   # 8(gainer)+5(active)+15(move)+15(buzz)+12(trending)+8(finviz)

NEXT_SCAN_INFO = "Weekdays 9:35am, 11:30am & 1:30pm ET"

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

    def _fetch_articles(extra_params=""):
        url = (
            f"https://api.polygon.io/v2/reference/news"
            f"?limit=50&sort=published_utc&order=desc{extra_params}&apiKey={api_key}"
        )
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            print(f"[PolygonNews] HTTP {r.status_code}: {r.text[:300]}")
            return []
        return r.json().get("results", [])

    try:
        # Try with date filter first; fall back to no filter if it returns nothing
        articles = _fetch_articles(f"&published_utc.gte={yesterday}")
        print(f"[PolygonNews] {len(articles)} articles (date-filtered)")
        if not articles:
            articles = _fetch_articles()
            print(f"[PolygonNews] {len(articles)} articles (no date filter fallback)")

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
        # Threshold of 1 — any article mention counts; ranked by frequency
        lookup = {t: c for t, c in counts.items() if c >= 1}
        print(f"[PolygonNews] {len(lookup)} tickers with >= 1 mention")
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

def _finnhub_get(url, retries=2):
    """GET a Finnhub URL with simple 429 backoff."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"[Finnhub] 429 — waiting {wait}s...")
                time.sleep(wait)
                continue
            return resp.json()
        except Exception:
            return None
    return None


def get_stock_quote(ticker):
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}"
    return _finnhub_get(url)


def get_company_profile(ticker):
    url = f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}"
    return _finnhub_get(url)


# ── Stock analysis ─────────────────────────────────────────────────────────────

def analyze_stock(ticker, yahoo_cats, buzz_lookup, yahoo_trending=None, buzz_label="Reddit",
                  buzz_source="news", finviz_set=None):
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

    # Gainer: reduced from +15 to +8 to avoid double-dip with strong move signal
    if is_gainer:
        score += 8
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
    # Thresholds differ by source: Polygon article counts are smaller than Reddit weighted scores
    if buzz_source in ("news", "mixed"):
        _hi, _mid, _lo = 12, 6, 3
    else:
        _hi, _mid, _lo = 20, 10, 5
    if reddit_mentions >= _hi:
        score += 15
        signals.append(f"High {buzz_label} buzz ({reddit_mentions})")
    elif reddit_mentions >= _mid:
        score += 10
        signals.append(f"{buzz_label} buzz ({reddit_mentions})")
    elif reddit_mentions >= _lo:
        score += 5
        signals.append(f"{buzz_label} activity ({reddit_mentions})")

    st_rank = (yahoo_trending or {}).get(ticker, 0)
    if st_rank:
        bonus = 12 if st_rank <= 10 else 8
        score += bonus
        signals.append(f"Yahoo trending (#{st_rank})")

    if finviz_set and ticker in finviz_set:
        score += 8
        signals.append("Unusual volume (Finviz)")

    market_cap = profile.get("marketCapitalization", 0) * 1_000_000
    sector     = profile.get("finnhubIndustry", "Unknown")

    return {
        "ticker":              ticker,
        "name":                profile.get("name", ticker),
        "sector":              sector,
        "current_price":       current_price,
        "change_pct":          change_pct,
        "high":                high,
        "low":                 low,
        "open":                open_,
        "prev_close":          prev_close,
        "score":               score,
        "signals":             signals,
        "reddit_mentions":     reddit_mentions,
        "market_cap":          market_cap,
        "is_gainer":           is_gainer,
        "is_active":           is_active,
        "logo":                profile.get("logo", ""),
        "weburl":              profile.get("weburl", ""),
        "yahoo_trending_rank": st_rank if st_rank else None,
    }


# ── Categorize ─────────────────────────────────────────────────────────────────

def categorize(results, buzz_lookup, universe, yahoo_cats=None, buzz_label="Reddit", yahoo_trending=None):
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

    # No more cross-section dedup. A high-quality $20+ name with strong
    # momentum is legitimately both a day-trade play (intraday) AND a swing
    # play (multi-day large cap) — the section headers already frame them
    # differently. Excluding day picks from swing was leaving swing empty
    # whenever the top scorers happened to also meet swing criteria.

    result_map = {r["ticker"]: r for r in results if r}
    reddit_candidates = sorted(buzz_lookup.items(), key=lambda x: x[1], reverse=True)

    # Chatter nominees: no green-only filter — buzz is valuable regardless of today's movement
    reddit_cards = []
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
            reddit_cards.append(card)
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
            st_rank = (yahoo_trending or {}).get(ticker, 0)
            signals = [f"{buzz_label} buzz ({mentions} mentions)"]
            if st_rank:
                signals.append(f"Yahoo trending (#{st_rank})")
            card = {
                "ticker":              ticker,
                "mentions":            mentions,
                "name":                profile.get("name", ticker),
                "sector":              profile.get("finnhubIndustry", "Unknown"),
                "current_price":       quote.get("c", 0),
                "change_pct":          change_pct,
                "high":                quote.get("h", 0),
                "low":                 quote.get("l", 0),
                "open":                quote.get("o", 0),
                "prev_close":          quote.get("pc", 0),
                "market_cap":          market_cap,
                "score":               0,
                "signals":             signals,
                "reddit_mentions":     mentions,
                "is_gainer":           False,
                "is_active":           False,
                "yahoo_trending_rank": st_rank if st_rank else None,
            }
            reddit_cards.append(card)
            time.sleep(1.1)
        except Exception:
            continue

    return day_cands[:6], swing_cands[:6], reddit_cards


# ── Earnings enrichment ────────────────────────────────────────────────────────

def enrich_with_earnings(nominees, earnings_cal):
    """Adds earnings_info dict to each nominee card in-place."""
    upcoming_by_ticker = {e["ticker"]: e for e in (earnings_cal or [])}

    for card in nominees:
        ticker = card.get("ticker", "")
        if not ticker:
            continue

        info = {"upcoming": None, "recent": None}

        if ticker in upcoming_by_ticker:
            e = upcoming_by_ticker[ticker]
            info["upcoming"] = {"date": e.get("date", ""), "hour": e.get("hour", "")}

        try:
            url  = f"https://finnhub.io/api/v1/stock/earnings?symbol={ticker}&limit=4&token={FINNHUB_API_KEY}"
            resp = requests.get(url, timeout=6)
            if resp.status_code == 200:
                eps_list = resp.json()
                if isinstance(eps_list, list):
                    for eq in eps_list:
                        actual   = eq.get("actual")
                        estimate = eq.get("estimate")
                        period   = eq.get("period", "")
                        if actual is not None and estimate is not None and period:
                            try:
                                report_dt = datetime.strptime(period, "%Y-%m-%d")
                                days_ago  = (datetime.now() - report_dt).days
                                if 0 <= days_ago <= 90:
                                    surprise_pct = 0
                                    if estimate and estimate != 0:
                                        surprise_pct = round(((actual - estimate) / abs(estimate)) * 100, 1)
                                    info["recent"] = {
                                        "period":       period,
                                        "actual":       round(float(actual), 2),
                                        "estimate":     round(float(estimate), 2),
                                        "beat":         actual >= estimate,
                                        "surprise_pct": surprise_pct,
                                    }
                                    break
                            except Exception:
                                pass
            time.sleep(0.5)
        except Exception as e:
            print(f"[Earnings] {ticker}: {e}")

        card["earnings_info"] = info


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


# ── Sector Rotation (SPDR ETFs) ────────────────────────────────────────────────

SECTOR_ETFS = [
    ("XLK",  "Technology"),
    ("XLF",  "Financials"),
    ("XLV",  "Health Care"),
    ("XLE",  "Energy"),
    ("XLI",  "Industrials"),
    ("XLC",  "Comm. Services"),
    ("XLY",  "Cons. Discretionary"),
    ("XLP",  "Cons. Staples"),
    ("XLRE", "Real Estate"),
    ("XLB",  "Materials"),
    ("XLU",  "Utilities"),
]

# Keyword lists to fuzzy-match Finnhub finnhubIndustry strings → SPDR sector names
SECTOR_KEYWORDS = {
    "Technology":          ["technology", "software", "semiconductor", "hardware", "electronics"],
    "Financials":          ["financial", "finance", "bank", "insurance", "asset management", "investment"],
    "Health Care":         ["health", "biotech", "pharmaceutical", "medical", "drug", "clinical"],
    "Energy":              ["energy", "oil", "gas", "petroleum", "coal", "renewable energy"],
    "Industrials":         ["industrial", "aerospace", "defense", "machinery", "logistics", "transport", "construction"],
    "Comm. Services":      ["communication", "media", "entertainment", "telecom", "internet services", "broadcasting"],
    "Cons. Discretionary": ["consumer cyclical", "retail", "automobile", "auto", "leisure", "restaurant", "apparel", "hotel"],
    "Cons. Staples":       ["consumer defensive", "consumer staples", "food", "beverage", "household", "grocery", "tobacco"],
    "Real Estate":         ["real estate", "reit"],
    "Materials":           ["basic material", "chemical", "mining", "metal", "steel", "aluminum", "packaging"],
    "Utilities":           ["utility", "utilities", "electric", "power", "water", "gas distribution"],
}


def get_sector_rotation(scan_results=None):
    """Fetch 1D/5D/1M/3M % returns for all 11 SPDR sector ETFs via yfinance.
    Optionally enriches each sector with top_stocks from today's scan results."""
    result = []
    for ticker, sector_name in SECTOR_ETFS:
        try:
            hist = yf.Ticker(ticker).history(period='3mo')
            if hist.empty or len(hist) < 2:
                continue
            close = hist['Close']
            current = float(close.iloc[-1])

            def pct_change(n, _close=close, _current=current):
                if len(_close) <= n:
                    return None
                ref = float(_close.iloc[-(n + 1)])
                return round((_current - ref) / ref * 100, 2)

            # Find top movers from today's scan that belong to this sector
            top_stocks = []
            if scan_results:
                keywords = SECTOR_KEYWORDS.get(sector_name, [])
                matches = [
                    r for r in scan_results
                    if any(kw in (r.get('sector') or '').lower() for kw in keywords)
                ]
                matches.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
                top_stocks = [
                    {
                        'ticker':     r['ticker'],
                        'name':       r.get('name', r['ticker']),
                        'change_pct': r.get('change_pct'),
                        'price':      r.get('current_price'),
                    }
                    for r in matches[:3]
                ]

            result.append({
                'ticker':     ticker,
                'sector':     sector_name,
                'ret_1d':     pct_change(1),
                'ret_5d':     pct_change(5),
                'ret_1m':     pct_change(21),
                'ret_3m':     pct_change(63),
                'top_stocks': top_stocks,
            })
        except Exception as e:
            print(f"[SectorRot] {ticker}: {e}")

    result.sort(key=lambda x: (x['ret_1d'] or 0), reverse=True)
    print(f"[SectorRot] Fetched {len(result)}/11 sectors")
    return result


# ── Supplemental data ─────────────────────────────────────────────────────────

# Fear & Greed is now sourced by scripts/market_temperature_scan.py and
# surfaced inside the Market Temperature card on the homepage. The legacy
# get_fear_greed() helper that lived here was removed once the homepage
# Newsstand stopped reading the fear_greed field from results.json.


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
        today       = datetime.now().strftime("%Y-%m-%d")
        five_days   = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={five_days}&token={FINNHUB_API_KEY}"
        resp = requests.get(url, timeout=8)
        items = resp.json().get("earningsCalendar", [])[:30]
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
    start = datetime.now(timezone.utc)

    yahoo_cats = get_yahoo_movers_categorized()
    # Exclude losers — they fail the change_pct > 0 check anyway, wasting Finnhub quota
    universe   = sorted(yahoo_cats["gainers"] | yahoo_cats["active"])
    print(f"[scan.py] Universe: {len(universe)} tickers (gainers + active only)")

    print("[scan.py] Fetching Yahoo trending tickers...")
    yahoo_trending = get_yahoo_trending()

    print("[scan.py] Fetching Reddit buzz...")
    reddit_lookup, reddit_feed = get_reddit_buzz()
    print(f"[scan.py] Reddit: {len(reddit_lookup)} tickers with buzz")

    print("[scan.py] Fetching Polygon.io news buzz...")
    news_lookup, news_feed = get_polygon_news_buzz(POLYGON_API_KEY)
    print(f"[scan.py] News: {len(news_lookup)} tickers in news")

    # Polygon news is always primary; merge Reddit counts as bonus when available
    buzz_lookup = dict(news_lookup)
    buzz_feed   = news_feed
    if reddit_lookup:
        for ticker, count in reddit_lookup.items():
            buzz_lookup[ticker] = buzz_lookup.get(ticker, 0) + count
        buzz_source = "mixed" if news_lookup else "reddit"
        if not news_lookup:
            buzz_feed = reddit_feed
    else:
        buzz_source = "news" if news_lookup else "none"

    # Yahoo Trending as guaranteed fallback when both Polygon and Reddit fail
    if not buzz_lookup and yahoo_trending:
        buzz_lookup = {ticker: (21 - rank) for ticker, rank in yahoo_trending.items()}
        buzz_source = "trending"
        buzz_feed   = []
        print(f"[scan.py] Buzz fallback: Yahoo Trending ({len(buzz_lookup)} tickers)")

    buzz_label = ("Reddit"   if buzz_source == "reddit"
                  else "Trending" if buzz_source == "trending"
                  else "News")
    print(f"[scan.py] Buzz source: {buzz_source} ({len(buzz_lookup)} tickers)")

    print("[scan.py] Fetching Finviz unusual volume...")
    finviz_unusual = get_finviz_movers()
    finviz_set     = set(finviz_unusual)

    results = []
    for i, ticker in enumerate(universe, 1):
        if i % 10 == 0:
            print(f"[scan.py] Analyzing {i}/{len(universe)}: {ticker}")
        result = analyze_stock(ticker, yahoo_cats, buzz_lookup, yahoo_trending, buzz_label,
                               buzz_source, finviz_set)
        if result:
            results.append(result)
        time.sleep(1.1)

    day_trades, swing_trades, reddit_cards = categorize(results, buzz_lookup, universe, yahoo_cats, buzz_label, yahoo_trending)

    print("[scan.py] Fetching earnings calendar...")
    earnings_cal = get_earnings_calendar()

    print("[scan.py] Fetching sector rotation data...")
    sector_rotation = get_sector_rotation(results)

    print(f"[scan.py] Enriching nominees with earnings data...")
    enrich_with_earnings(day_trades + swing_trades + reddit_cards, earnings_cal)

    confirmed = {card["ticker"] for card in reddit_cards}
    filtered_feed = []
    for item in buzz_feed:
        matched = [t for t in item.get("tickers", []) if t in confirmed]
        if matched:
            enriched = dict(item)
            enriched["confirmed_tickers"] = matched
            filtered_feed.append(enriched)
    display_feed = filtered_feed if filtered_feed else buzz_feed[:20]

    # Last-resort feed: fetch Finnhub company news for chatter picks when no feed exists
    if not display_feed and reddit_cards:
        print("[scan.py] No chatter feed — fetching Finnhub news for chatter picks...")
        for card in reddit_cards[:3]:
            ticker = card["ticker"]
            try:
                today    = datetime.now().strftime("%Y-%m-%d")
                week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                url  = (f"https://finnhub.io/api/v1/company-news"
                        f"?symbol={ticker}&from={week_ago}&to={today}&token={FINNHUB_API_KEY}")
                resp = requests.get(url, timeout=8)
                if resp.status_code == 200:
                    for item in resp.json()[:5]:
                        headline = item.get("headline", "")[:120]
                        if not headline:
                            continue
                        pub_ts    = item.get("datetime", 0)
                        hours_ago = round((time.time() - pub_ts) / 3600, 1) if pub_ts else 0.0
                        display_feed.append({
                            "id":                str(item.get("id", "")),
                            "title":             headline,
                            "subreddit":         item.get("source", "News"),
                            "ups":               0,
                            "tickers":           [ticker],
                            "confirmed_tickers": [ticker],
                            "hours_ago":         hours_ago,
                            "url":               item.get("url", ""),
                            "is_news":           True,
                        })
                time.sleep(1.1)
            except Exception as e:
                print(f"[FinnhubNews] {ticker}: {e}")
        display_feed.sort(key=lambda x: x["hours_ago"])
        display_feed = display_feed[:20]
        print(f"[scan.py] Chatter feed: {len(display_feed)} Finnhub headlines for chatter picks")

    # Normalize scores to 0-100 scale for frontend display
    for nominee in day_trades + swing_trades + reddit_cards:
        raw = nominee.get("score", 0)
        nominee["score_normalized"] = round(min(raw / MAX_POSSIBLE_SCORE * 100, 100))

    output = {
        "scan_time":        start.isoformat(),
        "next_scan_info":   NEXT_SCAN_INFO,
        "total_scanned":    len(universe),
        "day_trades":       day_trades,
        "swing_trades":     swing_trades,
        "buzz_source":      buzz_source,
        "reddit_cards":     reddit_cards,
        "sector_rotation":  sector_rotation,
        "reddit_feed":      display_feed,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[scan.py] Done in {elapsed}s — {len(day_trades)}D {len(swing_trades)}S {len(reddit_cards)}R")
    print(f"[scan.py] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
