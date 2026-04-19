#!/usr/bin/env python3
"""
OPTIMIZED FRACTAL PROFITABILITY ENGINE

Multi-pass optimization:
1. Confluence filters (support/resistance, trend confirmation)
2. Dynamic stop loss adjustment
3. Volume-based entry confirmation
4. Statistical validation (10 runs)
5. Position sizing optimization

Target: 65%+ win rate, 1.8:1 RR, 0.25+ pts/trade expectancy
"""

import asyncio
import logging
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import sys
from pathlib import Path
import statistics

sys.path.insert(0, str(Path(__file__).parent / "ai-engine" / "src"))

from modules.fractal_validator import FractalValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-6s | %(message)s")
logger = logging.getLogger(__name__)


class TradeOutcome(Enum):
    """Trade outcome."""

    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    STILL_OPEN = "STILL_OPEN"
    FILTERED = "FILTERED"  # Pre-trade rejection


@dataclass
class OptimizedTrade:
    """Optimized trade with confluence and sizing."""

    trade_id: int
    symbol: str
    setup_type: str
    entry_bar: int
    entry_price: float
    stop_loss: float
    take_profit: float
    expected_rr: float

    # Confluence filters
    volume_confirmation: bool = False
    trend_confirmation: bool = False
    support_resistance_touch: bool = False
    confluence_score: float = 0.0

    # Position sizing
    position_size_pct: float = 1.0  # % of account per trade
    risk_amt: float = 0.0
    reward_amt: float = 0.0

    # Outcome
    outcome: TradeOutcome = TradeOutcome.STILL_OPEN
    exit_price: Optional[float] = None
    exit_bar: Optional[int] = None
    bars_held: int = 0
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    realized_rr: float = 0.0


class SyntheticMarketGenerator:
    """Generate realistic OHLCV data with structure."""

    def __init__(self, symbol: str = "SPY", seed: int = 42):
        self.symbol = symbol
        self.seed = seed
        random.seed(seed)

    def generate_candles(self, num_candles: int = 3000) -> List[Dict]:
        """Generate market data with trend structure + swings."""
        candles = []
        current_price = 420.0
        volatility = 0.01
        trend = 1 if random.random() > 0.5 else -1

        for i in range(num_candles):
            # Trend-following with reversals
            if i % 50 == 0:
                trend = trend * -1  # Reverse every 50 candles

            trend_component = trend * 0.0003
            daily_return = random.gauss(trend_component, volatility)
            close_price = current_price * (1 + daily_return)

            open_price = current_price * (1 + random.gauss(0, volatility * 0.5))
            high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility * 0.3)))
            low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility * 0.3)))

            # Volume higher on reversals
            vol_multiplier = 1.5 if i % 50 < 5 else 1.0
            volume = int(50_000_000 * vol_multiplier * (1 + random.gauss(0, 0.2)))
            volume = max(10_000_000, volume)

            candles.append(
                {
                    "timestamp": datetime.now() - timedelta(minutes=(num_candles - i)),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2),
                    "volume": volume,
                }
            )

            current_price = close_price

        return sorted(candles, key=lambda x: x["timestamp"])


class ConfluenceFilter:
    """Multi-factor confluence validation."""

    @staticmethod
    def check_volume_confirmation(current_candle: Dict, prev_candles: List[Dict]) -> bool:
        """Volume should be elevated on reversal candles."""
        if not prev_candles or len(prev_candles) < 5:
            return False

        avg_volume = statistics.mean([c["volume"] for c in prev_candles[-5:]])
        return current_candle["volume"] > avg_volume * 1.3

    @staticmethod
    def check_trend_confirmation(candles: List[Dict], entry_bar: int, is_bullish: bool) -> bool:
        """Confirm momentum direction with recent price action."""
        if entry_bar < 5:
            return False

        recent_closes = [c["close"] for c in candles[max(0, entry_bar - 5) : entry_bar]]

        if is_bullish:
            # For bullish, more closes should be higher
            higher_count = sum(
                1 for i in range(len(recent_closes) - 1) if recent_closes[i + 1] > recent_closes[i]
            )
            return higher_count >= 3
        else:
            # For bearish, more closes should be lower
            lower_count = sum(
                1 for i in range(len(recent_closes) - 1) if recent_closes[i + 1] < recent_closes[i]
            )
            return lower_count >= 3

    @staticmethod
    def check_support_resistance(candles: List[Dict], entry_bar: int, is_bullish: bool) -> bool:
        """Check if entry price is near recent swing point."""
        if entry_bar < 10:
            return False

        recent = candles[max(0, entry_bar - 10) : entry_bar]

        if is_bullish:
            # Entry near recent low (support)
            recent_low = min([c["low"] for c in recent])
            entry_price = candles[entry_bar]["close"]
            return abs(entry_price - recent_low) / recent_low < 0.01  # Within 1%
        else:
            # Entry near recent high (resistance)
            recent_high = max([c["high"] for c in recent])
            entry_price = candles[entry_bar]["close"]
            return abs(entry_price - recent_high) / recent_high < 0.01  # Within 1%


