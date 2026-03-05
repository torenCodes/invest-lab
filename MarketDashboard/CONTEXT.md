# Market Scanner Dashboard — Project Context

This document is a handoff brief for continuing development in Claude Code.
Read `app.py` and `dashboard.html` alongside this file for full context.

---

## What This Is

A personal stock trading dashboard built for daily use. It runs a background
scanner that identifies green (upward-moving only) stock candidates for day
trading and swing trading, enriches them with Reddit sentiment and market data,
and presents everything in a single-page web dashboard.

**Not financial advice — educational/personal use only.**

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask backend + all scanner logic |
| `dashboard.html` | Single-file frontend (HTML/CSS/JS, no framework) |
| `scan_results.json` | Auto-generated on each scan cycle; read by the frontend |
| `CONTEXT.md` | This file |

**Run with:** `python app.py` then open the URL printed in the terminal (auto-detects a free port starting at 8080 — port 5000 is blocked on Mac by AirPlay).

---

## Architecture

```
app.py (Flask)
 ├── Background thread: run_scan() — runs every 15 minutes
 │    ├── get_yahoo_movers_categorized()   → gainers / losers / active (top 60 each)
 │    ├── get_reddit_buzz()                → mention counts + live feed (5 subreddits)
 │    ├── analyze_stock()                  → Finnhub quote + profile per ticker
 │    ├── categorize()                     → sorts into day / swing / reddit nominees
 │    ├── build_sector_flow()              → groups green stocks by sector
 │    ├── get_fear_greed()                 → CNN Fear & Greed Index
 │    ├── get_market_news()                → Finnhub general news feed
 │    ├── get_earnings_calendar()          → Finnhub earnings today + tomorrow
 │    └── get_finviz_movers()              → Finviz unusual volume scrape
 │
 ├── Writes → scan_results.json (all data in one file)
 │
 └── Flask routes
      ├── GET /              → serves dashboard.html (read from disk, not static folder)
      ├── GET /api/status    → live scan progress (polled every 3s during scan)
      ├── GET /api/results   → full scan_results.json contents
      ├── GET /api/reddit_feed → live reddit feed from shared state
      └── GET /ping          → health check

dashboard.html (vanilla JS, Chart.js via CDN)
 └── Polls /api/status every 3s (scanning) or 15s (idle)
 └── Polls /api/results and updates panels only when data changes
```

---

## Data Sources

| Source | Method | API Key? | Notes |
|--------|--------|----------|-------|
| Yahoo Finance | HTTP scrape (regex on HTML) | No | Top 60 gainers, losers, most-active |
| Finnhub | REST API | Yes (free tier) | Quotes, profiles, news, earnings |
| Reddit | Public JSON API (`*.reddit.com/*.json`) | No | 5 subreddits: wallstreetbets, stocks, StockMarket, options, daytrading |
| CNN Fear & Greed | `production.dataviz.cnn.io` public endpoint | No | Score 0–100 + history |
| Finviz | HTTP scrape | No | Unusual volume screener |

**Finnhub API Key:** `d6703v9r01qmckkbjg6gd6703v9r01qmckkbjg70` (free tier)
**Finnhub free tier limits:** 60 API calls/minute. The scanner sleeps 1.1s between tickers to stay within limits.

---

## Scoring System

Each stock gets a score built from signals. Thresholds determine if it qualifies
as a nominee.

### Score Components
| Signal | Points |
|--------|--------|
| Top Yahoo gainer | +15 |
| High volume (Yahoo active list) | +5 |
| Strong move ≥5% | +15 |
| Good move ≥3% | +10 |
| Moderate move ≥1.5% | +5 |
| High Reddit buzz (≥20 mentions) | +15 |
| Reddit buzz (≥10 mentions) | +10 |
| Reddit activity (≥5 mentions) | +5 |
| Is Yahoo gainer (swing bonus) | +5 |

### Qualification Thresholds
| Category | Min Price | Max Price | Min Market Cap | Min Score | Min % Change |
|----------|-----------|-----------|----------------|-----------|--------------|
| Day Trade | $2.00 | $100.00 | $20M | 10 | +1.5% |
| Swing Trade | $2.00 | None | $50M | 8 | +1.0% |

