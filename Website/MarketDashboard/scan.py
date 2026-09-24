"""
MarketDashboard — Standalone Scanner
Runs once, writes results to data/results.json, then exits.
Invoked by GitHub Actions on a schedule (weekdays 8am & 1pm ET).
Run locally: python scan.py
"""

import csv
import io
import json
import math
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
import yfinance as yf


def json_safe(obj):
    """Recursively replace NaN/Infinity with None. Python's json.dump emits
    bare NaN/Infinity tokens (valid Python-JSON) that the browser's JSON.parse
    rejects — a single NaN silently breaks every browser consumer of
    results.json (the dashboard itself and the homepage cards). Run the output
    through this before serializing so the file is always strict JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "results.json")

# API keys come from the environment only — GitHub Actions secrets in CI, or
# your shell when running locally. Never commit a literal fallback: an unset
# secret should fail loudly, not silently authenticate with a leaked key.
FINNHUB_API_KEY = os.environ.get("FINNHUB_KEY", "")
POLYGON_API_KEY = os.environ.get("POLYGON_KEY", "")

DAY_TRADE_MIN_PRICE   = 5.0
DAY_TRADE_MAX_PRICE   = 150.0
MIN_MARKET_CAP        = 20_000_000
MIN_DAY_SCORE         = 10
# Score components: 8(gainer)+5(active)+15(move)+15(buzz)+12(trending)+8(finviz)
#                 + 3(closing strong) + 5(sector leader) = 71
MAX_POSSIBLE_SCORE    = 71


NEXT_SCAN_INFO = "Weekdays 9:35am, 11:30am & 1:30pm ET"


# ── Universe helpers ──────────────────────────────────────────────────────────

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

# Tally of why Finnhub calls failed, printed once in the run summary. Without
# it a partial outage is invisible: the scan completes, writes valid JSON, and
# the homepage just quietly loses cards.
_FINNHUB_FAILS = {}


def _redact(url):
    """Never let an API key reach a log line."""
    return re.sub(r"token=[^&\s]+", "token=***", url)


def _note_finnhub_fail(reason):
    _FINNHUB_FAILS[reason] = _FINNHUB_FAILS.get(reason, 0) + 1
    # Loud on the first occurrence, then counted quietly so 500 dead lookups
    # do not bury the rest of the log.
    if _FINNHUB_FAILS[reason] == 1:
        print(f"[Finnhub] FAILING — {reason}")


def _finnhub_get(url, retries=2, timeout=5):
    """GET a Finnhub URL, returning None on ANY failure.

    This used to `return resp.json()` for every status other than 429. Finnhub
    answers a bad or exhausted key with HTTP 401 and body
    {"error": "Invalid API key."} — a TRUTHY dict — so callers' `if not quote`
    guards passed it through, `quote.get("dp", 0)` gave 0 and
    `profile.get("name")` gave None, and every card was dropped. On 2026-08-31
    that emptied Top Day Trade, Highly Discussed and the swing list at once,
    with nothing in the log to say why.

    Same failure shape as the old empty-POLYGON_KEY bug: a credential problem
    degrading into plausible-looking empty results instead of an error. A
    credential failure must never be indistinguishable from "no data today".
    """
    if not FINNHUB_API_KEY:
        _note_finnhub_fail("FINNHUB_KEY is empty — the secret is missing from this run")
        return None

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
        except Exception as e:
            _note_finnhub_fail(f"request error: {type(e).__name__}")
            return None

        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"[Finnhub] 429 rate-limited — waiting {wait}s "
                  f"(attempt {attempt + 1}/{retries + 1})")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            _note_finnhub_fail(
                f"HTTP {resp.status_code} — {resp.text[:100].strip()} "
                f"[{_redact(url)}]")
            return None

        try:
            data = resp.json()
        except Exception:
            _note_finnhub_fail(f"HTTP 200 but body was not JSON [{_redact(url)}]")
            return None

        # A 200 can still carry an error envelope, and a dict with an "error"
        # key is truthy — exactly the trap this function exists to close.
        if isinstance(data, dict) and data.get("error"):
            _note_finnhub_fail(f"error in 200 body: {str(data['error'])[:100]}")
            return None

        return data

    _note_finnhub_fail(f"gave up after {retries + 1} attempts (429 backoff exhausted)")
    return None


def finnhub_failure_summary():
    """One-line-per-reason recap for the end of a run. Empty when all is well."""
    if not _FINNHUB_FAILS:
        return []
    return [f"{count:>5}x  {reason}" for reason, count in
            sorted(_FINNHUB_FAILS.items(), key=lambda kv: -kv[1])]


def get_stock_quote(ticker):
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}"
    return _finnhub_get(url)


def get_company_profile(ticker):
    url = f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}"
    return _finnhub_get(url)


# ── Social chatter sources (ApeWisdom + StockTwits) ─────────────────────────────

_SOCIAL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

CHATTER_MAX        = 6     # total Market Chatter cards (was 3, Reddit-only)
APEWISDOM_MIN_MENT = 15    # ignore long-tail noise when pulling new names


def get_apewisdom_buzz():
    """ApeWisdom aggregates ticker mentions across Reddit (WSB, stocks, options,
    …) AND reports the 24h-ago count — a broad social-mention source with a
    built-in velocity read. Returns {ticker: {"mentions", "prev", "rank"}}."""
    try:
        r = requests.get("https://apewisdom.io/api/v1.0/filter/all-stocks/page/1",
                         headers={"User-Agent": _SOCIAL_UA}, timeout=15)
        r.raise_for_status()
        rows = r.json().get("results", [])
    except Exception as e:
        print(f"[scan.py] ApeWisdom buzz failed: {e}")
        return {}
    out = {}
    for row in rows:
        t = (row.get("ticker") or "").upper().strip()
        if not t:
            continue
        try:
            out[t] = {
                "mentions": int(row.get("mentions") or 0),
                "prev":     int(row.get("mentions_24h_ago") or 0),
                "rank":     int(row.get("rank") or 0),
            }
        except (ValueError, TypeError):
            continue
    print(f"[scan.py] ApeWisdom: {len(out)} tickers")
    return out


def get_stocktwits_sentiment(ticker):
    """StockTwits (finance-Twitter) per-symbol stream — recent message count and
    the bull/bear lean of sentiment-tagged messages. Returns {"msgs","bull_pct"}
    or None. Free endpoint, best-effort."""
    try:
        r = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json",
                         headers={"User-Agent": _SOCIAL_UA}, timeout=6)
        if r.status_code != 200:   # 429 rate-limit is common and returns fast
            return None
        msgs = r.json().get("messages", [])
    except Exception:
        return None
    if not msgs:
        return None
    bull = bear = 0
    for m in msgs:
        basic = ((m.get("entities") or {}).get("sentiment") or {}).get("basic", "")
        if basic == "Bullish":
            bull += 1
        elif basic == "Bearish":
            bear += 1
    tagged = bull + bear
    return {
        "msgs":     len(msgs),
        "bull_pct": round(100.0 * bull / tagged) if tagged else None,
    }


def enrich_chatter(reddit_cards, apewisdom, result_map):
    """Broaden + enrich the Market Chatter cards with the new social sources,
    WITHOUT touching the day-trade buzz scoring (ApeWisdom counts run far larger
    than the Reddit/Polygon scale, so they'd skew the buzz thresholds):
      - pull in top ApeWisdom names the Reddit/news pass missed (momentum names
        often surface there first), up to CHATTER_MAX cards;
      - attach a `social` block to every card: broad Reddit mention count, the
        24h mention trend (velocity), and StockTwits bull/bear sentiment."""
    existing = {c["ticker"] for c in reddit_cards}

    for t, info in sorted(apewisdom.items(), key=lambda x: x[1]["mentions"], reverse=True):
        if len(reddit_cards) >= CHATTER_MAX:
            break
        if t in existing or info["mentions"] < APEWISDOM_MIN_MENT:
            continue
        if t in result_map:
            card = dict(result_map[t])
        else:
            try:
                quote   = get_stock_quote(t)
                profile = get_company_profile(t)
                if not quote or not profile or not profile.get("name"):
                    continue
                mcap = (profile.get("marketCapitalization", 0) or 0) * 1_000_000
                if mcap < MIN_MARKET_CAP:
                    continue
                card = {
                    "ticker":          t,
                    "name":            profile.get("name", t),
                    "sector":          profile.get("finnhubIndustry", "Unknown"),
                    "current_price":   quote.get("c", 0),
                    "change_pct":      quote.get("dp", 0),
                    "market_cap":      mcap,
                    "score":           0,
                    "signals":         [],
                    "reddit_mentions": 0,
                    "is_gainer":       False,
                    "is_active":       False,
                }
                time.sleep(1.1)
            except Exception:
                continue
        card["mentions"] = card.get("mentions") or info["mentions"]
        reddit_cards.append(card)
        existing.add(t)

    for idx, card in enumerate(reddit_cards):
        t = card["ticker"]
        sources, social = [], {}
        reddit_total = card.get("reddit_mentions") or 0
        aw = apewisdom.get(t)
        if aw and aw["mentions"]:
            reddit_total = max(reddit_total, aw["mentions"])
            if aw["prev"] > 0:
                social["trend_pct"] = round(100.0 * (aw["mentions"] - aw["prev"]) / aw["prev"])
        if reddit_total:
            social["reddit"] = reddit_total
            sources.append("Reddit")
        # StockTwits is best-effort (rate-limits hard) — only try the top cards
        # so a slow/blocked response can't drag out the whole scan.
        if idx < 4:
            st = get_stocktwits_sentiment(t)
            if st:
                social["st_bull"] = st["bull_pct"]
                social["st_msgs"] = st["msgs"]
                sources.append("StockTwits")
            time.sleep(0.4)
        social["sources"] = sources
        card["social"] = social

    return reddit_cards


# Phase B — "Emerging Chatter" velocity signal (data-gathering, not yet surfaced)
EMERGING_MIN_MENTIONS = 20    # real chatter floor (avoid 2->8 noise)
EMERGING_MIN_PREV     = 3     # was at least faintly on the radar yesterday
EMERGING_RATIO        = 2.5   # today's mentions >= 2.5x yesterday's


def compute_emerging_chatter(apewisdom, limit=3):
    """Surface tickers whose chatter is ACCELERATING — quiet yesterday, spiking
    today — the 'catch it before the breakout' candidates. Distinct from the
    most-discussed cards (already hot). Liquidity-gated, ranked by absolute new
    attention (mentions − prev). Output is archived so calculate_outcomes can
    measure whether the signal actually predicts a move before we ever surface
    it as a live trading flag."""
    cands = []
    for t, info in apewisdom.items():
        m, p = info["mentions"], info["prev"]
        if m < EMERGING_MIN_MENTIONS or p < EMERGING_MIN_PREV or m < p * EMERGING_RATIO:
            continue
        cands.append((t, info, m - p))
    cands.sort(key=lambda x: x[2], reverse=True)

    out, checked = [], 0
    for t, info, _jump in cands:
        if len(out) >= limit or checked >= 12:
            break
        checked += 1
        try:
            quote   = get_stock_quote(t)
            profile = get_company_profile(t)
            if not quote or not profile or not profile.get("name"):
                continue
            mcap = (profile.get("marketCapitalization", 0) or 0) * 1_000_000
            if mcap < MIN_MARKET_CAP:
                continue
            out.append({
                "ticker":        t,
                "name":          profile.get("name", t),
                "sector":        profile.get("finnhubIndustry", "Unknown"),
                "mentions":      info["mentions"],
                "prev":          info["prev"],
                "trend_pct":     round(100.0 * (info["mentions"] - info["prev"]) / info["prev"]),
                "current_price": quote.get("c", 0),
                "change_pct":    quote.get("dp", 0),
                "market_cap":    mcap,
            })
            time.sleep(1.1)
        except Exception:
            continue
    return out


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

    # Closing strong: stock is in the upper half of today's intraday range
    # AND finished at-or-above its open. A constructive daily candle —
    # bullish for an overnight hold rather than a fade-into-close.
    if (high and low and high > low
            and current_price > (high + low) / 2.0
            and current_price >= open_):
        score += 3
        signals.append("Closing strong")

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


# ── Sector Leadership ──────────────────────────────────────────────────────────

def apply_sector_leadership(results):
    """Per sector with 2+ scored stocks, the top-scored one earns +5 and a
    'Sector leader' signal. Run AFTER all stocks have been analyzed but
    BEFORE categorization, so the bonus can lift a stock over the score
    cutoffs. Sectors with only one entrant are skipped — there's nothing to
    'lead' against."""
    by_sector = defaultdict(list)
    for r in results:
        if r and r.get("sector") and r.get("sector") != "Unknown":
            by_sector[r["sector"]].append(r)

    leader_count = 0
    for sector, stocks in by_sector.items():
        if len(stocks) < 2:
            continue
        leader = max(stocks, key=lambda x: x.get("score", 0))
        leader["score"] = leader.get("score", 0) + 5
        sigs = leader.setdefault("signals", [])
        sigs.append(f"Sector leader ({sector})")
        leader_count += 1

    print(f"[scan.py] Sector leadership: tagged {leader_count} sector leaders")


# ── Categorize ─────────────────────────────────────────────────────────────────

def categorize(results, buzz_lookup, universe, yahoo_cats=None, buzz_label="Reddit",
               yahoo_trending=None):
    """Build the day-trade list and the chatter cards.

    Day trades: full scan universe (gainers + active), $5–$150, +1.5%+, score 10+.

    There is no swing list. It was taken off the page on 2026-06-18 when swing
    moved to the Coil engine on Pattern Scanner, but this scan kept computing
    it, and two consumers kept reading it: the archive, which recorded whichever
    of day or swing scored higher (so an invisible swing pick could displace the
    Top Day Trade visitors actually saw), and The Analyst, which labelled those
    names "Movers & Shakers" and sent readers to a dashboard with no swing
    section. Benchmarked over 30 days the hidden list trailed SPY by ~2 points at
    the median, where Coil ran slightly ahead. Removed in Sep 2026, along with
    the Russell 1000 download it needed on every run.
    """
    day_cands   = []

    for r in results:
        if not r:
            continue
        price      = r["current_price"]
        market_cap = r["market_cap"]
        chg_pct    = r["change_pct"]

        if (DAY_TRADE_MIN_PRICE <= price <= DAY_TRADE_MAX_PRICE
                and market_cap >= MIN_MARKET_CAP
                and chg_pct >= 1.5
                and r["score"] >= MIN_DAY_SCORE):
            day_cands.append(r)

    day_cands.sort(key=lambda x: x["score"], reverse=True)

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

    return day_cands[:6], reddit_cards


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


# Cyclical vs defensive baskets → the risk-on / risk-off read
CYCLICAL_ETFS  = {"XLK", "XLY", "XLF", "XLI", "XLB", "XLC"}
DEFENSIVE_ETFS = {"XLP", "XLU", "XLV", "XLRE"}

# RRG (Relative Rotation Graph) params — JdK-style, computed vs SPY
RRG_WINDOW = 50   # z-score baseline lookback (trading days, ~10 weeks)
RRG_MOM    = 5    # momentum lookback (~1 week)
RRG_TAIL   = 6    # trail points, sampled weekly


def _sector_returns(close):
    """1D/5D/1M/3M % returns for a close-price series."""
    cur = float(close.iloc[-1])
    def pc(n):
        if len(close) <= n:
            return None
        ref = float(close.iloc[-(n + 1)])
        if not (math.isfinite(ref) and math.isfinite(cur)) or ref == 0:
            return None
        return round((cur - ref) / ref * 100, 2)
    return {"1d": pc(1), "5d": pc(5), "1m": pc(21), "3m": pc(63)}


def _compute_rrg(sector_close, spy_close):
    """JdK-style Relative Rotation Graph coordinates vs SPY. Returns
    {x: RS-Ratio, y: RS-Momentum, quadrant, tail:[{x,y}...]} — both axes
    z-scored against the sector's own history and centered on 100:
    (>100,>100)=Leading, (>100,<100)=Weakening, (<100,>100)=Improving,
    (<100,<100)=Lagging. A read of relative price structure, not a claim to
    reproduce any vendor's proprietary formula."""
    rs = (sector_close / spy_close).dropna()   # relative-strength line
    if len(rs) < RRG_WINDOW + RRG_MOM + 3:
        return None
    mean = rs.rolling(RRG_WINDOW).mean()
    std  = rs.rolling(RRG_WINDOW).std().replace(0, 1e-9)
    ratio = 100 + ((rs - mean) / std).clip(-3, 3)
    mom_raw = ratio.diff(RRG_MOM)
    mmean = mom_raw.rolling(RRG_WINDOW).mean()
    mstd  = mom_raw.rolling(RRG_WINDOW).std().replace(0, 1e-9)
    mom = 100 + ((mom_raw - mmean) / mstd).clip(-3, 3)

    ratio, mom = ratio.dropna(), mom.dropna()
    n = min(len(ratio), len(mom))
    if n < 2:
        return None
    ratio, mom = ratio.iloc[-n:], mom.iloc[-n:]
    x = round(float(ratio.iloc[-1]), 2)
    y = round(float(mom.iloc[-1]), 2)
    quadrant = ("Leading"   if x >= 100 and y >= 100 else
                "Weakening" if x >= 100 and y <  100 else
                "Improving" if x <  100 and y >= 100 else "Lagging")
    start = max(0, n - 1 - RRG_TAIL * RRG_MOM)
    tail = [{"x": round(float(ratio.iloc[i]), 2), "y": round(float(mom.iloc[i]), 2)}
            for i in range(start, n, RRG_MOM)]
    return {"x": x, "y": y, "quadrant": quadrant, "tail": tail}


def get_sector_rotation(scan_results=None):
    """Relative-strength sector rotation vs SPY for the 11 SPDR sector ETFs.
    Per sector: absolute + SPY-relative returns, an RRG position (RS-Ratio /
    RS-Momentum + trail), a rotating-in/out rank shift, and a conviction
    (relative-volume) read. Plus a market-posture (risk-on/off) summary from
    cyclical vs defensive leadership. Optionally enriches each sector with
    top_stocks from today's scan. Returns {sectors, posture, benchmark}."""
    # SPY baseline (relative strength + RRG denominator)
    spy_close, spy_ret = None, {}
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")
        spy_close = spy_hist["Close"].dropna()
        if len(spy_close) >= 2:
            spy_ret = _sector_returns(spy_close)
    except Exception as e:
        print(f"[SectorRot] SPY baseline failed: {e}")

    sectors = []
    for ticker, sector_name in SECTOR_ETFS:
        try:
            hist = yf.Ticker(ticker).history(period="1y")
            if hist.empty or len(hist) < 2:
                continue
            close = hist["Close"].dropna()
            vol   = hist["Volume"].dropna()
            abs_ret = _sector_returns(close)

            # Relative strength vs SPY (positive = outperforming the market)
            rel = {}
            for w in ("1d", "5d", "1m", "3m"):
                a, b = abs_ret.get(w), spy_ret.get(w)
                rel[w] = round(a - b, 2) if (a is not None and b is not None) else None

            rrg = _compute_rrg(close, spy_close) if spy_close is not None else None

            # Conviction: last COMPLETED session's volume vs its prior 20-day
            # norm. The scan runs intraday, so the latest bar is a partial day —
            # use iloc[-2] so the ratio isn't understated.
            rvol = None
            if len(vol) >= 22:
                base = float(vol.iloc[-22:-2].mean())
                if base > 0:
                    rvol = round(float(vol.iloc[-2]) / base, 2)

            # Top scan movers in this sector (unchanged drill-down)
            top_stocks = []
            if scan_results:
                keywords = SECTOR_KEYWORDS.get(sector_name, [])
                matches = [r for r in scan_results
                           if any(kw in (r.get('sector') or '').lower() for kw in keywords)]
                matches.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
                top_stocks = [{'ticker': r['ticker'], 'name': r.get('name', r['ticker']),
                               'change_pct': r.get('change_pct'), 'price': r.get('current_price')}
                              for r in matches[:3]]

            sectors.append({
                'ticker': ticker, 'sector': sector_name,
                'ret_1d': abs_ret['1d'], 'ret_5d': abs_ret['5d'],
                'ret_1m': abs_ret['1m'], 'ret_3m': abs_ret['3m'],
                'rel_1d': rel['1d'], 'rel_5d': rel['5d'],
                'rel_1m': rel['1m'], 'rel_3m': rel['3m'],
                'rvol': rvol, 'rrg': rrg, 'top_stocks': top_stocks,
            })
        except Exception as e:
            print(f"[SectorRot] {ticker}: {e}")

    # Rotating in/out: recent (5D) vs medium (1M) relative-strength rank.
    # A positive shift = the sector's rank improved recently = money rotating in.
    def rank_by(key):
        ordered = sorted([s for s in sectors if s[key] is not None],
                         key=lambda s: s[key], reverse=True)
        return {s['ticker']: i + 1 for i, s in enumerate(ordered)}
    rank_1m, rank_5d = rank_by('rel_1m'), rank_by('rel_5d')
    for s in sectors:
        s['rotation'] = (rank_1m.get(s['ticker'], 0) - rank_5d.get(s['ticker'], 0)
                         if s['ticker'] in rank_1m and s['ticker'] in rank_5d else 0)

    # Market posture: cyclical vs defensive leadership (1M relative strength)
    posture = None
    cyc = [s['rel_1m'] for s in sectors if s['ticker'] in CYCLICAL_ETFS and s['rel_1m'] is not None]
    dfn = [s['rel_1m'] for s in sectors if s['ticker'] in DEFENSIVE_ETFS and s['rel_1m'] is not None]
    if cyc and dfn:
        spread = round(sum(cyc) / len(cyc) - sum(dfn) / len(dfn), 2)
        label = "Risk-on" if spread > 1.0 else "Risk-off" if spread < -1.0 else "Neutral"
        ranked = sorted([s for s in sectors if s['rel_1m'] is not None],
                        key=lambda s: s['rel_1m'], reverse=True)
        posture = {
            'label': label, 'spread': spread,
            'leaders':  [s['sector'] for s in ranked[:2]],
            'laggards': [s['sector'] for s in ranked[-2:]],
        }

    # Default order: strongest medium-term relative strength (leadership) first
    sectors.sort(key=lambda s: (s['rel_1m'] if s['rel_1m'] is not None else -999), reverse=True)
    print(f"[SectorRot] {len(sectors)}/11 sectors | posture={posture['label'] if posture else 'n/a'}")
    return {
        'sectors': sectors,
        'posture': posture,
        'benchmark': {'ticker': 'SPY', 'ret_1d': spy_ret.get('1d'), 'ret_5d': spy_ret.get('5d'),
                      'ret_1m': spy_ret.get('1m'), 'ret_3m': spy_ret.get('3m')},
    }


# ── Supplemental data ─────────────────────────────────────────────────────────

# Fear & Greed is now sourced by scripts/market_temperature_scan.py and
# surfaced inside the Market Temperature card on the homepage. The legacy
# get_fear_greed() helper that lived here was removed once the homepage
# Newsstand stopped reading the fear_greed field from results.json.


def get_market_news():
    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
        # Via _finnhub_get so a 401/429 is logged rather than blowing up on
        # dict slicing inside the bare except below. Keeps the original 8s
        # timeout - these payloads are larger than a single quote.
        data = _finnhub_get(url, timeout=8)
        if not isinstance(data, list):
            return []
        items = data[:12]
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
        # Was resp.json().get("earningsCalendar", []) — on a 401 the error
        # envelope has no such key, so this returned [] and the calendar simply
        # vanished with no error anywhere. Keeps the original 8s timeout.
        data = _finnhub_get(url, timeout=8)
        if not isinstance(data, dict):
            return []
        items = data.get("earningsCalendar", [])[:30]
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
    """Tickers on Finviz's unusual-volume screener — feeds the +8 'Unusual
    volume (Finviz)' scoring signal.

    Finviz's redesign moved links from `quote.ashx?t=` to `stock?t=`, so the
    old regex silently matched nothing and the signal was dead for every scan
    (no error — just a permanently empty list). Match the `data-boxover-ticker`
    attribute instead: it carries the clean symbol and is the same attribute
    the insider and newsstand scans now rely on."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&o=-volume&f=sh_price_o5"
        resp = requests.get(url, headers=headers, timeout=10)
        tickers = re.findall(r'data-boxover-ticker="([A-Z0-9.\-]{1,6})"', resp.text)[:20]
        tickers = list(dict.fromkeys(tickers))
        if not tickers:
            print("[Finviz] No tickers parsed — markup may have changed again")
        return tickers
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

    # Sector leadership pass — applied before categorize so the +5 bonus
    # can lift a stock over the day-trade score cutoff.
    apply_sector_leadership(results)

    day_trades, reddit_cards = categorize(
        results, buzz_lookup, universe, yahoo_cats, buzz_label, yahoo_trending,
    )

    print("[scan.py] Enriching Market Chatter (ApeWisdom + StockTwits)...")
    apewisdom   = get_apewisdom_buzz()
    chatter_map = {c["ticker"]: c for c in (day_trades + reddit_cards)}
    reddit_cards = enrich_chatter(reddit_cards, apewisdom, chatter_map)
    chatter_emerging = compute_emerging_chatter(apewisdom)
    print(f"[scan.py] Emerging chatter (accelerating): {[c['ticker'] for c in chatter_emerging]}")

    print("[scan.py] Fetching earnings calendar...")
    earnings_cal = get_earnings_calendar()

    print("[scan.py] Fetching sector rotation data...")
    sector_rotation = get_sector_rotation(results)

    print(f"[scan.py] Enriching nominees with earnings data...")
    enrich_with_earnings(day_trades + reddit_cards, earnings_cal)

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
    for nominee in day_trades + reddit_cards:
        raw = nominee.get("score", 0)
        nominee["score_normalized"] = round(min(raw / MAX_POSSIBLE_SCORE * 100, 100))

    output = {
        "scan_time":        start.isoformat(),
        "next_scan_info":   NEXT_SCAN_INFO,
        "total_scanned":    len(universe),
        "day_trades":       day_trades,
        "buzz_source":      buzz_source,
        "reddit_cards":     reddit_cards,
        "chatter_emerging": chatter_emerging,
        "sector_rotation":  sector_rotation,
        "reddit_feed":      display_feed,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    # Serialize first (allow_nan=False as a strict guard): if any NaN/Infinity
    # slipped past json_safe it raises here, before the file is truncated, so
    # the last-good results.json survives instead of being half-written.
    payload = json.dumps(json_safe(output), indent=2, allow_nan=False)
    with open(OUTPUT_FILE, "w") as f:
        f.write(payload)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[scan.py] Done in {elapsed}s — {len(day_trades)}D {len(reddit_cards)}R")

    # An empty board is a normal outcome on a red tape, but it is also what a
    # dead API key looks like. Say which, every run, so the two are never
    # confused again.
    fails = finnhub_failure_summary()
    if fails:
        print(f"[scan.py] !! FINNHUB DEGRADED — {sum(_FINNHUB_FAILS.values())} failed calls:")
        for line in fails:
            print(f"[scan.py]    {line}")
        if not (day_trades or reddit_cards):
            print("[scan.py] !! Board is EMPTY and Finnhub was failing — treat the "
                  "empty result as unproven, not as 'no candidates today'.")
    else:
        print("[scan.py] Finnhub: all calls OK")

    print(f"[scan.py] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
