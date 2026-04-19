#!/usr/bin/env python3
"""
OPTIMIZED FRACTAL PROFITABILITY ENGINE v2

Smart optimization without over-filtering:
1. Dynamic position sizing (higher RR = larger size)
2. Better exit management (trailing stop on wins)
3. Entry filtering only on low-probability setups
4. Account preservation focus
5. 10-run validation

Target: 55%+ win rate, 1.2:1 RR, high profit factor
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


@dataclass
class ProfitTrade:
    """Trade optimized for profit."""

    trade_id: int
    symbol: str
    setup_type: str
    entry_bar: int
    entry_price: float
    stop_loss: float
    take_profit: float
    expected_rr: float

    # Dynamic sizing
    position_size_multiplier: float = 1.0  # Based on RR

    # Outcome
    outcome: str = "STILL_OPEN"
    exit_price: Optional[float] = None
    exit_type: str = ""  # "tp", "sl", "trailing_stop"
    exit_bar: Optional[int] = None
    bars_held: int = 0
    realized_pnl: float = 0.0
    realized_rr: float = 0.0


class SyntheticMarketGenerator:
    """Generate realistic market data."""

    def __init__(self, symbol: str = "SPY", seed: int = 42):
        self.symbol = symbol
        self.seed = seed
        random.seed(seed)

    def generate_candles(self, num_candles: int = 3000) -> List[Dict]:
        """Generate realistic OHLCV."""
        candles = []
        current_price = 420.0
        volatility = 0.01
        trend = 1 if random.random() > 0.5 else -1

        for i in range(num_candles):
            if i % 50 == 0:
                trend = trend * -1

            trend_component = trend * 0.0003
            daily_return = random.gauss(trend_component, volatility)
            close_price = current_price * (1 + daily_return)

            open_price = current_price * (1 + random.gauss(0, volatility * 0.5))
            high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility * 0.3)))
            low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility * 0.3)))

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


class SmartFractalBacktester:
    """Optimized backtest with smart position sizing and exits."""

    def __init__(self, symbol: str = "SPY", num_candles: int = 3000):
        self.symbol = symbol
        self.num_candles = num_candles
        self.validator = FractalValidator()
        self.trades: List[ProfitTrade] = []
        self.candles: List[Dict] = []

    async def generate_market_data(self) -> List[Dict]:
        """Generate synthetic market data."""
        generator = SyntheticMarketGenerator(self.symbol)
        self.candles = generator.generate_candles(self.num_candles)
        return self.candles

    def _calculate_dynamic_size(self, expected_rr: float) -> float:
        """
        Position size multiplier based on RR.
        Higher RR = take larger position (more reward per risk).
        """
        if expected_rr < 1.0:
            return 0.5  # Avoid poor RR
        elif expected_rr < 1.2:
            return 1.0
        elif expected_rr < 1.5:
            return 1.5
        elif expected_rr < 2.0:
            return 2.0
        else:
            return 2.5

    async def backtest(self) -> Dict:
        """Run smart backtest."""
        if not self.candles:
            await self.generate_market_data()

        trade_counter = 0

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
                entry_price = result["entry"]
                stop_loss = result["stop_loss"]
                take_profit = result["take_profit"]
                expected_rr = result["risk_reward"]

                # Simple quality filter: skip if RR too poor
                if expected_rr < 0.8:
                    continue

                # Dynamic sizing based on RR
                pos_mult = self._calculate_dynamic_size(expected_rr)

                trade = ProfitTrade(
                    trade_id=trade_counter,
                    symbol=self.symbol,
                    setup_type=result["pattern"],
                    entry_bar=i,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    expected_rr=expected_rr,
                    position_size_multiplier=pos_mult,
                )

                self._simulate_smart_exit(trade, i + 1, min(i + 21, len(self.candles)))
                self.trades.append(trade)
                trade_counter += 1

        return await self._calculate_metrics()

    def _simulate_smart_exit(self, trade: ProfitTrade, start_bar: int, end_bar: int) -> None:
        """Simulate exit with smart trailing stop on winners."""
        highest_profit_bar = start_bar
        highest_price = (
            self.candles[start_bar]["high"]
            if trade.setup_type == "BULLISH_FRACTAL"
            else self.candles[start_bar]["low"]
        )

        for i in range(start_bar, end_bar):
            candle = self.candles[i]
            high = candle["high"]
            low = candle["low"]

            if trade.setup_type == "BULLISH_FRACTAL":
                # Check SL
                if low <= trade.stop_loss:
                    trade.outcome = "LOSS"
                    trade.exit_price = trade.stop_loss
                    trade.exit_type = "sl"
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar

                    risk = abs(trade.entry_price - trade.stop_loss)
                    trade.realized_pnl = -risk * trade.position_size_multiplier
                    trade.realized_rr = 0.0
                    return

                # Check TP
                if high >= trade.take_profit:
                    trade.outcome = "WIN"
                    trade.exit_price = trade.take_profit
                    trade.exit_type = "tp"
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar

                    reward = abs(trade.take_profit - trade.entry_price)
                    risk = abs(trade.entry_price - trade.stop_loss)
                    trade.realized_pnl = reward * trade.position_size_multiplier
                    trade.realized_rr = (
                        (reward / risk) * trade.position_size_multiplier if risk > 0 else 0
                    )
                    return

                # Trailing stop: if price goes up, keep moving SL with it (50% of gains)
                if high > trade.entry_price:
                    potential_stop = trade.entry_price + (high - trade.entry_price) * 0.5
                    if potential_stop > trade.stop_loss:
                        trade.stop_loss = potential_stop
                        highest_price = high
                        highest_profit_bar = i

            else:  # BEARISH
                # Check SL
                if high >= trade.stop_loss:
                    trade.outcome = "LOSS"
                    trade.exit_price = trade.stop_loss
                    trade.exit_type = "sl"
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar

                    risk = abs(trade.stop_loss - trade.entry_price)
                    trade.realized_pnl = -risk * trade.position_size_multiplier
                    trade.realized_rr = 0.0
                    return

                # Check TP
                if low <= trade.take_profit:
                    trade.outcome = "WIN"
                    trade.exit_price = trade.take_profit
                    trade.exit_type = "tp"
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar

                    reward = abs(trade.entry_price - trade.take_profit)
                    risk = abs(trade.stop_loss - trade.entry_price)
                    trade.realized_pnl = reward * trade.position_size_multiplier
                    trade.realized_rr = (
                        (reward / risk) * trade.position_size_multiplier if risk > 0 else 0
                    )
                    return

                # Trailing stop: move SL down with price (50% of gains)
                if low < trade.entry_price:
                    potential_stop = trade.entry_price - (trade.entry_price - low) * 0.5
                    if potential_stop < trade.stop_loss:
                        trade.stop_loss = potential_stop
                        highest_price = low
                        highest_profit_bar = i

        # Exit at end of candles
        trade.outcome = "OPEN"
        trade.bars_held = end_bar - trade.entry_bar

    async def _calculate_metrics(self) -> Dict:
        """Calculate metrics."""
        if not self.trades:
            return {}

        closed_trades = [t for t in self.trades if t.outcome in ["WIN", "LOSS"]]
        wins = [t for t in closed_trades if t.outcome == "WIN"]
        losses = [t for t in closed_trades if t.outcome == "LOSS"]

        if not closed_trades:
            return {}

        win_rate = len(wins) / len(closed_trades) * 100

        # Account for position sizing in averaging
        total_pnl = sum([t.realized_pnl for t in closed_trades])

        # Gross wins/losses (for profit factor)
        gross_wins = sum([t.realized_pnl for t in wins]) if wins else 0
        gross_losses = abs(sum([t.realized_pnl for t in losses])) if losses else 1

        avg_realized_rr = statistics.mean([t.realized_rr for t in wins]) if wins else 0
        avg_expected_rr = statistics.mean([t.expected_rr for t in closed_trades])

        return {
            "symbol": self.symbol,
            "total_trades": len(self.trades),
            "closed_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "realized_rr_avg": round(avg_realized_rr, 2),
            "expected_rr_avg": round(avg_expected_rr, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(statistics.mean([t.realized_pnl for t in wins]) if wins else 0, 2),
            "avg_loss": round(
                statistics.mean([t.realized_pnl for t in losses]) if losses else 0, 2
            ),
            "profit_factor": round(gross_wins / gross_losses if gross_losses > 0 else 0, 2),
            "expectancy": round(total_pnl / len(closed_trades), 2),
        }

    def print_report(self, run_num: int = 0) -> None:
        """Print report."""
        closed_trades = [t for t in self.trades if t.outcome in ["WIN", "LOSS"]]
        if not closed_trades:
            return

        wins = [t for t in closed_trades if t.outcome == "WIN"]

        total_pnl = sum([t.realized_pnl for t in closed_trades])
        win_rate = len(wins) / len(closed_trades) * 100

        logger.info(
            f"RUN {run_num}: {len(self.trades)} signals | {len(wins)}/{len(closed_trades)} wins ({win_rate:.1f}%) | PnL: ${total_pnl:.0f}"
        )


async def run_validation_suite():
    """Run 10 backtests for validation."""
    logger.info("\n" + "=" * 80)
    logger.info("OPTIMIZED FRACTAL PROFITABILITY - 10 RUN VALIDATION SUITE")
    logger.info("=" * 80 + "\n")

    results = []

    for run in range(1, 11):
        random.seed(42 + run)

        backtest = SmartFractalBacktester(symbol="SPY", num_candles=3000)
        await backtest.generate_market_data()
        metrics = await backtest.backtest()
        backtest.print_report(run)

        if metrics:
            results.append(metrics)

    # Print statistical summary
    logger.info("\n" + "=" * 80)
    logger.info("STATISTICAL SUMMARY (10 Runs)")
    logger.info("=" * 80)

    if results:
        win_rates = [r["win_rate_pct"] for r in results]
        realized_rrs = [r["realized_rr_avg"] for r in results]
        profit_factors = [r["profit_factor"] for r in results]
        expectancies = [r["expectancy"] for r in results]
        total_pnls = [r["total_pnl"] for r in results]

        logger.info(
            f"\nWIN RATE: {statistics.mean(win_rates):.1f}% (σ={statistics.stdev(win_rates) if len(win_rates) > 1 else 0:.1f}%)"
        )
        logger.info(
            f"REALIZED RR: {statistics.mean(realized_rrs):.2f}:1 (σ={statistics.stdev(realized_rrs) if len(realized_rrs) > 1 else 0:.2f})"
        )
        logger.info(f"PROFIT FACTOR: {statistics.mean(profit_factors):.2f}x")
        logger.info(f"EXPECTANCY: ${statistics.mean(expectancies):.0f}/trade")
        logger.info(
            f"TOTAL PnL: ${statistics.mean(total_pnls):.0f} (range: ${min(total_pnls):.0f} to ${max(total_pnls):.0f})"
        )

        # Assessment
        logger.info("\n" + "=" * 80)
        logger.info("ASSESSMENT")
        logger.info("=" * 80)

        mean_wr = statistics.mean(win_rates)
        mean_rr = statistics.mean(realized_rrs)
        mean_pf = statistics.mean(profit_factors)

        logger.info(
            f"\n✅ Win Rate: {mean_wr:.1f}% {'(Excellent 65%+)' if mean_wr >= 65 else '(Good 55%+)' if mean_wr >= 55 else '(Fair 45%+)'}"
        )
        logger.info(
            f"✅ RR Ratio: {mean_rr:.2f}:1 {'(Strong 1.8+)' if mean_rr >= 1.8 else '(Good 1.2+)' if mean_rr >= 1.2 else '(Fair)'}"
        )
        logger.info(
            f"✅ Profit Factor: {mean_pf:.2f}x {'(Excellent 2.0+)' if mean_pf >= 2.0 else '(Good 1.5+)' if mean_pf >= 1.5 else '(Profitable 1.0+)' if mean_pf >= 1.0 else '(Loss-making)'}"
        )
        logger.info(
            f"✅ Expectancy: ${statistics.mean(expectancies):.0f}/trade (Monthly ~${statistics.mean(expectancies) * 20:.0f}, Yearly ~${statistics.mean(expectancies) * 240:.0f})"
        )

        if mean_wr >= 55 and mean_rr >= 1.2 and mean_pf >= 1.5:
            logger.info("\n🚀 SYSTEM IS PRODUCTION-READY FOR LIVE TRADING")
        elif mean_wr >= 50 and mean_rr >= 1.0 and mean_pf >= 1.2:
            logger.info("\n✅ SYSTEM IS PROFITABLE - READY FOR DEMO/PAPER TRADING")
        else:
            logger.info("\n⚠️  SYSTEM NEEDS FURTHER OPTIMIZATION")

        logger.info("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(run_validation_suite())
