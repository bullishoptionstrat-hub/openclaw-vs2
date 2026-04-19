#!/usr/bin/env python3
"""
FRACTAL BACKTEST - Synthetic Data Version

Backtests the 4-candle fractal validator using generated market data.
Calculates actual win rate and realized RR vs expected metrics.

No external dependencies - pure Python simulation.
"""

import asyncio
import logging
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import sys
from pathlib import Path
import math

# Add parent dirs to path for imports
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


@dataclass
class BacktestTrade:
    """Trade from backtest simulation."""

    trade_id: int
    symbol: str
    setup_type: str
    entry_bar: int
    entry_price: float
    stop_loss: float
    take_profit: float
    expected_rr: float

    outcome: TradeOutcome = TradeOutcome.STILL_OPEN
    exit_price: Optional[float] = None
    exit_bar: Optional[int] = None
    bars_held: int = 0
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    realized_rr: float = 0.0


class SyntheticMarketGenerator:
    """Generate realistic synthetic market data using geometric random walk."""

    def __init__(self, symbol: str = "SPY", seed: int = 42):
        self.symbol = symbol
        self.seed = seed
        random.seed(seed)

    def generate_candles(self, num_candles: int = 2000) -> List[Dict]:
        """Generate realistic OHLCV candles using geometric random walk."""
        candles = []
        current_price = 420.0  # Start at SPY-like price
        volatility = 0.01  # 1% daily volatility

        for i in range(num_candles):
            # Generate using geometric random walk
            daily_return = random.gauss(0.0005, volatility)  # Slightly bullish drift
            close_price = current_price * (1 + daily_return)

            # Open slightly offset from previous close
            open_price = current_price * (1 + random.gauss(0, volatility * 0.5))

            # High and low with some structure
            high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility * 0.3)))
            low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility * 0.3)))

            # Volume typically inversely correlated with volatility
            volume = int(50_000_000 * (1 + random.gauss(0, 0.3)))
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


