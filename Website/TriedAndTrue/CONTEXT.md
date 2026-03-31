# Tried and True — Project Context

A buy-and-hold research dashboard. It identifies the stocks with the strongest consensus
across top growth ETFs that have historically outperformed SPY — acting as a research
assistant nominating long-term holdings with multi-source institutional backing.

**Not financial advice. For personal educational use only.**

---

## What It Does

1. Fetches holdings for each ETF in the universe using `yfinance`
2. Aggregates appearances: how many ETFs hold each stock, and at what weight
3. Scores each stock: `(ETF count × 10) + average weight` — rewards breadth of consensus first, depth second
4. Ranks the top 10 candidates and enriches them with fundamentals
5. Fetches 3yr/5yr performance for each ETF vs SPY for the scorecard section

---

## Run

```bash
pip install flask yfinance
python app.py
```

Opens at `http://localhost:8090` (auto-detects a free port: 8090, 8091, 8092, 9090, 9091).

Results are cached in `results.json`. On restart, cached results load immediately — no waiting for a rescan.

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask backend — scanner logic, data fetching, API routes |
| `dashboard.html` | Single-file frontend (vanilla JS, no framework) |
| `results.json` | Auto-generated on each scan; read by the frontend |
| `CONTEXT.md` | This file |

---

## ETF Universe

| Symbol | Name | Provider | Category |
|--------|------|----------|----------|
| QQQ | Nasdaq-100 | Invesco | Nasdaq Growth |
| SCHG | US Large-Cap Growth | Schwab | Large-Cap Growth |
| VUG | Growth ETF | Vanguard | Large-Cap Growth |
| IWF | Russell 1000 Growth | iShares | Large-Cap Growth |
| VGT | Information Technology | Vanguard | Sector — Tech |
| XLK | Technology Select | SPDR | Sector — Tech |
| MGK | Mega Cap Growth | Vanguard | Mega-Cap Growth |
| FTEC | MSCI Info Technology | Fidelity | Sector — Tech |
| SPYG | S&P 500 Growth | SPDR | S&P 500 Growth |
| BGRWX | Growth Fund | Baron | Active Growth |

To add or swap ETFs, edit `ETF_UNIVERSE` in `app.py`. Changes take effect on the next scan.

---

## Architecture

```
app.py (Flask)
 ├── Background thread: run_scan() — on demand / first boot
 │    ├── calc_return()           → 1yr/3yr/5yr returns via yfinance history
 │    ├── get_holdings()          → top holdings from funds_data.top_holdings (yfinance ≥0.2)
 │    │    └── fallback:          → info.get('holdings') dict
 │    ├── get_stock_info()        → fundamentals (name, sector, mkt cap, P/E)
 │    └── Scoring: (count × 10) + avg_weight → ranked top 10
 │
 ├── Writes → results.json
 │
 └── Flask routes
      ├── GET /               → serves dashboard.html
      ├── GET /api/status     → scan progress (polled every 3s scanning / 30s idle)
      ├── GET /api/results    → full results.json
      ├── POST /api/rescan    → triggers a fresh scan
      └── GET /ping           → health check
```

---

## Data Source

All data via `yfinance` (free, no API key required).

- **Holdings**: `Ticker.funds_data.top_holdings` — works for ETFs and most mutual funds.
  Falls back to `Ticker.info['holdings']` if `funds_data` is unavailable.
- **Performance**: computed from daily price history (`Ticker.history(period='Ny')`).
  A fresh 3-year return is calculated by comparing close price N years ago to today.

**Scan time:** ~2–3 minutes (10 ETF calls + 10 stock enrichment calls with 1s sleep between each)

---

## Scoring Methodology

```
overlap_score = (etf_count × 10) + avg_weight
```

- **ETF count** is weighted 10× to make breadth of consensus the primary signal.
  A stock in 9 of 10 ETFs scores at least 90, regardless of weight.
- **Avg weight** (average allocation across holding ETFs) breaks ties.
  Higher conviction positions push the score higher.
- Only stocks held by **2 or more** ETFs are eligible to appear in the top 10.

---

## Dashboard Sections

1. **Top 10 Nominees** — ranked cards showing ticker, company name, sector, ETF overlap count,
   average weight, 3yr return, market cap, P/E, and the specific ETF pills (with weights) that
   contribute to each stock's score.
2. **ETF Scorecards** — a responsive grid of cards, one per ETF, showing 3yr and 5yr total
   returns, the delta vs SPY, a "Beats SPY ✓" / "Trails SPY" badge, and the ETF's top holdings.

---

## Known Limitations

- `funds_data.top_holdings` may return empty for some funds (especially mutual funds like BGRWX).
  If so, that fund contributes no holdings to the overlap calculation but still appears in
  the scorecard with performance data.
- yfinance can be rate-limited or return stale data. If holdings look wrong, trigger a rescan.
- Historical return calculation uses calendar days (365 × N), not trading days. Off by ~1–2%
  vs official fund fact-sheet numbers.

---

## Possible Enhancements

- Add more ETFs: QQQM, ONEQ, FBGRX, VONG, WCLD (cloud), ARKK (for contrast)
- Add a "vs SPY" return column to the top 10 nominees
- Show a consensus matrix: stocks × ETFs grid with weight heatmap
- Weekly scheduled rescan (Task Scheduler on Windows, cron on Linux/Mac)
- Export top 10 to CSV / email digest
