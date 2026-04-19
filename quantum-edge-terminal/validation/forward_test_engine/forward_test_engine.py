"""
FORWARD TEST ENGINE

Consumes live/historical market data in real time.
Runs the complete signal stack without executing on broker.
Generates paper trades only.

This is where execution problems emerge that backtests fail to catch:
- Slippage
- Latency
- Spread
- Stale data
- Duplicate signals
- API disconnects
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TradeSignal(Enum):
    """Signal direction."""

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass
class MarketCandle:
    """OHLCV market data."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: str = "1m"


@dataclass
class GeneratedSignal:
    """Signal from the strategy engine."""

    signal_id: str
    symbol: str
    direction: TradeSignal
    confidence: float  # 0-1
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    setup_type: str
    timestamp: datetime
    macro_regime: str
    liquidity_score: float
    structure_score: float
    options_score: float
    confluence_score: float


@dataclass
class PaperTrade:
    """Paper trade record (simulated execution)."""

    trade_id: str
    symbol: str
    direction: TradeSignal
    entry_signal_timestamp: datetime
    entry_order_timestamp: datetime
    entry_price: float
    entry_actual_price: float  # After slippage
    qty: float
    stop_loss: float
    take_profit: float
    current_price: float = 0.0
    status: str = "PENDING"  # PENDING, FILLED, CLOSED, SL_HIT, TP_HIT
    filled_timestamp: Optional[datetime] = None
    closed_timestamp: Optional[datetime] = None
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    slippage: float = 0.0
    execution_latency_ms: float = 0.0