class FractalBacktester:
    """Backtest fractal validator against synthetic data."""

    def __init__(self, symbol: str = "SPY", num_candles: int = 2000):
        self.symbol = symbol
        self.num_candles = num_candles
        self.validator = FractalValidator()
        self.trades: List[BacktestTrade] = []
        self.candles: List[Dict] = []

    async def generate_market_data(self) -> List[Dict]:
        """Generate synthetic market data."""
        logger.info(f"Generating {self.num_candles} synthetic candles for {self.symbol}...")
        generator = SyntheticMarketGenerator(self.symbol)
        self.candles = generator.generate_candles(self.num_candles)
        logger.info(
            f"Generated {len(self.candles)} candles from {self.candles[0]['timestamp']} to {self.candles[-1]['timestamp']}"
        )
        return self.candles

    async def backtest(self) -> Dict:
        """Run backtest: scan all 4-candle windows."""
        if not self.candles:
            await self.generate_market_data()

        logger.info(f"\nScanning for fractal patterns...")
        trade_counter = 0
        valid_signals = 0

        # Scan all possible 4-candle windows
        for i in range(3, len(self.candles) - 20):  # -20 to allow room for exit
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

            # Validate fractal
            result = await self.validator.validate(candles_window)

            if result.get("valid"):
                valid_signals += 1
                trade_id = trade_counter
                trade_counter += 1

                entry_price = result["entry"]
                stop_loss = result["stop_loss"]
                take_profit = result["take_profit"]
                expected_rr = result["risk_reward"]
                setup_type = result["pattern"]

                # Create trade entry
                trade = BacktestTrade(
                    trade_id=trade_id,
                    symbol=self.symbol,
                    setup_type=setup_type,
                    entry_bar=i,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    expected_rr=expected_rr,
                )

                # Simulate exit: scan next 20 candles for TP/SL hit
                self._simulate_exit(trade, i + 1, min(i + 21, len(self.candles)))

                self.trades.append(trade)

        logger.info(f"Found {valid_signals} valid fractals, created {len(self.trades)} trades")
        return await self._calculate_metrics()

    def _simulate_exit(self, trade: BacktestTrade, start_bar: int, end_bar: int) -> None:
        """Simulate trade exit: TP/SL hit or timeout."""
        for i in range(start_bar, end_bar):
            candle = self.candles[i]
            high = candle["high"]
            low = candle["low"]
            close = candle["close"]

            # Check TP/SL hit
            if trade.setup_type == "BULLISH_FRACTAL":
                if low <= trade.stop_loss:
                    trade.outcome = TradeOutcome.LOSS
                    trade.exit_price = trade.stop_loss
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = -abs(trade.entry_price - trade.stop_loss)
                    trade.realized_pnl_pct = (trade.realized_pnl / trade.entry_price) * 100
                    trade.realized_rr = 0.0
                    return
                elif high >= trade.take_profit:
                    trade.outcome = TradeOutcome.WIN
                    trade.exit_price = trade.take_profit
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = trade.take_profit - trade.entry_price
                    trade.realized_pnl_pct = (trade.realized_pnl / trade.entry_price) * 100
                    trade.realized_rr = abs(trade.take_profit - trade.entry_price) / abs(
                        trade.entry_price - trade.stop_loss
                    )
                    return
            else:  # BEARISH_FRACTAL
                if high >= trade.stop_loss:
                    trade.outcome = TradeOutcome.LOSS
                    trade.exit_price = trade.stop_loss
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = -(trade.stop_loss - trade.entry_price)
                    trade.realized_pnl_pct = (trade.realized_pnl / trade.entry_price) * 100
                    trade.realized_rr = 0.0
                    return
                elif low <= trade.take_profit:
                    trade.outcome = TradeOutcome.WIN
                    trade.exit_price = trade.take_profit
                    trade.exit_bar = i
                    trade.bars_held = i - trade.entry_bar
                    trade.realized_pnl = trade.entry_price - trade.take_profit
                    trade.realized_pnl_pct = (trade.realized_pnl / trade.entry_price) * 100
                    trade.realized_rr = abs(trade.entry_price - trade.take_profit) / abs(
                        trade.stop_loss - trade.entry_price
                    )
                    return

        # Trade didn't exit (still open)
        trade.outcome = TradeOutcome.STILL_OPEN
        trade.exit_price = None
        trade.bars_held = end_bar - trade.entry_bar

    async def _calculate_metrics(self) -> Dict:
        """Calculate backtest statistics."""
        if not self.trades:
            logger.warning("No trades generated")
            return {}

        # Separate by outcome
        closed_trades = [
            t for t in self.trades if t.outcome in [TradeOutcome.WIN, TradeOutcome.LOSS]
        ]
        wins = [t for t in closed_trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in closed_trades if t.outcome == TradeOutcome.LOSS]

        if not closed_trades:
            logger.warning("No closed trades to analyze")
            return {}

        # Calculate metrics
        win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
        loss_rate = len(losses) / len(closed_trades) * 100 if closed_trades else 0

        avg_expected_rr = sum([t.expected_rr for t in closed_trades]) / len(closed_trades)

        if wins:
            avg_realized_rr_wins = sum([t.realized_rr for t in wins]) / len(wins)
        else:
            avg_realized_rr_wins = 0

        total_pnl = sum([t.realized_pnl for t in closed_trades])
        total_pnl_pct = sum([t.realized_pnl_pct for t in closed_trades])
        avg_pnl_per_trade = total_pnl / len(closed_trades)

        if wins:
            avg_win = sum([t.realized_pnl for t in wins]) / len(wins)
        else:
            avg_win = 0

        if losses:
            avg_loss = sum([t.realized_pnl for t in losses]) / len(losses)
        else:
            avg_loss = 0

        expectancy = (win_rate / 100 * avg_win) - (loss_rate / 100 * abs(avg_loss))

        metrics = {
            "symbol": self.symbol,
            "total_candles": len(self.candles),
            "total_signals": len(self.trades),
            "closed_trades": len(closed_trades),
            "open_trades": len([t for t in self.trades if t.outcome == TradeOutcome.STILL_OPEN]),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "loss_rate_pct": round(loss_rate, 2),
            "expected_rr_avg": round(avg_expected_rr, 2),
            "realized_rr_avg_on_wins": round(avg_realized_rr_wins, 2),
            "total_pnl_pts": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "avg_pnl_per_trade": round(avg_pnl_per_trade, 2),
            "avg_win_size": round(avg_win, 2),
            "avg_loss_size": round(avg_loss, 2),
            "expectancy": round(expectancy, 4),
            "avg_bars_held": round(
                sum([t.bars_held for t in closed_trades]) / len(closed_trades), 1
            )
            if closed_trades
            else 0,
        }

        return metrics

    def print_report(self) -> None:
        """Print formatted backtest report."""
        if not self.trades:
            logger.warning("No trades to report")
            return

        closed_trades = [
            t for t in self.trades if t.outcome in [TradeOutcome.WIN, TradeOutcome.LOSS]
        ]
        wins = [t for t in closed_trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in closed_trades if t.outcome == TradeOutcome.LOSS]

        logger.info("\n" + "=" * 80)
        logger.info("FRACTAL BACKTEST RESULTS (Synthetic Data)")
        logger.info("=" * 80)
        logger.info(f"\nSymbol: {self.symbol} | Candles: {len(self.candles)}")
        logger.info(f"\nTRADE STATISTICS:")
        logger.info(f"   Total Signals Generated: {len(self.trades)}")
        logger.info(f"   Closed Trades: {len(closed_trades)}")
        logger.info(
            f"   Still Open: {len([t for t in self.trades if t.outcome == TradeOutcome.STILL_OPEN])}"
        )

        logger.info(f"\nWIN/LOSS BREAKDOWN:")
        logger.info(f"   Wins: {len(wins)} ({len(wins) / len(closed_trades) * 100:.1f}%)")
        logger.info(f"   Losses: {len(losses)} ({len(losses) / len(closed_trades) * 100:.1f}%)")

        if wins:
            avg_win = sum([t.realized_pnl for t in wins]) / len(wins)
            logger.info(f"   Avg Win: {avg_win:.2f} pts")
            avg_realized_rr_wins = sum([t.realized_rr for t in wins]) / len(wins)
            logger.info(f"   Avg Win RR: {avg_realized_rr_wins:.2f}:1")

        if losses:
            avg_loss = sum([t.realized_pnl for t in losses]) / len(losses)
            logger.info(f"   Avg Loss: {avg_loss:.2f} pts")

        avg_expected_rr = (
            sum([t.expected_rr for t in closed_trades]) / len(closed_trades) if closed_trades else 0
        )
        logger.info(f"\nEXPECTED vs REALIZED RR:")
        logger.info(f"   Expected RR (avg): {avg_expected_rr:.2f}:1")
        if wins:
            logger.info(f"   Realized RR (on wins): {avg_realized_rr_wins:.2f}:1")

        total_pnl = sum([t.realized_pnl for t in closed_trades])
        logger.info(f"\nPROFITABILITY:")
        logger.info(f"   Total PnL: {total_pnl:.2f} pts")
        logger.info(f"   Avg PnL/Trade: {total_pnl / len(closed_trades):.2f} pts")

        if wins:
            avg_win = sum([t.realized_pnl for t in wins]) / len(wins)
        else:
            avg_win = 0
        if losses:
            avg_loss = sum([t.realized_pnl for t in losses]) / len(losses)
        else:
            avg_loss = 0

        win_pct = len(wins) / len(closed_trades) if closed_trades else 0
        loss_pct = len(losses) / len(closed_trades) if closed_trades else 0
        expectancy = (win_pct * avg_win) - (loss_pct * abs(avg_loss))
        logger.info(f"   Expectancy: {expectancy:.4f} pts/trade")

        logger.info(f"\nHOLDING TIME:")
        avg_bars = (
            sum([t.bars_held for t in closed_trades]) / len(closed_trades) if closed_trades else 0
        )
        logger.info(f"   Avg Bars Held: {avg_bars:.1f}")

        logger.info("=" * 80 + "\n")

        # Top 5 trades
        if closed_trades:
            logger.info("TOP 5 TRADES:")
            sorted_by_pnl = sorted(closed_trades, key=lambda t: t.realized_pnl, reverse=True)[:5]
            for i, t in enumerate(sorted_by_pnl, 1):
                logger.info(
                    f"   {i}. {t.setup_type} | "
                    f"Entry: {t.entry_price:.2f} | PnL: {t.realized_pnl:.2f} | "
                    f"RR: {t.realized_rr:.2f}:1 | {t.outcome.value}"
                )
            logger.info("")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fractal Pattern Backtest (Synthetic Data)")
    parser.add_argument("--symbol", default="SPY", help="Symbol (default: SPY)")
    parser.add_argument(
        "--candles", type=int, default=2000, help="Number of candles (default: 2000)"
    )
    parser.add_argument("--export", help="Export results to JSON file")

    args = parser.parse_args()

    # Run backtest
    backtest = FractalBacktester(symbol=args.symbol, num_candles=args.candles)
    await backtest.generate_market_data()
    metrics = await backtest.backtest()
    backtest.print_report()

    # Export if requested
    if args.export:
        export_data = {"metrics": metrics, "trades": [asdict(t) for t in backtest.trades]}
        with open(args.export, "w") as f:
            json.dump(export_data, f, indent=2, default=str)
        logger.info(f"Results exported to {args.export}")

    # Return metrics for verification
    if metrics:
        logger.info("\nKEY METRICS:")
        logger.info(f"  Win Rate: {metrics.get('win_rate_pct')}%")
        logger.info(f"  Realized RR (wins): {metrics.get('realized_rr_avg_on_wins')}:1")
        logger.info(f"  Expected RR (avg): {metrics.get('expected_rr_avg')}:1")
        logger.info(f"  Expectancy: {metrics.get('expectancy')} pts/trade")


if __name__ == "__main__":
    asyncio.run(main())
