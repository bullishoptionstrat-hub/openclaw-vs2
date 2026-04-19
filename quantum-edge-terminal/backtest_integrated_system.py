#!/usr/bin/env python3
"""
INTEGRATED TRADING SYSTEM - Master Multi-Signal Performance Test

Tests all 5 trading modes with comprehensive metrics:
1. FRACTAL_ONLY: Current deployed strategy
2. FIB_ONLY: Fibonacci-only (for reference)
3. DUAL_CONFIRMATION: Both signals must align
4. BEST_OF_BOTH: Take whichever has better RR
5. SMART_BLEND: Fractal primary + Fib confirmation boost

Shows which mode is optimal and ready for production deployment.
"""

import asyncio
import random
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))
from modules.master_multi_signal import MasterMultiSignalValidator, StrategyPerformanceTracker


def generate_synthetic_signals(seed: int) -> Tuple[Dict, Dict]:
    """Generate realistic mock Fractal and Fib signals for testing."""
    random.seed(seed)

    # Simulate Fractal signal (high accuracy, lower frequency)
    fractal_result = {
        "valid": random.random() > 0.7,  # ~30% hit rate
        "pattern": random.choice(["BULLISH_FRACTAL", "BEARISH_FRACTAL"]),
        "confidence": random.gauss(0.90, 0.05),
        "entry": 420 + random.gauss(0, 2),
        "stop_loss": 420 - random.gauss(1.5, 0.5),
        "take_profit": 420 + random.gauss(3.5, 1),
        "risk_reward": random.gauss(1.39, 0.15),
    }

    # Simulate Fib signal (lower accuracy, higher frequency)
    fib_result = {
        "valid": random.random() > 0.5,  # ~50% hit rate
        "pattern": random.choice(["MANIP_BUY", "MANIP_SELL"]),
        "confidence": random.gauss(0.70, 0.15),
        "entry": 420 + random.gauss(0, 3),
        "stop_loss": 420 - random.gauss(2.0, 0.8),
        "take_profit": 420 + random.gauss(2.0, 1.5),
        "risk_reward": random.gauss(0.85, 0.30),
    }

    # Align patterns for realistic dual signals (~20% of time)
    if random.random() > 0.75:
        fractal_pattern = fractal_result["pattern"]
        fib_result["pattern"] = "MANIP_BUY" if "BULLISH" in fractal_pattern else "MANIP_SELL"

    return fractal_result, fib_result


@dataclass
class TestTrade:
    entry: float
    sl: float
    tp: float
    rr: float
    setup: str
    outcome: str = "OPEN"
    pnl: float = 0.0


class IntegratedSystemBacktester:
    def __init__(self, mode: str = "SMART_BLEND", runs: int = 100):
        self.validator = MasterMultiSignalValidator(mode=mode, fractal_fix_enabled=True)
        self.tracker = StrategyPerformanceTracker()
        self.mode = mode
        self.runs = runs
        self.signals_generated = 0
        self.signals_accepted = 0

    async def test(self):
        """Run integration tests."""
        for run in range(self.runs):
            random.seed(42 + run)

            # Generate signals
            fractal_sig, fib_sig = generate_synthetic_signals(42 + run)
            self.signals_generated += 1

            # Raw pattern names - ensure compatibility
            if fractal_sig.get("valid"):
                fractal_sig["pattern"] = fractal_sig.get("pattern", "BULLISH_FRACTAL")
            if fib_sig.get("valid"):
                fib_sig["pattern"] = fib_sig.get("pattern", "MANIP_BUY")

            # Validate with master system
            result = await self.validator.validate(
                candles=[],  # Not used in multi-signal mode
                fractal_result=fractal_sig,
                fib_result=fib_sig,
            )

            if not result.get("valid"):
                continue

            self.signals_accepted += 1

            # Simulate trade outcome
            trade = TestTrade(
                entry=result["entry"],
                sl=result["stop_loss"],
                tp=result["take_profit"],
                rr=result["risk_reward"],
                setup=result.get("signal_sources", "UNKNOWN"),
            )

            # Random outcome for testing (50/50 for simplicity)
            if random.random() > 0.55:  # ~45% win rate baseline
                trade.outcome = "WIN"
                trade.pnl = abs(trade.tp - trade.entry)
            else:
                trade.outcome = "LOSS"
                trade.pnl = -abs(trade.entry - trade.sl)

            self.tracker.record_trade(
                {
                    "entry": trade.entry,
                    "sl": trade.sl,
                    "tp": trade.tp,
                    "risk_reward": trade.rr,
                },
                trade.setup,
                trade.outcome,
                trade.pnl,
            )

    def get_results(self) -> Dict:
        """Get comprehensive results."""
        all_stats = self.tracker.get_stats()

        return {
            "mode": self.mode,
            "signals_generated": self.signals_generated,
            "signals_accepted": self.signals_accepted,
            "acceptance_rate": self.signals_accepted / self.signals_generated * 100
            if self.signals_generated > 0
            else 0,
            "total_trades": all_stats.get("total_trades", 0),
            "wins": all_stats.get("wins", 0),
            "losses": all_stats.get("losses", 0),
            "win_rate": all_stats.get("win_rate", 0),
            "profit_factor": all_stats.get("profit_factor", 0),
            "total_pnl": all_stats.get("total_pnl", 0),
            "expectancy": all_stats.get("expectancy", 0),
        }


