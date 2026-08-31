"""
Newsstand Scanner — Standalone
Fetches market context data (earnings calendar, news, unusual volume)
and writes to MarketDashboard/data/newsstand.json for the homepage.

Invoked by GitHub Actions on schedule.
Run locally: python scripts/newsstand_scan.py
"""

import csv
import io
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "MarketDashboard", "data", "newsstand.json")

# Environment only — no committed fallback (see MarketDashboard/scan.py note).
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
POLYGON_KEY = os.environ.get("POLYGON_KEY", "")

NEXT_SCAN_INFO = "Weekdays at 10:30am, 1pm, 4pm ET"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


# ── Russell 3000 universe (for earnings calendar filter) ─────────────────────

IWV_URL = ("https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/"
           "1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund")


def fetch_russell3000_universe():
    """Fetch the iShares IWV (Russell 3000) holdings CSV and return a set of
    equity tickers. The Russell 3000 ≈ top ~3000 US stocks by market cap,
    covering S&P 500, Russell 2000, and mid-cap contenders.

    Returns an empty set on failure (callers should treat that as "no filter").
    """
    print("[newsstand] Fetching Russell 3000 universe from iShares IWV...")
    try:
        r = requests.get(IWV_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[newsstand] IWV fetch failed: {e}")
        return set()

    tickers = set()
    reader = csv.reader(io.StringIO(r.text))
    in_holdings = False
    for row in reader:
        if not row:
            continue
        if not in_holdings:
            # Header row — first cell is exactly "Ticker"
            if row[0].strip().lower() == "ticker":
                in_holdings = True
            continue
        # Data row — only keep Equity rows with a real ticker
        if len(row) < 4:
            continue
        ticker    = row[0].strip().upper()
        asset_cls = row[3].strip() if len(row) > 3 else ""
        if not ticker or asset_cls.lower() != "equity":
            continue
        # Normalize away punctuation — iShares/Finnhub/Yahoo disagree on
        # share-class formatting (BRKB vs BRK.B vs BRK-B). Strip on both
        # sides of the comparison.
        tickers.add(_norm_ticker(ticker))

    print(f"[newsstand] Universe: {len(tickers)} tickers loaded")
    return tickers


def _norm_ticker(t):
    """Canonicalize a ticker for set membership: uppercase, strip . and -."""
    return (t or "").upper().replace(".", "").replace("-", "").strip()


# ── Finnhub Earnings Calendar ────────────────────────────────────────────────

def fetch_earnings(days_ahead=14, universe=None):
    """Fetch upcoming earnings from Finnhub for the next N days.

    If `universe` is a non-empty set, entries whose symbol is not in that set
    are dropped — used to cap the calendar at the Russell 3000 so small-cap
    earnings don't overwhelm the homepage card.

    Implementation note: Finnhub's calendar endpoint caps a multi-day response
    at ~1500 entries and serves later dates first when the cap is hit, silently
    dropping the earliest 1-2 days from the result. Workaround: query day by
    day so each request returns a complete single-day list.
    """
    print("[newsstand] Fetching earnings calendar (day-by-day)...")
    today = datetime.now(timezone.utc).date()

    url = "https://finnhub.io/api/v1/calendar/earnings"

    raw_total = 0
    notable = []
    dropped_universe = 0
    dropped_reported = 0
    fetch_failures = 0

    for offset in range(days_ahead + 1):
        day = (today + timedelta(days=offset)).isoformat()
        try:
            r = requests.get(url, params={
                "from": day, "to": day, "token": FINNHUB_KEY,
            }, timeout=15)
            r.raise_for_status()
            day_raw = r.json().get("earningsCalendar", [])
        except Exception as e:
            fetch_failures += 1
            print(f"[newsstand] Earnings fetch failed for {day}: {e}")
            continue

        raw_total += len(day_raw)
        for e in day_raw:
            # Require an EPS estimate (filters out analyst-less micro-caps)
            if e.get("epsEstimate") is None:
                continue
            # Skip entries that have already reported (epsActual filled in).
            # Today's pre-market names accumulate actuals after ~9am ET, so
            # the scan picks them up as "already happened" not "upcoming".
            if e.get("epsActual") is not None:
                dropped_reported += 1
                continue
            symbol = (e.get("symbol") or "").upper().strip()
            # Russell 3000 filter (skip if caller didn't supply a universe).
            # Normalize both sides: iShares IWV uses "BRKB", Finnhub uses "BRK.B".
            if universe and _norm_ticker(symbol) not in universe:
                dropped_universe += 1
                continue
            notable.append({
                "date":             e.get("date"),
                "symbol":           symbol,
                "eps_estimate":     e.get("epsEstimate"),
                "eps_actual":       e.get("epsActual"),
                "revenue_estimate": e.get("revenueEstimate"),
                "revenue_actual":   e.get("revenueActual"),
                "hour":             e.get("hour", ""),  # bmo = before market open, amc = after market close
                "quarter":          e.get("quarter"),
                "year":             e.get("year"),
            })

        # Stay well under Finnhub's free-tier 60 req/min limit
        time.sleep(0.2)

    print(f"[newsstand] Earnings: scanned {days_ahead + 1} days, "
          f"{raw_total} raw entries from Finnhub, {fetch_failures} day(s) failed")
    if universe:
        print(f"[newsstand] Earnings: dropped {dropped_universe} outside Russell 3000, "
              f"{dropped_reported} already reported")

    # Group by date so we can spread coverage across days instead of letting
    # a single heavy day (50+ reports) eat the whole 50-entry cap.
    PER_DAY_CAP   = 8
    DAYS_TO_SHOW  = 7   # first 7 calendar days that actually have entries

    by_date = {}
    for x in notable:
        by_date.setdefault(x["date"], []).append(x)

    # Within each day, surface larger companies first (revenue estimate desc),
    # then alphabetical. Larger companies tend to be the recognizable names
    # users want to see — keeps obscure micro-caps off the top of each day.
    for date_key in by_date:
        by_date[date_key].sort(
            key=lambda x: (-(x.get("revenue_estimate") or 0), x["symbol"])
        )
        by_date[date_key] = by_date[date_key][:PER_DAY_CAP]

    notable = []
    for date_key in sorted(by_date.keys())[:DAYS_TO_SHOW]:
        notable.extend(by_date[date_key])

    print(f"[newsstand] Earnings: {len(notable)} notable entries across "
          f"{min(len(by_date), DAYS_TO_SHOW)} days")
    return notable


# ── Polygon.io Market News ───────────────────────────────────────────────────

def fetch_news(limit=15, retries=3):
    """Fetch latest market news from Polygon.io with retry logic."""
    print("[newsstand] Fetching market news...")
    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
        "apiKey": POLYGON_KEY,
    }

    results = []
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                wait = 15 * attempt
                print(f"[newsstand] Polygon rate-limited (429), waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            print(f"[newsstand] News: {len(results)} articles from Polygon.io")
            break
        except Exception as e:
            print(f"[newsstand] News fetch attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(5 * attempt)

    if not results:
        print("[newsstand] News: falling back to Finnhub general news")
        results = _fetch_news_finnhub(limit)

    articles = []
    for a in results:
        # Normalize — Polygon and Finnhub have different field names
        tickers = a.get("tickers") or a.get("related", "").split(",") if a.get("related") else []
        tickers = [t.strip() for t in tickers if t.strip()][:5]
        publisher = a.get("publisher", {})
        source = publisher.get("name", "") if isinstance(publisher, dict) else (a.get("source", "") or str(publisher))
        articles.append({
            "title":     a.get("title") or a.get("headline", ""),
            "url":       a.get("article_url") or a.get("url", ""),
            "source":    source,
            "published": a.get("published_utc") or a.get("datetime", ""),
            "tickers":   tickers,
            "snippet":   (a.get("description") or a.get("summary", "") or "")[:200],
        })

    return articles


def _fetch_news_finnhub(limit=15):
    """Fallback: fetch general news from Finnhub."""
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": FINNHUB_KEY}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        items = r.json()
        print(f"[newsstand] Finnhub fallback: {len(items)} articles")
        return items[:limit]
    except Exception as e:
        print(f"[newsstand] Finnhub news fallback also failed: {e}")
        return []


# ── Finviz Unusual Volume ────────────────────────────────────────────────────

MIN_UNUSUAL_VOLUME_PRICE = 7.00  # Filter out penny stocks ($7 floor)


def fetch_unusual_volume(limit=10):
    """Scrape Finviz unusual volume screener. Positive movers only.
    Filters out stocks priced under MIN_UNUSUAL_VOLUME_PRICE to avoid penny-stock noise."""
    print("[newsstand] Fetching unusual volume...")
    # f=sh_price_o5  → pre-filter at Finviz to price > $5 so we don't burn
    # the 20-row budget on penny stocks. Python post-filter below raises to $7.
    url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&o=-volume&f=sh_price_o5"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[newsstand] Finviz fetch failed: {e}")
        return []

    tickers = []

    # Finviz screener table: find the main results table
    # The data rows are in a table with class "screener_table" or similar
    table = soup.find("table", class_="screener_table")
    if not table:
        # Fallback: try finding by ID or broader search
        tables = soup.find_all("table")
        for t in tables:
            if t.find("td", class_="screener-body-table-nw"):
                table = t
                break

    if not table:
        print("[newsstand] Finviz: could not find screener table")
        return []

    rows = table.find_all("tr")[1:]  # Skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        # Finviz (Jul 2026 redesign) carries the clean symbol as a data
        # attribute on the cell — the anchor's text is now decorated with
        # logo/styling elements and yields only the first letter.
        ticker_cell = cells[1]
        ticker = (ticker_cell.get("data-boxover-ticker") or "").strip()
        if not ticker:
            ticker_link = ticker_cell.find("a")
            href = ticker_link.get("href", "") if ticker_link else ""
            m = re.search(r"[?&]t=([A-Za-z0-9.\-]+)", href)
            ticker = m.group(1) if m else (ticker_link.text.strip() if ticker_link else "")

        name_cell = cells[2]
        name_link = name_cell.find("a")
        name = name_link.text.strip() if name_link else ""
        if not name:
            name = (ticker_cell.get("data-boxover-company") or "").strip()

        # Price is in column index 8 (0-based), change in 9
        try:
            price_text = cells[8].text.strip().replace(",", "")
            price = float(price_text) if price_text else None
        except (ValueError, IndexError):
            price = None

        try:
            change_text = cells[9].text.strip().replace("%", "")
            change_pct = float(change_text) if change_text else None
        except (ValueError, IndexError):
            change_pct = None

        # Volume is the LAST column (10) in the current v=111 layout —
        # cells[6] is Market Cap (the old code was showing caps as "volume").
        # Finviz serves a raw share count; compact it to 95.9M style.
        volume_text = ""
        if len(cells) > 10:
            raw = cells[10].text.strip().replace(",", "")
            if raw.isdigit():
                v = int(raw)
                volume_text = (f"{v/1e9:.2f}B" if v >= 1e9 else
                               f"{v/1e6:.1f}M" if v >= 1e6 else
                               f"{v/1e3:.0f}K" if v >= 1e3 else str(v))

        if (ticker
                and change_pct is not None and change_pct > 0
                and price is not None and price >= MIN_UNUSUAL_VOLUME_PRICE):
            tickers.append({
                "ticker":     ticker,
                "name":       name,
                "price":      price,
                "change_pct": change_pct,
                "volume":     volume_text,
            })
            if len(tickers) >= limit:
                break

    print(f"[newsstand] Unusual volume: {len(tickers)} positive tickers "
          f"(price >= ${MIN_UNUSUAL_VOLUME_PRICE:.2f})")
    return tickers


# ── Trading Conditions (proprietary market-regime read) ──────────────────────

SECTOR_ETFS = ["XLK", "XLY", "XLF", "XLI", "XLB", "XLC", "XLP", "XLU", "XLV", "XLRE", "XLE"]


def _todays_tape(spy_h, yf):
    """What is the tape doing RIGHT NOW, as opposed to this month?

    Every other input on this card is slow by construction. Trend is price
    against the 50-day, momentum is a 5-day lookback, VIX and the 10-year
    barely twitch on a single session. On 2026-08-31 that produced "Favorable"
    while SPY was down 0.56%, pinned at 10% of its daily range, with 10 of 11
    sector ETFs red — every input was technically right and the verdict was
    still wrong, because nothing in it measured today.

    Reads three things off the current session:
      • direction  — close against the prior session's close
      • conviction — where in the day's range price is sitting. Near the low
        means sellers held control into the print; near the high means buyers
        absorbed the move. A -0.5% day off the lows is a different tape from
        a -0.5% day at the lows.
      • breadth    — how many sector ETFs are green. Separates "one mega-cap
        dragged the index" from "everything is being sold".

    Note the deliberate contrast with _participation(), which DROPS today's
    bar: volume needs a completed session to mean anything, direction does
    not. Same frame, opposite treatment, on purpose.

    Outside market hours this describes the most recent completed session,
    which is still the honest answer to "what is the tape doing".
    """
    try:
        import numpy as np
    except ImportError:
        return None

    try:
        df = spy_h.dropna(subset=["Close"])
        if len(df) < 2:
            return None
        cur, prev = df.iloc[-1], df.iloc[-2]
        last  = float(cur["Close"])
        prevc = float(prev["Close"])
        hi, lo, op = float(cur["High"]), float(cur["Low"]), float(cur["Open"])
        if not all(np.isfinite(x) for x in (last, prevc, hi, lo, op)) or prevc <= 0:
            return None
    except Exception as e:
        print(f"[newsstand] session read failed: {e}")
        return None

    chg      = (last / prevc - 1.0) * 100.0
    from_open = (last / op - 1.0) * 100.0 if op > 0 else 0.0
    rng_pos  = (last - lo) / (hi - lo) if hi > lo else 0.5

    session_date = df.index[-1]
    try:
        is_live = session_date.date() == datetime.now().date()
    except Exception:
        is_live = False

    # ── Direction is the backbone of the score ──
    if   chg >=  0.75: pts = 2
    elif chg >=  0.25: pts = 1
    elif chg >= -0.25: pts = 0
    elif chg >= -0.75: pts = -1
    else:              pts = -2

    # ── Conviction: where in the range did it settle ──
    if   rng_pos <= 0.25: pts -= 1
    elif rng_pos >= 0.75: pts += 1

    # ── Breadth across the sector ETFs ──
    green = total = None
    try:
        b = yf.download(SECTOR_ETFS, period="5d", interval="1d",
                        progress=False, auto_adjust=False)["Close"]
        cur_row, prev_row = b.iloc[-1], b.iloc[-2]
        green = total = 0
        for t in SECTOR_ETFS:
            try:
                a, p = float(cur_row[t]), float(prev_row[t])
                if not (np.isfinite(a) and np.isfinite(p) and p > 0):
                    continue
                total += 1
                if a >= p:
                    green += 1
            except Exception:
                continue
        if total:
            frac = green / total
            if   frac <= 0.20: pts -= 1        # near-universal selling
            elif frac >= 0.80: pts += 1        # near-universal buying
        else:
            green = total = None
    except Exception as e:
        print(f"[newsstand] sector breadth unavailable: {e}")
        green = total = None

    pts = max(-3, min(3, pts))

    if   pts >=  2: read, tone = "Strong", "good"
    elif pts ==  1: read, tone = "Firm", "good"
    elif pts ==  0: read, tone = "Flat", "neutral"
    elif pts == -1: read, tone = "Soft", "neutral"
    else:           read, tone = "Weak", "bad"

    where = ("at the lows" if rng_pos <= 0.25 else
             "at the highs" if rng_pos >= 0.75 else
             "mid-range")
    bits = [f"{chg:+.2f}% vs prior close", f"{where} ({rng_pos * 100:.0f}% of range)"]
    if total:
        bits.append(f"{green}/{total} sectors green")
    if not is_live:
        bits.append("last completed session")

    return {
        "points": pts,
        "signal": {
            "label": "Today's tape",
            "sub":   "Session move + breadth",
            "value": f"{chg:+.2f}%",
            "read":  read,
            "tone":  tone,
        },
        "detail":        " · ".join(bits),
        "change_pct":    round(chg, 2),
        "from_open_pct": round(from_open, 2),
        "range_pos":     round(rng_pos, 3),
        "sectors_green": green,
        "sectors_total": total,
        "live":          bool(is_live),
    }


def _participation(vol):
    """Is there enough volume in the tape to trade, and is that normal for the
    calendar? Returns a signal dict, a score contribution and a headline clause.

    Volume is strongly seasonal. Ten years of our own SPY data puts the week
    after Christmas ~35% and late August ~9% below what a normal week runs
    against its own 50-day average, so a naive "volume is light" read would cry
    wolf every summer and every holiday. We therefore report two things: the
    ABSOLUTE thinness a trader has to deal with today, which is what sets the
    score, and how that compares with the same ISO week in prior years, which
    is what explains it.

    The seasonal expectation is the median of the SAME 5d/50d statistic in that
    week of earlier years. An earlier draft compared the 5d/50d ratio against an
    index built on the annual median; those are two different baselines and the
    quotient meant nothing.

    Today's bar is always dropped. The morning scan runs an hour after the open
    with the session a fraction complete, and a partial bar reads as a volume
    collapse. Using completed sessions only also keeps the card stable across
    all three daily runs instead of drifting as the day fills in.
    """
    try:
        import numpy as np
    except ImportError:
        return None

    v = vol.dropna()
    if len(v) < 60:
        return None
    try:
        if v.index[-1].date() == datetime.now().date():
            v = v.iloc[:-1]
    except Exception:
        pass
    if len(v) < 60:
        return None

    recent5 = float(v.tail(5).mean())
    prior5  = float(v.tail(10).head(5).mean())
    base50  = float(v.tail(50).mean())
    if not np.isfinite(recent5) or not np.isfinite(base50) or base50 <= 0:
        return None
    raw = recent5 / base50

    # ── What does this calendar week normally look like? ──
    expected = adjusted = None
    try:
        ratio = (v.rolling(5).mean() / v.rolling(50).mean()).dropna()
        iso   = ratio.index.isocalendar()
        wk    = np.asarray(iso["week"], dtype=int)
        yr    = np.asarray(ratio.index.year, dtype=int)
        cur_w, cur_y = int(wk[-1]), int(yr[-1])
        prior = ratio.to_numpy()[(yr < cur_y) & (wk == cur_w)]
        if len(prior) >= 10:                      # ~2 full weeks of prior years
            expected = float(np.median(prior))
            if expected > 0:
                adjusted = raw / expected
    except Exception as e:
        print(f"[newsstand] seasonal baseline unavailable: {e}")

    # ── Absolute band drives the score: thin is thin, whatever the month ──
    if   raw >= 1.10: read, tone, pts = "Heavy", "good", 1
    elif raw >= 0.92: read, tone, pts = "Normal", "neutral", 0
    elif raw >= 0.80: read, tone, pts = "Light", "neutral", -1
    else:             read, tone, pts = "Thin", "bad", -2

    # ── Seasonal context adjusts the wording, and softens by at most a notch ──
    note = None
    if adjusted is not None:
        if adjusted < 0.80:
            note = "unusually light even for this week of the year"
        elif adjusted > 1.20:
            note = "busier than this week normally runs"
        elif pts < 0:
            # Below its 50-day norm, but only as far below as this week usually
            # sits. A slow tape to plan around, not a signal that anything broke.
            pts += 1
            tone = "neutral"
            note = "about normal for this week of the year"

    drift = (recent5 / prior5 - 1.0) if prior5 else 0.0
    if   drift >= 0.10:  direction = "building"
    elif drift <= -0.10: direction = "fading"
    else:                direction = "steady"

    last = v.index[-1]
    when = "early" if last.day <= 10 else ("mid" if last.day <= 20 else "late")
    season_label = f"{when} {last.strftime('%B')}"

    # ── One sentence appended to the verdict headline ──
    clause = None
    if read in ("Thin", "Light"):
        if note and note.startswith("unusually"):
            clause = (f"Participation is unusually light even for {season_label} and still "
                      f"{direction}, so expect wider spreads, slower fills and more failed "
                      f"breakouts than the verdict alone implies.")
        else:
            clause = (f"Volume is under its 50-day norm, though that is ordinary for "
                      f"{season_label} — plan for a slow tape rather than reading it as a warning.")
    elif read == "Heavy":
        clause = ("Volume is running above its 50-day norm, so there is real participation "
                  "behind these moves rather than a thin-tape drift.")

    detail = f"{recent5 / 1e6:.0f}M vs {base50 / 1e6:.0f}M avg"
    if note:
        detail += f" · {note}"

    return {
        "points": pts,
        "clause": clause,
        "signal": {
            "label": "Participation",
            # Kept to the length of its sibling subs on purpose: .tc-sig-vals is
            # flex-shrink:0, the same shape that crushed the Market Temperature
            # heads, so the left column is the one that has to give.
            "sub":   "Volume vs 50-day norm",
            "value": f"{(raw - 1) * 100:+.0f}%",
            "read":  read,
            "tone":  tone,
        },
        "detail":    detail,
        "ratio":     round(raw, 3),
        "expected":  round(expected, 3) if expected is not None else None,
        "adjusted":  round(adjusted, 3) if adjusted is not None else None,
        "direction": direction,
        "drift_pct": round(drift * 100, 1),
    }


def fetch_trading_conditions():
    """A tactical read on whether the current backdrop favors active day/swing
    trading. Synthesizes SPY trend + momentum, participation (volume, adjusted
    for how thin that calendar week normally runs), VIX (volatility), and the
    10-year yield into a verdict (Favorable / Mixed / Cautious / Risk-Off) with
    color-coded signal readouts. This is the proprietary replacement for the
    commoditized news feed — the macro interpreted for a trader, not headlines."""
    print("[newsstand] Computing trading conditions...")
    try:
        import yfinance as yf
    except ImportError:
        print("[newsstand] yfinance unavailable, skipping trading conditions")
        return None

    def frame(sym, period):
        try:
            h = yf.Ticker(sym).history(period=period, auto_adjust=False)
            return h if h is not None and not h.empty else None
        except Exception as e:
            print(f"[newsstand] {sym} fetch failed: {e}")
            return None

    def closes(sym, period):
        h = frame(sym, period)
        return h["Close"].dropna() if h is not None else None

    # 10y of SPY so the participation read can learn what a given calendar week
    # normally looks like. Every trend/momentum read below uses .tail() or
    # .iloc[-n], so the longer window leaves those numbers unchanged.
    spy_h = frame("SPY", "10y")
    spy = spy_h["Close"].dropna() if spy_h is not None else None
    vix = closes("^VIX", "2mo")
    tnx = closes("^TNX", "2mo")
    if spy is None or len(spy) < 50 or vix is None or len(vix) < 6:
        print("[newsstand] insufficient data for trading conditions")
        return None

    price = float(spy.iloc[-1])
    ma20  = float(spy.tail(20).mean())
    ma50  = float(spy.tail(50).mean())
    ma200 = float(spy.tail(200).mean()) if len(spy) >= 200 else None
    ret5  = (price / float(spy.iloc[-6]) - 1.0) * 100.0

    vix_level = float(vix.iloc[-1])
    vix_chg5  = vix_level - float(vix.iloc[-6])

    tnx_level = tnx_chg5 = None
    if tnx is not None and len(tnx) >= 6:
        tl, t5 = float(tnx.iloc[-1]), float(tnx.iloc[-6])
        if tl > 20:           # Yahoo quotes ^TNX ~10x (43.9 -> 4.39%)
            tl /= 10.0; t5 /= 10.0
        tnx_level, tnx_chg5 = tl, tl - t5

    signals, pts = [], 0

    # ── Today's tape — FIRST, because it is the only input that measures now ──
    tape = _todays_tape(spy_h, yf) if spy_h is not None else None
    if tape:
        pts += tape["points"]
        signals.append(tape["signal"])

    # ── Trend (SPY vs its moving averages) ──
    above50, above20 = price > ma50, price > ma20
    golden = ma200 is not None and ma50 > ma200
    if above50 and golden:
        t_read, t_tone, tp = "Uptrend", "good", 3
    elif above50 or above20:
        t_read, t_tone, tp = "Mixed trend", "neutral", 1
    else:
        t_read, t_tone, tp = "Downtrend", "bad", -1
    pts += tp
    signals.append({"label": "Market trend", "sub": "SPY vs moving averages",
                    "value": ("Above" if above50 else "Below") + " 50-day",
                    "read": t_read, "tone": t_tone})

    # ── Momentum (SPY 1-week change) ──
    if   ret5 >= 1.5: m_read, m_tone, mp = "Strong", "good", 2
    elif ret5 >= 0.0: m_read, m_tone, mp = "Firm", "good", 1
    elif ret5 >= -1.5: m_read, m_tone, mp = "Soft", "neutral", 0
    else:             m_read, m_tone, mp = "Weak", "bad", -1
    pts += mp
    signals.append({"label": "5-day momentum", "sub": "SPY one-week change",
                    "value": ("+" if ret5 >= 0 else "") + f"{ret5:.1f}%",
                    "read": m_read, "tone": m_tone})

    # ── Participation (is there volume behind the move?) ──
    part = _participation(spy_h["Volume"]) if spy_h is not None and "Volume" in spy_h else None
    if part:
        pts += part["points"]
        signals.append(part["signal"])

    # ── Volatility (VIX) ──
    rising = vix_chg5 > 1.5
    if   vix_level > 26: v_read, v_tone, vp = "High fear", "bad", -2
    elif vix_level >= 20: v_read, v_tone, vp = "Elevated", "neutral", 0
    elif vix_level >= 12: v_read, v_tone, vp = ("Calm but rising" if rising else "Calm"), \
                                               ("neutral" if rising else "good"), (0 if rising else 1)
    else:                v_read, v_tone, vp = "Complacent", "neutral", 0
    pts += vp
    signals.append({"label": "Volatility (VIX)", "sub": "Implied S&P volatility",
                    "value": f"{vix_level:.1f}", "read": v_read, "tone": v_tone})

    # ── 10-year yield (rate pressure on momentum/growth) ──
    if tnx_level is not None:
        if tnx_chg5 is not None and tnx_chg5 >= 0.25:
            y_read, y_tone, yp = "Rising fast", "bad", -1
        elif tnx_chg5 is not None and tnx_chg5 <= -0.15:
            y_read, y_tone, yp = "Easing", "good", 0
        else:
            y_read, y_tone, yp = "Stable", "neutral", 0
        pts += yp
        signals.append({"label": "10-year yield", "sub": "Rate pressure on growth",
                        "value": f"{tnx_level:.2f}%", "read": y_read, "tone": y_tone})

    # Range is now roughly -10..+10: trend 3, momentum 2, VIX 1, yield 0,
    # participation -2..+1, today's tape -3..+3. The bands are set so that a
    # calm uptrend on a flat day still reads Favorable, while a broad decline
    # drags it to Cautious no matter how healthy the monthly trend looks —
    # which was the whole failure this replaces.
    if   pts >=  5: verdict = "Favorable"
    elif pts >=  2: verdict = "Mixed"
    elif pts >= -1: verdict = "Cautious"
    else:           verdict = "Risk-Off"

    headlines = {
        "Favorable": "The trend is up and volatility is manageable, a constructive backdrop "
                     "where momentum and breakout setups have room to run.",
        "Mixed":     "The tape is sending mixed signals, so it pays to stay selective, keep "
                     "position sizes measured, and let the cleaner setups come to you.",
        "Cautious":  "Conditions are choppy and participation is thinning, which favors quick "
                     "trades and tighter risk over holding momentum overnight.",
        "Risk-Off":  "Trend and volatility are working against momentum longs, a defensive "
                     "backdrop where smaller size and mean-reversion setups make more sense "
                     "than chasing strength.",
    }

    headline = headlines[verdict]

    # Today's tape leads the headline when it disagrees with the slow inputs —
    # that disagreement is exactly the information a trader needs at 10:30am.
    if tape and tape["points"] <= -2:
        broad = (f", with only {tape['sectors_green']} of {tape['sectors_total']} sectors green"
                 if tape.get("sectors_total") else "")
        headline = (f"Today's tape is working against the longer-term trend: SPY "
                    f"{tape['change_pct']:+.2f}% and "
                    f"{'holding near the session low' if tape['range_pos'] <= 0.25 else 'off its highs'}"
                    f"{broad}. " + headline)
    elif tape and tape["points"] >= 2:
        headline = (f"Today's tape is confirming the trend: SPY {tape['change_pct']:+.2f}% "
                    f"and closing strong. " + headline)

    if part and part.get("clause"):
        headline += " " + part["clause"]

    print(f"[newsstand] Trading conditions: {verdict} (score {pts})")
    if tape:
        print(f"[newsstand]   today's tape {tape['signal']['read']} "
              f"({tape['detail']}), {tape['points']:+d}pt")
    if part:
        print(f"[newsstand]   participation {part['signal']['read']} "
              f"{part['signal']['value']} ({part['detail']}), {part['direction']}, "
              f"{part['points']:+d}pt")

    out = {
        "verdict":  verdict,
        "score":    pts,
        "headline": headline,
        "signals":  signals,
        "updated":  datetime.now(timezone.utc).isoformat(),
    }
    if tape:
        out["session"] = {
            "change_pct":    tape["change_pct"],
            "from_open_pct": tape["from_open_pct"],
            "range_pos":     tape["range_pos"],
            "sectors_green": tape["sectors_green"],
            "sectors_total": tape["sectors_total"],
            "live":          tape["live"],
            "detail":        tape["detail"],
        }
    if part:
        out["participation"] = {
            "ratio":     part["ratio"],
            "expected":  part["expected"],
            "adjusted":  part["adjusted"],
            "direction": part["direction"],
            "drift_pct": part["drift_pct"],
            "detail":    part["detail"],
        }
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    start = datetime.now(timezone.utc)
    print(f"[newsstand] Starting scan at {start.isoformat()}")

    universe = fetch_russell3000_universe()
    earnings = fetch_earnings(days_ahead=14, universe=universe)

    time.sleep(1)
    unusual_volume = fetch_unusual_volume(limit=15)

    # Proprietary market-regime read — replaces the commoditized news feed
    trading_conditions = fetch_trading_conditions()

    output = {
        "scan_time":          start.isoformat(),
        "next_scan_info":     NEXT_SCAN_INFO,
        "trading_conditions": trading_conditions,
        "earnings":           earnings,
        "unusual_volume":     unusual_volume,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    tc = trading_conditions["verdict"] if trading_conditions else "n/a"
    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[newsstand] Done in {elapsed}s — conditions: {tc}, "
          f"{len(earnings)} earnings, {len(unusual_volume)} volume")
    print(f"[newsstand] Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
