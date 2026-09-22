# The Invest Lab — Context for the Portfolio Site

**Audience:** the `Data by Toren` Claude Code project (the data-analysis portfolio site).
**Purpose:** everything that project needs to present The Invest Lab as a portfolio piece,
link to it correctly, and own the funnel as the GitHub profile goes public.

This is a **handoff document, not a description of the site**. The project page already
carries the narrative copy. What follows is the factual scaffolding behind it: where things
live, what is actually true right now, what is load-bearing, and what would embarrass us if
stated wrongly. Where something is uncertain, it says so.

Written 2026-09-22. Figures were measured from the repo on that date, not recalled.

---

## 1. One-paragraph standing

The Invest Lab is a self-updating stock research platform: an automated data pipeline feeding
five analytics dashboards and a set of proprietary scoring engines that **grade their own
predictions**. It has been running continuously since **2026-03-04**. It is a personal research
and educational tool — **never financial advice**, and that framing is non-negotiable in any
copy written about it.

The single most distinctive thing about it, and the thing worth leading with, is that it
**measures its own accuracy in public and publishes results that contradicted its author.**
Details in §6.

---

## 2. Where everything lives

| Thing | Location |
|---|---|
| GitHub repo | `github.com/torenCodes/invest-lab` — **private as of 2026-09-22, see §8** |
| Live site | `theinvestlab.com` |
| Repo-facing README | `README.md` at the repo root — **portfolio-facing, keep it current** |
| Screenshots for embedding | `docs/screenshots/` — `homepage.png`, `movers-shakers.png`, `pattern-scanner.png`, `the-analyst.png` |
| This document | `docs/INVESTLAB_PROJECT_CONTEXT.md` |

### The five dashboards

All five are Render services. The URLs are stable and safe to link.

| Dashboard | URL | What it surfaces |
|---|---|---|
| Movers & Shakers | `invest-movers-shakers.onrender.com` | Day/swing candidates, sector rotation (RRG), chatter velocity |
| The Marathon | `invest-the-marathon.onrender.com` | Long-term holds: ETF consensus, deep value, fund scorecards |
| Insider Buying | `invest-insider-buying.onrender.com` | Corporate Form 4 clusters + a Congress tab from House filings |
| Pattern Scanner | `invest-patterns.onrender.com` | Coiled swing setups and constructive market leaders |
| The Analyst | `invest-the-analyst.onrender.com` | Daily cross-dashboard board with fundamental verdicts |

**Five dashboards is the lineup.** Do not write "more coming soon" or imply expansion.

---

## 3. Repository layout

Everything the site is made of lives under `Website/`; the root holds only deployment and
automation config. That split is deliberate and should be described accurately.

```
invest-lab/
├── README.md                   # portfolio-facing
├── render.yaml                 # reference map of the 5 Render services (NOT a live Blueprint)
├── .github/workflows/          # 11 scheduled workflows — the pipeline's clock
├── docs/                       # screenshots + this file
└── Website/
    ├── index.html              # homepage        ─┐
    ├── blog.html  ·  Blog/     # research posts   ├─ hosted on GoDaddy, NOT Render
    ├── styles.css              # shared design    ─┘
    ├── images/
    ├── scripts/                # the shared scan engines (10 files, see below)
    ├── MarketDashboard/        # Movers & Shakers  (Flask web service)
    ├── TheMarathon/            # Tried & True · Underdogs · ETF Scorecard (static)
    ├── InsiderBuying/          # Corporate + Politician tabs (static)
    ├── PatternScanner/         # Coil Score dashboard (static)
    ├── TheAnalyst/             # daily all-star board (static)
    └── TriedAndTrue/ · Underdogs/   # legacy folders, retain only scan.py
```

`Website/scripts/` holds the shared engines:

