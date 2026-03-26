# Site Expansion Plan — theinvestlab.com
*Last updated: March 2026*

---

## Inspiration Sources

| Site | What It Does Well |
|------|-------------------|
| **AskLivermore** (asklivermore.com) | Methodology transparency, credibility proof (historical picks), quality scoring system, earnings integration, clean freemium model |
| **Blossom Social** (blossomsocial.com) | Portfolio + dividend tracking, community discovery angle, all-in-one feel |

**What we're NOT copying:** Blossom's social feed / community features. This stays a data-driven research tool, not a social platform.

---

## Overview

The current site does a solid job of presenting what it *is* — but not enough of what it *does for the visitor*. The expansion plan focuses on three pillars:

1. **Credibility** — prove the dashboards work (track record, methodology transparency)
2. **Value density** — give visitors more useful data before they ever click into a dashboard
3. **Depth** — new dashboards and content that attract and retain serious stock pickers

---

## Phase 1 — Homepage & Static Site Upgrades
*Target: Quick wins, no new backend required*

### ✅ 1.1 — Metrics / Credibility Bar
~~Implemented then removed~~ — user decided to keep homepage clean. Revisit if the site grows.

### ~~1.2 — "How It Works" Section~~
Removed — user prefers to keep methodology proprietary. Reserved for Methodology Page (2.1).

### ✅ 1.3 — Track Record / Past Nominees Section *(DONE — Mar 2026)*
Fully implemented as an **automated system**:
- `scripts/archive_nominee.py` runs after every scan, saves top pick to `MarketDashboard/data/nominees_archive.json`
- `scripts/calculate_outcomes.py` fills 30-day outcome prices weekly (GitHub Actions)
- Homepage fetches archive from `https://invest-movers-shakers.onrender.com/data/nominees_archive.json`
- Seeded with 4 historical picks (AXTI, SMCI, PYPL, PLTR) with real outcomes

### ✅ 1.4 — Expanded Market Snapshot Cards *(DONE — Mar 2026)*
- Fear & Greed strip added above preview cards
- Sector card reads from `sector_rotation[0]` (updated from `sector_flow`)

### ~~1.5 — FAQ Section~~
Removed — user found it overkill.

### 1.6 — Email / Newsletter CTA
Deferred — no newsletter setup yet. Revisit when traffic warrants.

---

## Phase 2 — New Static Pages
*Target: SEO, depth, repeat visits*

### 2.1 — Methodology Page (`/methodology.html`)
A full deep-dive on how each dashboard works:
- Scoring formulas (e.g., `composite = quality × 0.45 + beaten_up × 0.40 + recovery_bonus`)
- Data sources per dashboard
- What each signal means and why it matters
- "What this tool is / what it isn't" framing

This is the most powerful trust-builder for technically-minded visitors. AskLivermore's entire brand rests on pattern transparency — we can do the same for fundamental + sentiment scoring.

### 2.2 — Glossary Page (`/glossary.html`)
Definitions for every term used across the dashboards:
- RSI (Relative Strength Index), 52-week drawdown, YTD performance
- Graham Number, P/E, PEG ratio, FCF yield
- ETF overlap scoring, cross-ETF consensus
- Cluster buys, SEC Form 4, open-market purchases
- Fear & Greed index, Finnhub sentiment, Reddit mentions

Good for SEO ("what is RSI in stocks", etc.) and for new investors using the dashboards.

### 2.3 — Resources Page (`/resources.html`)
Curated list of trusted financial tools, data sources, and reading material:
- Data sources we actually use (Finnhub, Polygon.io, SEC EDGAR, yfinance)
- Recommended screeners (Finviz, Barchart)
- Books and resources for systematic investing
- Could include tasteful affiliate links (Tastytrade, TradingView, Seeking Alpha) as a Phase 5 monetization step

### 2.4 — Earnings Calendar Page (`/earnings.html`)
Static or lightly dynamic page:
- Next 7–14 days of earnings for notable stocks
- Pulls from Finnhub earnings calendar API
- Shows prior EPS surprise (beat/miss %) alongside upcoming date
- Static JSON refresh via GitHub Actions (similar to MarketDashboard pattern)

Earnings calendars are one of the most searched financial pages on the web. Good SEO surface area.

