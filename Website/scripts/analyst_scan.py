"""
The Analyst — Curated Deep Dive Scanner

Pulls top picks from every other dashboard, dedups by ticker, ranks by how
many independent dashboards surfaced each name, and runs the top 15 through
the Analyst's fundamental scoring (P/E, PEG, Free Cash Flow, Graham Number,
ROE, leverage, …). Output: TheAnalyst/data/results.json.

Cross-dashboard surfacing is the *primary* sort key. A stock flagged by
Tried & True + Insider Buying carries more conviction than one flagged by
a single lens, so it ranks higher even with a slightly lower per-source
score.

Run locally: python Website/scripts/analyst_scan.py
GitHub Actions: workflow runs daily ~10:30am ET (after the morning
dashboard scans complete and have fresh data on disk).
"""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# Path setup — import compute_verdict / analyze_ticker from TheAnalyst/app.py.
# That module's only side effect on import is instantiating a Flask app
# object (harmless when we never call .run()).
_HERE        = os.path.dirname(os.path.abspath(__file__))
_WEBSITE_DIR = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_WEBSITE_DIR, "TheAnalyst"))

from app import analyze_ticker  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────

OUTPUT_FILE  = os.path.join(_WEBSITE_DIR, "TheAnalyst", "data", "results.json")
TARGET_COUNT = 15
NEXT_SCAN_INFO = "Weekdays at 10:30am ET"

# Dashboard "families" for cross-source dedup. Movers' day + swing lenses
# come from the same scan, so they shouldn't double-count toward the
# "surfaced by N dashboards" tally. Same for Insider's cluster + csuite.
DASHBOARD_FAMILY = {
    "movers_day":      "movers",
    "movers_swing":    "movers",
    "tried_true":      "tried_true",
    "underdogs":       "underdogs",
    "insider":         "insider",
    "patterns_coil":   "patterns",
    "patterns_leader": "patterns",
}

# ── Source ingestion ──────────────────────────────────────────────────────────

def _load(rel_path):
    """Load a dashboard data file. Missing files are non-fatal — we just skip
    that source and note it in the log. Lets the scan still produce useful
    output if one dashboard hasn't run yet today."""
    full = os.path.join(_WEBSITE_DIR, rel_path)
    try:
        with open(full) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[analyst-scan] Source missing: {rel_path}")
        return None
    except Exception as e:
        print(f"[analyst-scan] Error loading {rel_path}: {e}")
        return None


def gather_sources():
    """Walk every dashboard's data file and build a {ticker: [tag, ...]} map.
    Each tag carries source_key, human-readable label, a one-line signal
    description, and the per-source score for tiebreaking."""
    surface = {}

    def add(ticker, tag):
        if not ticker:
            return
        t = str(ticker).upper().strip()
        if not t or t == "-":
            return
        surface.setdefault(t, []).append(tag)

    # ── Movers & Shakers — top 5 day, top 5 swing
    md = _load("MarketDashboard/data/results.json")
    if md:
        for s in (md.get("day_trades") or [])[:5]:
            add(s.get("ticker"), {
                "source_key": "movers_day",
                "label":      "Movers & Shakers",
                "signal":     f"Day Trade nominee (score {s.get('score', 0)})",
                "score":      s.get("score") or 0,
            })
        for s in (md.get("swing_trades") or [])[:5]:
            add(s.get("ticker"), {
                "source_key": "movers_swing",
                "label":      "Movers & Shakers",
                "signal":     f"Swing Trade nominee (score {s.get('score', 0)})",
                "score":      s.get("score") or 0,
            })

    # ── The Marathon: Tried & True (ETF consensus) — top 8 by rank
    tt = _load("TheMarathon/data/consensus.json")
    if tt:
        for s in (tt.get("top_10") or [])[:8]:
            rank = s.get("rank") or "?"
            add(s.get("ticker"), {
                "source_key": "tried_true",
                "label":      "Tried & True",
                "signal":     f"ETF consensus rank #{rank}",
                "score":      s.get("score_normalized") or s.get("score") or 0,
            })

    # ── The Marathon: Underdogs (deep value) — top 8 by composite score
    dv = _load("TheMarathon/data/deep_value.json")
    if dv:
        for s in (dv.get("nominees") or [])[:8]:
            rank = s.get("rank") or "?"
            add(s.get("ticker"), {
                "source_key": "underdogs",
                "label":      "The Underdogs",
                "signal":     f"Deep value rank #{rank}",
                "score":      s.get("composite_score") or 0,
            })

    # ── Insider Buying — top 10 conviction-ranked nominees
    # Single ranked list (cluster + C-suite + big-money were unified into
    # `nominees` by the Insider scan's Phase B/C rebuild). One source_key
    # covers all three lenses since `conviction_score` already weighs them.
    ib = _load("InsiderBuying/data/results.json")
    if ib:
        for s in (ib.get("nominees") or [])[:10]:
            tier   = s.get("tier", "?")
            score  = s.get("conviction_score", 0)
            sig    = " · ".join((s.get("signals") or [])[:2]) or f"Tier {tier} insider buy"
            add(s.get("ticker"), {
                "source_key": "insider",
                "label":      "Insider Buying",
                "signal":     f"Tier {tier} (score {score}) — {sig}",
                "score":      score,
            })

    # ── Pattern Scanner — top swing setups from the Coil engine.
    # Coiled (tightness-ranked) + Leaders (constructive strength). Both lists
    # are the same dashboard, so a name in both still counts once toward the
    # cross-dashboard tally (like Movers day+swing).
    ps = _load("PatternScanner/data/coil.json")
    if ps:
        for s in (ps.get("coiled") or [])[:8]:
            add(s.get("ticker"), {
                "source_key": "patterns_coil",
                "label":      "Pattern Scanner",
                "signal":     f"{s.get('pattern') or 'Coiled setup'} — Coil {round(s.get('coil_score') or 0)}",
                "score":      s.get("coil_score") or 0,
            })
        for s in (ps.get("leaders") or [])[:8]:
            add(s.get("ticker"), {
                "source_key": "patterns_leader",
                "label":      "Pattern Scanner",
                "signal":     f"Constructive leader — Leader {round(s.get('leader_score') or 0)}, RS {s.get('rs_pct') or 0}th",
                "score":      s.get("leader_score") or 0,
            })

    return surface


