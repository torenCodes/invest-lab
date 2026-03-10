# The Analyst Dashboard — Project Context

This document is a handoff brief for continuing development in Claude Code.
Read `app.py` and `dashboard.html` alongside this file for full context.

---

## What This Is

A personal stock analysis dashboard. Users type a ticker and receive a fundamentals
report: valuation verdict, Graham Number, SEC filing dates, key ratios, and an
AI-generated commentary paragraph. Three pre-scanned example stocks (AAPL, MSFT, NVDA)
are shown on load for quick reference.

**Not financial advice — educational/personal use only.**

---

## Architecture

```
app.py  (Flask backend)
 ├── GET  /                → serves dashboard.html
 ├── POST /api/analyze     → fetches + scores a ticker on demand
 ├── GET  /api/prescan     → returns status + results of background prescan
 └── GET  /ping            → health check

dashboard.html  (single-file frontend)
 └── Calls /api/analyze on user submit; polls /api/prescan on load

results.json  (prescan cache, auto-generated)
 └── Written on each prescan run; loaded on next startup to avoid re-fetching
```

**Run server:** `python app.py` → auto-detects port starting at 8095

---

## Data Sources

| Source | Method | API Key? | Notes |
|--------|--------|----------|-------|
| Yahoo Finance (yfinance) | Python library | No | All fundamental data: P/E, PEG, margins, growth, etc. |
| SEC EDGAR | REST API (public) | No | `company_tickers.json` for CIK lookup; `data.sec.gov/submissions/` for filings |

**User-Agent for SEC:** `TheInvestLab personal-research@example.com` (required by SEC policy)

---

## Prescan Behaviour

On startup:
1. Load `results.json` if it exists.
2. If all entries are present **and error-free**, mark prescan `done` — no re-fetch.
3. If the file is missing, incomplete, or **any entry contains an `"error"` key**, kick
   off a fresh background prescan.

The error check (step 3) prevents stale rate-limit errors from being served indefinitely
after a bad startup — especially on Render free tier where yfinance 429s are common
during market hours.

**Prescan tickers:** `AAPL`, `MSFT`, `NVDA`
**Inter-ticker delay:** 4 seconds (increased from 1.5s on Mar 9 2026 to reduce 429s)
**yfinance retry delays:** `[5, 15, 30]` seconds on rate-limit (increased Mar 9 2026)
**Result cache TTL:** 300 seconds (5 min) in-memory

---

## Valuation Scoring

Score range: −100 (very overpriced) to +100 (very undervalued).

| Signal | Points |
|--------|--------|
| P/E well below sector median (< 70%) | +25 |
| P/E below sector median | +10 |
| P/E 25–80% above sector median | −12 to −25 |
| PEG < 1.0 | +20 |
| PEG 1.0–1.5 | +8 |
| PEG > 2.5 | −15 |
| Revenue growth > 20% | +15 |
| Revenue growth 8–20% | +8 |
| Revenue declining | −15 |
| Net margin > 20% | +10 |
| Net margin > 10% | +5 |
| Negative net margin | −20 |
| Price < Graham Number (margin of safety) | +10 to +20 |
| Price > 2× Graham Number | −15 |
| ROE > 25% | +8 |
| Negative ROE | −10 |
| Debt/Equity > 200% | −12 |

**Verdict labels:** `UNDERVALUED` (≥25), `FAIRLY VALUED` (−15 to 24), `OVERPRICED` (<−15), `SPECULATIVE` (pre-profit + high revenue growth)

**Graham Number formula:** `√(22.5 × trailingEPS × bookValuePerShare)`

**Sector P/E benchmarks** are hardcoded in `SECTOR_PE` dict in `app.py`.

---

## Key Design Decisions & History

- **Prescan error-skip fix (Mar 9 2026):** Startup logic now checks all cached results
  for `"error"` keys before marking prescan as done. Previously, a rate-limited prescan
  would write errors to `results.json`, and those errors would be served forever on
  every subsequent restart.
- **Increased retry delays (Mar 9 2026):** yfinance retry sequence bumped from
  `[3, 7, 15]s` to `[5, 15, 30]s`; inter-ticker prescan delay from 1.5s to 4s.
  Both changes target market-hours rate limiting.
- **Retry endpoint + button (Mar 10 2026):** `POST /api/retry-prescan` resets prescan
  state and triggers a fresh background prescan without requiring a service restart.
  The frontend shows a "↺ Retry Prescan" button on error cards.
- **Polygon.io news feed (Mar 10 2026):** `get_polygon_news(ticker)` fetches last 7 days
  of news from Polygon.io `/v2/reference/news`. Result included as `recent_news[]` on
  every analysis response and rendered as a "Recent News" section in each mini-card.
  Key: `POLYGON_KEY` env var (default hardcoded).
- **File-based prescan cache:** `results.json` persists between restarts so the prescan
  doesn't re-fetch on every dyno spin-up (important on Render free tier).
- **SEC EDGAR integration:** CIK lookup + most-recent 10-K/10-Q filing dates displayed
  on each card.
- **In-memory result cache:** User-triggered analyses are cached for 5 minutes to avoid
  redundant yfinance calls during a session.

---

## Known Issues / Potential Improvements

- **yfinance rate limits during market hours** — especially for high-traffic tickers
  like AAPL/MSFT/NVDA. The prescan can fail on first startup if the server comes up
  during peak hours; it will retry on next restart.
- **No real-time price updates** — data is fetched once per user request, not streamed.
- **Polygon.io key available** (`P9fRbZP9VAKhjwABMtvcS7tfcYGU6z1T`) — could replace
  or supplement yfinance for more reliable real-time quotes.

---

## Possible Next Features

- **Polygon.io integration** for real-time quotes (bypasses yfinance rate limits)
- **News feed** per ticker via Polygon.io `/v2/reference/news`
- **Watchlist** — save tickers and auto-refresh on a schedule
- **Historical chart** via Polygon.io aggregates endpoint
