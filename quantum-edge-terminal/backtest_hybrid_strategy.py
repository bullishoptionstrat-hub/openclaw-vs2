#!/usr/bin/env python3
"""
HYBRID STRATEGY - Best of Both Worlds

Combines:
1. Fibonacci Manipulation Legs (institutional moves + 0.62 retracement entry)
2. Approach 1 Fix (tighter stops - 30% closer)
3. Conservative Targets (0.618 extension instead of 1.618)
4. Tight Risk Management (RR > 1.5 filter for quality)

Expected result: Beat fixed fractal by combining their strengths.
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


class HybridBacktester:
    def __init__(self, n: int = 10000):
        self.validator = FibManipulationValidator(min_leg_points=1.5)
        self.candles = DataGen().gen(n)
        self.trades = []

    async def backtest(self):
        """Run hybrid strategy."""
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

            entry = result["entry"]
            sl_orig = result["stop_loss"]
            setup = result["pattern"]

            leg_info = result["manipulation_leg"]
            leg_magnitude = leg_info["magnitude"]

            # APPLY APPROACH 1 FIX: Tighter stops (30% closer)
            sl = entry + (sl_orig - entry) * 0.7

            # Use 0.618 extension (conservative) instead of 1.618
            if setup == "MANIP_BUY":
                tp = entry + (leg_magnitude * 0.618)
            else:
                tp = entry - (leg_magnitude * 0.618)

            # Calculate RR
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0

            # QUALITY FILTER: Only take trades with RR > 1.5
            if rr < 1.5:
                continue

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


async def main():
    print("\n" + "=" * 80)
    print("HYBRID STRATEGY BACKTEST")
    print("= Fib Manipulation Legs + Approach 1 Tighter Stops + 0.618 Targets =")
    print("=" * 80 + "\n")

    results = []

    for run in range(10):
        print(f"Run {run + 1}/10...", end=" ")
        random.seed(42 + run)
        bt = HybridBacktester(n=10000)
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
        print("SUMMARY - HYBRID STRATEGY (10 runs)")
        print("=" * 80)
        print(f"  Mean Signals:     {statistics.mean(signals):.0f} per run")
        print(f"  Mean Win Rate:    {statistics.mean(wrs):6.1f}%")
        print(f"  Mean Realized RR: {statistics.mean(rrs):6.2f}:1")
        print(f"  Mean Profit Factor: {statistics.mean(pfs):6.2f}x")
        print(f"  Total P&L:        ${sum(pnls):8.2f} (${statistics.mean(pnls):7.2f} per run)")
        print(f"  Mean Expectancy:  ${statistics.mean(exps):7.2f}/trade")

        # Comparison with Fixed Fractal
        print("\n" + "=" * 80)
        print("COMPARISON vs FIXED FRACTAL STRATEGY")
        print("=" * 80)

        fractal = {"wr": 39.0, "rr": 1.39, "pf": 1.07, "pnl_per_run": 189.32, "exp": 0.75}

        hybrid = {
            "wr": statistics.mean(wrs),
            "rr": statistics.mean(rrs),
            "pf": statistics.mean(pfs),
            "pnl_per_run": statistics.mean(pnls),
            "exp": statistics.mean(exps),
        }

        print(
            f"  FRACTAL:  WR={fractal['wr']:5.1f}% | RR={fractal['rr']:5.2f}:1 | PF={fractal['pf']:5.2f}x | Exp=${fractal['exp']:6.2f}/trade"
        )
        print(
            f"  HYBRID:   WR={hybrid['wr']:5.1f}% | RR={hybrid['rr']:5.2f}:1 | PF={hybrid['pf']:5.2f}x | Exp=${hybrid['exp']:6.2f}/trade"
        )

        wr_delta = hybrid["wr"] - fractal["wr"]
        rr_delta = hybrid["rr"] - fractal["rr"]
        pf_delta = hybrid["pf"] - fractal["pf"]
        exp_delta = hybrid["exp"] - fractal["exp"]

        print(
            f"  DELTA:    WR={wr_delta:+.1f}% | RR={rr_delta:+.2f}:1 | PF={pf_delta:+.2f}x | Exp=${exp_delta:+.2f}/trade"
        )

        # Winner
        print("\n" + "=" * 80)
        if hybrid["pf"] >= 1.0:
            if hybrid["exp"] > fractal["exp"]:
                print("[WINNER] HYBRID STRATEGY - BEATS FIXED FRACTAL")
                print(f"         +${exp_delta:.2f} better expectancy per trade")
            elif hybrid["exp"] >= fractal["exp"]:
                print("[TIE] Both strategies are similarly good")
                print(f"      Choose HYBRID for more variety, FRACTAL for stability")
            else:
                print("[CLOSE SECOND] HYBRID is profitable but FRACTAL is still better")
                print(
                    f"                HYBRID offers {hybrid['wr']:.1f}% WR vs {fractal['wr']:.1f}%"
                )
        else:
            print("[NOT VIABLE] HYBRID is not profitable (PF < 1.0)")

        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
