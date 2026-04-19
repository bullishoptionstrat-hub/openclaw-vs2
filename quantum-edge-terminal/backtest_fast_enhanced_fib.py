#!/usr/bin/env python3
"""
FAST ENHANCED FIB STRATEGY - Optimized Performance Testing

Simplified institutional filters for speed:
- Liquidity grab detection (wicks vs body)
- Trend confirmation
- Simple support/resistance
- Partial exit management
"""

import asyncio
import random
import statistics
from typing import List, Dict, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))


def detect_liquidity_grab(candles: List[Dict], window: int = 5) -> Tuple[bool, float]:
    """Quick liquidity grab detection based on wick patterns."""
    if len(candles) < window:
        return False, 0.0

    recent = candles[-window:]
    wick_scores = []

    for candle in recent:
        body = abs(candle["c"] - candle["o"])
        upper_wick = candle["h"] - max(candle["o"], candle["c"])
        lower_wick = min(candle["o"], candle["c"]) - candle["l"]
        max_wick = max(upper_wick, lower_wick)
        wick_ratio = max_wick / body if body > 0 else 0
        wick_scores.append(wick_ratio)

    grab_strength = statistics.mean(wick_scores)
    return grab_strength > 1.2, grab_strength


def detect_trend(candles: List[Dict]) -> str:
    """Detect trend - UP, DOWN, or RANGING."""
    if len(candles) < 5:
        return "RANGING"

    closes = [c["c"] for c in candles[-5:]]
    if closes[-1] > closes[-2] > closes[-3]:
        return "UP"
    elif closes[-1] < closes[-2] < closes[-3]:
        return "DOWN"
    return "RANGING"


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

    def gen(self, n: int = 5000) -> List[Dict]:
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


class FastFibBacktester:
    def __init__(self, n: int = 5000, use_filters: bool = True):
        self.candles = DataGen().gen(n)
        self.trades = []
        self.use_filters = use_filters

    async def backtest(self):
        """Fast backtest with optional filters."""
        for i in range(20, len(self.candles) - 20):
            window = self.candles[max(0, i - 19) : i + 1]
            current = self.candles[i]["c"]

            # Find swing high/low
            swing_high = max(c["h"] for c in window)
            swing_low = min(c["l"] for c in window)

            swing_high_idx = next((idx for idx, c in enumerate(window) if c["h"] == swing_high), -1)
            swing_low_idx = next((idx for idx, c in enumerate(window) if c["l"] == swing_low), -1)

            if swing_high_idx < 0 or swing_low_idx < 0:
                continue

            is_upleg = swing_high_idx > swing_low_idx
            leg_start = swing_low if is_upleg else swing_high
            leg_end = swing_high if is_upleg else swing_low
            leg_mag = abs(leg_end - leg_start)

            if leg_mag < 1.5:
                continue

            # Optional filters
            if self.use_filters:
                is_grab, _ = detect_liquidity_grab(window)
                if not is_grab:
                    continue

                trend = detect_trend(window)
                if is_upleg and trend == "DOWN":
                    continue
                if not is_upleg and trend == "UP":
                    continue

            # Calculate Fib levels
            if is_upleg:
                fib_0618 = leg_end - (leg_mag * 0.618)
                fib_0786 = leg_end - (leg_mag * 0.786)
                fib_1618 = leg_end + (leg_mag * 0.618)
                pattern = "MANIP_BUY"
            else:
                fib_0618 = leg_end + (leg_mag * 0.618)
                fib_0786 = leg_end + (leg_mag * 0.786)
                fib_1618 = leg_end - (leg_mag * 0.618)
                pattern = "MANIP_SELL"

            # Entry zone check
            entry_zone_low = fib_0618 - (leg_mag * 0.08)
            entry_zone_high = fib_0618 + (leg_mag * 0.08)

            if not (entry_zone_low <= current <= entry_zone_high):
                continue

            # Create trade
            entry = fib_0618
            sl = fib_0786
            tp = fib_1618

            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0

            trade = Trade(entry=entry, sl=sl, tp=tp, expected_rr=rr, setup=pattern)

            self._exit(trade, i + 1, min(i + 50, len(self.candles)))
            self.trades.append(trade)

    def _exit(self, trade: Trade, start: int, end: int):
        """Exit logic."""
        is_buy = trade.setup == "MANIP_BUY"

        for i in range(start, end):
            if i >= len(self.candles):
                break
            h = self.candles[i]["h"]
            l = self.candles[i]["l"]

            if is_buy:
                if l <= trade.sl:
                    trade.outcome = "LOSS"
                    trade.pnl = -abs(trade.entry - trade.sl)
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
                    trade.pnl = -abs(trade.sl - trade.entry)
                    return
                elif l <= trade.tp:
                    trade.outcome = "WIN"
                    reward = abs(trade.entry - trade.tp)
                    risk = abs(trade.sl - trade.entry)
                    trade.pnl = reward
                    trade.realized_rr = reward / risk if risk > 0 else 0
                    return

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


