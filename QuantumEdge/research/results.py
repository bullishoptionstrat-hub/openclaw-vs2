"""
Result Parser — reads Lean backtest output and extracts structured stats.

Parses:
  - STATISTICS:: lines from launcher stdout/stderr
  - DATA USAGE:: lines for data quality
  - QuantumEdge-summary.json for equity curve (optional)

Produces a ResultRecord dataclass for comparison and archiving.
"""

from __future__ import annotations
import re
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------


@dataclass
class ResultRecord:
    experiment_name: str
    run_timestamp: str
    valid: str  # "FULLY_VALID" | "PARTIALLY_VALID" | "INVALID"
    validity_note: str

    # Core performance
    cagr: Optional[float] = None
    total_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None

    # Risk
    annual_vol: Optional[float] = None
    drawdown_recovery_days: Optional[int] = None

    # Activity
    total_orders: Optional[int] = None
    total_fees: Optional[float] = None
    turnover: Optional[float] = None

    # Capital
    start_equity: Optional[float] = None
    end_equity: Optional[float] = None
    net_profit_pct: Optional[float] = None

    # Data quality
    data_requests_succeeded: Optional[int] = None
    data_requests_failed: Optional[int] = None
    data_failure_pct: Optional[float] = None
    universe_failure_pct: Optional[float] = None

    # Config snapshot (subset)
    sleeves_active: str = ""
    regime_filters: str = ""
    raw_stats: dict = field(default_factory=dict)

    def to_summary_line(self) -> str:
        """One-line CSV-style summary for quick comparison."""
        return (
            f"{self.experiment_name:<35} | "
            f"CAGR={self.cagr or 0:.2%}  "
            f"DD={self.max_drawdown or 0:.2%}  "
            f"Sharpe={self.sharpe or 0:.2f}  "
            f"Sortino={self.sortino or 0:.2f}  "
            f"Orders={self.total_orders or 0}  "
            f"Fees=${self.total_fees or 0:,.0f}  "
            f"Valid={self.valid}"
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_stats", None)
        return d


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class ResultParser:
    # Maps STATISTICS:: key → ResultRecord field name + type
    STAT_MAP = {
        "Compounding Annual Return": ("cagr", float, 0.01),
        "Net Profit": ("net_profit_pct", float, 0.01),
        "Drawdown": ("max_drawdown", float, -0.01),
        "Sharpe Ratio": ("sharpe", float, 1.0),
        "Sortino Ratio": ("sortino", float, 1.0),
        "Win Rate": ("win_rate", float, 0.01),
        "Annual Standard Deviation": ("annual_vol", float, 1.0),
        "Total Orders": ("total_orders", int, 1),
        "Total Fees": ("total_fees", float, 1.0),
        "Portfolio Turnover": ("turnover", float, 0.01),
        "Start Equity": ("start_equity", float, 1.0),
        "End Equity": ("end_equity", float, 1.0),
        "Drawdown Recovery": ("drawdown_recovery_days", int, 1),
    }

    DATA_USAGE_MAP = {
        "Succeeded data requests": "data_requests_succeeded",
        "Failed data requests": "data_requests_failed",
        "Failed data requests percentage": "data_failure_pct",
        "Failed universe data requests percentage": "universe_failure_pct",
    }

    @classmethod
    def parse_output(
        cls,
        stdout_text: str,
        experiment_name: str,
        config_overrides: dict,
        lean_results_json: Optional[str] = None,
    ) -> ResultRecord:
        raw_stats: dict[str, str] = {}
        record = ResultRecord(
            experiment_name=experiment_name,
            run_timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            valid="UNKNOWN",
            validity_note="",
        )

        # ── Primary: parse QuantumEdge.json written by Lean ──────────────
        # Lean writes a full JSON result file even when the process crashes
        # at shutdown (GIL cleanup crash on pythonnet 2.0.53). stdout-based
        # STATISTICS:: parsing is unreliable because the crash can truncate
        # stdout before those lines flush.
        if lean_results_json and os.path.exists(lean_results_json):
            try:
                with open(lean_results_json, encoding="utf-8") as f:
                    lean_data = json.load(f)
                stats_dict = lean_data.get("statistics", {})
                for key, val in stats_dict.items():
                    raw_stats[key] = str(val)
                    cls._apply_stat(record, key, str(val))
                # data-monitor report for data quality (separate file)
            except Exception:
                pass  # fall through to stdout parsing below

        # ── Fallback: parse STATISTICS:: lines from stdout/stderr ────────
        if not raw_stats:
            for line in stdout_text.splitlines():
                m = re.match(r"STATISTICS::\s+(.+?)\s+(.+)", line)
                if m:
                    key, val = m.group(1).strip(), m.group(2).strip()
                    raw_stats[key] = val
                    cls._apply_stat(record, key, val)

        # ── Parse DATA USAGE lines from stdout (not in JSON) ─────────────
        for line in stdout_text.splitlines():
            m = re.match(r"DATA USAGE::\s+(.+?)\s+(\d+\.?\d*)", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
                field_name = cls.DATA_USAGE_MAP.get(key)
                if field_name:
                    try:
                        pct_fields = {"data_failure_pct", "universe_failure_pct"}
                        v = float(val) / 100 if field_name in pct_fields else float(val)
                        setattr(
                            record, field_name, v if "pct" not in field_name else float(val) / 100
                        )
                        if field_name in ("data_requests_succeeded", "data_requests_failed"):
                            setattr(record, field_name, int(float(val)))
                    except ValueError:
                        pass

        # ── Also try data-monitor report for data quality ─────────────────
        # Lean writes data-monitor-report-<timestamp>.json in LEAN_WORK_DIR
        if lean_results_json:
            work_dir = os.path.dirname(lean_results_json)
            dm_files = sorted(
                [f for f in os.listdir(work_dir) if f.startswith("data-monitor-report-")],
                reverse=True,
            )
            if dm_files:
                try:
                    with open(os.path.join(work_dir, dm_files[0]), encoding="utf-8") as f:
                        dm = json.load(f)
                    succeeded = dm.get("succeededDataRequests", 0) or 0
                    failed = dm.get("failedDataRequests", 0) or 0
                    total = succeeded + failed
                    if record.data_requests_succeeded is None:
                        record.data_requests_succeeded = int(succeeded)
                    if record.data_requests_failed is None:
                        record.data_requests_failed = int(failed)
                    if record.data_failure_pct is None and total > 0:
                        record.data_failure_pct = round(failed / total, 6)
                    univ_failed = dm.get("failedUniverseDataRequests", 0) or 0
                    univ_total = dm.get("totalUniverseDataRequests", 0) or 0
                    if record.universe_failure_pct is None and univ_total > 0:
                        record.universe_failure_pct = round(univ_failed / univ_total, 6)
                except Exception:
                    pass

        record.raw_stats = raw_stats

        # ── Compute profit factor if available ────────────────────────────
        avg_win = cls._parse_pct(raw_stats.get("Average Win", ""))
        avg_loss = cls._parse_pct(raw_stats.get("Average Loss", ""))
        win_rate = record.win_rate or 0.0
        if avg_win and avg_loss and win_rate > 0:
            record.profit_factor = round((win_rate * avg_win) / ((1 - win_rate) * abs(avg_loss)), 3)

        # Validity is set by the caller (runner.py) via research.validity.classify().
        # Leave it as "PENDING" here so a missing assignment is visible.
        record.valid = "PENDING"
        record.validity_note = ""

        # ── Config snapshot ───────────────────────────────────────────────
        a = config_overrides.get("ENABLE_SLEEVE_A", True)
        b = config_overrides.get("ENABLE_SLEEVE_B", False)
        c = config_overrides.get("ENABLE_SLEEVE_C", True)
        record.sleeves_active = (
            f"A={'ON' if a else 'OFF'}  B={'ON' if b else 'OFF'}  C={'ON' if c else 'OFF'}"
        )
        r = config_overrides.get("USE_REGIME_FILTER", True)
        sv = config_overrides.get("USE_SPY_SMA_FILTER", True)
        vx = config_overrides.get("USE_VXX_FILTER", True)
        record.regime_filters = f"regime={r}  spy_sma={sv}  vxx={vx}"

        return record

    @classmethod
    def _apply_stat(cls, record: ResultRecord, key: str, val: str) -> None:
        mapping = cls.STAT_MAP.get(key)
        if not mapping:
            return
        field_name, typ, scale = mapping
        try:
            if "%" in val:
                # _parse_pct already divides by 100 → apply sign of scale only
                # (scale magnitude encodes "is percentage" which _parse_pct handles)
                v = cls._parse_pct(val)
                if v is None:
                    return
                if scale < 0:
                    v = -abs(v)
            else:
                v = float(val.replace(",", "").replace("$", ""))
                if abs(scale) != 1.0:
                    v = v * scale
            if typ is int:
                v = int(round(v))
            setattr(record, field_name, round(v, 6) if typ is float else v)
        except (ValueError, TypeError):
            pass

    @staticmethod
    def _parse_pct(val: str) -> Optional[float]:
        val = val.strip().rstrip("%")
        try:
            return float(val) / 100.0
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_result(record: ResultRecord, output_dir: str) -> str:
    """Save result JSON to output/experiments/<name>_<timestamp>.json."""
    os.makedirs(output_dir, exist_ok=True)
    fname = f"{record.experiment_name}_{record.run_timestamp.replace(':', '-')}.json"
    path = os.path.join(output_dir, fname)
    with open(path, "w") as f:
        json.dump(record.to_dict(), f, indent=2)
    return path


def load_results(output_dir: str) -> list[ResultRecord]:
    """Load all saved experiment results from output/experiments/."""
    records = []
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(output_dir, fname)) as f:
            d = json.load(f)
        r = ResultRecord(**{k: v for k, v in d.items() if k != "raw_stats"})
        records.append(r)
    return records
