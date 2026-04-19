#!/usr/bin/env python3
"""
POST-FIX VALIDATION - Confirms Approach 1 Fix Applied Successfully

Runs baseline backtest AFTER applying the stop loss adjustment to fractal_validator.py.
Should show:
- Win Rate: ~39% (vs 45% baseline)
- Realized RR: ~1.39:1 (vs 0.96:1 baseline)
- Profit Factor: ~1.07x (vs 0.99x baseline)
- Expectancy: ~+$0.75/trade (vs -$0.10 baseline)
"""

import asyncio
import random
import statistics
from typing import List, Dict
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


class PostFixValidator:
    def __init__(self, n: int = 10000):
        self.validator = FractalValidator()
        self.candles = DataGen().gen(n)
        self.trades = []

    async def backtest(self):
        """Run backtest with fixed validator."""
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


async def main():
    print("\n" + "=" * 80)
    print("POST-FIX VALIDATION - Testing Approach 1 (Tighter Stops)")
    print("=" * 80 + "\n")

    results = []

    for run in range(10):
        print(f"Run {run + 1}/10...", end=" ")
        random.seed(42 + run)
        bt = PostFixValidator(n=10000)
        await bt.backtest()
        stats = bt.stats()
        if stats:
            results.append(stats)
            print(
                f"WR={stats['wr']:5.1f}% | RR={stats['rr']:4.2f}:1 | "
                f"PF={stats['pf']:4.2f}x | PnL=${stats['pnl']:8.2f}"
            )

    if results:
        wrs = [r["wr"] for r in results]
        rrs = [r["rr"] for r in results]
        pfs = [r["pf"] for r in results]
        pnls = [r["pnl"] for r in results]
        exps = [r["exp"] for r in results]

        print("\n" + "=" * 80)
        print("SUMMARY (10 runs with fix applied)")
        print("=" * 80)
        print(
            f"  Mean Win Rate:    {statistics.mean(wrs):6.1f}% (StdDev: {statistics.stdev(wrs) if len(wrs) > 1 else 0:.1f}%)"
        )
        print(
            f"  Mean Realized RR: {statistics.mean(rrs):6.2f}:1 (StdDev: {statistics.stdev(rrs) if len(rrs) > 1 else 0:.2f})"
        )
        print(
            f"  Mean Profit Factor: {statistics.mean(pfs):6.2f}x (StdDev: {statistics.stdev(pfs) if len(pfs) > 1 else 0:.2f})"
        )
        print(f"  Total P&L:        ${sum(pnls):8.2f} (${statistics.mean(pnls):7.2f} per run)")
        print(f"  Mean Expectancy:  ${statistics.mean(exps):7.2f}/trade")

        # Comparison with baseline
        baseline_wr = 45.1
        baseline_rr = 0.96
        baseline_pf = 0.99
        baseline_pnl = -247.70
        baseline_exp = -0.10

        print("\n" + "=" * 80)
        print("IMPROVEMENT vs BASELINE")
        print("=" * 80)
        mean_wr = statistics.mean(wrs)
        mean_rr = statistics.mean(rrs)
        mean_pf = statistics.mean(pfs)
        total_pnl = sum(pnls)
        mean_exp = statistics.mean(exps)

        wr_change = mean_wr - baseline_wr
        rr_change = mean_rr - baseline_rr
        pf_change = mean_pf - baseline_pf
        pnl_change = total_pnl - baseline_pnl
        exp_change = mean_exp - baseline_exp

        print(f"  Win Rate:    {mean_wr:5.1f}% [{wr_change:+.1f}%]")
        print(f"  Realized RR: {mean_rr:4.2f}:1 [{rr_change:+.2f}:1]")
        print(
            f"  Profit Factor: {mean_pf:4.2f}x [{pf_change:+.2f}x] {'[CROSSED PROFITABILITY]' if baseline_pf < 1.0 and mean_pf >= 1.0 else ''}"
        )
        print(f"  Total P&L:   ${total_pnl:8.2f} [{pnl_change:+.2f}]")
        print(f"  Expectancy:  ${mean_exp:7.2f}/trade [{exp_change:+.2f}]")

        # Final verdict
        print("\n" + "=" * 80)
        if mean_pf >= 1.0 and mean_exp > 0:
            print("[SUCCESS] System is NOW PROFITABLE after Approach 1 fix!")
            print(f"Implementation: Move stops 30% closer to entry in fractal_validator.py")
        else:
            print("[WARNING] System still not profitable, needs additional work")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
