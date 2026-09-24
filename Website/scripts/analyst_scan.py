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
import math
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
# Current #1 from each board not in the homepage's main row, written to the
# Movers data API (CORS-enabled) for the homepage's "Other Lab Results" cards.
LEADERS_FILE = os.path.join(_WEBSITE_DIR, "MarketDashboard", "data", "homepage_leaders.json")
TARGET_COUNT = 15
NEXT_SCAN_INFO = "Weekdays at 10:30am ET"


def json_safe(obj):
    """Recursively replace NaN/Infinity with None — bare NaN from json.dump is
    invalid JSON and breaks browser consumers (see project-json-nan-safety).
    analyze_ticker can emit non-finite ratios (PEG, FCF yield), so both the
    Analyst results.json and the leaders file get scrubbed before writing."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(json_safe(payload), indent=2, allow_nan=False)
    with open(path, "w") as f:
        f.write(text)

# Dashboard "families" for cross-source dedup, so two lenses from the same
# dashboard (Pattern Scanner's coil + leaders, Insider's cluster + csuite)
# don't double-count toward the "surfaced by N dashboards" tally.
DASHBOARD_FAMILY = {
    "movers_day":      "movers",
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
        # No Movers swing source. That list was hidden from the Movers page in
        # June 2026 and has since been removed from the scan; names sourced from
        # it here carried a "Movers & Shakers" pill that led readers to a page
        # with no swing section. Swing reaches this board through Pattern
        # Scanner's Coil and Leaders lists instead.

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


# ── Homepage "Other Lab Results" — current #1 from each un-featured board ──────

def _num(x, dp=0):
    try:
        v = float(x)
        if not math.isfinite(v):
            return None
        return round(v, dp) if dp else round(v)
    except (TypeError, ValueError):
        return None


def build_homepage_leaders(analyses):
    """One current-leader card per board not already in the homepage's main row
    (Tried & True, Underdogs, Insider, The Analyst). Uniform card shape so the
    homepage can render them identically: {board, ticker, name, badge, line1,
    line2, href}."""
    leaders = {}

    tt = _load("TheMarathon/data/consensus.json")
    if tt and (tt.get("top_10") or []):
        p = tt["top_10"][0]
        leaders["tried_true"] = {
            "board":  "Tried & True",
            "ticker": p.get("ticker"),
            "name":   p.get("full_name") or p.get("name") or p.get("ticker"),
            "badge":  _num(p.get("score_normalized") or p.get("score")),
            "line1":  f"Held in {_num(p.get('etf_count')) or 0} growth ETFs",
            "line2":  "ETF-consensus leader",
            "href":   "https://invest-the-marathon.onrender.com/?tab=tried-true",
        }

    dv = _load("TheMarathon/data/deep_value.json")
    if dv and (dv.get("nominees") or []):
        p = dv["nominees"][0]
        dd = _num(p.get("drawdown_52w"), 1)
        leaders["underdogs"] = {
            "board":  "The Underdogs",
            "ticker": p.get("ticker"),
            "name":   p.get("name") or p.get("ticker"),
            "badge":  _num(p.get("composite_score")),
            "line1":  f"Quality {_num(p.get('quality_score'))} · Beaten-up {_num(p.get('beaten_up_score'))}",
            "line2":  (f"{dd}% from 52-week high" if dd is not None else "Deep-value nominee"),
            "href":   "https://invest-the-marathon.onrender.com/?tab=underdogs",
        }

    ib = _load("InsiderBuying/data/results.json")
    if ib and (ib.get("nominees") or []):
        p = ib["nominees"][0]
        sigs = p.get("signals") or []
        leaders["insider"] = {
            "board":  "Insider Buying",
            "ticker": p.get("ticker"),
            "name":   p.get("company") or p.get("ticker"),
            "badge":  _num(p.get("conviction_score")),
            "line1":  sigs[0] if sigs else f"Tier {p.get('tier', '?')} insider buy",
            "line2":  sigs[1] if len(sigs) > 1 else "Open-market purchase",
            "href":   "https://invest-insider-buying.onrender.com",
        }

    top = next((a for a in analyses if not a.get("error")), None)
    if top:
        fams  = {t.get("source_key", "").split("_")[0] for t in (top.get("cross_dashboard_tags") or [])}
        n     = len(fams)
        leaders["analyst"] = {
            "board":  "The Analyst",
            "ticker": top.get("ticker"),
            "name":   top.get("company") or top.get("ticker"),
            "badge":  top.get("verdict") or "—",
            "line1":  f"Surfaced by {n} dashboard" + ("s" if n != 1 else ""),
            "line2":  (f"Verdict score {_num(top.get('score'))}" if top.get("score") is not None else "Top all-star pick"),
            "href":   "https://invest-the-analyst.onrender.com/?ticker=" + str(top.get("ticker") or ""),
        }

    return {"generated": datetime.now(timezone.utc).isoformat(), "leaders": leaders}


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

    # Never publish a card that failed to analyze. A ticker only reaches this
    # board because another dashboard surfaced it, so an error here means the
    # upstream symbol was bad — and a public "could not fetch data" card is
    # worse than a shorter list. (Jul 2026: a Finviz parsing bug fed phantom
    # tickers in from Insider Buying and 3 of 15 cards rendered as errors.)
    failed = [a for a in analyses if a.get("error")]
    if failed:
        print(f"[analyst-scan] Dropping {len(failed)} card(s) that failed to "
              f"analyze: {', '.join(a['ticker'] for a in failed)}")
    analyses = [a for a in analyses if not a.get("error")]

    output = {
        "scan_time":        start.isoformat(),
        "next_scan_info":   NEXT_SCAN_INFO,
        "total_surfaced":   len(surface),
        "tickers_analyzed": len(analyses),
        "tickers":          analyses,
    }

    _write_json(OUTPUT_FILE, output)

    leaders = build_homepage_leaders(analyses)
    _write_json(LEADERS_FILE, leaders)
    got = ", ".join(sorted(leaders["leaders"])) or "none"
    print(f"[analyst-scan] Homepage leaders: {got} -> {LEADERS_FILE}")

    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"[analyst-scan] Done in {elapsed}s. Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
