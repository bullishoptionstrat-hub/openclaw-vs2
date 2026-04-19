"""
Experiment Runner

Runs named Lean backtest experiments in sequence.
For each experiment:
  1. Create run directory: output/runs/<name>/<timestamp>/
  2. Write experiment_config.json (overrides for config.py)
  3. Launch QuantConnect.Lean.Launcher.exe as subprocess
  4. Capture output; copy Lean artifacts into run dir
  5. Parse results from QuantumEdge.json (not stdout — stdout is unreliable
     due to .NET GIL crash at shutdown on pythonnet 2.0.53)
  6. Classify validity (explicit rules in research/validity.py)
  7. Write manifest.json + result.json into run dir
  8. Print summary line

Usage:
  python research/runner.py                                  # run all experiments
  python research/runner.py baseline_full                    # run one
  python research/runner.py baseline_full sectors_only       # run subset
  python research/runner.py ablation_*                       # glob matching
  python research/runner.py --list                           # list all experiment names

Requirements:
  - Run from the QuantumEdge/ directory (or from the repo root)
  - Lean engine must be built at lean/Launcher/bin/Release/
  - PYTHONNET_PYDLL env var must be set (or configure the default below)
"""

from __future__ import annotations

import sys
import os
import io
import json
import subprocess
import time
import fnmatch
import shutil
from datetime import datetime

# Force UTF-8 output on Windows consoles (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_QE_ROOT = os.path.dirname(_SCRIPT_DIR)
_REPO_ROOT = os.path.dirname(_QE_ROOT)

sys.path.insert(0, _QE_ROOT)

from research.experiments import EXPERIMENTS, get_experiment
from research.results import ResultParser, save_result, ResultRecord
from research.validity import classify as classify_validity
from research.manifest import build_manifest, STRATEGY_VERSION

# ── Lean engine paths ─────────────────────────────────────────────────────────
LEAN_LAUNCHER = os.path.join(
    _REPO_ROOT, "lean", "Launcher", "bin", "Release", "QuantConnect.Lean.Launcher.exe"
)
LEAN_WORK_DIR = os.path.join(_REPO_ROOT, "lean", "Launcher", "bin", "Release")
LEAN_RESULTS_JSON = os.path.join(LEAN_WORK_DIR, "QuantumEdge.json")
LEAN_LOG_SRC = os.path.join(LEAN_WORK_DIR, "QuantumEdge-log.txt")

EXPERIMENT_CONFIG_PATH = os.path.join(_QE_ROOT, "experiment_config.json")

# ── Output layout ─────────────────────────────────────────────────────────────
# output/
#   runs/
#     <experiment_name>/
#       <YYYYMMDDTHHMMSS>/
#         manifest.json
#         result.json
#         lean.log
#         QuantumEdge.json   (copy of Lean's result file)
#         data-monitor.json  (copy of Lean's data monitor report, if present)
#   experiments/            (legacy flat JSON files — kept for backwards compat)
OUTPUT_RUNS_DIR = os.path.join(_QE_ROOT, "output", "runs")
OUTPUT_LEGACY_DIR = os.path.join(_QE_ROOT, "output", "experiments")

# ── Python 3.11 DLL (required for pythonnet 2.0.53 compatibility) ─────────────
PYTHONNET_PYDLL = os.environ.get(
    "PYTHONNET_PYDLL",
    r"C:\Users\alexm\AppData\Roaming\uv\python\cpython-3.11.14-windows-x86_64-none\python311.dll",
)

LEAN_TIMEOUT_SECONDS = 600  # 10 minutes max per run


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def write_experiment_config(overrides: dict) -> None:
    """Write experiment_config.json so config.py picks up the overrides."""
    with open(EXPERIMENT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)


def clear_experiment_config() -> None:
    if os.path.exists(EXPERIMENT_CONFIG_PATH):
        os.remove(EXPERIMENT_CONFIG_PATH)


# ---------------------------------------------------------------------------
# Run directory management
# ---------------------------------------------------------------------------


def make_run_dir(experiment_name: str) -> tuple[str, str]:
    """
    Create and return (run_dir, timestamp_str).
    run_dir = output/runs/<name>/<YYYYMMDDTHHMMSS>/
    """
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    run_dir = os.path.join(OUTPUT_RUNS_DIR, experiment_name, ts)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir, ts


