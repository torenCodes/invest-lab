# Site Expansion Plan — theinvestlab.com
*Last updated: March 30, 2026*

---

## Inspiration Sources

| Site | What It Does Well |
|------|-------------------|
| **AskLivermore** (asklivermore.com) | Methodology transparency, credibility proof (historical picks), quality scoring system, earnings integration, clean freemium model |
| **Blossom Social** (blossomsocial.com) | Portfolio + dividend tracking, community discovery angle, all-in-one feel |

**What we're NOT copying:** Blossom's social feed / community features. This stays a data-driven research tool, not a social platform.

---

## Dashboard Investing Themes

The dashboards now map to three investing horizons. This framing should inform how they're presented on the homepage, in nav, and in content:

| Theme | Dashboard | Horizon |
|-------|-----------|---------|
| **Trading Nominees** | Movers and Shakers | Day / swing trades |
| **Short-Term Holding Nominees** | Pattern Scanner | Swing / position (days–weeks) |
| **Long-Term Holding Nominees** | Tried and True | Buy & hold (months–years) |

Other dashboards (Insider Buying, The Underdogs) cross-cut these themes — they surface signals used across all horizons.

---

## Overview

Three pillars:

1. **Credibility** — prove the dashboards work (track record, methodology transparency)
2. **Value density** — give visitors more useful data before they ever click into a dashboard
3. **Depth** — new dashboards and content that attract and retain serious stock pickers

---

## Phase 1 — Homepage & Static Site Upgrades
*Target: Quick wins, no new backend required*

### ✅ 1.1 — Metrics / Credibility Bar
~~Implemented then removed~~ — decided to keep homepage clean. Revisit if the site grows.

### ~~1.2 — "How It Works" Section~~
Removed — methodology stays proprietary. Reserved for Methodology Page (2.1).

### ✅ 1.3 — Track Record / Past Nominees Section *(DONE — Mar 2026)*
Fully implemented as an **automated system**:
- `scripts/archive_nominee.py` runs after every scan, saves top pick to `MarketDashboard/data/nominees_archive.json`
- `scripts/calculate_outcomes.py` fills 30-day outcome prices weekly (GitHub Actions)
- Homepage fetches archive from `https://invest-movers-shakers.onrender.com/data/nominees_archive.json`
- Seeded with 4 historical picks (AXTI, SMCI, PYPL, PLTR) with real outcomes

### ✅ 1.4 — Expanded Market Snapshot Cards *(DONE — Mar 2026)*
- Fear & Greed strip added above preview cards
- Sector card reads from `sector_rotation[0]`

### ~~1.5 — FAQ Section~~
Removed — found it overkill.

### 1.6 — Email / Newsletter CTA
Deferred — no newsletter setup yet. Revisit when traffic warrants.

### 1.7 — Homepage Layout Refresh *(NEXT — from EDITS.md)*
A focused round of homepage edits to tighten the page and prepare for the Newsstand:

**1.7a — Rename section:** "Today's Market Snapshot" → **"Today's Lab Results"**

**1.7b — Remove Pattern Scanner preview card.** Four cards remain: Day Trade, Swing Trade, Leading Sector, Highly Discussed. The Pattern Scanner is better represented in the dashboard grid below (Short-Term Holding theme) than as a daily preview card.

**1.7c — Create "The Newsstand" section on the homepage.** A new informational section below the preview cards (or below Past Nominees). This is where market context lives — not trade picks, but the backdrop:
- Fear & Greed bar (moves here from the Lab Results section)
- Market News highlights
- Unusual Volume alerts
- Earnings calendar snippet (upcoming week)
- Links to a dedicated **Newsstand page** (`newsstand.html`) with full-size versions of all cards

This replaces the old 2.4 Earnings Calendar concept with something broader and more useful.

**1.7d — Dashboard theme labels (optional).** Consider grouping the "All Dashboards" cards under the three investing theme headings (Trading / Short-Term / Long-Term) instead of a flat list. Open question — may be overdesign for 5–6 dashboards.

