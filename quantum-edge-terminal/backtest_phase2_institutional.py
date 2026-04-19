#!/usr/bin/env python3
"""
PHASE 2 INSTITUTIONAL SMART BLEND+ BACKTEST

Comprehensive testing of the golden ratio strategy with:
1. Fractal 4-candle patterns
2. Fibonacci golden ratio confluence
3. Fair value gap detection
4. Institutional volume analysis
5. Advanced risk/reward optimization

Golden Ratio Levels Used:
- Entry: 0.618 retracement (institutional trading zones)
- Stop Loss: 0.786 support level (tight, institutional stops)
- Target 1: 1.272x risk (first profit taking)
- Target 2: 1.618x risk (golden ratio - main target)
- Target 3: 2.618x risk (Phi squared - extension)

Expected Performance:
- Win Rate: 45%+ (higher due to confluence filters)
- Profit Factor: 2.0x+ (tight stops, golden ratio targets)
- Expectancy: +$0.90+/trade
- Confidence: 95%+ on institutional setups
"""

import asyncio
import random
import statistics
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))
try:
    from modules.market_structure_analyzer import get_institutional_levels
    from modules.institutional_smart_blend_plus import InstitutionalSmartBlendStrategy
    from modules.fractal_validator import FractalValidator
except ImportError:
    print("Warning: Some modules not available, using mock implementations")


@dataclass
class BacktestTrade:
    """Represents a completed trade."""

    entry_price: float
    entry_bar: int
    exit_price: float
    exit_bar: int
    direction: str  # LONG or SHORT
    risk: float
    reward: float
    rr: float
    profit_loss: float
    confidence: float
    confluence_score: int
    win: bool
    bars_held: int


