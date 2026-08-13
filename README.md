# The Invest Lab

**A self-updating stock research platform — an automated data pipeline, five analytics dashboards, and a set of proprietary scoring engines that grade their own predictions.**

🔗 **Live site: [theinvestlab.com](https://theinvestlab.com)**

> Built as a personal research tool and an exercise in end-to-end data engineering: collection → scoring → publication → **measured outcomes**. Educational only — not financial advice.

---

## What it does

Every weekday, without anyone touching it, the platform pulls market data from six sources, scores roughly 2,500 liquid US stocks through several custom ranking engines, publishes the results to five dashboards, and then **tracks how its own picks actually performed 30 days later**.

| Dashboard | What it surfaces |
|---|---|
| **[Movers & Shakers](https://invest-movers-shakers.onrender.com)** | Day/swing candidates, sector rotation, social chatter velocity |
| **[The Marathon](https://invest-the-marathon.onrender.com)** | Long-term holds: ETF consensus, deep value, fund scorecards |
| **[Insider Buying](https://invest-insider-buying.onrender.com)** | Cluster buys, C-suite purchases, high-conviction insider activity |
| **[Pattern Scanner](https://invest-patterns.onrender.com)** | Coiled swing setups and constructive market leaders |
| **[The Analyst](https://invest-the-analyst.onrender.com)** | Daily "all-star" board — top names across every dashboard, with fundamental valuation verdicts |

---

## The part I'd point a data team at

**1. It grades its own homework.**
Every scan archives its top pick with an entry price. A scheduled job fills in the 30-day outcome once — as a fixed point-in-time snapshot that is never revisited or quietly revised. The homepage publishes the aggregate: winners, losers, and hit rate. Being able to say *"here is how the model actually did"* was the whole point.

**2. Unproven signals stay out of the public numbers.**
A newer experiment flags stocks whose social-mention volume is accelerating, on the theory that chatter precedes breakouts. It is archived and scored every day, but it is deliberately **excluded from the published track record** until it has enough matured outcomes to justify a place there. Measure first, publish second.

**3. Data-quality defenses, learned the hard way.**
- Python's `json.dump` emits bare `NaN`, which is valid Python but invalid JSON — browsers reject the entire file. A single unguarded division silently broke every dashboard while `curl` and Python read it back fine. All writes now go through a NaN-safe serializer.
- The Coil engine once ranked pending-acquisition stocks at the very top: a buyout target gaps once, then trades pinned near the deal price on drying volume — a mathematically *perfect* "coiled spring" that can never break out. A liveliness filter now screens them out.

**4. Statistics over gut feel.**
Percentile ranks, z-scores, and relative-strength comparisons against a benchmark rather than raw returns — a sector up 1% on a day the S&P gains 2% is *losing* ground, and the tooling says so.

---

## Proprietary scoring engines

| Engine | Idea | Inputs |
|---|---|---|
| **Coil Score** | How wound-up is this setup before it moves? | Trend stack, relative strength, range tightness, volume dry-up |
| **Cadence Score** | Does this stock have a *tradeable daily rhythm*? | Average daily range, consistency, liquidity, price band |
| **Market Temperature** | Live market regime, Cold → Hot | Risk posture, trend heat, breadth, new highs, sentiment, credit spreads |
| **Sector Rotation** | Where is money actually flowing? | Relative strength vs S&P, momentum quadrants (RRG), conviction volume |
| **Verdict Score** | Is this fundamentally cheap or expensive? | P/E vs sector, PEG, growth, margins, FCF yield, Graham number |

---

## Architecture

```
GitHub Actions (10 scheduled workflows)
        │
        ├─ Pull: Polygon · Finnhub · yfinance · FRED · Reddit/ApeWisdom · SEC EDGAR
        ├─ Score: proprietary engines (Python)
        └─ Commit JSON  ──────────────┐
                                      │ push triggers auto-deploy
                                      ▼
                            Render.com (5 services)
                            ├─ Flask app  → dashboard + CORS JSON API
                            └─ 4 static sites → read their own data/*.json
                                      │
                                      ▼
                            Static homepage (theinvestlab.com)
```

**Design note:** the scans are decoupled from the web tier entirely. Workflows write JSON into the repo; the commit *is* the deployment trigger. No database, no servers to babysit, no runtime API calls — dashboards load pre-computed results instantly and cannot fail because a vendor API is down.

**Tech:** Python (pandas, yfinance, BeautifulSoup, requests) · Flask · vanilla JS + SVG (no frontend framework) · GitHub Actions · Render · GoDaddy

---

## Repository layout

Everything the site is made of lives under `Website/`; the repository root holds
only deployment and automation config.

```
├── Website/                    # the platform itself
│   ├── index.html              #   homepage — lab results, market reading, track record
│   ├── blog.html  ·  Blog/     #   research write-ups (markdown + manifest)
│   ├── styles.css              #   shared design system
│   ├── scripts/                #   scheduled scan engines — the data pipeline
│   │   ├── coil_scan.py                # Coil Score — swing setups
│   │   ├── cadence_scan.py             # Cadence Score — day-trade rhythm
│   │   ├── market_temperature_scan.py  # market regime thermometer
│   │   ├── analyst_scan.py             # cross-dashboard "all-star" selection
│   │   ├── newsstand_scan.py           # trading conditions, unusual volume, earnings
│   │   ├── archive_nominee.py          # records each scan's top pick
│   │   └── calculate_outcomes.py       # fills 30-day outcomes → track record
│   ├── MarketDashboard/        #   Movers & Shakers (Flask app + scan)
│   ├── TheMarathon/            #   Tried & True · Underdogs · ETF Scorecard
│   ├── InsiderBuying/          #   insider purchase clusters
│   ├── PatternScanner/         #   Coil Score dashboard
│   └── TheAnalyst/             #   daily all-star board
├── .github/workflows/          # the schedule that drives everything
└── render.yaml                 # deployment map for the five Render services
```

Each dashboard folder is self-contained — its own `index.html`, its `scan.py`
where applicable, and a `data/` folder holding the JSON its scans produce. That
is what lets Render deploy them as five independent services from one repo.

---

## A note on the commit history

Most commits in this repository read `chore: market scan …` and were made by a bot. That is the pipeline working as designed — scheduled workflows commit fresh scan results several times a day, and each commit is what deploys the updated dashboards. Human-authored commits are the ones with conventional prefixes (`feat:`, `fix:`, `polish:`).

---

## Disclaimer

A personal research and educational project. Nothing here is investment advice, and the scoring engines are algorithmic reads of price and fundamental data that can and do misjudge. Always do your own research.