```
analyst_scan.py            cross-dashboard "all-star" selection
cadence_scan.py            Cadence Score — day-trade rhythm
coil_scan.py               Coil Score — swing setups
market_temperature_scan.py market regime thermometer (10 components, 4 themes)
newsstand_scan.py          Trading Conditions read
insider_pulse_scan.py      market-wide insider buy/sell breadth
capitol_flow_scan.py       House PTR filings → congressional trades
insider_backtest.py        research harness — measures the conviction model
archive_nominee.py         records each scan's top pick
calculate_outcomes.py      fills 30-day outcomes → the track record
```

### Scale (measured 2026-09-22)

- **~8,600 lines of Python** across the scans and engines
- **~4,200 lines** of `index.html` + `blog.html` + `styles.css` (vanilla JS + SVG, no framework)
- **5 published research posts**, the "AI Factory" infrastructure series among them
- **4,453 commits**, of which **4,241 are the bot** and **212 are human-authored** — see §8, this
  needs explaining rather than hiding

---

## 4. Architecture — the part worth explaining

```
GitHub Actions (11 scheduled workflows)
        │
        ├─ Pull: Polygon · Finnhub · yfinance · FRED · Reddit/ApeWisdom
        │        SEC EDGAR · House Clerk disclosures · OpenInsider
        ├─ Score: proprietary engines (Python)
        └─ Commit JSON  ──────────────┐
                                      │ the commit IS the deploy trigger
                                      ▼
                            Render.com (5 services)
                            ├─ Flask app  → dashboard + CORS JSON API
                            └─ 4 static sites → read their own data/*.json
                                      │
                                      ▼
                            Static homepage (theinvestlab.com, GoDaddy)
```

**The design decision worth highlighting:** the scans are decoupled from the web tier entirely.
Workflows write JSON into the repo and the commit *is* the deployment trigger. No database, no
servers to babysit, no runtime API calls — dashboards load pre-computed results instantly and
cannot fail because a vendor API is down. That is a genuine engineering argument, not a
limitation being dressed up.

**Tech:** Python (pandas, yfinance, BeautifulSoup, requests) · Flask · vanilla JS + SVG ·
GitHub Actions · Render · GoDaddy.

### Two architectural facts that are load-bearing

1. **Only Movers is a Flask web service.** The other four are Render *static* sites. Render
   static sites ignore `_headers` files, so they cannot send CORS headers. The Movers Flask app
   is therefore the de-facto **CORS-enabled data API** — anything the homepage fetches
   cross-origin must live in `MarketDashboard/data/`. This has caused real outages; don't
   describe the five as interchangeable.

2. **`render.yaml` is documentation, not a live Blueprint.** The Render dashboard is the source
   of truth. Same category of trap as the workflow files in §7.

---

## 5. Proprietary scoring engines

These are the original work and the right thing to foreground.

| Engine | Idea | Inputs |
|---|---|---|
| **Coil Score** | How wound-up is this setup before it moves? | Trend stack, relative strength, range tightness, volume dry-up |
| **Cadence Score** | Does this stock have a *tradeable daily rhythm*? | Average daily range, consistency, liquidity, price band |
| **Macro Temperature** | Live market regime, Cold → Hot | 10 signals in 4 themes, weighted 40/25/20/15 |
| **Trading Conditions** | Is today worth trading? | Today's tape, trend, momentum, participation, VIX, rates |
| **Sector Rotation** | Where is money actually flowing? | Relative strength vs S&P, RRG momentum quadrants, conviction volume |
| **Verdict Score** | Fundamentally cheap or expensive? | P/E vs sector, PEG, growth, margins, FCF yield, Graham number |
| **Insider Conviction** | Is this insider purchase informative? | Price context, cluster size, role seniority, position growth — **weights set by backtest, not judgement** |

---

## 6. The strongest portfolio story

If the site leads with one thing, lead with this. It is in the README under
*"The part I am most willing to be judged on."*

`insider_backtest.py` reconstructs **22,600 historical insider-buying clusters** from five years
of SEC Form 4 filings, scores each using only what was knowable that day, and compares forward
60-day returns against a size-matched benchmark. Entry is the **filing date, never the trade
date**, because you cannot act on a form you cannot see.

The result overturned the author's own model:

