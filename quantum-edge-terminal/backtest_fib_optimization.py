#!/usr/bin/env python3
"""
FIBONACCI MANIPULATION OPTIMIZED BACKTEST

Testing multiple target levels to find optimal RR vs Win Rate balance:
- V1: Conservative: 0.618 extension (closer target)
- V2: Moderate: 1.0 extension (balanced)
- V3: Aggressive: 1.618 extension (original, too far)

Also testing with dual-layer exits (partial take profit).
"""

import asyncio
import random
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))
from modules.fib_manipulation_validator import FibManipulationValidator


@dataclass
class Trade:
    entry: float
    sl: float
    tp: float
    expected_rr: float
    setup: str

    outcome: str = "OPEN"
    pnl: float = 0.0
    realized_rr: float = 0.0


class DataGen:
    def __init__(self, seed: int = 42):
        random.seed(seed)

    def gen(self, n: int = 10000) -> List[Dict]:
        candles = []
        p, vol = 420.0, 0.01
        trend = 1 if random.random() > 0.5 else -1

        for i in range(n):
            if i % random.randint(60, 80) == 0:
                trend *= -1

            ret = random.gauss(trend * 0.0003, vol)
            close = p * (1 + ret)
            open_ = p * (1 + random.gauss(0, vol * 0.5))
            high = max(open_, close) * (1 + abs(random.gauss(0, vol * 0.3)))
            low = min(open_, close) * (1 - abs(random.gauss(0, vol * 0.3)))

            candles.append({"o": open_, "h": high, "l": low, "c": close})
            p = close

        return candles


class FibOptimizedBacktester:
    def __init__(self, n: int = 10000, target_extension: float = 1.0):
        """
        Args:
            n: Number of candles
            target_extension: Fibonacci extension multiplier (0.618, 1.0, 1.618, etc)
        """
        self.validator = FibManipulationValidator(min_leg_points=1.5)
        self.candles = DataGen().gen(n)
        self.trades = []
        self.target_extension = target_extension

    async def backtest(self):
        """Run backtest with specified target extension."""
        for i in range(20, len(self.candles) - 20):
            window = []
            for j in range(i - 19, i + 1):
                c = self.candles[j]
                window.append(
                    {
                        "open": float(c["o"]),
                        "high": float(c["h"]),
                        "low": float(c["l"]),
                        "close": float(c["c"]),
                        "volume": 1,
                    }
                )

            result = await self.validator.validate(window)
            if not result.get("valid"):
                continue

            # Get basic entry/SL from validator
            entry = result["entry"]
            sl = result["stop_loss"]
            setup = result["pattern"]

            # Calculate custom TP based on target extension
            leg_info = result["manipulation_leg"]
            leg_magnitude = leg_info["magnitude"]

            if setup == "MANIP_BUY":
                tp = entry + (leg_magnitude * self.target_extension)
            else:
                tp = entry - (leg_magnitude * self.target_extension)

            # Calculate new RR
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0

            trade = Trade(entry=entry, sl=sl, tp=tp, expected_rr=rr, setup=setup)

            self._exit(trade, i + 1, min(i + 50, len(self.candles)))
            self.trades.append(trade)

    def _exit(self, trade: Trade, start: int, end: int):
        """Simulate trade exit."""
        is_buy = trade.setup == "MANIP_BUY"

        for i in range(start, end):
            h = self.candles[i]["h"]
            l = self.candles[i]["l"]

            if is_buy:
                if l <= trade.sl:
                    trade.outcome = "LOSS"
                    risk = abs(trade.entry - trade.sl)
                    trade.pnl = -risk
                    trade.realized_rr = 0.0
                    return
                elif h >= trade.tp:
                    trade.outcome = "WIN"
                    reward = abs(trade.tp - trade.entry)
                    risk = abs(trade.entry - trade.sl)
                    trade.pnl = reward
                    trade.realized_rr = reward / risk if risk > 0 else 0
                    return
            else:
                if h >= trade.sl:
                    trade.outcome = "LOSS"
                    risk = abs(trade.sl - trade.entry)
                    trade.pnl = -risk
                    trade.realized_rr = 0.0
                    return
                elif l <= trade.tp:
                    trade.outcome = "WIN"
                    reward = abs(trade.entry - trade.tp)
                    risk = abs(trade.sl - trade.entry)
                    trade.pnl = reward
                    trade.realized_rr = reward / risk if risk > 0 else 0
                    return

        trade.outcome = "OPEN"

    def stats(self) -> Dict:
        closed = [t for t in self.trades if t.outcome in ["WIN", "LOSS"]]
        if not closed:
            return {}

        wins = [t for t in closed if t.outcome == "WIN"]
        losses = [t for t in closed if t.outcome == "LOSS"]

        wr = len(wins) / len(closed) * 100
        pnl = sum([t.pnl for t in closed])
        pw = sum([t.pnl for t in wins]) if wins else 0
        pl = abs(sum([t.pnl for t in losses])) if losses else 1

        return {
            "signals": len(self.trades),
            "closed": len(closed),
            "wins": len(wins),
            "wr": round(wr, 1),
            "rr": round(statistics.mean([t.realized_rr for t in wins]) if wins else 0, 2),
            "pf": round(pw / pl, 2) if pl > 0 else 0,
            "pnl": round(pnl, 2),
            "exp": round(pnl / len(closed), 2),
        }


