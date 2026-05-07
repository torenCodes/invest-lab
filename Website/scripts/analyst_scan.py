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
    "insider_cluster": "insider",
    "insider_csuite":  "insider",
    "patterns":        "patterns",
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

    # ── Insider Buying — top 5 cluster, top 5 c-suite
    ib = _load("InsiderBuying/data/results.json")
    if ib:
        for s in (ib.get("cluster_buys") or [])[:5]:
            buyers   = s.get("insider_count") or "?"
            value_m  = (s.get("total_value") or 0) / 1e6
            add(s.get("ticker"), {
                "source_key": "insider_cluster",
                "label":      "Insider Buying",
                "signal":     f"Insider cluster ({buyers} buyers, ${value_m:.1f}M)",
                "score":      value_m,    # scale of $1M ≈ 1 score point
            })
        for s in (ib.get("csuite_buys") or [])[:5]:
            title    = s.get("title") or "exec"
            value_m  = (s.get("value") or 0) / 1e6
            add(s.get("ticker"), {
                "source_key": "insider_csuite",
                "label":      "Insider Buying",
                "signal":     f"C-suite buy ({title}, ${value_m:.1f}M)",
                "score":      value_m,
            })

    # ── Pattern Scanner — top 10 setups (Grade A/B only — Watch tier excluded)
    ps = _load("PatternScanner/data/results.json")
    if ps:
        graded = [s for s in (ps.get("setups") or [])
                  if s.get("grade") in ("A", "B")]
        graded.sort(key=lambda x: (
            {"A": 0, "B": 1}.get(x.get("grade", "B"), 9),
            -(x.get("score") or 0),
        ))
        for s in graded[:10]:
            pattern = s.get("pattern") or "?"
            grade   = s.get("grade") or "?"
            add(s.get("ticker"), {
                "source_key": "patterns",
                "label":      "Pattern Scanner",
                "signal":     f"{pattern} (Grade {grade})",
                "score":      s.get("score") or 0,
            })

    return surface


def rank_and_select(surface):
    """Sort surfaced tickers by:
       1. Number of distinct dashboards (DASHBOARD_FAMILY) that surfaced it
       2. Best per-source score across its tags (tiebreaker)
    Returns the top TARGET_COUNT entries.
    """
    rows = []
    for ticker, tags in surface.items():
        families  = {DASHBOARD_FAMILY.get(t["source_key"], t["source_key"]) for t in tags}
        n_dash    = len(families)
        max_score = max((t.get("score", 0) for t in tags), default=0)
        rows.append({
            "ticker":     ticker,
            "n_dash":     n_dash,
            "max_score":  max_score,
            "tags":       tags,
        })

    rows.sort(key=lambda r: (-r["n_dash"], -r["max_score"]))
    return rows[:TARGET_COUNT]


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