### 1.8 — Streamline MarketDashboard (Movers & Shakers)
Remove Fear & Greed and Market Chatter sections from the MarketDashboard itself. These migrate to the Newsstand. Movers & Shakers stays focused on: Day Trades, Swing Trades, Sector Rotation.

---

## Phase 2 — New Static Pages
*Target: SEO, depth, repeat visits*

### 2.1 — Methodology Page (`/methodology.html`)
A full deep-dive on how each dashboard works:
- Scoring formulas (e.g., `composite = quality × 0.45 + beaten_up × 0.40 + recovery_bonus`)
- Data sources per dashboard
- What each signal means and why it matters
- "What this tool is / what it isn't" framing

Most powerful trust-builder for technically-minded visitors.

### 2.2 — Glossary Page (`/glossary.html`)
Definitions for every term used across the dashboards:
- RSI, 52-week drawdown, YTD performance
- Graham Number, P/E, PEG ratio, FCF yield
- ETF overlap scoring, cross-ETF consensus
- Cluster buys, SEC Form 4, open-market purchases
- Fear & Greed index, Finnhub sentiment, Reddit mentions

Good for SEO ("what is RSI in stocks", etc.) and for new investors.

### 2.3 — Resources Page (`/resources.html`)
Curated list of trusted financial tools, data sources, and reading material:
- Data sources we actually use (Finnhub, Polygon.io, SEC EDGAR, yfinance)
- Recommended screeners (Finviz, Barchart)
- Books and resources for systematic investing
- Could include tasteful affiliate links (Tastytrade, TradingView, Seeking Alpha) as a Phase 5 step

### 2.4 — The Newsstand *(inline expandable cards on homepage)*
No standalone page — all Newsstand content lives on the homepage in expandable cards to keep visitors on the main page. Each card click-expands to show full data inline.

**Data pipeline:** `scripts/newsstand_scan.py` → `data/newsstand.json`, hosted on Render or committed to repo. GitHub Actions runs on schedule.

**Card content when expanded:**
- **Earnings Calendar** — next 7–14 days of notable earnings, prior EPS surprise, Finnhub API
- **Market News** — curated headlines from Polygon.io / Finnhub
- **Unusual Volume** — Finviz unusual volume tickers
- Fear & Greed already populated from Movers & Shakers scan data

This avoids page sprawl while still surfacing high-value market context. Earnings calendar data is the highest-SEO-value content on financial sites.

---

## Phase 3 — New Dashboards
*Target: Grow the tool suite, attract advanced users*

### ✅ 3.1 — Technical Pattern Scanner *(DONE — Mar 2026)*
Live at `https://invest-patterns.onrender.com`. Detects 6 chart patterns across S&P 500, grades A/B/Watch, cross-references insider buying and ETF consensus. Daily scan at 9:40am ET. See `PatternScanner/PROGRESS.md` for full architecture.

### 3.2 — Earnings Dashboard
**What:** Tracks upcoming and recent earnings across a curated universe of quality stocks.
- Upcoming earnings: next 14 days with sector, expected EPS, prior EPS surprise
- Recent results: beat/miss %, stock reaction (day-after % change)
- "Earnings movers": stocks that gapped up/down significantly post-earnings
- Cross-reference with Insider Buying data (insiders buying before earnings = strong signal)

**Note:** The Newsstand (2.4) now covers the earnings calendar inline on the homepage. This dashboard would only be needed if there's demand for deeper earnings analysis (movers, cross-ref with insider buying) beyond what the Newsstand card provides. Lower priority — revisit after 2.4 is live.

**Stack:** Flask + Finnhub earnings API + yfinance price history
**URL:** `https://invest-earnings.onrender.com`

### ✅ 3.3 — Sector Rotation Tracker *(DONE — merged into MarketDashboard, Mar 2026)*
Full-width panel in MarketDashboard showing 11 SPDR ETFs with 1D/5D/1M/3M % returns. Sortable columns, expandable rows with top movers.