async def test_target(extension: float, name: str, runs: int = 10) -> Tuple[str, Dict]:
    """Test one target extension across multiple runs."""
    results = []

    for run in range(runs):
        random.seed(42 + run)
        bt = FibOptimizedBacktester(n=10000, target_extension=extension)
        await bt.backtest()
        stats = bt.stats()
        if stats:
            results.append(stats)

    if not results:
        return name, {}

    wrs = [r["wr"] for r in results]
    rrs = [r["rr"] for r in results]
    pfs = [r["pf"] for r in results]
    pnls = [r["pnl"] for r in results]
    exps = [r["exp"] for r in results]

    return name, {
        "mean_wr": round(statistics.mean(wrs), 1),
        "mean_rr": round(statistics.mean(rrs), 2),
        "mean_pf": round(statistics.mean(pfs), 2),
        "total_pnl": round(sum(pnls), 2),
        "mean_exp": round(statistics.mean(exps), 2),
    }


async def main():
    print("\n" + "=" * 80)
    print("FIB MANIPULATION OPTIMIZATION - TARGET LEVEL TESTING")
    print("=" * 80 + "\n")

    # Test different Fibonacci extension levels
    targets = [
        (0.236, "SHALLOW (0.236x)"),
        (0.382, "SHALLOW+ (0.382x)"),
        (0.618, "CONSERVATIVE (0.618x)"),
        (1.0, "BALANCED (1.0x)"),
        (1.272, "AGGRESSIVE (1.272x)"),
        (1.618, "EXTREME (1.618x)"),
    ]

    results = {}

    for extension, name in targets:
        print(f"Testing {name}...", end=" ")
        label, stats = await test_target(extension, name)
        results[name] = stats

        if stats:
            print(
                f"WR={stats['mean_wr']:5.1f}% | RR={stats['mean_rr']:5.2f}:1 | "
                f"PNLR=${stats['total_pnl']:8.2f} | Exp=${stats['mean_exp']:6.2f}/trade"
            )

    # Find best by different metrics
    valid_results = {k: v for k, v in results.items() if v}

    if valid_results:
        best_wr = max(valid_results.items(), key=lambda x: x[1]["mean_wr"])
        best_pf = max(valid_results.items(), key=lambda x: x[1]["mean_pf"])
        best_exp = max(valid_results.items(), key=lambda x: x[1]["mean_exp"])

        print("\n" + "=" * 80)
        print("OPTIMIZATION RESULTS")
        print("=" * 80)
        print(f"\n  Best Win Rate:    {best_wr[0]} - {best_wr[1]['mean_wr']:.1f}%")
        print(f"  Best Profit Factor: {best_pf[0]} - {best_pf[1]['mean_pf']:.2f}x")
        print(f"  Best Expectancy:  {best_exp[0]} - ${best_exp[1]['mean_exp']:.2f}/trade")

        # Compare with Fixed Fractal
        print("\n" + "=" * 80)
        print("COMPARISON - BEST FIB vs FIXED FRACTAL")
        print("=" * 80)

        fractal = {"wr": 39.0, "rr": 1.39, "pf": 1.07, "exp": 0.75}
        fib_best = best_exp[1]

        print(f"  Win Rate:       {fib_best['mean_wr']:5.1f}% vs {fractal['wr']:5.1f}% fractal")
        print(f"  Realized RR:    {fib_best['mean_rr']:5.2f}:1 vs {fractal['rr']:5.2f}:1 fractal")
        print(f"  Profit Factor:  {fib_best['mean_pf']:5.2f}x vs {fractal['pf']:5.2f}x fractal")
        print(f"  Expectancy:     ${fib_best['mean_exp']:6.2f} vs ${fractal['exp']:6.2f} fractal")

        if fib_best["mean_pf"] >= 1.0 and fib_best["mean_exp"] > fractal["exp"]:
            print(f"\n[WINNER] FIB MANIPULATION with {best_exp[0]}")
        elif fib_best["mean_pf"] >= 1.0:
            print(f"\n[VIABLE] {best_exp[0]} is profitable but fractal is better")
        else:
            print(f"\n[KEEP FRACTAL] Fixed fractal remains superior")

        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