def _find_latest_data_monitor() -> str:
    """Return path of the most-recently-written data-monitor report in LEAN_WORK_DIR."""
    candidates = sorted(
        (f for f in os.listdir(LEAN_WORK_DIR) if f.startswith("data-monitor-report-")),
        reverse=True,
    )
    return os.path.join(LEAN_WORK_DIR, candidates[0]) if candidates else ""


def archive_lean_artifacts(run_dir: str) -> tuple[str, str, str]:
    """
    Copy Lean output files into run_dir.
    Returns (lean_log_dst, lean_results_dst, data_monitor_dst).
    Missing files are noted but do not raise.
    """
    lean_log_dst = ""
    lean_results_dst = ""
    data_monitor_dst = ""

    if os.path.exists(LEAN_LOG_SRC):
        lean_log_dst = os.path.join(run_dir, "lean.log")
        shutil.copy2(LEAN_LOG_SRC, lean_log_dst)

    if os.path.exists(LEAN_RESULTS_JSON):
        lean_results_dst = os.path.join(run_dir, "QuantumEdge.json")
        shutil.copy2(LEAN_RESULTS_JSON, lean_results_dst)

    dm_src = _find_latest_data_monitor()
    if dm_src:
        data_monitor_dst = os.path.join(run_dir, "data-monitor.json")
        shutil.copy2(dm_src, data_monitor_dst)

    return lean_log_dst, lean_results_dst, data_monitor_dst


# ---------------------------------------------------------------------------
# Lean subprocess
# ---------------------------------------------------------------------------


def run_lean(experiment_name: str) -> tuple[str, int, float]:
    """
    Launch Lean, capture combined stdout+stderr, return (output, exit_code, elapsed_s).
    """
    env = os.environ.copy()
    env["PYTHONNET_PYDLL"] = PYTHONNET_PYDLL

    print(f"  [RUN ] {experiment_name} ...")
    start = time.time()

    proc = subprocess.run(
        [LEAN_LAUNCHER],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=LEAN_WORK_DIR,
        env=env,
        timeout=LEAN_TIMEOUT_SECONDS,
    )

    elapsed = time.time() - start
    combined = proc.stdout + "\n" + proc.stderr
    print(f"  [DONE] {experiment_name}  exit={proc.returncode}  {elapsed:.0f}s")
    return combined, proc.returncode, elapsed


# ---------------------------------------------------------------------------
# Core experiment run
# ---------------------------------------------------------------------------


def run_experiment(name: str) -> ResultRecord:
    """Run one named experiment; return a fully-populated ResultRecord."""
    overrides = get_experiment(name)
    run_dir, ts = make_run_dir(name)

    write_experiment_config(overrides)
    try:
        output, exit_code, elapsed = run_lean(name)
    finally:
        clear_experiment_config()

    # Archive Lean artifacts before parsing (so they're there even on parse error)
    lean_log_dst, lean_results_dst, data_monitor_dst = archive_lean_artifacts(run_dir)

    # Parse result from QuantumEdge.json (primary) with stdout fallback
    record = ResultParser.parse_output(
        stdout_text=output,
        experiment_name=name,
        config_overrides=overrides,
        lean_results_json=LEAN_RESULTS_JSON,
    )

    # Classify validity with explicit rules
    validity = classify_validity(record, overrides)
    record.valid = validity.label
    record.validity_note = validity.reason

    # Save result.json into run dir
    result_path = os.path.join(run_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)

    # Also write to legacy flat dir for backwards compat with existing analytics
    os.makedirs(OUTPUT_LEGACY_DIR, exist_ok=True)
    legacy_path = save_result(record, OUTPUT_LEGACY_DIR)

    # Build and save manifest
    manifest = build_manifest(
        experiment_name=name,
        overrides=overrides,
        validity_label=validity.label,
        validity_reason=validity.reason,
        warnings=validity.warnings,
        run_dir=run_dir,
        result_json_path=result_path,
        lean_log_path=lean_log_dst,
        lean_results_json_path=lean_results_dst,
        data_monitor_path=data_monitor_dst,
        repo_root=_REPO_ROOT,
        config_overrides_path=EXPERIMENT_CONFIG_PATH,
    )
    manifest.save()

    print(f"         -> {record.to_summary_line()}")
    print(f"         -> run dir: {run_dir}")
    return record


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------


