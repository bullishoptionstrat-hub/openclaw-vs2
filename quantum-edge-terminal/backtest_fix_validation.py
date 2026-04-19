#!/usr/bin/env python3
"""
PROFITABILITY FIX VALIDATION - Testing All 3 Approaches

Approach 1: Tighter Stops (Move stop 30% closer)
Approach 2: High RR Filter (Only RR > 1.8)
Approach 3: Extended TP (Push TP 25% further)
Approach 4: HYBRID (All 3 combined)

Run 10 validates on each approach to find THE WIN.
"""

import asyncio
import random
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))
from modules.fractal_validator import FractalValidator


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
            if i % 60 == 0:
                trend *= -1

            ret = random.gauss(trend * 0.0003, vol)
            close = p * (1 + ret)
            open_ = p * (1 + random.gauss(0, vol * 0.5))
            high = max(open_, close) * (1 + abs(random.gauss(0, vol * 0.3)))
            low = min(open_, close) * (1 - abs(random.gauss(0, vol * 0.3)))

            candles.append({"o": open_, "h": high, "l": low, "c": close})
            p = close

        return candles


class Backtester:
    def __init__(self, n: int = 10000, approach: str = "baseline"):
        self.validator = FractalValidator()
        self.candles = DataGen().gen(n)
        self.trades = []
        self.approach = approach

    async def backtest(self):
        """Run backtest with specified approach."""
        for i in range(3, len(self.candles) - 20):
            window = [
                {
                    "open": float(self.candles[i - 3]["o"]),
                    "high": float(self.candles[i - 3]["h"]),
                    "low": float(self.candles[i - 3]["l"]),
                    "close": float(self.candles[i - 3]["c"]),
                    "volume": 1,
                },
                {
                    "open": float(self.candles[i - 2]["o"]),
                    "high": float(self.candles[i - 2]["h"]),
                    "low": float(self.candles[i - 2]["l"]),
                    "close": float(self.candles[i - 2]["c"]),
                    "volume": 1,
                },
                {
                    "open": float(self.candles[i - 1]["o"]),
                    "high": float(self.candles[i - 1]["h"]),
                    "low": float(self.candles[i - 1]["l"]),
                    "close": float(self.candles[i - 1]["c"]),
                    "volume": 1,
                },
                {
                    "open": float(self.candles[i]["o"]),
                    "high": float(self.candles[i]["h"]),
                    "low": float(self.candles[i]["l"]),
                    "close": float(self.candles[i]["c"]),
                    "volume": 1,
                },
            ]

            result = await self.validator.validate(window)
            if not result.get("valid"):
                continue

            entry = result["entry"]
            sl = result["stop_loss"]
            tp = result["take_profit"]
            rr = result["risk_reward"]
            setup = result["pattern"]

            # Apply approach-specific modifications
            if self.approach == "approach1":
                # Tighter stops: Move 30% closer
                sl = entry + (sl - entry) * 0.7  # 70% of original distance

            elif self.approach == "approach2":
                # High RR filter: Only RR > 1.8
                if rr < 1.8:
                    continue

            elif self.approach == "approach3":
                # Extended TP: 25% further
                tp = entry + (tp - entry) * 1.25

            elif self.approach == "hybrid":
                # All three combined
                sl = entry + (sl - entry) * 0.7  # Tighter stops
                if rr < 1.5:  # Slightly relaxed filter for hybrid
                    continue
                tp = entry + (tp - entry) * 1.15  # More modest TP extension

            trade = Trade(entry=entry, sl=sl, tp=tp, expected_rr=rr, setup=setup)

            self._exit(trade, i + 1, min(i + 21, len(self.candles)))
            self.trades.append(trade)

    def _exit(self, trade: Trade, start: int, end: int):
        """Basic exit."""
        is_long = trade.setup == "BULLISH_FRACTAL"

        for i in range(start, end):
            h = self.candles[i]["h"]
            l = self.candles[i]["l"]

            if is_long:
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
        """Get stats."""
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
            "pf": round(pw / pl, 2),
            "pnl": round(pnl, 2),
            "exp": round(pnl / len(closed), 2),
        }