---

## Phase 3 — New Dashboards
*Target: Grow the tool suite, attract advanced users*

### 3.1 — Technical Pattern Scanner *(AskLivermore-inspired)* — **NEXT BUILD**
**What:** Automated daily scan detecting classic swing-trade chart patterns across ~500 liquid stocks.

**Inspiration:** asklivermore.com — detects 21 patterns, grades A+/A/B, shows historical credibility anchors (SMCI +2,515%, NVDA +638%). Free tier = top 6 results; $29/mo for full access.
**Our differentiator:** Free + open + cross-references our own insider buying and ETF data for multi-signal confluence picks.

#### Patterns to detect (Phase 1, ordered by priority):
1. **Bull Flag** — strong uptrend (10%+ in 1–4 wks), tight consolidation on declining volume, then breakout
2. **VCP** (Volatility Contraction Pattern) — Minervini method; 3–4 progressively tighter consolidations with lower volume
3. **Bollinger Band Squeeze** — BB width at N-month low; pending explosive move direction unclear, but alerts to watch
4. **MA Crossover** — 20-day crossing above 50-day with above-average volume
5. **Cup-with-Handle** — rounded base + shallow handle before breakout above prior high
6. **Power Earnings Gap** — stock gaps up 5%+ on earnings day, holds above gap in subsequent sessions

#### Grading system:
- **Grade A** — 3+ confirming signals (pattern + volume + relative strength + any cross-ref signal)
- **Grade B** — 2 confirming signals; pattern forming cleanly
- **Watch** — pattern developing but not yet confirmed; volume or RS not yet there

#### Cross-reference bonus (unique to us):
- Insider buying match (from InsiderBuying/data/results.json) → +1 grade or flag
- ETF overlap (appears in 3+ growth ETFs from TriedAndTrue universe) → flag as "ETF confirmed"

#### Technical stack:
- **Language/Framework:** Python + Flask (same as all other dashboards)
- **Data:** yfinance for OHLCV history (daily bars, 1-year lookback minimum)
- **Indicators:** `pandas-ta` library (RSI, EMA/SMA, Bollinger Bands, ATR, volume MA)
- **Pattern logic:** Custom detection functions per pattern type
- **Output:** `data/results.json` with ranked list of setups
- **Charts:** Link to TradingView chart for each ticker (no embedded chart to keep it simple)

#### Infrastructure:
- **Folder:** `PatternScanner/`
- **Render URL:** `https://invest-patterns.onrender.com`
- **Scan schedule:** Daily at market open, ~9:40am ET (`40 13 * * 1-5` cron)
- **GitHub Actions workflow:** `pattern-scanner.yml`
- **Universe:** S&P 500 tickers (~500 stocks) — fetched from a static list or Wikipedia

#### Homepage integration:
- New preview card in Market Snapshot section showing top-graded setup of the day
- Dashboard card in "All Dashboards" section
- Added to nav dropdown across ALL HTML files (position 6, after The Underdogs)

**Stack:** Flask + yfinance + pandas-ta
*This is the highest-impact new dashboard — differentiates the site from pure fundamental screeners.*

### 3.2 — Earnings Dashboard
**What:** Tracks upcoming and recent earnings across a curated universe of quality stocks.
- Upcoming earnings: next 14 days with sector, expected EPS, prior EPS surprise
- Recent results: beat/miss %, stock reaction (day-after % change)
- "Earnings movers": stocks that gapped up/down significantly post-earnings
- Cross-reference with Insider Buying data (insiders buying before earnings = strong signal)

**Stack:** Flask + Finnhub earnings API + yfinance price history
**URL:** `https://invest-earnings.onrender.com`

### ✅ 3.3 — Sector Rotation Tracker *(DONE — merged into MarketDashboard, Mar 2026)*
- Full-width panel in MarketDashboard showing 11 SPDR ETFs with 1D/5D/1M/3M % returns
- Sortable by any column; rows expand on click to show top 3 scan movers in that sector
- yfinance fetches ETF history; `SECTOR_KEYWORDS` fuzzy-matches Finnhub industry strings
- Homepage "Leading Sector" preview card reads from `sector_rotation[0]`

