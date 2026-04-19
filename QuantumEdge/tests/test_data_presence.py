"""
Tests — Data presence checks (runs outside Lean, pure Python)

Usage: python -m pytest tests/  (or just python tests/test_data_presence.py)
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch AlgorithmImports with stubs so tests work outside Lean
import types, importlib

_ai = types.ModuleType("AlgorithmImports")
for name in [
    "QCAlgorithm",
    "Symbol",
    "Resolution",
    "DataNormalizationMode",
    "BrokerageName",
    "AccountType",
    "SecurityChanges",
    "SimpleMovingAverage",
    "StandardDeviation",
    "RateOfChange",
    "Security",
    "Universe",
]:
    setattr(_ai, name, type(name, (), {}))
sys.modules["AlgorithmImports"] = _ai
sys.modules["Selection.FundamentalUniverseSelectionModel"] = types.ModuleType(
    "Selection.FundamentalUniverseSelectionModel"
)
setattr(
    sys.modules["Selection.FundamentalUniverseSelectionModel"],
    "FundamentalUniverseSelectionModel",
    type("FundamentalUniverseSelectionModel", (), {"__init__": lambda s, **k: None}),
)

from algorithm.config import SECTORS, IBS_ETFS, LETF_TICKER, FALLBACK_ASSET

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DAILY_DIR = os.path.join(_REPO_ROOT, "lean", "Data", "equity", "usa", "daily")


def _zip_exists(ticker: str) -> bool:
    return os.path.exists(os.path.join(_DAILY_DIR, f"{ticker.lower()}.zip"))


def test_required_sectors_present():
    missing = [t for t in SECTORS if not _zip_exists(t)]
    assert not missing, f"Missing sector zips: {missing}"


def test_fallback_and_letf_present():
    for t in [FALLBACK_ASSET, LETF_TICKER, "SPY", "VXX"]:
        assert _zip_exists(t), f"Missing required ticker: {t}"


def test_ibs_etfs_present():
    missing = [t for t in IBS_ETFS if not _zip_exists(t)]
    assert not missing, f"Missing IBS ETF zips: {missing}"


def test_config_allocations_sum_to_one():
    import algorithm.config as cfg

    enabled_total = (
        (cfg.SLEEVE_A_ALLOC if cfg.ENABLE_SLEEVE_A else 0)
        + (cfg.SLEEVE_B_ALLOC if cfg.ENABLE_SLEEVE_B else 0)
        + (cfg.SLEEVE_C_ALLOC if cfg.ENABLE_SLEEVE_C else 0)
    )
    # When B is disabled with redistribute, A+C should be re-normalised to 1.0
    if not cfg.ENABLE_SLEEVE_B and cfg.SLEEVE_B_FALLBACK == "redistribute":
        from strategy.allocator import Allocator

        # Can't instantiate without Symbol map, just check math
        a_raw = cfg.SLEEVE_A_ALLOC if cfg.ENABLE_SLEEVE_A else 0
        c_raw = cfg.SLEEVE_C_ALLOC if cfg.ENABLE_SLEEVE_C else 0
        total = a_raw + c_raw
        assert abs(total) > 0, "All sleeves disabled — nothing to trade"
    else:
        assert abs(enabled_total - 1.0) < 0.01, (
            f"Sleeve allocations don't sum to 1.0: {enabled_total}"
        )


if __name__ == "__main__":
    import traceback

    tests = [
        test_required_sectors_present,
        test_fallback_and_letf_present,
        test_ibs_etfs_present,
        test_config_allocations_sum_to_one,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