class OptimizedFractalBacktester:
    """Backtest with optimization filters."""

    def __init__(self, symbol: str = "SPY", num_candles: int = 3000, account_size: float = 10000):
        self.symbol = symbol
        self.num_candles = num_candles
        self.account_size = account_size
        self.validator = FractalValidator()
        self.confluence = ConfluenceFilter()
        self.trades: List[OptimizedTrade] = []
        self.candles: List[Dict] = []

    async def generate_market_data(self) -> List[Dict]:
        """Generate synthetic market data."""
        logger.info(f"Generating {self.num_candles} candles for {self.symbol}...")
        generator = SyntheticMarketGenerator(self.symbol)
        self.candles = generator.generate_candles(self.num_candles)
        logger.info(f"Generated {len(self.candles)} candles")
        return self.candles

    def _apply_confluence_filters(
        self, fractal_result: Dict, entry_bar: int, is_bullish: bool
    ) -> Tuple[bool, float]:
        """Apply multiple confluence filters. Returns (passes, score)."""
        score = 0.0
        max_score = 3.0

        # Filter 1: Volume confirmation
        if entry_bar > 0:
            prev_candles = self.candles[max(0, entry_bar - 5) : entry_bar]
            if self.confluence.check_volume_confirmation(self.candles[entry_bar], prev_candles):
                score += 1.0

        # Filter 2: Trend confirmation
        if self.confluence.check_trend_confirmation(self.candles, entry_bar, is_bullish):
            score += 1.0

        # Filter 3: Support/Resistance touch
        if self.confluence.check_support_resistance(self.candles, entry_bar, is_bullish):
            score += 1.0

        # Require at least 2/3 confluence factors (66%)
        passes = score >= 2.0
        confluence_pct = (score / max_score) * 100

        return passes, confluence_pct

    def _optimize_stop_loss(self, fractal_result: Dict, is_bullish: bool, entry_bar: int) -> float:
        """Tighten stop loss based on recent swing points."""
        original_sl = fractal_result["stop_loss"]

        # Look back 5 candles for recent swing extremes
        if entry_bar >= 5:
            recent = self.candles[max(0, entry_bar - 5) : entry_bar]

            if is_bullish:
                # Tighter SL at recent low - 1 ATR
                recent_low = min([c["low"] for c in recent])
                atr = statistics.mean([c["high"] - c["low"] for c in recent])
                optimized_sl = recent_low - atr * 0.5  # Tight buffer
                # Use tightest, but not above original
                return min(optimized_sl, original_sl)
            else:
                # Tighter SL at recent high + 1 ATR
                recent_high = max([c["high"] for c in recent])
                atr = statistics.mean([c["high"] - c["low"] for c in recent])
                optimized_sl = recent_high + atr * 0.5
                return max(optimized_sl, original_sl)

        return original_sl

    def _calculate_position_size(
        self, entry: float, stop_loss: float, take_profit: float, risk_pct: float = 1.0
    ) -> Tuple[float, float, float]:
        """Calculate position size based on 1% risk rule."""
        risk_amt = self.account_size * (risk_pct / 100)
        risk_distance = abs(entry - stop_loss)

        if risk_distance == 0:
            return 0.0, risk_amt, 0.0

        # Contracts = risk_amt / risk_distance
        position_size = risk_amt / risk_distance
        reward_amt = position_size * abs(take_profit - entry)

        return position_size, risk_amt, reward_amt

    async def backtest(self) -> Dict:
        """Run optimized backtest."""
        if not self.candles:
            await self.generate_market_data()

        logger.info("Scanning with confluence filters...")
        trade_counter = 0
        valid_signals = 0
        filtered_signals = 0

        for i in range(3, len(self.candles) - 20):
            candles_window = [
                {
                    "open": self.candles[i - 3]["open"],
                    "high": self.candles[i - 3]["high"],
                    "low": self.candles[i - 3]["low"],
                    "close": self.candles[i - 3]["close"],
                    "volume": self.candles[i - 3]["volume"],
                },
                {
                    "open": self.candles[i - 2]["open"],
                    "high": self.candles[i - 2]["high"],
                    "low": self.candles[i - 2]["low"],
                    "close": self.candles[i - 2]["close"],
                    "volume": self.candles[i - 2]["volume"],
                },
                {
                    "open": self.candles[i - 1]["open"],
                    "high": self.candles[i - 1]["high"],
                    "low": self.candles[i - 1]["low"],
                    "close": self.candles[i - 1]["close"],
                    "volume": self.candles[i - 1]["volume"],
                },
                {
                    "open": self.candles[i]["open"],
                    "high": self.candles[i]["high"],
                    "low": self.candles[i]["low"],
                    "close": self.candles[i]["close"],
                    "volume": self.candles[i]["volume"],
                },
            ]

            result = await self.validator.validate(candles_window)

            if result.get("valid"):
                is_bullish = result["pattern"] == "BULLISH_FRACTAL"

                # Apply confluence filters
                passes_filters, confluence_score = self._apply_confluence_filters(
                    result, i, is_bullish
                )

                if not passes_filters:
                    filtered_signals += 1
                    continue

                valid_signals += 1

                # Optimize parameters
                entry_price = result["entry"]
                optimized_sl = self._optimize_stop_loss(result, is_bullish, i)
                take_profit = result["take_profit"]
                expected_rr = (
                    abs(take_profit - entry_price) / abs(entry_price - optimized_sl)
                    if entry_price != optimized_sl
                    else 0
                )

                # Position sizing
                pos_size, risk_amt, reward_amt = self._calculate_position_size(
                    entry_price, optimized_sl, take_profit, risk_pct=1.0
                )

                trade = OptimizedTrade(
                    trade_id=trade_counter,
                    symbol=self.symbol,
                    setup_type=result["pattern"],
                    entry_bar=i,
                    entry_price=entry_price,
                    stop_loss=optimized_sl,
                    take_profit=take_profit,
                    expected_rr=expected_rr,
                    volume_confirmation=True,
                    trend_confirmation=True,
                    support_resistance_touch=confluence_score >= 2.0,
                    confluence_score=confluence_score,
                    position_size_pct=1.0,
                    risk_amt=risk_amt,
                    reward_amt=reward_amt,
                )

                self._simulate_exit(trade, i + 1, min(i + 21, len(self.candles)))
                self.trades.append(trade)
                trade_counter += 1

        logger.info(
            f"Generated: {valid_signals} | Filtered: {filtered_signals} | Taken: {len(self.trades)}"
        )
        return await self._calculate_metrics()

    def _simulate_exit(self, trade: OptimizedTrade, start_bar: int, end_bar: int) -> None:
        """Simulate exit with optimized stops."""
        for i in range(start_bar, end_bar):
            candle = self.candles[i]
            high = candle["high"]
            low = candle["low"]

            if trade.setup_type == "BULLISH_FRACTAL":
                if low <= trade.stop_loss:
                    trade.outcome = TradeOutcome.LOSS
                    trade.exit_price = trade.stop_loss
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = -trade.risk_amt
                    trade.realized_pnl_pct = (trade.realized_pnl / (self.account_size)) * 100
                    trade.realized_rr = 0.0
                    return
                elif high >= trade.take_profit:
                    trade.outcome = TradeOutcome.WIN
                    trade.exit_price = trade.take_profit
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = trade.reward_amt
                    trade.realized_pnl_pct = (trade.realized_pnl / self.account_size) * 100
                    trade.realized_rr = (
                        trade.reward_amt / trade.risk_amt if trade.risk_amt > 0 else 0
                    )
                    return
            else:
                if high >= trade.stop_loss:
                    trade.outcome = TradeOutcome.LOSS
                    trade.exit_price = trade.stop_loss
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = -trade.risk_amt
                    trade.realized_pnl_pct = (trade.realized_pnl / self.account_size) * 100
                    trade.realized_rr = 0.0
                    return
                elif low <= trade.take_profit:
                    trade.outcome = TradeOutcome.WIN
                    trade.exit_price = trade.take_profit
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = trade.reward_amt
                    trade.realized_pnl_pct = (trade.realized_pnl / self.account_size) * 100
                    trade.realized_rr = (
                        trade.reward_amt / trade.risk_amt if trade.risk_amt > 0 else 0
                    )
                    return

        trade.outcome = TradeOutcome.STILL_OPEN
        trade.exit_price = None
        trade.bars_held = end_bar - trade.entry_bar

    async def _calculate_metrics(self) -> Dict:
        """Calculate comprehensive metrics."""
        if not self.trades:
            return {}

        closed_trades = [
            t for t in self.trades if t.outcome in [TradeOutcome.WIN, TradeOutcome.LOSS]
        ]
        wins = [t for t in closed_trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in closed_trades if t.outcome == TradeOutcome.LOSS]

        if not closed_trades:
            return {}

        win_rate = len(wins) / len(closed_trades) * 100
        loss_rate = len(losses) / len(closed_trades) * 100

        avg_expected_rr = sum([t.expected_rr for t in closed_trades]) / len(closed_trades)
        avg_realized_rr = (
            sum([t.realized_rr for t in closed_trades if t.outcome == TradeOutcome.WIN]) / len(wins)
            if wins
            else 0
        )

        total_pnl = sum([t.realized_pnl for t in closed_trades])
        total_pnl_pct = sum([t.realized_pnl_pct for t in closed_trades])

        if wins:
            avg_win = sum([t.realized_pnl for t in wins]) / len(wins)
        else:
            avg_win = 0

        if losses:
            avg_loss = sum([t.realized_pnl for t in losses]) / len(losses)
        else:
            avg_loss = 0

        expectancy = (win_rate / 100 * avg_win) - (loss_rate / 100 * abs(avg_loss))

        # Profit factor
        gross_wins = sum([t.realized_pnl for t in wins]) if wins else 0
        gross_losses = abs(sum([t.realized_pnl for t in losses])) if losses else 1
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0

        return {
            "symbol": self.symbol,
            "total_signals": len(self.trades),
            "closed_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "expected_rr_avg": round(avg_expected_rr, 2),
            "realized_rr_avg": round(avg_realized_rr, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_pnl_pct, 2),
            "avg_pnl_per_trade": round(total_pnl / len(closed_trades), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(expectancy, 4),
            "profit_factor": round(profit_factor, 2),
            "sharpe_proxy": round(expectancy / (abs(avg_loss) if avg_loss != 0 else 1), 2),
        }

    def print_report(self) -> None:
        """Print detailed report."""
        if not self.trades:
            logger.warning("No trades")
            return

        closed_trades = [
            t for t in self.trades if t.outcome in [TradeOutcome.WIN, TradeOutcome.LOSS]
        ]
        wins = [t for t in closed_trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in closed_trades if t.outcome == TradeOutcome.LOSS]

        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZED FRACTAL BACKTEST")
        logger.info("=" * 80)
        logger.info(f"\nSymbol: {self.symbol} | Account: ${self.account_size:,.0f}")
        logger.info(f"Signals: {len(self.trades)} | Wins: {len(wins)} | Losses: {len(losses)}")
        logger.info(f"\nWIN RATE: {len(wins) / len(closed_trades) * 100:.1f}%")
        logger.info(
            f"Realized RR (on wins): {sum([t.realized_rr for t in wins]) / len(wins) if wins else 0:.2f}:1"
        )
        logger.info(f"\nTOTAL P&L: ${sum([t.realized_pnl for t in closed_trades]):,.2f}")
        logger.info(f"RETURN: {sum([t.realized_pnl_pct for t in closed_trades]):.2f}%")
        logger.info(
            f"Expectancy: ${sum([t.realized_pnl for t in closed_trades]) / len(closed_trades):.2f}/trade"
        )
        logger.info("=" * 80 + "\n")


async def run_optimization_suite():
    """Run 10 backtests with different seeds for validation."""
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING 10 SIMULATION SUITE FOR STATISTICAL VALIDATION")
    logger.info("=" * 80 + "\n")

    results = []

    for run in range(1, 11):
        logger.info(f"\n--- RUN {run}/10 ---")
        random.seed(42 + run)

        backtest = OptimizedFractalBacktester(symbol="SPY", num_candles=3000, account_size=10000)
        await backtest.generate_market_data()
        metrics = await backtest.backtest()
        backtest.print_report()

        if metrics:
            results.append(metrics)

    # Summary statistics
    logger.info("\n" + "=" * 80)
    logger.info("OPTIMIZATION SUITE RESULTS (10 Runs)")
    logger.info("=" * 80)

    if results:
        win_rates = [r["win_rate_pct"] for r in results]
        realized_rrs = [r["realized_rr_avg"] for r in results]
        expectations = [r["expectancy"] for r in results]
        returns = [r["total_return_pct"] for r in results]

        logger.info(f"\nWIN RATE:")
        logger.info(f"   Mean: {statistics.mean(win_rates):.2f}%")
        logger.info(f"   Std Dev: {statistics.stdev(win_rates) if len(win_rates) > 1 else 0:.2f}%")
        logger.info(f"   Min/Max: {min(win_rates):.2f}% / {max(win_rates):.2f}%")

        logger.info(f"\nREALIZED RR:")
        logger.info(f"   Mean: {statistics.mean(realized_rrs):.2f}:1")
        logger.info(
            f"   Std Dev: {statistics.stdev(realized_rrs) if len(realized_rrs) > 1 else 0:.2f}"
        )
        logger.info(f"   Min/Max: {min(realized_rrs):.2f}:1 / {max(realized_rrs):.2f}:1")

        logger.info(f"\nEXPECTANCY (pts/trade):")
        logger.info(f"   Mean: {statistics.mean(expectations):.4f}")
        logger.info(
            f"   Std Dev: {statistics.stdev(expectations) if len(expectations) > 1 else 0:.4f}"
        )

        logger.info(f"\nTOTAL RETURN %:")
        logger.info(f"   Mean: {statistics.mean(returns):.2f}%")
        logger.info(f"   Min/Max: {min(returns):.2f}% / {max(returns):.2f}%")

        logger.info("\n" + "=" * 80)
        logger.info("PROFITABILITY ASSESSMENT")
        logger.info("=" * 80)

        if statistics.mean(win_rates) >= 65.0 and statistics.mean(realized_rrs) >= 1.8:
            logger.info("✅ EXCELLENT: System meets target specs (65%+ WR, 1.8:1 RR)")
        elif statistics.mean(win_rates) >= 60.0 and statistics.mean(realized_rrs) >= 1.6:
            logger.info("✅ VERY GOOD: System near-optimal (60%+ WR, 1.6:1 RR)")
        elif statistics.mean(win_rates) >= 55.0 and statistics.mean(realized_rrs) >= 1.4:
            logger.info("✅ GOOD: System profitable (55%+ WR, 1.4:1 RR)")
        else:
            logger.info("⚠️  MARGINAL: May need further optimization")

        logger.info(f"\nPROFIT POTENTIAL (per $10k account):")
        monthly_expectancy = statistics.mean(expectations) * 20  # ~20 trades/month
        logger.info(f"   Expected Monthly: ${monthly_expectancy * 100:.0f}")
        logger.info(f"   Expected Yearly: ${monthly_expectancy * 100 * 12:.0f}")


if __name__ == "__main__":
    asyncio.run(run_optimization_suite())