def rank_and_select(surface):
    """Pick the TARGET_COUNT 'all-stars' across the whole site.

    Two tiers so no single dashboard can crowd out the others (per-source
    score scales aren't comparable — Coil runs 0-100, others differ — so a
    raw score sort would just rank by whichever scale is biggest):

      Tier 1 — names surfaced by 2+ distinct dashboards, the highest-conviction
               all-stars, sorted by dashboard count then best score.
      Tier 2 — single-dashboard names, filled round-robin across dashboards so
               every dashboard earns a seat before any dashboard gets a second.
    """
    rows = []
    for ticker, tags in surface.items():
        families  = {DASHBOARD_FAMILY.get(t["source_key"], t["source_key"]) for t in tags}
        max_score = max((t.get("score", 0) for t in tags), default=0)
        rows.append({
            "ticker":     ticker,
            "families":   families,
            "n_dash":     len(families),
            "max_score":  max_score,
            "tags":       tags,
        })

    multi = sorted([r for r in rows if r["n_dash"] >= 2],
                   key=lambda r: (-r["n_dash"], -r["max_score"]))

    # Bucket single-dashboard names by their one family, best score first.
    buckets = defaultdict(list)
    for r in rows:
        if r["n_dash"] == 1:
            buckets[next(iter(r["families"]))].append(r)
    for fam in buckets:
        buckets[fam].sort(key=lambda r: -r["max_score"])

    # Order families by their strongest single-source pick so the best
    # dashboards lead each round, but every dashboard still gets a turn.
    fam_order = sorted(buckets, key=lambda f: -buckets[f][0]["max_score"])

    selected = list(multi)
    while len(selected) < TARGET_COUNT and any(buckets.values()):
        for fam in fam_order:
            if buckets[fam]:
                selected.append(buckets[fam].pop(0))
                if len(selected) >= TARGET_COUNT:
                    break

    return selected[:TARGET_COUNT]


# ── Per-ticker analysis ───────────────────────────────────────────────────────

def analyze(ticker, tags):
    """Run TheAnalyst's fundamental scoring on a single ticker, then attach
    the cross-dashboard tags. Errors are swallowed into the result dict
    so a single bad ticker doesn't kill the whole scan."""
    print(f"[analyst-scan] Analyzing {ticker} ({len(tags)} tag(s))...")
    try:
        result = analyze_ticker(ticker)
    except Exception as e:
        print(f"[analyst-scan] {ticker}: ERROR {e}")
        return {
            "ticker": ticker,
            "error": f"Analysis failed: {e}",
            "cross_dashboard_tags": tags,
        }
    if isinstance(result, dict) and "error" in result:
        result["cross_dashboard_tags"] = tags
        return result
    result["cross_dashboard_tags"] = tags
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    start = datetime.now(timezone.utc)
    print(f"[analyst-scan] Starting at {start.isoformat()}")

    surface = gather_sources()
    print(f"[analyst-scan] {len(surface)} unique tickers surfaced across all dashboards")

    selection = rank_and_select(surface)
    print(f"[analyst-scan] Selected top {len(selection)} for deep-dive:")
    for row in selection:
        labels = ", ".join(sorted({t["label"] for t in row["tags"]}))
        print(f"  {row['ticker']:6} surfaced by {row['n_dash']} dashboard(s): {labels}")

    analyses = []
    for row in selection:
        analyses.append(analyze(row["ticker"], row["tags"]))
        time.sleep(1)   # be nice to yfinance

    output = {
        "scan_time":        start.isoformat(),
        "next_scan_info":   NEXT_SCAN_INFO,
        "total_surfaced":   len(surface),
        "tickers_analyzed": len(analyses),
        "tickers":          analyses,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[analyst-scan] Done in {elapsed}s. Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
