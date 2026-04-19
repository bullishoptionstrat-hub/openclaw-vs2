#!/usr/bin/env python3
"""
FIBONACCI MANIPULATION STRATEGY BACKTEST

Strategy: Institutional Manipulation Leg + Fib Retracement
- Identifies significant price moves (manipulation legs)
- Enters at 0.62 Fibonacci retracement level
- Targets 1.618 Fibonacci extension
- Uses 0.786 level for stop loss placement

Tests on 10,000 candles with 10 independent runs.
"""

import asyncio
import random
import statistics
from typing import List, Dict
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
        """Generate synthetic OHLC data with trend reversals."""
        candles = []
        p, vol = 420.0, 0.01
        trend = 1 if random.random() > 0.5 else -1

        for i in range(n):
            # Reversal every 60-80 candles (creates manipulation legs)
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


class FibManipBacktester:
    def __init__(self, n: int = 10000):
        self.validator = FibManipulationValidator(min_leg_points=1.5)
        self.candles = DataGen().gen(n)
        self.trades = []

    async def backtest(self):
        """Run backtest on all candles."""
        for i in range(20, len(self.candles) - 20):
            # Create candle window (last 20 candles for manipulation leg detection)
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

            entry = result["entry"]
            sl = result["stop_loss"]
            tp = result["take_profit"]
            rr = result["risk_reward"]
            setup = result["pattern"]

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
                # BUY: SL below, TP above
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
                # SELL: SL above, TP below
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
        """Get trading statistics."""
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


async def main():
    print("\n" + "=" * 80)
    print("FIBONACCI MANIPULATION STRATEGY BACKTEST")
    print("Entry: 0.62 Fib Retracement | SL: 0.786 | Target: 1.618 Extension")
    print("=" * 80 + "\n")

    results = []

    for run in range(10):
        print(f"Run {run + 1}/10...", end=" ")
        random.seed(42 + run)
        bt = FibManipBacktester(n=10000)
        await bt.backtest()
        stats = bt.stats()
        if stats:
            results.append(stats)
            print(
                f"Signals={stats['signals']:3d} | "
                f"WR={stats['wr']:5.1f}% | RR={stats['rr']:4.2f}:1 | "
                f"PF={stats['pf']:4.2f}x | PnL=${stats['pnl']:8.2f} | "
                f"Exp=${stats['exp']:6.2f}/trade"
            )

    if results:
        signals = [r["signals"] for r in results]
        wrs = [r["wr"] for r in results]
        rrs = [r["rr"] for r in results]
        pfs = [r["pf"] for r in results]
        pnls = [r["pnl"] for r in results]
        exps = [r["exp"] for r in results]

        print("\n" + "=" * 80)
        print("SUMMARY - FIB MANIPULATION STRATEGY (10 runs)")
        print("=" * 80)
        print(f"  Mean Signals:     {statistics.mean(signals):.0f} per run")
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

        # Comparison with FIXED Fractal (Approach 1)
        fractal_wr = 39.0
        fractal_rr = 1.39
        fractal_pf = 1.07
        fractal_pnl = +189.32
        fractal_exp = +0.75

        print("\n" + "=" * 80)
        print("COMPARISON vs FIXED FRACTAL STRATEGY (Approach 1)")
        print("=" * 80)
        mean_wr = statistics.mean(wrs)
        mean_rr = statistics.mean(rrs)
        mean_pf = statistics.mean(pfs)
        mean_pnl = statistics.mean(pnls)
        mean_exp = statistics.mean(exps)

        wr_delta = mean_wr - fractal_wr
        rr_delta = mean_rr - fractal_rr
        pf_delta = mean_pf - fractal_pf
        pnl_delta = mean_pnl - fractal_pnl
        exp_delta = mean_exp - fractal_exp

        print(
            f"  FIB WIN RATE:     {mean_wr:6.1f}% vs {fractal_wr:6.1f}% [delta: {wr_delta:+.1f}%]"
        )
        print(
            f"  FIB REALIZED RR:  {mean_rr:6.2f}:1 vs {fractal_rr:6.2f}:1 [delta: {rr_delta:+.2f}:1]"
        )
        print(
            f"  FIB PROFIT FACTOR: {mean_pf:6.2f}x vs {fractal_pf:6.2f}x [delta: {pf_delta:+.2f}x]"
        )
        print(
            f"  FIB AVG P&L:      ${mean_pnl:8.2f} vs ${fractal_pnl:8.2f} [delta: {pnl_delta:+.2f}]"
        )
        print(
            f"  FIB EXPECTANCY:   ${mean_exp:7.2f} vs ${fractal_exp:7.2f} [delta: {exp_delta:+.2f}]"
        )

        # Winner
        print("\n" + "=" * 80)
        if mean_pf > fractal_pf and mean_exp > fractal_exp:
            print("[WINNER] FIB MANIPULATION STRATEGY - BETTER PERFORMANCE")
            recommendation = "REPLACE"
        elif mean_pf == fractal_pf and mean_exp == fractal_exp:
            print("[TIE] Similar performance, FIB offers more opportunities")
            recommendation = "COMBINE"
        else:
            print("[SECOND PLACE] Fixed Fractal is still better")
            recommendation = "KEEP_FRACTAL"

        print(f"Recommendation: {recommendation}")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