### 3.4 — Dividend & Income Dashboard *(Blossom-inspired)*
**What:** Identifies high-quality dividend payers with sustainable yield + growth.
- Universe: Quality ETFs (VYM, SCHD, DVY) + individual screening
- Scoring: dividend yield, payout ratio, dividend growth rate, FCF coverage, years of consecutive growth
- Filter for "dividend growers" vs. "high yielders" vs. "aristocrats"
- Pairs well with Tried & True's ETF-overlap methodology

**Stack:** Flask + yfinance
**URL:** `https://invest-dividends.onrender.com`

---

## Phase 4 — Blog & Content Expansion
*Target: SEO, engagement, newsletter fuel*

### 4.1 — Complete the AI Infrastructure Series
Parts 2–5 of the AI Infrastructure stack deep-dive are already planned:
- Part 2: Power & Cooling (EQIX, AMT, VST, CEG)
- Part 3: Networking & Interconnects (ANET, CSCO, MRVL)
- Part 4: Memory & Storage (MU, WDC, SMCI)
- Part 5: The Software Layer (PLTR, SNOW, MDB)

### 4.2 — Dashboard Tutorial Posts
One blog post per dashboard explaining how to use it:
- "How to Use Movers & Shakers to Find Day Trade Ideas"
- "How the Underdogs Scanner Finds Quality Stocks at a Discount"
- "Reading Insider Buying Signals: What Form 4 Actually Tells You"

These are high-SEO posts that funnel blog readers directly into the dashboards.

### 4.3 — Weekly Market Roundup
Short (500-word) weekly post: *"What the Scans Are Showing This Week."*
- Brief narrative of which sectors are leading
- Notable scan nominees from the week
- Fear & Greed reading and what it might mean
- Feeds directly into the newsletter (Phase 5)

### 4.4 — Historical Trade Reviews
Occasional deep-dive on a past nominee: what the scan picked, why, what happened.
- Wins and losses both — honest retrospectives build credibility
- Directly addresses the "does this actually work?" question first-time visitors have

---

## Phase 5 — Monetization
*Reference MONETIZATION.md for full detail — this is just the priority sequence*

| Priority | Action | Effort | Notes |
|----------|--------|--------|-------|
| 1 | Broker affiliate links on blog + dashboards | Low | Webull, Tastytrade, Moomoo — $50–200/referral |
| 2 | Google AdSense on blog posts | Low | Start immediately, low CPM but zero maintenance |
| 3 | Free newsletter (Substack/Beehiiv) | Low | List-building; positions for paid tier later |
| 4 | Paid newsletter tier | Medium | Once list reaches ~200+ subscribers |
| 5 | Premium dashboard access | High | Requires auth layer — validate demand first |

---

## Implementation Order (Suggested)

```
Phase 1 first — homepage improvements are highest-visibility, lowest effort
  → 1.2 "How It Works" section
  → 1.1 Metrics bar
  → 1.3 Track Record callout
  → 1.4 Market Snapshot expansion
  → 1.5 FAQ section
  → 1.6 Newsletter CTA

Phase 2 next — static pages, good for SEO
  → 2.1 Methodology page (highest trust-builder)
  → 2.4 Earnings calendar (highest SEO value)
  → 2.2 Glossary
  → 2.3 Resources

Phase 3 — new dashboards (pick one at a time)
  → 3.1 Technical Pattern Scanner (biggest differentiator)
  → 3.2 Earnings Dashboard
  → 3.3 Sector Rotation (can be merged into MarketDashboard)
  → 3.4 Dividend Dashboard

Phase 4 — content runs in parallel throughout
Phase 5 — monetization begins as soon as traffic justifies
```

---

## Notes & Constraints

- Site is hosted statically on GoDaddy — new pages require manual upload or a GoDaddy pipeline
- Dashboards run on Render free tier — spin-up delay is a known UX tradeoff
- All dashboards must follow the shared nav/sidebar standard (see MEMORY.md)
- Polygon.io free tier: 5 API calls/min — plan data fetching accordingly for new dashboards
- Finnhub free tier: 60 calls/min — sufficient for current scale, watch if adding more dashboards
- Every new dashboard needs: its own Render service, GitHub Actions scan workflow, and nav dropdown entry across ALL HTML files