- Clusters scoring 70–84 **trailed** the index by 2.84% at a 39.9% win rate — worse than
  clusters scoring under 40. The model had been ranking names close to backwards.
- **Price context**, which carried *zero* weight, was the only dimension that separated
  outcomes consistently.
- **Cluster size**, which had been weighted most heavily, was a **confound** — large clusters
  concentrate in distressed companies. Hold price constant and the penalty vanishes.
- Benchmark choice mattered: the same sample reads −0.94% vs SPY and −0.31% vs IWM. This
  universe is small-cap; SPY confuses a size mismatch for a broken signal.

The model was rebuilt on the evidence, weak dimensions were cut, and **the methodology panel on
the live dashboard says so publicly**, including that the effects are modest and drawn from a
single market regime.

Two supporting stories, both real and both safe to tell:

- **It grades its own homework.** Every scan archives its top pick with an entry price. A
  scheduled job fills the 30-day outcome *once*, as a fixed point-in-time snapshot never
  revisited or quietly revised. The homepage publishes winners, losers and hit rate.
- **Unproven signals stay out of the published numbers.** A chatter-velocity experiment is
  archived and scored daily but deliberately excluded from the public track record until it has
  enough matured outcomes. Measure first, publish second.

### Honesty constraints when writing about this

Do not inflate it. The backtest covers **one market regime (2021–2026)**, which rewarded
momentum over contrarian buying; a sustained value cycle could invert the price-context
finding. Sector was **untestable** — SEC bulk data has no sector field. Say the effects are
modest, because they are. The credibility of the whole piece rests on not overclaiming.

---

## 7. Operational reality the portfolio project should know

### The workflow files do not tell you when things run

**This is the single most important operational gotcha.** Some workflows are triggered
externally by **cron-job.org**, which POSTs to the GitHub `workflow_dispatch` API, because
GitHub's own `schedule:` queue runs **hours late** — Market Temperature ran four to six hours
late every weekday for two weeks before this was caught.

| Workflow | Real trigger | GitHub `schedule:` |
|---|---|---|
| `newsstand-scan` | cron-job.org, 4×/day market hours | one post-close fallback |
| `market-temperature` | cron-job.org, 9:50 + 10:50 ET | one post-close fallback |
| the other nine | GitHub `schedule:` | as written in the file |

For comparison: a cron-job.org dispatch landed **91 seconds** after its slot; GitHub's
scheduler was taking four-plus hours. In the Actions tab, external runs show as
`repository_dispatch`, GitHub's own as `Scheduled`.

**Never quote a cron expression from a workflow file as fact.** Check cron-job.org.

### Current schedule, as actually observed

11 workflows: `market-scan` (6×/day) · `insider-buying-scan` · `tried-true-scan` (weekly) ·
`underdogs-scan` · `cadence-scan` · `coil-scan` · `newsstand-scan` · `market-temperature` ·
`capitol-flow` (Tue + Fri) · `analyst-scan` · `outcomes-calc` (weekdays).

### Deploy split — matters if the portfolio site ever links to a specific file

- **Dashboards** → push to `main`, Render auto-deploys. Fully automated.
- **Homepage** (`index.html`, `styles.css`, `Blog/`) → **manual FTP upload to GoDaddy by Toren**.
  Committing these does *not* publish them. If the live homepage and the repo disagree, this is
  usually why.

---

## 8. Going public — what the funnel project owns

### The commit history needs a caption, not concealment

**4,241 of 4,453 commits are `github-actions[bot]`** writing `chore: market scan …`. A visitor
skimming the commit graph sees a wall of bot noise and may read it as padding.

Frame it correctly: that *is* the pipeline working as designed — scheduled workflows committing
fresh scan results several times a day, and each commit is what deploys the updated dashboards.
Human-authored commits carry conventional prefixes (`feat:`, `fix:`, `polish:`, `chore:` with
real messages). The README already has a short section on this; the portfolio site should make
the same point rather than leaving it to be discovered.

### Pre-public checklist — verify before linking publicly