async def test_config(use_filters: bool, runs: int = 10) -> Tuple[str, Dict]:
    """Test configuration."""
    config_name = "WITH FILTERS" if use_filters else "NO FILTERS"
    results = []

    for run in range(runs):
        random.seed(42 + run)
        bt = FastFibBacktester(n=5000, use_filters=use_filters)
        await bt.backtest()
        stats = bt.stats()
        if stats:
            results.append(stats)

    if not results:
        return config_name, {}

    wrs = [r["wr"] for r in results]
    rrs = [r["rr"] for r in results]
    pfs = [r["pf"] for r in results]
    pnls = [r["pnl"] for r in results]
    exps = [r["exp"] for r in results]
    signals = [r["signals"] for r in results]

    return config_name, {
        "signals": round(statistics.mean(signals)),
        "mean_wr": round(statistics.mean(wrs), 1),
        "mean_rr": round(statistics.mean(rrs), 2),
        "mean_pf": round(statistics.mean(pfs), 2),
        "total_pnl": round(sum(pnls), 2),
        "mean_exp": round(statistics.mean(exps), 2),
    }


async def main():
    print("\n" + "=" * 90)
    print("FAST ENHANCED FIB STRATEGY - FILTERS IMPACT TEST")
    print("=" * 90 + "\n")

    results = {}

    print("Testing NO FILTERS...", end=" ", flush=True)
    tag, stats = await test_config(use_filters=False)
    results[tag] = stats
    print(
        f"Signals={stats['signals']:4.0f} | WR={stats['mean_wr']:5.1f}% | "
        f"RR={stats['mean_rr']:5.2f}:1 | PF={stats['mean_pf']:5.2f}x | "
        f"Exp=${stats['mean_exp']:6.2f}/trade"
    )

    print("Testing WITH INSTITUTIONAL FILTERS...", end=" ", flush=True)
    tag, stats = await test_config(use_filters=True)
    results[tag] = stats
    print(
        f"Signals={stats['signals']:4.0f} | WR={stats['mean_wr']:5.1f}% | "
        f"RR={stats['mean_rr']:5.2f}:1 | PF={stats['mean_pf']:5.2f}x | "
        f"Exp=${stats['mean_exp']:6.2f}/trade"
    )

    # Compare
    print("\n" + "=" * 90)
    print("ANALYSIS")
    print("=" * 90)

    no_filter = results.get("NO FILTERS", {})
    with_filter = results.get("WITH FILTERS", {})

    if no_filter and with_filter:
        print(
            f"\nFilter Impact on Win Rate: {no_filter['mean_wr']:.1f}% -> {with_filter['mean_wr']:.1f}% ({with_filter['mean_wr'] - no_filter['mean_wr']:+.1f}%)"
        )
        print(
            f"Filter Impact on PF: {no_filter['mean_pf']:.2f}x -> {with_filter['mean_pf']:.2f}x ({with_filter['mean_pf'] - no_filter['mean_pf']:+.2f}x)"
        )
        print(
            f"Filter Impact on Expectancy: ${no_filter['mean_exp']:.2f} -> ${with_filter['mean_exp']:.2f} ({with_filter['mean_exp'] - no_filter['mean_exp']:+.2f})"
        )

        # Best version vs Fixed Fractal
        fractal = {"exp": 0.75, "pf": 1.07, "wr": 39.0}
        best = with_filter if with_filter["mean_pf"] >= no_filter["mean_pf"] else no_filter

        print(f"\n[BEST VERSION] {('WITH FILTERS' if best == with_filter else 'NO FILTERS')}")
        print(f"  vs Fixed Fractal:")
        print(f"    Win Rate:   {best['mean_wr']:.1f}% vs {fractal['wr']:.1f}%")
        print(f"    Profit Factor: {best['mean_pf']:.2f}x vs {fractal['pf']:.2f}x")
        print(f"    Expectancy: ${best['mean_exp']:.2f}/trade vs ${fractal['exp']:.2f}/trade")

        if best["mean_pf"] >= fractal["pf"] * 0.95 and best["mean_exp"] >= fractal["exp"] * 0.8:
            print(f"\n  Status: VIABLE as secondary strategy")
        else:
            print(f"\n  Status: Good learning, but keep Fixed Fractal as primary")

    print("=" * 90 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