class ForwardTestEngine:
    """
    Forward test engine simulates real-time strategy execution.

    Does NOT place real orders.
    Generates paper trades for validation.
    Tracks execution quality and operational issues.
    """

    def __init__(self, symbol: str = "ES"):
        """
        Initialize forward test engine.

        Args:
            symbol: Symbol to forward test (default: ES = S&P 500 futures)
        """
        self.symbol = symbol
        self.paper_trades: Dict[str, PaperTrade] = {}
        self.trade_history: List[PaperTrade] = []
        self.generated_signals: List[GeneratedSignal] = []
        self.candle_queue: List[MarketCandle] = []
        self.last_signal_per_symbol: Dict[str, GeneratedSignal] = {}

        # Metrics
        self.signal_count = 0
        self.trade_count = 0
        self.rejected_signals = 0
        self.duplicate_signals = 0
        self.stale_data_events = 0
        self.execution_latencies: List[float] = []

        logger.info(f"ForwardTestEngine initialized for {symbol}")

    def feed_candle(self, candle: MarketCandle) -> None:
        """
        Process incoming market candle.

        Args:
            candle: New market candle
        """

        self.candle_queue.append(candle)

        # Update all active paper trades
        for trade_id, trade in self.paper_trades.items():
            if trade.status in ["PENDING", "FILLED"]:
                self._update_trade(trade, candle)

    def generate_signal_from_engines(
        self, signal_payload: Dict
    ) -> Optional[GeneratedSignal]:
        """
        Accept signal from strategy engines (AI + macro + structure).

        Args:
            signal_payload: Dictionary with signal data

        Returns:
            GeneratedSignal if accepted, None if rejected

        Validates:
        - Duplicate signals
        - Stale timestamps
        - Confidence thresholds
        """

        # Parse signal
        try:
            signal = GeneratedSignal(
                signal_id=signal_payload.get("signal_id", f"SIG_{self.signal_count}"),
                symbol=signal_payload.get("symbol", self.symbol),
                direction=TradeSignal[
                    signal_payload.get("direction", "NEUTRAL")
                ],
                confidence=signal_payload.get("confidence", 0.5),
                entry_price=signal_payload.get("entry_price", 0),
                stop_loss=signal_payload.get("stop_loss", 0),
                take_profit=signal_payload.get("take_profit", 0),
                risk_reward_ratio=signal_payload.get("risk_reward_ratio", 1.5),
                setup_type=signal_payload.get("setup_type", "unknown"),
                timestamp=datetime.now(),
                macro_regime=signal_payload.get("macro_regime", "UNKNOWN"),
                liquidity_score=signal_payload.get("liquidity_score", 0.5),
                structure_score=signal_payload.get("structure_score", 0.5),
                options_score=signal_payload.get("options_score", 0.5),
                confluence_score=signal_payload.get("confluence_score", 0.5),
            )
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid signal format: {e}")
            self.rejected_signals += 1
            return None

        # Validation checks
        if self._is_duplicate_signal(signal):
            logger.warning(
                f"Duplicate signal detected: {signal.signal_id}"
            )
            self.duplicate_signals += 1
            return None

        if self._is_stale_signal(signal):
            logger.warning(f"Stale signal rejected: {signal.signal_id}")
            self.stale_data_events += 1
            return None

        if signal.confidence < 0.4:  # Minimum confidence
            logger.debug(f"Low confidence signal rejected: {signal.confidence:.1%}")
            self.rejected_signals += 1
            return None

        # Accept signal
        self.signal_count += 1
        self.generated_signals.append(signal)
        self.last_signal_per_symbol[signal.symbol] = signal

        logger.info(
            f"Signal accepted: {signal.signal_id} | "
            f"Direction: {signal.direction.value} | "
            f"Confidence: {signal.confidence:.1%}"
        )

        return signal

    def execute_signal_as_paper_trade(
        self, signal: GeneratedSignal, simulated_entry_price: float,
        slippage_bps: float = 0.5
    ) -> Optional[PaperTrade]:
        """
        Convert accepted signal into paper trade.

        Args:
            signal: GeneratedSignal
            simulated_entry_price: Current market price (for execution)
            slippage_bps: Slippage in basis points (default 0.5 bps)

        Returns:
            PaperTrade if executed, None if rejected
        """

        # Calculate entry price with slippage
        if signal.direction == TradeSignal.LONG:
            actual_entry = simulated_entry_price * (1 + slippage_bps / 10000)
        else:
            actual_entry = simulated_entry_price * (1 - slippage_bps / 10000)

        slippage = abs(actual_entry - simulated_entry_price)

        # Create paper trade
        trade = PaperTrade(
            trade_id=f"PT_{signal.signal_id}",
            symbol=signal.symbol,
            direction=signal.direction,
            entry_signal_timestamp=signal.timestamp,
            entry_order_timestamp=datetime.now(),
            entry_price=simulated_entry_price,
            entry_actual_price=actual_entry,
            qty=1.0,  # Default to 1 unit
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            status="PENDING",
            slippage=slippage,
        )

        # Record
        self.paper_trades[trade.trade_id] = trade
        self.trade_count += 1

        # Calculate execution latency
        latency_ms = (
            trade.entry_order_timestamp - signal.timestamp
        ).total_seconds() * 1000
        trade.execution_latency_ms = latency_ms
        self.execution_latencies.append(latency_ms)

        logger.info(
            f"Paper trade created: {trade.trade_id} | "
            f"Entry: ${actual_entry:.2f} | "
            f"Slippage: {slippage:.4f} | "
            f"Latency: {latency_ms:.1f}ms"
        )

        return trade

    # ==================== PRIVATE HELPERS ====================

    def _is_duplicate_signal(self, signal: GeneratedSignal) -> bool:
        """Check if signal is duplicate of recent signal."""
        if signal.symbol not in self.last_signal_per_symbol:
            return False

        last = self.last_signal_per_symbol[signal.symbol]
        time_diff = (signal.timestamp - last.timestamp).total_seconds()

        # Same signal within 5 seconds = duplicate
        if (
            signal.signal_id == last.signal_id
            and time_diff < 5
        ):
            return True

        return False

    def _is_stale_signal(self, signal: GeneratedSignal) -> bool:
        """Check if signal timestamp is too old."""
        now = datetime.now()
        age_seconds = (now - signal.timestamp).total_seconds()

        # Signal older than 30 seconds = stale
        if age_seconds > 30:
            logger.warning(f"Signal age: {age_seconds:.1f}s (stale threshold: 30s)")
            return True

        return False

    def _update_trade(
        self, trade: PaperTrade, candle: MarketCandle
    ) -> None:
        """
        Update open trade with new candle data.

        Checks for TP/SL hits, marks filled, calculates PnL.

        Args:
            trade: PaperTrade to update
            candle: New market candle
        """

        # Mark as filled on first candle after entry
        if trade.status == "PENDING" and candle.timestamp > trade.entry_order_timestamp:
            trade.status = "FILLED"
            trade.filled_timestamp = candle.timestamp

        if trade.status != "FILLED":
            return

        # Check for TP/SL
        if trade.direction == TradeSignal.LONG:
            if candle.high >= trade.take_profit:
                self._close_trade(trade, trade.take_profit, "TP_HIT")
                return

            if candle.low <= trade.stop_loss:
                self._close_trade(trade, trade.stop_loss, "SL_HIT")
                return

            # Update current price
            trade.current_price = candle.close
        else:  # SHORT
            if candle.low <= trade.take_profit:
                self._close_trade(trade, trade.take_profit, "TP_HIT")
                return

            if candle.high >= trade.stop_loss:
                self._close_trade(trade, trade.stop_loss, "SL_HIT")
                return

            # Update current price
            trade.current_price = candle.close

    def _close_trade(
        self, trade: PaperTrade, exit_price: float, exit_reason: str
    ) -> None:
        """
        Close a trade and calculate PnL.

        Args:
            trade: Trade to close
            exit_price: Exit price
            exit_reason: Reason for closeout (TP_HIT, SL_HIT, etc)
        """

        trade.exit_price = exit_price
        trade.status = exit_reason
        trade.closed_timestamp = datetime.now()

        # Calculate PnL
        if trade.direction == TradeSignal.LONG:
            trade.pnl = (exit_price - trade.entry_actual_price) * trade.qty
        else:  # SHORT
            trade.pnl = (trade.entry_actual_price - exit_price) * trade.qty

        trade.pnl_pct = trade.pnl / (trade.entry_actual_price * trade.qty)

        # Move to history
        del self.paper_trades[trade.trade_id]
        self.trade_history.append(trade)

        logger.info(
            f"Trade closed: {trade.trade_id} | "
            f"Exit: {exit_reason} @ ${exit_price:.2f} | "
            f"P&L: ${trade.pnl:.2f} ({trade.pnl_pct:+.2%})"
        )

    def get_performance_summary(self) -> Dict:
        """Get current forward test performance summary."""
        all_trades = list(self.paper_trades.values()) + self.trade_history

        if not all_trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "avg_rr": 0,
                "total_pnl": 0,
            }

        wins = [t for t in all_trades if t.pnl > 0]
        losses = [t for t in all_trades if t.pnl < 0]
        closed_trades = [t for t in all_trades if t.status in ["TP_HIT", "SL_HIT"]]

        win_rate = len(wins) / len(closed_trades) if closed_trades else 0
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
        avg_rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        total_pnl = sum(t.pnl for t in closed_trades)
        avg_latency = sum(self.execution_latencies) / len(
            self.execution_latencies
        ) if self.execution_latencies else 0

        return {
            "total_signals": self.signal_count,
            "total_trades": self.trade_count,
            "closed_trades": len(closed_trades),
            "open_trades": len(self.paper_trades),
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "total_pnl": total_pnl,
            "avg_slippage": sum(
                t.slippage for t in closed_trades
            ) / len(closed_trades) if closed_trades else 0,
            "avg_execution_latency_ms": avg_latency,
            "duplicate_signals": self.duplicate_signals,
            "stale_data_events": self.stale_data_events,
        }
