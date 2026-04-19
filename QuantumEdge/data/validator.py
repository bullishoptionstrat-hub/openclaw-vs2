"""
Data Validation Layer

Checks data presence and quality BEFORE the algorithm starts trading.
Called from initialize() to catch problems early and emit explicit warnings.

Design goals:
  - Fail fast on critical missing symbols
  - Warn (not fail) on degraded coverage
  - Produce a structured report for the experiment log
  - Distinguish "strategy issue" from "data issue"
"""

from __future__ import annotations
import os
import zipfile
from dataclasses import dataclass, field
from AlgorithmImports import *
from algorithm.config import (
    SECTORS,
    IBS_ETFS,
    LETF_TICKER,
    FALLBACK_ASSET,
    ENABLE_SLEEVE_B,
    ENABLE_SLEEVE_C,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class SymbolStatus:
    ticker: str
    present: bool
    row_count: int = 0
    coverage_pct: float = 0.0
    note: str = ""


@dataclass
class ValidationReport:
    valid: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    symbol_statuses: list[SymbolStatus] = field(default_factory=list)
    fundamental_data_available: bool = False

    def to_log_lines(self) -> list[str]:
        lines = [
            "=" * 60,
            f"DATA VALIDATION  valid={self.valid}",
            f"  fundamental_data={self.fundamental_data_available}",
        ]
        if self.errors:
            lines.append("ERRORS:")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        if self.warnings:
            lines.append("WARNINGS:")
            for w in self.warnings:
                lines.append(f"  WARN: {w}")
        lines.append("SYMBOL STATUS:")
        for s in self.symbol_statuses:
            mark = "OK " if s.present else "MISSING"
            lines.append(
                f"  {mark}  {s.ticker:<8}  rows={s.row_count:>5}  "
                f"cov={s.coverage_pct:>5.1f}%  {s.note}"
            )
        lines.append("=" * 60)
        return lines


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class DataValidator:
    """
    Validates local Lean data files and reports what is missing.

    Usage:
        report = DataValidator(lean_data_root).validate()
        for line in report.to_log_lines():
            algorithm.log(line)
        if not report.valid:
            raise Exception("Data validation failed — see log")
    """

    REQUIRED_TICKERS = ["SPY", "SHY", LETF_TICKER] + SECTORS

    OPTIONAL_TICKERS = [
        "VXX",  # Only available from 2018-01-25 locally
    ] + (IBS_ETFS if ENABLE_SLEEVE_C else [])

    # Minimum trading days expected for a 10-year backtest with warmup
    MIN_ROWS = 500

    def __init__(self, lean_data_root: str):
        self._daily_dir = os.path.join(lean_data_root, "equity", "usa", "daily")
        self._fundamental_dir = os.path.join(lean_data_root, "equity", "usa", "fundamental")

    # ------------------------------------------------------------------

    def validate(self) -> ValidationReport:
        report = ValidationReport()

        # 1. Required ETF data
        for ticker in self.REQUIRED_TICKERS:
            status = self._check_zip(ticker)
            report.symbol_statuses.append(status)
            if not status.present:
                report.errors.append(f"REQUIRED ticker missing: {ticker}")
                report.valid = False
            elif status.row_count < self.MIN_ROWS:
                report.warnings.append(
                    f"{ticker} has only {status.row_count} rows — may cause degraded signals"
                )

        # 2. Optional ETF data
        for ticker in self.OPTIONAL_TICKERS:
            status = self._check_zip(ticker)
            report.symbol_statuses.append(status)
            if not status.present:
                report.warnings.append(
                    f"Optional ticker missing: {ticker} — strategy will degrade gracefully"
                )

        # 3. Fundamental data (Sleeve B)
        fund_present = self._check_fundamental_data()
        report.fundamental_data_available = fund_present
        if ENABLE_SLEEVE_B and not fund_present:
            report.errors.append(
                "ENABLE_SLEEVE_B=True but fundamental data NOT found at "
                f"{self._fundamental_dir}. "
                "Sleeve B will produce no trades — results are INVALID."
            )
            report.valid = False
        elif not fund_present:
            report.warnings.append(
                "Fundamental data absent — Sleeve B must remain disabled. "
                "This is expected in local-only mode."
            )

        return report

    # ------------------------------------------------------------------

    def _check_zip(self, ticker: str) -> SymbolStatus:
        path = os.path.join(self._daily_dir, f"{ticker.lower()}.zip")
        if not os.path.exists(path):
            return SymbolStatus(ticker=ticker, present=False, note="zip not found")

        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if not names:
                    return SymbolStatus(ticker=ticker, present=False, note="zip empty")
                content = zf.read(names[0]).decode(errors="replace")
                rows = [ln for ln in content.splitlines() if ln.strip()]
                n = len(rows)
                return SymbolStatus(
                    ticker=ticker,
                    present=True,
                    row_count=n,
                    coverage_pct=min(100.0, n / 3_650 * 100),
                )
        except Exception as ex:
            return SymbolStatus(ticker=ticker, present=False, note=f"zip error: {ex}")

    def _check_fundamental_data(self) -> bool:
        """
        Fundamental data exists if the coarse and fine subdirectories
        are non-empty.  This is a quick presence check, not a content check.
        """
        coarse_dir = os.path.join(self._fundamental_dir, "coarse")
        fine_dir = os.path.join(self._fundamental_dir, "fine")
        if not os.path.isdir(coarse_dir) or not os.path.isdir(fine_dir):
            return False
        try:
            coarse_files = os.listdir(coarse_dir)
            fine_files = os.listdir(fine_dir)
            return len(coarse_files) > 10 and len(fine_files) > 10
        except OSError:
            return False