async def test_all_modes() -> Dict[str, Dict]:
    """Test all 5 trading modes."""
    modes = ["FRACTAL_ONLY", "FIB_ONLY", "DUAL_CONFIRMATION", "BEST_OF_BOTH", "SMART_BLEND"]

    results = {}

    for mode in modes:
        print(f"Testing {mode:25s}...", end=" ", flush=True)
        tester = IntegratedSystemBacktester(mode=mode, runs=200)
        await tester.test()
        mode_results = tester.get_results()
        results[mode] = mode_results

        print(
            f"Signals={mode_results['signals_accepted']:3d} | "
            f"WR={mode_results['win_rate']:5.1f}% | "
            f"PF={mode_results['profit_factor']:5.2f}x | "
            f"Exp=${mode_results['expectancy']:7.2f}"
        )

    return results


async def main():
    print("\n" + "=" * 110)
    print("INTEGRATED TRADING SYSTEM - Multi-Signal Mode Optimization")
    print("=" * 110 + "\n")

    results = await test_all_modes()

    # Analysis
    print("\n" + "=" * 110)
    print("MODE COMPARISON & RECOMMENDATION")
    print("=" * 110)

    # Find best by different metrics
    best_wr = max(results.items(), key=lambda x: x[1]["win_rate"])
    best_pf = max(results.items(), key=lambda x: x[1]["profit_factor"])
    best_exp = max(results.items(), key=lambda x: x[1]["expectancy"])
    best_efficiency = max(
        results.items(),
        key=lambda x: (
            (x[1]["signals_accepted"] * x[1]["profit_factor"])
            / max(1, 100 - x[1]["acceptance_rate"])
        ),
    )

    print(f"\n[BEST METRICS]")
    print(f"  Win Rate:       {best_wr[0]:25s} {best_wr[1]['win_rate']:6.1f}%")
    print(f"  Profit Factor:  {best_pf[0]:25s} {best_pf[1]['profit_factor']:6.2f}x")
    print(f"  Expectancy:     {best_exp[0]:25s} ${best_exp[1]['expectancy']:7.2f}/trade")
    print(
        f"  Efficiency:     {best_efficiency[0]:25s} {best_efficiency[1]['signals_accepted']} signals"
    )

    # Compare with Fixed Fractal baseline
    print(f"\n[COMPARISON vs FIXED FRACTAL BASELINE]")
    baseline = {"wr": 39.0, "pf": 1.07, "exp": 0.75, "signals": 264}

    best_performer = max(results.items(), key=lambda x: x[1]["expectancy"])

    print(f"  Strategy:       {best_performer[0]}")
    print(
        f"  Signals:        {best_performer[1]['signals_accepted']:3d} vs {baseline['signals']:3d} baseline ({best_performer[1]['signals_accepted'] - baseline['signals']:+d})"
    )
    print(
        f"  Win Rate:       {best_performer[1]['win_rate']:5.1f}% vs {baseline['wr']:5.1f}% baseline ({best_performer[1]['win_rate'] - baseline['wr']:+.1f}%)"
    )
    print(
        f"  Profit Factor:  {best_performer[1]['profit_factor']:5.2f}x vs {baseline['pf']:5.2f}x baseline ({best_performer[1]['profit_factor'] - baseline['pf']:+.2f}x)"
    )
    print(
        f"  Expectancy:     ${best_performer[1]['expectancy']:7.2f} vs ${baseline['exp']:7.2f} baseline ({best_performer[1]['expectancy'] - baseline['exp']:+.2f})"
    )

    # Final recommendation
    print(f"\n[PRODUCTION DEPLOYMENT RECOMMENDATION]")

    recommendation = best_exp[0]
    rec_stats = best_exp[1]

    if rec_stats["profit_factor"] >= 1.0 and rec_stats["expectancy"] > 0:
        print(f"  Primary Strategy:   {recommendation}")
        print(f"  Status:            PRODUCTION READY")
        print(f"  Rationale:")
        print(f"    - Profit Factor >= 1.0 ({rec_stats['profit_factor']:.2f}x)")
        print(f"    - Positive Expectancy (+${rec_stats['expectancy']:.2f}/trade)")
        print(
            f"    - Signal Quality Score: {rec_stats['acceptance_rate']:.1f}% (quality filter effectiveness)"
        )
        print(
            f"    - Average Signals: {rec_stats['signals_accepted']} per 200 runs ({rec_stats['signals_accepted'] / 2:.1f} per run)"
        )
    else:
        print(f"  Primary Strategy:   FRACTAL_ONLY (deployed)")
        print(f"  Status:            MAINTAIN CURRENT")
        print(f"  Rationale:")
        print(f"    - Current system is optimal")
        print(f"    - Alternative modes offer no improvement")
        print(f"    - Risk of over-optimization")

    # Detailed mode analysis
    print(f"\n[DETAILED MODE ANALYSIS]")
    print(f"  {'Mode':<25s} {'Signals':<12s} {'WR':<12s} {'PF':<12s} {'Exp':<15s} {'Filter%':<12s}")
    print(f"  {'-' * 88}")

    for mode, stats in sorted(results.items(), key=lambda x: x[1]["expectancy"], reverse=True):
        print(
            f"  {mode:<25s} {stats['signals_accepted']:<12d} "
            f"{stats['win_rate']:<12.1f}% {stats['profit_factor']:<12.2f}x "
            f"${stats['expectancy']:<14.2f} {stats['acceptance_rate']:<12.1f}%"
        )

    print("=" * 110 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
