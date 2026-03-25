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

### 1.1 — Metrics / Credibility Bar
Add a horizontal stats strip between the Hero and Market Snapshot sections.
- "5 active dashboards"
- "~500 stocks scanned per day"
- "Updated 4× per trading day"
- "Powered by Finnhub · Polygon.io · SEC filings · Reddit"

Short, punchy, builds trust. Modeled after how AskLivermore leads with "741 setups found today."

### 1.2 — "How It Works" Section
A new 3–4 step explainer section on the homepage showing the scan-to-surface pipeline:
1. **Scan** — pull movers, ETF holdings, insider filings from live data feeds
2. **Score** — apply multi-factor scoring (momentum, quality, sentiment, drawdown)
3. **Surface** — rank and present the top nominees per category
4. **Decide** — you do the research, you pull the trigger

This directly addresses the question a first-time visitor asks: *"Why should I trust this?"* AskLivermore does this extremely well with its pattern-scoring transparency.

### 1.3 — Track Record / Notable Picks Section
A "Past Nominees" callout section — 3–4 historical scan picks with outcome data.
- Format: Ticker · Date picked · % gain/loss over X days · Dashboard source
- Frame as informational, not as financial advice
- Honest mix of wins and near-misses builds more trust than cherry-picking
- Could be a static section manually curated monthly, or eventually pull from a historical JSON file

*Inspired by AskLivermore's "SMCI +2,515% · NVDA +638%" credibility anchors.*

### 1.4 — Expanded Market Snapshot Cards
The current preview cards are solid. Expand with:
- **Fear & Greed index** as a fifth card (data already fetched in MarketDashboard)
- **Top sector today** surfaced more prominently (already in scan data)
- Mini sparkline / trend arrow on the day-trade and swing-trade cards (simple SVG)

### 1.5 — "Why Use This?" FAQ / Objections Section
A short Q&A block near the bottom of the homepage:
- *"Is this financial advice?"* — No. Methodology-driven screening only.
- *"Where does the data come from?"* — Finnhub, Polygon.io, SEC Form 4, Reddit, yfinance
- *"How often do scans run?"* — Movers 4×/day; Underdogs 3×/week; Insider Buying daily
- *"Do I need an account?"* — No. Fully open, no login required.

Helps skeptical visitors self-qualify and sets proper expectations.

### 1.6 — Email / Newsletter CTA
Add a clean single-row section: *"Get weekly scan highlights in your inbox."*
- Link to a Substack or Beehiiv free newsletter
- No account required on our end; no backend needed
- Just a simple email input or a prominent "Subscribe on Substack" button
- Placed below the Blog section

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

### 3.1 — Technical Pattern Scanner *(AskLivermore-inspired)*
**What:** Automated daily scan detecting classic swing-trade chart patterns.
- Patterns: Bull flag, bear flag, VCP (Volatility Contraction Pattern), cup-with-handle, moving average crossover (20/50/200-day), RSI divergence, Bollinger Band squeeze
- Universe: Top 500–1,000 liquid stocks (use Polygon.io or yfinance)
- Quality grade: A / B / Watch (like AskLivermore's A+ to B system)
- Output: Ranked list with pattern type, grade, and live chart link (TradingView embed)

**Stack:** Flask + yfinance/Polygon.io + pandas-ta for pattern detection
**Scan schedule:** Daily at market open (9:40am ET)
**URL:** `https://invest-patterns.onrender.com`

*This is the highest-impact new dashboard — differentiates the site from pure fundamental screeners.*

### 3.2 — Earnings Dashboard
**What:** Tracks upcoming and recent earnings across a curated universe of quality stocks.
- Upcoming earnings: next 14 days with sector, expected EPS, prior EPS surprise
- Recent results: beat/miss %, stock reaction (day-after % change)
- "Earnings movers": stocks that gapped up/down significantly post-earnings
- Cross-reference with Insider Buying data (insiders buying before earnings = strong signal)

**Stack:** Flask + Finnhub earnings API + yfinance price history
**URL:** `https://invest-earnings.onrender.com`

### 3.3 — Sector Rotation Tracker
**What:** Shows where institutional money is flowing week-over-week.
- 11 S&P 500 sectors with 1-week, 1-month, 3-month performance
- Heatmap-style visualization (green = leading, red = lagging)
- Identifies rotation patterns (e.g., money leaving tech, entering energy)
- Pairs well with Movers & Shakers sector flow data

**Stack:** Flask + yfinance sector ETF data (XLK, XLF, XLV, XLE, etc.)
**URL:** Could be a section within MarketDashboard rather than standalone

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
