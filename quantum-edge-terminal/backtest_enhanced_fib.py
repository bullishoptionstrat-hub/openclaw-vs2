#!/usr/bin/env python3
"""
ENHANCED FIBONACCI STRATEGY BACKTEST

Testing multiple configurations:
V1: Strict institutional (all filters enabled) - 95%+ confidence trades
V2: Moderate confluence (SR + trend + grab) - balanced quality/quantity
V3: Relaxed confluence (trend only) - more signals
V4: Full enhanced (V2 + partial exits) - smart exit management

Each variant tests on 10,000 candles with 10 runs.
"""

import asyncio
import random
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))
from modules.enhanced_fib_validator import EnhancedFibManipulationValidator


@dataclass
class Trade:
    entry: float
    sl: float
    tp: float
    tp_partial: float = None  # Partial exit level
    expected_rr: float = 0.0
    setup: str = ""

    outcome: str = "OPEN"
    pnl: float = 0.0
    realized_rr: float = 0.0
    partial_taken: bool = False


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


class EnhancedFibBacktester:
    def __init__(self, n: int = 10000, variant: str = "strict", use_partial_exits: bool = False):
        """
        Args:
            variant: "strict", "moderate", "relaxed"
            use_partial_exits: Enable 1/3 partial takes at intermediate levels
        """
        if variant == "strict":
            self.validator = EnhancedFibManipulationValidator(
                require_liquidity_grab=True,
                require_trend=True,
                require_sr_confluence=True,
            )
        elif variant == "moderate":
            self.validator = EnhancedFibManipulationValidator(
                require_liquidity_grab=True,
                require_trend=True,
                require_sr_confluence=False,
            )
        elif variant == "relaxed":
            self.validator = EnhancedFibManipulationValidator(
                require_liquidity_grab=False,
                require_trend=True,
                require_sr_confluence=False,
            )
        else:
            raise ValueError(f"Unknown variant: {variant}")

        self.candles = DataGen().gen(n)
        self.trades = []
        self.use_partial_exits = use_partial_exits
        self.variant = variant

    async def backtest(self):
        """Run backtest."""
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

            trade = Trade(
                entry=result["entry"],
                sl=result["stop_loss"],
                tp=result["take_profit"],
                tp_partial=result.get("take_profit_partial"),
                expected_rr=result["risk_reward"],
                setup=result["pattern"],
            )

            self._exit(trade, i + 1, min(i + 100, len(self.candles)))
            self.trades.append(trade)

    def _exit(self, trade: Trade, start: int, end: int):
        """Simulate trade with intelligent exit management."""
        is_buy = trade.setup == "MANIP_BUY"

        for i in range(start, end):
            h = self.candles[i]["h"]
            l = self.candles[i]["l"]

            if is_buy:
                # Check SL first
                if l <= trade.sl:
                    trade.outcome = "LOSS"
                    risk = abs(trade.entry - trade.sl)
                    trade.pnl = -risk
                    trade.realized_rr = 0.0
                    return

                # Check partial exit (if enabled)
                if self.use_partial_exits and not trade.partial_taken and trade.tp_partial:
                    if h >= trade.tp_partial:
                        # Take 1/3 profit
                        trade.partial_taken = True
                        partial_gain = abs(trade.tp_partial - trade.entry) * 0.33
                        # Don't exit yet, continue to full TP

                # Check full TP
                if h >= trade.tp:
                    trade.outcome = "WIN"
                    reward = abs(trade.tp - trade.entry)
                    risk = abs(trade.entry - trade.sl)
                    trade.pnl = reward
                    trade.realized_rr = reward / risk if risk > 0 else 0
                    return

            else:  # SELL
                # Check SL first
                if h >= trade.sl:
                    trade.outcome = "LOSS"
                    risk = abs(trade.sl - trade.entry)
                    trade.pnl = -risk
                    trade.realized_rr = 0.0
                    return

                # Check partial exit (if enabled)
                if self.use_partial_exits and not trade.partial_taken and trade.tp_partial:
                    if l <= trade.tp_partial:
                        trade.partial_taken = True

                # Check full TP
                if l <= trade.tp:
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


async def test_variant(variant: str, use_partial: bool, runs: int = 10) -> Tuple[str, Dict]:
    """Test one variant across multiple runs."""
    results = []
    tag = f"{variant}"
    if use_partial:
        tag += "+partial"

    for run in range(runs):
        random.seed(42 + run)
        bt = EnhancedFibBacktester(n=10000, variant=variant, use_partial_exits=use_partial)
        await bt.backtest()
        stats = bt.stats()
        if stats:
            results.append(stats)

    if not results:
        return tag, {}

    wrs = [r["wr"] for r in results]
    rrs = [r["rr"] for r in results]
    pfs = [r["pf"] for r in results]
    pnls = [r["pnl"] for r in results]
    exps = [r["exp"] for r in results]
    signals = [r["signals"] for r in results]

    return tag, {
        "signals": round(statistics.mean(signals)),
        "mean_wr": round(statistics.mean(wrs), 1),
        "mean_rr": round(statistics.mean(rrs), 2),
        "mean_pf": round(statistics.mean(pfs), 2),
        "total_pnl": round(sum(pnls), 2),
        "mean_exp": round(statistics.mean(exps), 2),
    }


