"""
Run Manifest — machine-readable provenance for every backtest run.

Written to output/runs/<experiment_name>/<timestamp>/manifest.json
immediately after each run completes.  Contains everything needed to:
  - reproduce the run (config, git state)
  - audit the result (file paths, validity, warnings)
  - filter runs in analytics (sleeves, allocations, dates)

Design rule: manifest is written even if the run crashed (INVALID_NO_OUTPUT).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Strategy version — bump manually when algorithm logic changes
# ---------------------------------------------------------------------------

STRATEGY_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Manifest dataclass
# ---------------------------------------------------------------------------


@dataclass
class RunManifest:
    # Identity
    experiment_name: str
    timestamp_utc: str  # ISO-8601 UTC: "2026-04-19T14:22:19Z"
    strategy_version: str  # from STRATEGY_VERSION above

    # Provenance
    git_commit: str  # full SHA or "unknown"
    git_dirty: bool  # True if working tree had uncommitted changes
    config_overrides_path: str  # absolute path to experiment_config.json at run time

    # Configuration snapshot
    enabled_sleeves: dict  # {"A": bool, "B": bool, "C": bool, "LETF": bool}
    raw_allocations: dict  # {"A": 0.50, "B": 0.40, "C": 0.10} from config
    effective_allocations: dict  # {"A": 0.833, "C": 0.167} after B-disabled scaling
    sleeve_b_behavior: str  # "redistribute" | "shy" | "fail"
    regime_filters: dict  # {"filter": bool, "spy_sma": bool, "vxx": bool}
    backtest_start: str  # "2013-01-01"
    backtest_end: str  # "2023-12-31"

    # Output file paths (all absolute)
    run_dir: str  # output/runs/<name>/<timestamp>/
    result_json_path: str  # run_dir/result.json
    lean_log_path: str  # run_dir/lean.log
    lean_results_json_path: str  # run_dir/QuantumEdge.json
    data_monitor_path: str  # run_dir/data-monitor.json  (may be "")

    # Validity
    validity_label: str  # FULLY_VALID | PARTIALLY_VALID_MISSING_DATA |
    #   INVALID_DEPENDENCY_FAILURE | INVALID_NO_OUTPUT
    validity_reason: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self) -> str:
        """Write manifest.json into run_dir; return path."""
        os.makedirs(self.run_dir, exist_ok=True)
        path = os.path.join(self.run_dir, "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _git_state(repo_root: str) -> tuple[str, bool]:
    """Return (commit_sha, is_dirty).  Falls back gracefully if git absent."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return sha, bool(status)
    except Exception:
        return "unknown", False


def _effective_allocations(overrides: dict) -> dict[str, float]:
    """
    Compute the allocations that the Allocator actually uses.
    Mirrors Allocator._compute_effective_allocations() without importing it.
    """
    a_en = overrides.get("ENABLE_SLEEVE_A", True)
    b_en = overrides.get("ENABLE_SLEEVE_B", False)
    c_en = overrides.get("ENABLE_SLEEVE_C", True)

    a_w = overrides.get("SLEEVE_A_ALLOC", 0.50) if a_en else 0.0
    b_w = overrides.get("SLEEVE_B_ALLOC", 0.40) if b_en else 0.0
    c_w = overrides.get("SLEEVE_C_ALLOC", 0.10) if c_en else 0.0

    behavior = overrides.get(
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR", overrides.get("SLEEVE_B_FALLBACK", "redistribute")
    )

    if behavior == "redistribute" and not b_en:
        total = a_w + c_w
        if total > 0:
            a_w = round(a_w / total, 6)
            c_w = round(c_w / total, 6)
            b_w = 0.0

    result = {}
    if a_w:
        result["A"] = a_w
    if b_w:
        result["B"] = b_w
    if c_w:
        result["C"] = c_w
    return result


def build_manifest(
    *,
    experiment_name: str,
    overrides: dict,
    validity_label: str,
    validity_reason: str,
    warnings: list[str],
    run_dir: str,
    result_json_path: str,
    lean_log_path: str,
    lean_results_json_path: str,
    data_monitor_path: str,
    repo_root: str,
    config_overrides_path: str,
) -> RunManifest:
    sha, dirty = _git_state(repo_root)

    a_en = overrides.get("ENABLE_SLEEVE_A", True)
    b_en = overrides.get("ENABLE_SLEEVE_B", False)
    c_en = overrides.get("ENABLE_SLEEVE_C", True)
    letf_en = overrides.get("ENABLE_LETF_OVERLAY", True)

    return RunManifest(
        experiment_name=experiment_name,
        timestamp_utc=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        strategy_version=STRATEGY_VERSION,
        git_commit=sha,
        git_dirty=dirty,
        config_overrides_path=config_overrides_path,
        enabled_sleeves={"A": a_en, "B": b_en, "C": c_en, "LETF": letf_en},
        raw_allocations={
            "A": overrides.get("SLEEVE_A_ALLOC", 0.50),
            "B": overrides.get("SLEEVE_B_ALLOC", 0.40),
            "C": overrides.get("SLEEVE_C_ALLOC", 0.10),
        },
        effective_allocations=_effective_allocations(overrides),
        sleeve_b_behavior=overrides.get(
            "SLEEVE_B_UNAVAILABLE_BEHAVIOR",
            overrides.get("SLEEVE_B_FALLBACK", "redistribute"),
        ),
        regime_filters={
            "filter": overrides.get("USE_REGIME_FILTER", True),
            "spy_sma": overrides.get("USE_SPY_SMA_FILTER", True),
            "vxx": overrides.get("USE_VXX_FILTER", True),
        },
        backtest_start=f"{overrides.get('START_YEAR', 2013)}-"
        f"{overrides.get('START_MONTH', 1):02d}-"
        f"{overrides.get('START_DAY', 1):02d}",
        backtest_end=f"{overrides.get('END_YEAR', 2023)}-"
        f"{overrides.get('END_MONTH', 12):02d}-"
        f"{overrides.get('END_DAY', 31):02d}",
        run_dir=run_dir,
        result_json_path=result_json_path,
        lean_log_path=lean_log_path,
        lean_results_json_path=lean_results_json_path,
        data_monitor_path=data_monitor_path,
        validity_label=validity_label,
        validity_reason=validity_reason,
        warnings=warnings,
    )
