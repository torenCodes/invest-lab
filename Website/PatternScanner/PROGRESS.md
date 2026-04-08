# PatternScanner — Build Progress

**Last updated:** March 2026
**Status:** ALL CODE COMPLETE — Render deployment remaining

---

## File Checklist

```
PatternScanner/
├── ✅ PROGRESS.md          ← this file
├── ✅ scan.py              ← pattern detection engine
├── ✅ app.py               ← minimal Flask file server (same pattern as MarketDashboard)
├── ✅ requirements.txt     ← Render runtime deps (flask, gunicorn)
├── ✅ requirements-scan.txt← GitHub Actions scan deps (yfinance, pandas, lxml, requests)
├── ✅ data/results.json    ← initial placeholder (empty setups)
└── ✅ index.html          ← dashboard UI (sidebar + grade filter tabs + expandable cards)

.github/workflows/
└── ✅ pattern-scanner.yml ← daily cron at 9:40am ET (40 13 * * 1-5)

Website/index.html
└── ✅ 5th preview card in Market Snapshot ("Top Pattern Setup") — fetches from invest-patterns Render URL

All HTML nav dropdowns (index.html, blog.html, all dashboard index.html files)
└── ✅ Pattern Scanner added as #6 in all dropdowns
    URL: https://invest-patterns.onrender.com
    Label: Pattern Scanner

scripts/archive_nominee.py
└── ✅ extract_patterns() added — archives top Grade A setup daily

render.yaml or Render dashboard
└── 🔲 Create new web service: invest-patterns  ← ONLY REMAINING STEP
    Root dir: PatternScanner/
    Build cmd: pip install -r requirements.txt
    Start cmd: gunicorn app:app
    Port: 8110
```

---

## Architecture Decisions (already locked in)

| Decision | Choice | Reason |
|---|---|---|
| Serving model | Static JSON + minimal Flask | Same as MarketDashboard — no user input needed |
| Universe | S&P 500 from Wikipedia (~503 tickers) | Names + sectors come free from the table |
| History | 1yr daily OHLCV via yfinance batch download | Enough for all 6 patterns; one call |
| Indicators | Manual pandas (no pandas-ta) | Fewer deps, more reliable |
| Patterns | 6 patterns (see below) | Best signal/reliability balance |
| Grading | A ≥65 pts / B ≥45 pts / Watch ≥30 pts | Simple, consistent |
| Chart links | TradingView `https://www.tradingview.com/chart/?symbol=TICKER` | Best for traders |
| Port | 8110 | After Underdogs (8100) |
| Cross-ref | InsiderBuying + TriedAndTrue data files | Our unique angle vs AskLivermore |

---

## Patterns Implemented in scan.py

| Pattern | Key | Score Bonus | Detection Method |
|---|---|---|---|
| Bull Flag | `bull_flag` | +25 max | Flagpole 12%+ gain, tight flag <20% depth |
| VCP | `vcp` | +15 | 3 tightening 15-day windows, vol contracting |
| BB Squeeze | `bb_squeeze` | +12 | BB width at 6-month low |
| MA Crossover | `ma_crossover` | +10 | EMA 20 crossed above EMA 50 within 5 days |
| Cup & Handle | `cup_handle` | +18 | Within 15% of 52w high, rounded base, handle |
| High-Vol Gap | `hv_gap` | +20 | 5%+ gap on 2.5x volume within last 20 days |

---

## Grading Score Breakdown

Base score for any detected pattern: **30 pts**
Plus pattern bonus (see table above)
Plus:
- +10 — above 200-day EMA
- +10 / +5 — RS percentile ≥70% / ≥50% of 52w range
- +5 — RSI between 45–70
- +5 — recent volume trend rising
- +15 — insider buying cross-reference match
- +10 — ETF consensus match (TriedAndTrue top_10)

**Grade A:** ≥65 pts | **Grade B:** ≥45 pts | **Watch:** ≥30 pts | Below 30: excluded

---

## Output JSON Structure

```json
{
  "scan_time": "2026-03-26T09:45:00+00:00",
  "next_scan_info": "Weekdays ~9:40am ET",
  "total_scanned": 503,
  "setups_found": 18,
  "setups": [
    {
      "ticker": "NVDA",
      "name": "NVIDIA Corporation",
      "sector": "Information Technology",
      "pattern": "Bull Flag",
      "pattern_key": "bull_flag",
      "grade": "A",
      "score": 85,
      "signals": ["Flagpole +22.3% in 8d", "Flag depth 6.2%", "Volume contracting in flag",
                  "Above 200-day EMA", "In 7 growth ETFs (TriedAndTrue)"],
      "current_price": 875.50,
      "change_pct": 1.8,
      "week_change_pct": 5.2,
      "rs_pct": 82.1,
      "chart_url": "https://www.tradingview.com/chart/?symbol=NVDA",
      "insider_flag": false,
      "etf_flag": true,
      "etf_count": 7
    }
  ]
}
```

---

## index.html Notes (for when building it)

**Layout:** Same sidebar-left / main-right as all other dashboards

**Sidebar:**
- Title: "Pattern Scanner" + sub: "Technical setups — S&P 500"
- Scan pulse (last scan time)
- Navigation: All Setups / Grade A / Grade B / Watch
- Grade A count badge
- Scan schedule
- Disclaimer

**Main content:**
- Header bar: "X setups found — Y Grade A — Z Grade B" + scan timestamp
- Filter tabs: All / Grade A / Grade B / Watch
- Setup cards (one per ticker, sorted A → B → Watch, then by score)
- Each card shows:
  - Grade badge (A=green, B=teal, Watch=orange) — prominent, top-left
  - Pattern badge pill (Bull Flag / VCP / BB Squeeze / etc.)
  - Cross-ref badges: "👤 Insider" (green) and "📊 ETF" (teal) if flagged
  - Ticker + company name
  - Current price + today's % change (colored)
  - Signal list (first 2–3 signals visible)
  - "View Chart →" link (TradingView)
  - Click to expand: full signals, RS percentile, week change, score breakdown

**CSS notes:**
- Grade A: `--green` (#1a7a4a)
- Grade B: `--accent` (#2d6a4f) or teal
- Watch: `--orange` (#e67e22)
- Pattern pill: small pill badge, neutral gray background
- Insider badge: `--green-bg` background
- ETF badge: `--blue-bg` background

---

## If Resuming a Future Session

All code is complete. Only the Render deployment step remains:

**Render setup (manual — do this in the Render dashboard):**
1. New **Static Site** → connect repo (same as all other dashboards except The Analyst)
2. Root directory: `PatternScanner/`
3. Build command: *(leave empty)*
4. Publish directory: `.`
5. Service name: `invest-patterns` → URL: `https://invest-patterns.onrender.com`
6. After first deploy: manually trigger `pattern-scanner.yml` from GitHub Actions to populate `data/results.json`