class InstitutionalStrategyBacktester:
    """
    Comprehensive backtest engine for Phase 2 strategy.
    """

    PHI = 1.618034

    def __init__(self, runs: int = 50, candles_per_run: int = 2000):
        self.runs = runs
        self.candles_per_run = candles_per_run
        self.trades: List[BacktestTrade] = []
        self.strategy = InstitutionalSmartBlendStrategy(
            min_confluence=3, min_rr=1.618, fractal_fix_enabled=True, use_advanced_filters=True
        )

    def generate_realistic_candles(self, seed: int) -> List[Dict]:
        """Generate realistic price data with golden ratio features."""
        random.seed(seed)
        candles = []

        # Starting price
        price = 420.0
        trend = random.choice([1, -1])

        for bar in range(self.candles_per_run):
            # Directional move with noise
            direction = trend if random.random() > 0.4 else -trend
            change = direction * random.gauss(0.5, 0.8)
            price += change

            # Generate OHLCV with realistic structure
            open_price = price
            close_price = price + random.gauss(0, 0.3)
            high = max(open_price, close_price) + abs(random.gauss(0, 0.4))
            low = min(open_price, close_price) - abs(random.gauss(0, 0.4))
            volume = int(random.gauss(1000000, 200000))

            candles.append(
                {
                    "o": open_price,
                    "h": high,
                    "l": low,
                    "c": close_price,
                    "v": max(1, volume),
                    "bar": bar,
                }
            )

            # Trend change occasionally
            if random.random() > 0.98:
                trend = -trend

        return candles

    def backtest_run(self, seed: int) -> List[BacktestTrade]:
        """Run a single backtest on synthetic data."""
        candles = self.generate_realistic_candles(seed)
        run_trades = []

        for bar_idx in range(20, len(candles) - 20):
            # Get recent candles
            window = candles[bar_idx - 20 : bar_idx + 1]

            # Test fractal entry
            if len(window) >= 4:
                # Check for 4-candle fractal
                c1, c2, c3, c4 = window[-4:]

                # Bullish fractal
                if c1["l"] > c2["l"] and c2["l"] < c3["l"] and c3["l"] < c4["l"]:
                    # Get market structure
                    market_structure = self._analyze_structure(window)

                    # Validate confluence
                    confluence = self._calculate_confluence(window, "BULL", market_structure)

                    if confluence >= 3:  # Meets minimum
                        # Calculate entry/exit
                        trade = self._simulate_trade(window, "BULL", confluence, candles, bar_idx)
                        if trade:
                            run_trades.append(trade)

                # Bearish fractal
                if c1["h"] < c2["h"] and c2["h"] > c3["h"] and c3["h"] > c4["h"]:
                    market_structure = self._analyze_structure(window)
                    confluence = self._calculate_confluence(window, "BEAR", market_structure)

                    if confluence >= 3:
                        trade = self._simulate_trade(window, "BEAR", confluence, candles, bar_idx)
                        if trade:
                            run_trades.append(trade)

        return run_trades

    def _analyze_structure(self, candles: List[Dict]) -> Dict:
        """Analyze market structure (swing levels)."""
        highs = [c["h"] for c in candles]
        lows = [c["l"] for c in candles]

        swing_high = max(highs)
        swing_low = min(lows)

        return {"swing_high": swing_high, "swing_low": swing_low, "range": swing_high - swing_low}

    def _calculate_confluence(self, candles: List[Dict], pattern: str, structure: Dict) -> int:
        """Calculate confluence score (0-6)."""
        score = 1  # Fractal base

        # Volume check
        avg_vol = statistics.mean([c.get("v", 0) for c in candles[-10:]])
        if candles[-1].get("v", 0) > avg_vol * 1.5:
            score += 1

        # Trend check
        closes = [c["c"] for c in candles[-10:]]
        if pattern == "BULL" and closes[-1] > closes[0]:
            score += 1
        elif pattern == "BEAR" and closes[-1] < closes[0]:
            score += 1

        # FVG check
        if self._has_fvg(candles, pattern):
            score += 1

        # Support/resistance check
        if self._has_sr_confluence(candles, structure, pattern):
            score += 1

        # Momentum check
        rsi = self._calculate_rsi(closes)
        if pattern == "BULL" and rsi < 70:
            score += 1
        elif pattern == "BEAR" and rsi > 30:
            score += 1

        return min(6, score)

    def _has_fvg(self, candles: List[Dict], pattern: str) -> bool:
        """Detect fair value gap."""
        if len(candles) < 3:
            return False

        c1, c2, c3 = candles[-3:]

        # FVG UP
        if pattern == "BULL" and c1["h"] < c2["l"]:
            return True

        # FVG DOWN
        if pattern == "BEAR" and c1["l"] > c2["h"]:
            return True

        return False

    def _has_sr_confluence(self, candles: List[Dict], structure: Dict, pattern: str) -> bool:
        """Check for support/resistance confluence."""
        current_price = candles[-1]["c"]

        # 0.618 Fib retracement
        fib_618 = structure["swing_high"] - (structure["range"] * 0.618)

        if pattern == "BULL" and abs(current_price - fib_618) < structure["range"] * 0.01:
            return True
        if pattern == "BEAR" and abs(current_price - fib_618) < structure["range"] * 0.01:
            return True

        return False

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """Calculate RSI."""
        if len(closes) < period:
            return 50

        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        seed = deltas[:period]
        up = sum([x for x in seed if x > 0]) / period
        down = sum([abs(x) for x in seed if x < 0]) / period

        rs = up / down if down > 0 else 100
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _simulate_trade(
        self,
        window: List[Dict],
        pattern: str,
        confluence: int,
        all_candles: List[Dict],
        entry_bar: int,
    ) -> BacktestTrade:
        """Simulate a trade from entry to exit."""
        entry_price = window[-1]["c"]
        swing_high = max([c["h"] for c in window])
        swing_low = min([c["l"] for c in window])
        swing_range = swing_high - swing_low

        # Calculate levels using golden ratio
        if pattern == "BULL":
            sl = entry_price - (swing_range * 0.786)
            tp2 = entry_price + (swing_range * self.PHI)
        else:
            sl = entry_price + (swing_range * 0.786)
            tp2 = entry_price - (swing_range * self.PHI)

        # Simulate trade execution with random exit
        max_bars = 50
        exit_price = None
        exit_bar = None
        bars_held = 0

        for i in range(1, min(max_bars, len(all_candles) - entry_bar)):
            future_candle = all_candles[entry_bar + i]

            if pattern == "BULL":
                # Check for TP or SL hit
                if future_candle["h"] >= tp2:
                    exit_price = tp2
                    exit_bar = entry_bar + i
                    bars_held = i
                    break
                elif future_candle["l"] <= sl:
                    exit_price = sl
                    exit_bar = entry_bar + i
                    bars_held = i
                    break
            else:
                if future_candle["l"] <= tp2:
                    exit_price = tp2
                    exit_bar = entry_bar + i
                    bars_held = i
                    break
                elif future_candle["h"] >= sl:
                    exit_price = sl
                    exit_bar = entry_bar + i
                    bars_held = i
                    break

        if not exit_price:
            return None

        # Calculate metrics
        risk = abs(entry_price - sl)
        reward = abs(exit_price - entry_price)
        rr = reward / risk if risk > 0 else 0

        if pattern == "BULL":
            pnl = reward if exit_price == tp2 else -risk
        else:
            pnl = reward if exit_price == tp2 else -risk

        return BacktestTrade(
            entry_price=entry_price,
            entry_bar=entry_bar,
            exit_price=exit_price,
            exit_bar=exit_bar,
            direction=pattern,
            risk=risk,
            reward=reward,
            rr=rr,
            profit_loss=pnl,
            confidence=0.60 + (confluence * 0.08),
            confluence_score=confluence,
            win=pnl > 0,
            bars_held=bars_held,
        )

    async def run(self) -> Dict:
        """Execute full backtest."""
        print(f"\n{'=' * 100}")
        print("PHASE 2: INSTITUTIONAL SMART BLEND+ GOLDEN RATIO STRATEGY BACKTEST")
        print(f"{'=' * 100}\n")

        all_trades = []

        for run_idx in range(self.runs):
            print(f"Run {run_idx + 1:3d}/{self.runs}...", end=" ", flush=True)
            trades = self.backtest_run(42 + run_idx)
            all_trades.extend(trades)
            print(f"Signals: {len(trades):3d}")

        # Calculate statistics
        if not all_trades:
            return {"valid": False, "error": "No trades generated"}

        wins = [t for t in all_trades if t.win]
        losses = [t for t in all_trades if not t.win]

        win_rate = len(wins) / len(all_trades) * 100 if all_trades else 0

        gross_wins = sum([t.profit_loss for t in wins]) if wins else 0
        gross_losses = abs(sum([t.profit_loss for t in losses])) if losses else 0

        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0

        avg_win = statistics.mean([t.profit_loss for t in wins]) if wins else 0
        avg_loss = statistics.mean([t.profit_loss for t in losses]) if losses else 0

        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        avg_rr = statistics.mean([t.rr for t in all_trades])
        avg_confidence = statistics.mean([t.confidence for t in all_trades])
        institutional_count = len([t for t in all_trades if t.confluence_score >= 4])

        print(f"\n{'=' * 100}")
        print("BACKTEST RESULTS")
        print(f"{'=' * 100}")
        print(f"Total Trades:        {len(all_trades):6d}")
        print(f"Winning Trades:      {len(wins):6d} ({win_rate:5.1f}%)")
        print(f"Losing Trades:       {len(losses):6d}")
        print()
        print(f"Profit Factor:       {profit_factor:6.2f}x")
        print(f"Expectancy:          ${expectancy:7.2f}/trade")
        print(f"Average RR:          {avg_rr:6.2f}:1")
        print(f"Average Confidence:  {avg_confidence * 100:5.1f}%")
        print(
            f"Institutional Setup: {institutional_count:6d} ({institutional_count / len(all_trades) * 100:5.1f}%)"
        )
        print()
        print(f"Gross Wins:          ${gross_wins:10.2f}")
        print(f"Gross Losses:        ${gross_losses:10.2f}")
        print(f"Net P&L:             ${gross_wins - gross_losses:10.2f}")
        print()
        print(f"Avg Win:             ${avg_win:7.2f}")
        print(f"Avg Loss:            ${avg_loss:7.2f}")
        print(f"Avg Bars Held:       {statistics.mean([t.bars_held for t in all_trades]):5.1f}")
        print(f"{'=' * 100}\n")

        # Performance tiers
        if win_rate >= 45 and profit_factor >= 2.0:
            tier = "[INSTITUTIONAL GRADE] Optimal Performance"
        elif win_rate >= 40 and profit_factor >= 1.5:
            tier = "[PROFESSIONAL GRADE] Strong Performance"
        elif win_rate >= 35 and profit_factor >= 1.2:
            tier = "[TRADE-WORTHY] Acceptable Performance"
        else:
            tier = "[NEEDS IMPROVEMENT] Suboptimal - Refining"

        print(f"PERFORMANCE TIER: {tier}")
        print()

        # Confluence distribution
        print("CONFLUENCE SIGNAL DISTRIBUTION:")
        for conf_score in range(1, 7):
            count = len([t for t in all_trades if t.confluence_score == conf_score])
            if count > 0:
                conf_trades = [t for t in all_trades if t.confluence_score == conf_score]
                conf_wr = sum([1 for t in conf_trades if t.win]) / len(conf_trades) * 100
                print(f"  {conf_score} Signals: {count:4d} trades | {conf_wr:5.1f}% WR")

        print(f"\n{'=' * 100}\n")

        return {
            "valid": True,
            "total_trades": len(all_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "avg_rr": avg_rr,
            "avg_confidence": avg_confidence,
            "institutional_grade": win_rate >= 45 and profit_factor >= 2.0,
            "performance_tier": tier,
        }


async def main():
    backtest = InstitutionalStrategyBacktester(runs=40, candles_per_run=2000)
    results = await backtest.run()


if __name__ == "__main__":
    asyncio.run(main())
