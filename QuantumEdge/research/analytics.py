"""
Analytics — load saved experiment results, compare, and summarise.

Usage:
  python research/analytics.py                       # compare all saved results
  python research/analytics.py baseline_*            # filter by name pattern
  python research/analytics.py --runs                # read from output/runs/ tree
  python research/analytics.py --valid-only          # skip INVALID* results
"""

from __future__ import annotations

import sys
import os
import json
import fnmatch
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_QE_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _QE_ROOT)

from research.results import ResultRecord, load_results
from research.validity import (
    FULLY_VALID,
    PARTIALLY_VALID_MISSING_DATA,
    INVALID_DEPENDENCY_FAILURE,
    INVALID_NO_OUTPUT,
)

LEGACY_OUTPUT_DIR = os.path.join(_QE_ROOT, "output", "experiments")
RUNS_OUTPUT_DIR = os.path.join(_QE_ROOT, "output", "runs")


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def load_from_runs_tree(runs_dir: str) -> list[ResultRecord]:
    """
    Walk output/runs/<experiment>/<timestamp>/result.json and load all records.
    """
    records = []
    if not os.path.isdir(runs_dir):
        return records
    for exp_name in os.listdir(runs_dir):
        exp_dir = os.path.join(runs_dir, exp_name)
        if not os.path.isdir(exp_dir):
            continue
        for ts_dir in sorted(os.listdir(exp_dir)):
            result_path = os.path.join(exp_dir, ts_dir, "result.json")
            if not os.path.exists(result_path):
                continue
            try:
                with open(result_path, encoding="utf-8") as f:
                    d = json.load(f)
                r = ResultRecord(**{k: v for k, v in d.items() if k != "raw_stats"})
                records.append(r)
            except Exception as e:
                print(f"  WARN: could not load {result_path}: {e}")
    return records


def deduplicate_latest(records: list[ResultRecord]) -> list[ResultRecord]:
    """Keep only the most recent run per experiment name."""
    latest: dict[str, ResultRecord] = {}
    for r in records:
        key = r.experiment_name
        if key not in latest or r.run_timestamp > latest[key].run_timestamp:
            latest[key] = r
    return list(latest.values())


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

_VALID_TAG = {
    FULLY_VALID: "OK",
    PARTIALLY_VALID_MISSING_DATA: "PARTIAL",
    INVALID_DEPENDENCY_FAILURE: "DEP_FAIL",
    INVALID_NO_OUTPUT: "NO_OUTPUT",
    "PENDING": "PENDING",
}


def _fmt(val: Optional[float], fmt: str, na: str = "N/A") -> str:
    if val is None:
        return na
    return format(val, fmt)