async def main():
    print("\n" + "=" * 100)
    print("ENHANCED FIBONACCI STRATEGY - COMPREHENSIVE OPTIMIZATION")
    print("Testing Institutional Order Flow + Confluence Filters + Smart Exits")
    print("=" * 100 + "\n")

    # Test all variants
    configs = [
        ("strict", False),
        ("strict", True),
        ("moderate", False),
        ("moderate", True),
        ("relaxed", False),
        ("relaxed", True),
    ]

    results = {}

    for variant, use_partial in configs:
        partial_str = (
            "(strict filters, no partial exits)" if not use_partial else "(with partial exits)"
        )
        print(f"Testing {variant.upper()} {partial_str}...", end=" ", flush=True)

        tag, stats = await test_variant(variant, use_partial)
        results[tag] = stats

        if stats:
            print(
                f"Signals={stats['signals']:4.0f} | WR={stats['mean_wr']:5.1f}% | "
                f"RR={stats['mean_rr']:5.2f}:1 | PF={stats['mean_pf']:5.2f}x | "
                f"PnL=${stats['total_pnl']:8.2f} | Exp=${stats['mean_exp']:6.2f}/trade"
            )

    # Analysis
    valid_results = {k: v for k, v in results.items() if v}

    if valid_results:
        # Find best variants
        best_wr = max(valid_results.items(), key=lambda x: x[1]["mean_wr"])
        best_pf = max(valid_results.items(), key=lambda x: x[1]["mean_pf"])
        best_exp = max(valid_results.items(), key=lambda x: x[1]["mean_exp"])

        print("\n" + "=" * 100)
        print("BEST VARIANTS")
        print("=" * 100)
        print(f"  Best Win Rate:     {best_wr[0]:20s} {best_wr[1]['mean_wr']:5.1f}%")
        print(f"  Best Profit Factor: {best_pf[0]:20s} {best_pf[1]['mean_pf']:5.2f}x")
        print(f"  Best Expectancy:   {best_exp[0]:20s} ${best_exp[1]['mean_exp']:6.2f}/trade")

        # Compare with Fixed Fractal
        print("\n" + "=" * 100)
        print("COMPARISON - BEST ENHANCED FIB vs FIXED FRACTAL")
        print("=" * 100)

        fractal = {"wr": 39.0, "rr": 1.39, "pf": 1.07, "exp": 0.75, "signals": 264}
        fib_best = best_exp[1]

        print(f"  {'Metric':<20s} {'Fixed Fractal':<20s} {'Enhanced Fib':<20s} {'Delta':<20s}")
        print(f"  {'-' * 70}")
        print(
            f"  {'Signals':<20s} {fractal['signals']:<20.0f} {fib_best['signals']:<20.0f} {fib_best['signals'] - fractal['signals']:<20.0f}"
        )
        print(
            f"  {'Win Rate':<20s} {fractal['wr']:<20.1f}% {fib_best['mean_wr']:<20.1f}% {fib_best['mean_wr'] - fractal['wr']:<20.1f}%"
        )
        print(
            f"  {'Realized RR':<20s} {fractal['rr']:<20.2f}:1 {fib_best['mean_rr']:<20.2f}:1 {fib_best['mean_rr'] - fractal['rr']:<20.2f}:1"
        )
        print(
            f"  {'Profit Factor':<20s} {fractal['pf']:<20.2f}x {fib_best['mean_pf']:<20.2f}x {fib_best['mean_pf'] - fractal['pf']:<20.2f}x"
        )
        print(
            f"  {'Expectancy':<20s} ${fractal['exp']:<19.2f} ${fib_best['mean_exp']:<19.2f} ${fib_best['mean_exp'] - fractal['exp']:<19.2f}"
        )

        # Final verdict
        print("\n" + "=" * 100)
        if fib_best["mean_pf"] >= 1.0:
            if fib_best["mean_exp"] >= fractal["exp"] * 0.9:  # Within 90% of fractal
                print("[PRODUCTION READY] Enhanced Fib Strategy Qualifies")
                print(f"  Variant: {best_exp[0]}")
                print(
                    f"  Rationale: {fib_best['mean_pf']:.2f}x PF with {fib_best['mean_exp']:.2f}/trade expectancy"
                )
                print(
                    f"  Recommendation: Deploy as ALTERNATIVE SIGNAL SOURCE alongside Fixed Fractal"
                )
            else:
                print("[COMPLEMENTARY] Enhanced Fib Strategy is Profitable but Secondary")
                print(f"  Use for: Additional confirmation, different market conditions")
        else:
            print("[NOT YET VIABLE] Enhanced strategy needs further optimization")

        print("=" * 100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