def run_experiments(names: list[str]) -> list[ResultRecord]:
    os.makedirs(OUTPUT_RUNS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_LEGACY_DIR, exist_ok=True)
    results = []
    total = len(names)

    print(f"\n{'=' * 72}")
    print(f"QUANTUM EDGE  EXPERIMENT RUNNER  v{STRATEGY_VERSION}  ({total} experiments)")
    print(f"{'=' * 72}")
    print(f"  Lean launcher : {LEAN_LAUNCHER}")
    print(f"  Python DLL    : {PYTHONNET_PYDLL}")
    print(f"  Runs dir      : {OUTPUT_RUNS_DIR}")
    print(f"{'=' * 72}\n")

    for i, name in enumerate(names, 1):
        print(f"[{i}/{total}] {name}")
        try:
            r = run_experiment(name)
            results.append(r)
        except Exception as ex:
            print(f"  [FAIL] {name}: {ex}")
            import traceback
            traceback.print_exc()
        print()

    print_comparison_table(results)
    return results


# ---------------------------------------------------------------------------
# Comparison table (terminal output)
# ---------------------------------------------------------------------------


def print_comparison_table(records: list[ResultRecord]) -> None:
    if not records:
        return

    col_w = 32
    line_w = col_w + 8 + 8 + 7 + 7 + 8 + 9 + 8 + 28
    print(f"\n{'=' * line_w}")
    print("RESULTS COMPARISON")
    print(f"{'=' * line_w}")
    hdr = (
        f"{'Experiment':<{col_w}}  "
        f"{'CAGR':>7}  {'MaxDD':>7}  "
        f"{'Sharpe':>6}  {'Sortino':>7}  "
        f"{'NetPft':>7}  {'EndEq':>8}  "
        f"{'WinRate':>7}  {'Fees$':>8}  {'Turn%':>5}  "
        f"{'Sleeves':<16}  Valid"
    )
    print(hdr)
    print("-" * line_w)

    for r in sorted(records, key=lambda x: x.sharpe or -999, reverse=True):
        cagr    = f"{r.cagr:.2%}"          if r.cagr          is not None else "N/A"
        dd      = f"{r.max_drawdown:.2%}"  if r.max_drawdown   is not None else "N/A"
        sharpe  = f"{r.sharpe:.2f}"        if r.sharpe         is not None else "N/A"
        sortino = f"{r.sortino:.2f}"       if r.sortino        is not None else "N/A"
        netpft  = f"{r.net_profit_pct:.1%}" if r.net_profit_pct is not None else "N/A"
        endeq   = f"${r.end_equity:,.0f}"  if r.end_equity     is not None else "N/A"
        wr      = f"{r.win_rate:.1%}"      if r.win_rate       is not None else "N/A"
        fees    = f"${r.total_fees:,.0f}"  if r.total_fees     is not None else "N/A"
        turn    = f"{r.turnover:.1%}"      if r.turnover       is not None else "N/A"
        sleeves = r.sleeves_active[:16]    if r.sleeves_active else ""

        # Flag degraded validity
        valid_tag = {
            "FULLY_VALID": "OK",
            "PARTIALLY_VALID_MISSING_DATA": "PARTIAL",
            "INVALID_DEPENDENCY_FAILURE": "DEP_FAIL",
            "INVALID_NO_OUTPUT": "NO_OUTPUT",
        }.get(r.valid, r.valid)

        print(
            f"{r.experiment_name:<{col_w}}  "
            f"{cagr:>7}  {dd:>7}  "
            f"{sharpe:>6}  {sortino:>7}  "
            f"{netpft:>7}  {endeq:>8}  "
            f"{wr:>7}  {fees:>8}  {turn:>5}  "
            f"{sleeves:<16}  {valid_tag}"
        )

    print(f"{'=' * line_w}")
    # Validity legend
    print("  Validity: OK=fully valid  PARTIAL=some data gaps  DEP_FAIL=missing dependency  NO_OUTPUT=crash")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list" in args:
        for name in EXPERIMENTS:
            print(name)
        sys.exit(0)

    if not args:
        names = list(EXPERIMENTS.keys())
    else:
        names = []
        all_names = list(EXPERIMENTS.keys())
        for pattern in args:
            matched = fnmatch.filter(all_names, pattern)
            if not matched:
                if pattern in EXPERIMENTS:
                    matched = [pattern]
                else:
                    print(f"WARNING: no experiments match '{pattern}'")
                    print(f"Available: {all_names}")
            names.extend(m for m in matched if m not in names)

    if not names:
        print("No experiments to run.")
        sys.exit(1)

    run_experiments(names)