### 3.4 — Dividend & Income Dashboard *(Blossom-inspired)*
**What:** Identifies high-quality dividend payers with sustainable yield + growth.
- Universe: Quality ETFs (VYM, SCHD, DVY) + individual screening
- Scoring: dividend yield, payout ratio, dividend growth rate, FCF coverage, years of consecutive growth
- Filter for "dividend growers" vs. "high yielders" vs. "aristocrats"
- Pairs well with Tried & True's ETF-overlap methodology

**Stack:** Flask + yfinance
**URL:** `https://invest-dividends.onrender.com`

### 3.5 — Optionality Dashboard *(idea stage)*
**What:** User inputs stock option parameters (ticker, strike, expiry, premium) and gets analysis — theoretical value, Greeks, risk/reward profile, breakeven. Think: The Analyst but for options contracts.
- Interactive (requires live Flask backend on Render, like TheAnalyst)
- Could use Black-Scholes or binomial pricing models
- Pairs with Movers & Shakers (found a mover → now evaluate an options play on it)

**Stack:** Flask + scipy/numpy + yfinance
**URL:** TBD — `https://invest-options.onrender.com`

### 3.6 — The Analyst Revival *(idea stage)*
Bring back The Analyst dashboard with verified setup and improved functionality. Currently hidden (`display:none`). Needs:
- Verify yfinance data reliability for fundamentals
- Improve error handling and loading UX
- Consider Render premium plan so the Flask server stays warm (applies to Optionality too)

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

High-SEO posts that funnel blog readers directly into the dashboards.

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

## Implementation Order

```
Immediate — Homepage refresh (1.7 + 1.8)
  → 1.7a  Rename to "Today's Lab Results"
  → 1.7b  Remove Pattern Scanner preview card
  → 1.7c  Build "The Newsstand" homepage section
  → 1.8   Streamline MarketDashboard (remove F&G + Chatter)

Next — The Newsstand data pipeline (2.4)
  → Build newsstand_scan.py (earnings + news + unusual volume)
  → GitHub Actions workflow to generate newsstand.json
  → Wire homepage Newsstand cards to expand with live data

Then — Static pages for SEO & trust
  → 2.1   Methodology page (highest trust-builder)
  → 2.2   Glossary
  → 2.3   Resources

Then — New dashboards (pick one at a time)
  → 3.4   Dividend Dashboard
  → 3.2   Earnings Dashboard (or fold into Newsstand — TBD)
  → 3.5   Optionality (idea stage)
  → 3.6   The Analyst revival (idea stage)

Parallel throughout — Blog content (Phase 4)
Monetization (Phase 5) — begins as soon as traffic justifies
```

---

## Open Questions

- **Dashboard density on homepage:** Are there too many dashboards pulling visitors away from the main page? Should some content (e.g., Underdogs, Insider Buying) be surfaced inline on the homepage rather than as separate click-away dashboards? The Newsstand concept is a step in this direction — pulling informational content back to the main site.
- **Render premium:** Interactive dashboards (The Analyst, Optionality) need a live Flask server. Free tier has cold-start delays. Worth evaluating Render paid plan if/when these go live.
- **Earnings overlap:** Newsstand page (2.4) vs. Earnings Dashboard (3.2) — how much depth belongs on the static page vs. warranting its own dashboard?

---

## Notes & Constraints

- Site is hosted statically on GoDaddy — new pages require manual upload or a GoDaddy pipeline
- Dashboards run on Render free tier — spin-up delay is a known UX tradeoff
- All dashboards must follow the shared nav/sidebar standard (see MEMORY.md)
- Polygon.io free tier: 5 API calls/min — plan data fetching accordingly for new dashboards
- Finnhub free tier: 60 calls/min — sufficient for current scale, watch if adding more dashboards
- Every new dashboard needs: its own Render service, GitHub Actions scan workflow, and nav dropdown entry across ALL HTML files
