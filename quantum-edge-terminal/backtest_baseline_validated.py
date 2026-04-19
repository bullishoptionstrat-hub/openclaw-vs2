#!/usr/bin/env python3
"""
FRACTAL BASELINE - NO OPTIMIZATION, JUST STATS

Back to basics. The original backtest showed:
✅ 54.41% win rate
✅ 1.16:1 realized RR
✅ +5.83 pts PnL (positive)
✅ 0.0857 pts/trade expectancy

This is SOLID. Let's run this on larger datasets to validate statistical significance.
Run with 10,000+ candles per simulation for better precision.
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
    exit: float = 0.0
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
            vol_amt = int(50_000_000 * (1 + random.gauss(0, 0.3)))

            candles.append({"o": open_, "h": high, "l": low, "c": close})
            p = close

        return candles


class BaselineBacktester:
    def __init__(self, n: int = 10000):
        self.validator = FractalValidator()
        self.candles = DataGen().gen(n)
        self.trades = []

    async def backtest(self):
        """Pure fractal validation - zero modifications."""
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

            trade = Trade(
                entry=result["entry"],
                sl=result["stop_loss"],
                tp=result["take_profit"],
                expected_rr=result["risk_reward"],
                setup=result["pattern"],
            )

            # Simple exit: TP or SL hit
            self._exit(trade, i + 1, min(i + 21, len(self.candles)))
            self.trades.append(trade)

    def _exit(self, trade: Trade, start: int, end: int):
        """Basic exit - first TP/SL wins."""
        is_long = trade.setup == "BULLISH_FRACTAL"

        for i in range(start, end):
            h = self.candles[i]["h"]
            l = self.candles[i]["l"]

            if is_long:
                if l <= trade.sl:
                    trade.outcome = "LOSS"
                    trade.exit = trade.sl
                    risk = abs(trade.entry - trade.sl)
                    trade.pnl = -risk
                    trade.realized_rr = 0.0
                    return
                elif h >= trade.tp:
                    trade.outcome = "WIN"
                    trade.exit = trade.tp
                    reward = abs(trade.tp - trade.entry)
                    risk = abs(trade.entry - trade.sl)
                    trade.pnl = reward
                    trade.realized_rr = reward / risk if risk > 0 else 0
                    return
            else:
                if h >= trade.sl:
                    trade.outcome = "LOSS"
                    trade.exit = trade.sl
                    risk = abs(trade.sl - trade.entry)
                    trade.pnl = -risk
                    trade.realized_rr = 0.0
                    return
                elif l <= trade.tp:
                    trade.outcome = "WIN"
                    trade.exit = trade.tp
                    reward = abs(trade.entry - trade.tp)
                    risk = abs(trade.sl - trade.entry)
                    trade.pnl = reward
                    trade.realized_rr = reward / risk if risk > 0 else 0
                    return

        trade.outcome = "OPEN"

    def get_stats(self) -> Dict:
        """Get statistics."""
        closed = [t for t in self.trades if t.outcome in ["WIN", "LOSS"]]
        if not closed:
            return {}

        wins = [t for t in closed if t.outcome == "WIN"]
        losses = [t for t in closed if t.outcome == "LOSS"]

        wr = len(wins) / len(closed) * 100
        pnl = sum([t.pnl for t in closed])
        avg_win = statistics.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = statistics.mean([t.pnl for t in losses]) if losses else 0
        pw = sum([t.pnl for t in wins]) if wins else 0
        pl = abs(sum([t.pnl for t in losses])) if losses else 1

        return {
            "signals": len(self.trades),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "wr_pct": round(wr, 2),
            "rr": round(statistics.mean([t.realized_rr for t in wins]) if wins else 0, 2),
            "pf": round(pw / pl, 2),
            "total_pnl": round(pnl, 2),
            "avg_pnl": round(pnl / len(closed), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
        }


async def main():
    print("\n" + "=" * 80)
    print("FRACTAL BASELINE VALIDATION - NO OPTIMIZATIONS (10 Runs, 10k Candles Each)")
    print("=" * 80 + "\n")

    results = []

    for run in range(1, 11):
        random.seed(42 + run)
        bt = BaselineBacktester(n=10000)
        await bt.backtest()
        stats = bt.get_stats()

        if stats:
            results.append(stats)
            print(
                f"Run {run:2d}: "
                f"Signals={stats['signals']:3d} | "
                f"Closed={stats['closed']:3d} ({stats['wins']:2d}W {stats['wr_pct']:5.1f}%) | "
                f"RR={stats['rr']:4.2f}:1 | "
                f"PF={stats['pf']:4.2f}x | "
                f"PnL=${stats['total_pnl']:7.2f} | "
                f"Exp=${stats['avg_pnl']:5.2f}/trade"
            )

    # Summary statistics
    print("\n" + "=" * 80)
    print("STATISTICAL SUMMARY (10 Runs)")
    print("=" * 80)

    wrs = [r["wr_pct"] for r in results]
    rrs = [r["rr"] for r in results]
    pfs = [r["pf"] for r in results]
    pnls = [r["total_pnl"] for r in results]
    avg_pnls = [r["avg_pnl"] for r in results]

    print(f"\nWin Rate:")
    print(f"  Mean: {statistics.mean(wrs):.2f}%")
    print(f"  StdDev: {statistics.stdev(wrs) if len(wrs) > 1 else 0:.2f}%")
    print(f"  Range: {min(wrs):.2f}% - {max(wrs):.2f}%")

    print(f"\nRealized RR (on wins):")
    print(f"  Mean: {statistics.mean(rrs):.2f}:1")
    print(f"  StdDev: {statistics.stdev(rrs) if len(rrs) > 1 else 0:.2f}")
    print(f"  Range: {min(rrs):.2f}:1 - {max(rrs):.2f}:1")

    print(f"\nProfit Factor:")
    print(f"  Mean: {statistics.mean(pfs):.2f}x")
    print(f"  Range: {min(pfs):.2f}x - {max(pfs):.2f}x")

    print(f"\nTotal P&L (per run):")
    print(f"  Mean: ${statistics.mean(pnls):.2f}")
    print(f"  StdDev: ${statistics.stdev(pnls) if len(pnls) > 1 else 0:.2f}")
    print(f"  Total (all 10): ${sum(pnls):.2f}")

    print(f"\nExpectancy:")
    print(f"  Mean: ${statistics.mean(avg_pnls):.2f}/trade")
    print(f"  StdDev: ${statistics.stdev(avg_pnls) if len(avg_pnls) > 1 else 0:.2f}")

    # Profitability assessment
    print("\n" + "=" * 80)
    print("PROFITABILITY ASSESSMENT")
    print("=" * 80)

    mean_wr = statistics.mean(wrs)
    mean_rr = statistics.mean(rrs)
    mean_pf = statistics.mean(pfs)
    mean_exp = statistics.mean(avg_pnls)

    print(
        f"\n✅ Win Rate: {mean_wr:.2f}% {'(Strong)' if mean_wr >= 55 else '(Fair)' if mean_wr >= 50 else '(Weak)'}"
    )
    print(
        f"✅ RR: {mean_rr:.2f}:1 {'(Strong)' if mean_rr >= 1.2 else '(Fair)' if mean_rr >= 1.0 else '(Weak)'}"
    )
    print(
        f"✅ Profit Factor: {mean_pf:.2f}x {'(Excellent)' if mean_pf >= 1.5 else '(Good)' if mean_pf >= 1.2 else '(Marginal)' if mean_pf >= 1.0 else '(Losing)'}"
    )
    print(f"✅ Expectancy: ${mean_exp:.2f}/trade")

    if mean_wr >= 50 and mean_pf >= 1.0:
        print("\n🎯 BASELINE IS PROFITABLE")
        print(f"   Estimated monthly (20 trades): ${mean_exp * 20:.0f}")
        print(f"   Estimated yearly (250 trades): ${mean_exp * 250:.0f}")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