async def test_approach(approach: str, runs: int = 10) -> Tuple[str, Dict]:
    """Test one approach across multiple runs."""
    results = []

    for run in range(runs):
        random.seed(42 + run)
        bt = Backtester(n=10000, approach=approach)
        await bt.backtest()
        stats = bt.stats()
        if stats:
            results.append(stats)

    if not results:
        return approach, {}

    # Aggregate
    wrs = [r["wr"] for r in results]
    rrs = [r["rr"] for r in results]
    pfs = [r["pf"] for r in results]
    pnls = [r["pnl"] for r in results]
    exps = [r["exp"] for r in results]

    return approach, {
        "mean_wr": round(statistics.mean(wrs), 1),
        "mean_rr": round(statistics.mean(rrs), 2),
        "mean_pf": round(statistics.mean(pfs), 2),
        "total_pnl": round(sum(pnls), 2),
        "mean_exp": round(statistics.mean(exps), 2),
        "signals": round(statistics.mean([r["signals"] for r in results])),
        "trades_taken": round(statistics.mean([r["closed"] for r in results])),
    }


async def main():
    print("\n" + "=" * 80)
    print("PROFITABILITY FIX VALIDATION - Testing 4 Approaches")
    print("=" * 80 + "\n")

    approaches = ["baseline", "approach1", "approach2", "approach3", "hybrid"]
    results = {}

    for approach in approaches:
        print(f"Testing {approach.upper()}...")
        name, stats = await test_approach(approach)
        results[name] = stats

        if stats:
            print(
                f"  OK {approach.upper():15s} | "
                f"WR={stats['mean_wr']:5.1f}% | "
                f"RR={stats['mean_rr']:4.2f}:1 | "
                f"PF={stats['mean_pf']:4.2f}x | "
                f"PnL=${stats['total_pnl']:8.2f} | "
                f"Exp=${stats['mean_exp']:5.2f}/trade"
            )

    # Comparison
    print("\n" + "=" * 80)
    print("COMPARISON & RECOMMENDATION")
    print("=" * 80)

    # Find best by different metrics
    best_wr = max(results.items(), key=lambda x: x[1]["mean_wr"] if x[1] else -999)
    best_pf = max(results.items(), key=lambda x: x[1]["mean_pf"] if x[1] else -999)
    best_pnl = max(results.items(), key=lambda x: x[1]["total_pnl"] if x[1] else -999)
    best_exp = max(results.items(), key=lambda x: x[1]["mean_exp"] if x[1] else -999)

    print(f"\n[BEST BY METRIC]:")
    print(f"   Win Rate:    {best_wr[0].upper():15s} ({best_wr[1]['mean_wr']:.1f}%)")
    print(f"   Profit Factor: {best_pf[0].upper():15s} ({best_pf[1]['mean_pf']:.2f}x)")
    print(f"   Total PnL:   {best_pnl[0].upper():15s} (${best_pnl[1]['total_pnl']:.2f})")
    print(f"   Expectancy:  {best_exp[0].upper():15s} (${best_exp[1]['mean_exp']:.2f}/trade)")

    # Winner: Which is actually profitable?
    print(f"\n[PROFITABILITY CHECK]:")
    profitable = []
    for approach, stats in results.items():
        if stats.get("mean_exp", 0) > 0 and stats.get("mean_pf", 0) >= 1.0:
            profitable.append((approach, stats))
            print(f"   [OK] {approach.upper():15s} - PROFITABLE")
        else:
            status = "[LOSS]" if stats.get("mean_exp", 0) < 0 else "[EVEN]"
            print(f"   {status} {approach.upper():15s}")

    if profitable:
        print(f"\n[WINNER]: {profitable[0][0].upper()}")
        print(f"\n   Implementation:")
        if profitable[0][0] == "approach1":
            print(f"   1. Move stop loss 30% closer to entry")
            print(f"   2. Keep original TP targets")
            print(f"   3. Take all signals")
        elif profitable[0][0] == "approach2":
            print(f"   1. Filter: Only take fractals with RR > 1.8")
            print(f"   2. Use original stops/targets")
            print(f"   3. Reject poor risk/reward setups")
        elif profitable[0][0] == "approach3":
            print(f"   1. Extend TP targets 25% further")
            print(f"   2. Keep original stops")
            print(f"   3. Take all signals")
        elif profitable[0][0] == "hybrid":
            print(f"   1. Move stops 30% closer")
            print(f"   2. Extend TP 15% further")
            print(f"   3. Filter for RR > 1.5 setups")
    else:
        print(f"\n[WARNING] NO APPROACH IS PROFITABLE YET")
        print(f"   Need to investigate deeper...")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
