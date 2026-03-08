# Coding Projects — Overview

This is a personal stock research and investing platform. The root folder contains several sub-projects at different stages of completion.

---

## Project Structure

```
D:/Coding Projects/
├── Website/                ← Main landing site (static HTML/CSS)
│   ├── index.html          ← Single-page site: hero, dashboards, about, blog
│   ├── styles.css          ← Site-wide styles (shared design system)
│   └── CONTEXT.md          ← Website dev notes
│
├── MarketDashboard/        ← Dashboard #1: real-time stock scanner (Flask + Python)
│   ├── app.py              ← Backend: scanner logic, Flask routes
│   ├── dashboard.html      ← Frontend: single-file SPA (vanilla JS, Chart.js)
│   ├── scan_results.json   ← Auto-generated scan output
│   └── CONTEXT.md          ← Full technical context (read this first)
│
├── TriedAndTrue/           ← Dashboard #2: buy-and-hold ETF overlap scanner (Flask + Python)
├── TheAnalyst/             ← Dashboard #3: fundamental analysis via SEC 10-K/10-Q (Flask + Python)
│   ├── app.py              ← Backend: yfinance ETF/holdings scan, Flask routes
│   ├── dashboard.html      ← Frontend: Top 10 nominees + ETF scorecards
│   ├── results.json        ← Auto-generated scan output
│   └── CONTEXT.md          ← Full technical context
│
├── MarketMailer/           ← Legacy / exploratory (email digest feature)
├── Quant/                  ← Quantitative experiments / scratch work
├── Tests/                  ← Miscellaneous test scripts
├── Tutorials/              ← Learning exercises
│
└── PROJECT_OVERVIEW.md     ← This file
```

---

## Active Projects

### Website (`Website/`)
The site's home page. Static — no server needed. Links to all dashboards. Blog section is a placeholder for now. Open `index.html` in any browser.

### Market Scanner Dashboard (`MarketDashboard/`) — "Movers and Shakers"
Day-trading and swing-trading scanner. Runs a background scan every 15 minutes. Identifies top movers, Reddit buzz, sector flow, Fear & Greed, unusual volume, earnings, and news.

**Run:** `python app.py` → opens at `http://localhost:8080`

See `MarketDashboard/CONTEXT.md` for full technical documentation.

### Fundamental Analysis Dashboard (`TheAnalyst/`) — "The Analyst"
Enter any U.S. ticker for a Wall Street-style fundamental research report. Pulls SEC 10-K/10-Q filing dates from EDGAR, computes the Graham Number, scores against sector P/E benchmarks, and generates a verdict: Undervalued / Fairly Valued / Overpriced / Speculative.

**Run:** `python app.py` → opens at `http://localhost:8095`
**Requires:** `pip install flask yfinance requests`

### ETF Overlap Dashboard (`TriedAndTrue/`) — "Tried and True"
Buy-and-hold research tool. Scans 10 top growth ETFs via yfinance, finds stocks with the highest cross-ETF consensus, ranks them by overlap score, and shows 3yr/5yr performance vs SPY for each fund.

**Run:** `python app.py` → opens at `http://localhost:8090`
**Requires:** `pip install flask yfinance`

See `TriedAndTrue/CONTEXT.md` for full technical documentation.

---

## Planned Dashboards

Future dashboards will each live in their own folder and be linked from `Website/index.html`.

### Insider Buying (`InsiderBuying/`) — NEXT UP
Track executive/insider stock purchases to find momentum signals before the market catches on.
Key signals: cluster buys (multiple insiders buying the same stock), CEO/CFO buys,
large dollar amounts, open-market purchases (not option exercises).
Free data sources: SEC EDGAR Form 4 filings, OpenInsider.com, Finviz insider filter.

### Other Candidates
- Technical indicators (RSI, MACD, volume ratio) via `yfinance`
- Watchlist tracker
- Options flow (Unusual Whales free tier)
- Historical scan archive / trend comparison

---

## Design System

All projects share the same visual language for a cohesive look:
- **Background:** `#f5f4f0` (warm off-white)
- **Accent:** `#2d6a4f` (forest green)
- **Fonts:** Instrument Serif (headings), DM Sans (body), DM Mono (mono)
- **Philosophy:** Light, clean, data-forward — no dark mode for now

---

## Notes

- `MarketMailer/`, `Quant/`, `Tests/`, `Tutorials/` are older experiments and can be ignored or archived. They contain no active, maintained code.
- Everything is local-only. No auth, no deployment, no CI/CD. Personal use.
- Not financial advice.