def compare(records: list[ResultRecord], valid_only: bool = False) -> None:
    if not records:
        print("No results found.")
        return

    if valid_only:
        records = [r for r in records if r.valid in (FULLY_VALID, PARTIALLY_VALID_MISSING_DATA)]
        if not records:
            print("No valid results after filtering.")
            return

    # Best-in-class for starring
    valid_cagrs   = [r.cagr for r in records if r.cagr is not None]
    valid_sharpes = [r.sharpe for r in records if r.sharpe is not None]
    valid_dds     = [r.max_drawdown for r in records if r.max_drawdown is not None]

    best_cagr   = max(valid_cagrs)   if valid_cagrs   else None
    best_sharpe = max(valid_sharpes) if valid_sharpes else None
    best_dd     = max(valid_dds)     if valid_dds     else None  # least negative

    name_w = 35
    line_w = name_w + 120

    print(f"\n{'=' * line_w}")
    print(f"  QUANTUM EDGE -- BACKTEST COMPARISON  ({len(records)} runs)")
    print(f"{'=' * line_w}")
    print(
        f"  {'Experiment':<{name_w}}  "
        f"{'CAGR':>7}  {'MaxDD':>7}  {'Sharpe':>6}  {'Sortino':>7}  "
        f"{'NetPft':>7}  {'EndEq':>9}  "
        f"{'WinRate':>7}  {'ProfFac':>7}  "
        f"{'Orders':>6}  {'Fees$':>8}  {'Turn%':>5}  "
        f"{'DataFail':>8}  {'Sleeves':<20}  Valid"
    )
    print("-" * line_w)

    for r in sorted(records, key=lambda x: x.sharpe or -999, reverse=True):
        cagr    = _fmt(r.cagr,           ".2%")
        dd      = _fmt(r.max_drawdown,   ".2%")
        sharpe  = _fmt(r.sharpe,         ".2f")
        sortino = _fmt(r.sortino,        ".2f")
        netpft  = _fmt(r.net_profit_pct, ".1%")
        endeq   = f"${r.end_equity:>8,.0f}" if r.end_equity else "       N/A"
        wr      = _fmt(r.win_rate,       ".1%")
        pf      = _fmt(r.profit_factor,  ".2f")
        orders  = str(r.total_orders or 0)
        fees    = f"${r.total_fees:,.0f}"  if r.total_fees    else "N/A"
        turn    = _fmt(r.turnover,       ".1%")
        dfail   = _fmt(r.data_failure_pct, ".0%")

        # Best-in-class stars
        star_c = "*" if r.cagr   is not None and best_cagr   is not None and abs(r.cagr   - best_cagr)   < 1e-6 else " "
        star_s = "*" if r.sharpe is not None and best_sharpe is not None and abs(r.sharpe - best_sharpe) < 1e-6 else " "
        star_d = "*" if r.max_drawdown is not None and best_dd is not None and abs(r.max_drawdown - best_dd) < 1e-6 else " "

        sleeves  = r.sleeves_active[:20] if r.sleeves_active else ""
        valid_tag = _VALID_TAG.get(r.valid, r.valid)

        print(
            f"  {r.experiment_name:<{name_w}}  "
            f"{cagr:>7}{star_c} {dd:>7}{star_d} {sharpe:>6}{star_s} {sortino:>7}  "
            f"{netpft:>7}  {endeq}  "
            f"{wr:>7}  {pf:>7}  "
            f"{orders:>6}  {fees:>8}  {turn:>5}  "
            f"{dfail:>8}  {sleeves:<20}  {valid_tag}"
        )

    print(f"{'=' * line_w}")
    print("  * = best in class  |  DataFail: fraction of data requests that failed")
    print("  Validity: OK=all data present  PARTIAL=some gaps  DEP_FAIL=hard dependency missing  NO_OUTPUT=crash")
    print()

    # ── Regime filter impact summary ─────────────────────────────────────────
    _print_regime_summary(records)

    # ── Sleeve composition summary ────────────────────────────────────────────
    _print_sleeve_summary(records)

    # ── Data issues summary ───────────────────────────────────────────────────
    invalid = [r for r in records if r.valid not in (FULLY_VALID, PARTIALLY_VALID_MISSING_DATA)]
    if invalid:
        print(f"DATA ISSUES ({len(invalid)} runs excluded from best-in-class starring):")
        for r in invalid:
            tag = _VALID_TAG.get(r.valid, r.valid)
            print(f"  {r.experiment_name:<35}  [{tag}]  {r.validity_note[:80]}")
        print()


def _print_regime_summary(records: list[ResultRecord]) -> None:
    on  = [r for r in records if "regime=True"  in (r.regime_filters or "")
           and r.cagr is not None]
    off = [r for r in records if "regime=False" in (r.regime_filters or "")
           and r.cagr is not None]
    if not (on and off):
        return

    avg = lambda items, attr: sum(getattr(x, attr) or 0 for x in items) / len(items)
    print("REGIME FILTER IMPACT (mean across matched experiments):")
    print(f"  With regime filter    : CAGR={avg(on, 'cagr'):.2%}  MaxDD={avg(on, 'max_drawdown'):.2%}  Sharpe={avg(on, 'sharpe'):.2f}  (n={len(on)})")
    print(f"  Without regime filter : CAGR={avg(off,'cagr'):.2%}  MaxDD={avg(off,'max_drawdown'):.2%}  Sharpe={avg(off,'sharpe'):.2f}  (n={len(off)})")
    print()


def _print_sleeve_summary(records: list[ResultRecord]) -> None:
    groups: dict[str, list[ResultRecord]] = {}
    for r in records:
        if r.cagr is not None:
            key = r.sleeves_active or "unknown"
            groups.setdefault(key, []).append(r)
    if len(groups) < 2:
        return

    avg = lambda items: sum(x.cagr or 0 for x in items) / len(items)
    print("SLEEVE COMPOSITION CAGR (mean per config):")
    for key, recs in sorted(groups.items(), key=lambda kv: -avg(kv[1])):
        print(f"  {key:<30}  CAGR={avg(recs):.2%}  Sharpe={sum(x.sharpe or 0 for x in recs)/len(recs):.2f}  (n={len(recs)})")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    args = sys.argv[1:]
    use_runs   = "--runs"       in args
    valid_only = "--valid-only" in args
    patterns   = [a for a in args if not a.startswith("--")] or ["*"]

    if use_runs:
        all_records = load_from_runs_tree(RUNS_OUTPUT_DIR)
    else:
        if os.path.isdir(LEGACY_OUTPUT_DIR):
            all_records = load_results(LEGACY_OUTPUT_DIR)
        else:
            all_records = load_from_runs_tree(RUNS_OUTPUT_DIR)

    filtered = [
        r for r in all_records
        if any(fnmatch.fnmatch(r.experiment_name, p) for p in patterns)
    ]
    deduped = deduplicate_latest(filtered)
    compare(deduped, valid_only=valid_only)