Verified against the repo on 2026-09-22 — status noted per item.

- [ ] 🔴 **The repo is still PRIVATE.** An anonymous GitHub API call to
      `repos/torenCodes/invest-lab` returns 404. **Any link to the repo will 404 for visitors
      until Toren flips it public.** This is the blocking item — check it before publishing
      anything that links there, and re-run the same probe to confirm rather than assuming.
- [ ] 🟡 **A personal email is in two tracked files.** `toren5@gmail.com` appears in
      `Website/scripts/capitol_flow_scan.py` and `Website/scripts/insider_pulse_scan.py`, inside
      the SEC User-Agent string — **SEC requires a real contact address on every request**, so it
      cannot simply be deleted. It also sits in the git history. Decide before going public:
      accept it, or switch to `contact@theinvestlab.com` and confirm SEC still accepts the
      requests. Not a security issue, a privacy one.
- [x] ✅ **No hardcoded key values in tracked Python.** Searched; none found. All three keys are
      GitHub **repository** secrets read with a bare `os.environ.get(...)` and no fallback:
      `FINNHUB_KEY`, `POLYGON_KEY`, `FRED_API_KEY`.
- [ ] 🟡 **`.git/config` remote URL contains a classic `ghp_` PAT.** Local-only and untracked, so
      it is *not* in the published history — but it should move to a credential manager or SSH.
- [ ] 🟡 **Scan git history for secrets** before flipping visibility. An Aug 2026 audit removed
      the last hardcoded API-key fallbacks and the keys were **rotated afterwards**, so values in
      old commits are dead. Confirm rather than trust this sentence.
- [ ] **Disclaimer** present and prominent on any page describing this project.

### Linking guidance

- Link the **repo root README** for the engineering story — it is written for exactly this.
- Link **`theinvestlab.com`** for the live product.
- Deep-link individual dashboards only if you are willing to check them; Render free-tier
  services cold-start and can take ~30s to wake.
- Screenshots in `docs/screenshots/` are current as of the README and can be copied into the
  portfolio site rather than hot-linked.

---

## 9. Things that are easy to get wrong

A short list of claims that would be **incorrect** if written about this project:

- ⚠️ **"Scans ~2,500 stocks" is true, but only of some engines.** The Coil/Cadence engines score
  the broad liquid universe via Polygon grouped-daily — `coil.json` reported `universe: 2392` on
  2026-09-22, so the README's "roughly 2,500" is fair. The **Movers day/swing scan is a different
  thing entirely**: it builds a small candidate list from movers and buzz sources and its
  `total_scanned` runs 12–25. Attach the number to the right engine; do not use it as a blanket
  figure for "every scan".
- ❌ "Real-time data." It is pre-computed and published on a schedule; nothing is fetched at
  page load. That is the design's strength — describe it as such.
- ❌ "Machine learning" / "AI-powered." There is no ML model. These are explicit, hand-built,
  documented scoring rules, some with backtest-derived weights. The transparency *is* the point.
- ❌ "Predicts stock prices." It ranks and scores, then measures how those rankings performed.
- ❌ Quoting a cron expression from a workflow file as the real schedule (see §7).
- ❌ Describing all five dashboards as the same kind of service (see §4).

---

## 10. Related context files

These live in the working project's memory directory and are **not** in the repo. They are
referenced here so the portfolio project knows depth exists if a question comes up that this
document cannot answer — ask Toren rather than guessing.

- `project_dashboards_reference.md` — deep per-dashboard internals
- `project_insider_political_flow.md` — the insider/congressional program and the backtest
- `project_coil_pattern_scanner.md` — Coil/Cadence engines
- `project_repo_restructure.md` — making the repo portfolio-ready
- `blog_content.md` — published posts and writing style

---

## 11. Disclaimer to carry forward

> The Invest Lab is a personal research and educational project. Nothing in it is investment
> advice, and the scoring engines are algorithmic reads of price and fundamental data that can
> and do misjudge.

Any portfolio page describing this project should carry an equivalent line.