**Green-only rule:** Any stock with `change_pct <= 0` is immediately discarded.
This was a deliberate design decision — the user does not short sell.

---

## Dashboard Panels

1. **Day Trades** — top 3 nominees, expandable cards with OHLC detail + trade plan
2. **Swing Trades** — top 3 nominees, same card format
3. **Reddit Buzz** — top 3 Reddit-trending tickers (independent of Yahoo universe)
4. **Sector Flow** — Chart.js horizontal bar chart, avg % gain per sector
5. **Live Reddit Feed** — top 40 high-upvote posts mentioning tickers (last 24h), deduplicated by post ID
6. **Fear & Greed** — CNN index score with gradient bar indicator
7. **Unusual Volume** — Finviz ticker tags
8. **Market News** — Finnhub headlines
9. **Earnings Calendar** — today + tomorrow, BMO/AMC badges

---

## Key Design Decisions & History

- **Port auto-detection:** Port 5000 is blocked on Mac by AirPlay Receiver. App
  tries 8080, 8081, 8888, 9000, 3000 in order.
- **`dashboard.html` served by reading file directly** (not Flask static folder)
  because `static_folder` caused blank page issues depending on working directory.
- **`BASE_DIR`** anchors all file paths to the script's own directory, not the
  shell's working directory. Critical for `scan_results.json` landing in the
  right place.
- **Reddit buzz decoupled from Yahoo universe:** Early versions only showed
  Reddit tickers that also appeared in Yahoo movers. Now Reddit nominees are
  looked up independently via Finnhub.
- **Sector chart and Reddit feed are hash-guarded:** They only re-render when
  data actually changes, preventing jarring redraws during the 3-second poll cycle.
- **Reddit dedup uses post `id` field**, not URL — URLs can vary in trailing
  slashes causing the same post to appear twice (once from `hot`, once from `new`).
- **Losers explicitly excluded:** Early bug had `is_loser` awarding +15 score
  same as gainers, and `abs(change_pct)` letting red stocks through. Both fixed.

---

## Known Issues / Potential Improvements

- **Yahoo scraping is fragile** — Yahoo changes their HTML structure occasionally.
  The current regex `"symbol":"([A-Z]{1,5})"` works as of early 2026 but may break.
- **Reddit noise filtering** — the NOISE set is a large hardcoded list. Occasional
  false positives (common words that are also valid tickers) still slip through.
- **No historical price data** — Finnhub free tier doesn't include OHLCV history.
  This limits technical analysis signals (no RSI, MACD, moving averages, etc.).
  Upgrading to a paid tier or adding yfinance as a fallback would unlock this.
- **Single-user, local only** — no auth, no multi-user support. Designed to run
  on a personal machine.
- **No persistent scan history** — `scan_results.json` is overwritten each cycle.
  Could add dated archive files for trend comparison.
- **Earnings calendar missing weekend/holiday awareness** — queries today+tomorrow
  literally, which may return empty on weekends.
- **Finviz scrape** — Finviz occasionally blocks scrapers or changes HTML. If
  unusual volume stops working, check the regex `quote\.ashx\?t=([A-Z]{1,5})"`.

---

## Possible Next Features

- **Technical indicators** via `yfinance` (free, no key) — RSI, MACD, volume
  ratio, 52-week high proximity
- **Push notifications** — send an alert when a high-score ticker appears
- **Watchlist integration** — user-defined tickers always checked regardless of
  Yahoo universe
- **Historical scan archive** — save each scan's JSON with timestamp for trend review
- **Pre-market data** — Finnhub supports pre/post market quotes on paid tier
- **Options flow** — unusual options activity is a strong day-trade signal;
  Unusual Whales has a free tier
- **Twitter/X sentiment** — similar to Reddit scraping but for $TICKER mentions
- **Scheduled morning run** — cron job or launchd (Mac) to auto-start at 8am ET
- **Export to email** — the original `scanner_free_tier.py` had an email digest
  feature (Gmail SMTP) that could be re-integrated as a "send report" button
