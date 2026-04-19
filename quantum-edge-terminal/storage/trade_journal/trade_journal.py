"""
TRADE JOURNAL - COMPLETE TRADE LIFECYCLE TRACKING

Tracks every trade from creation through closure.

Metrics tracked:
- Trade entry/exit (actual vs planned)
- Outcome (win/loss, TP/SL hit)
- Risk/reward realized vs expected
- Regime at time of trade
- Confluence score
- Performance by setup type, asset, regime

This is the FEEDBACK LOOP that makes the system improve over time.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class TradeOutcome(Enum):
    """Trade outcome classification."""

    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    CLOSED_EARLY = "closed_early"
    CANCELLED = "cancelled"
    PENDING = "pending"


@dataclass
class JournalEntry:
    """Single trade journal entry."""

    trade_id: str
    asset: str
    direction: str  # LONG or SHORT
    created_at: str

    # Entry (planned)
    entry_price_planned: float
    stop_loss_planned: float
    take_profit_planned: List[float]
    position_size_planned: float
    risk_planned: float
    reward_planned: float
    rr_planned: float

    # Entry (actual)
    entry_price_actual: Optional[float] = None
    entry_timestamp: Optional[str] = None
    entry_slippage: float = 0.0  # Actual vs planned

    # Exit (actual)
    exit_price_actual: Optional[float] = None
    exit_timestamp: Optional[str] = None
    exit_type: Optional[str] = None  # "tp", "sl", "manual", "timeout"
    position_size_actual: Optional[float] = None

    # Outcome
    outcome: TradeOutcome = TradeOutcome.PENDING
    pnl: float = 0.0  # Profit/loss in dollars
    pnl_pct: float = 0.0  # Profit/loss %
    rr_realized: float = 0.0  # Actual risk/reward ratio

    # Context
    signal_confidence: float = 0.0
    signal_type: str = ""
    macro_regime: str = ""
    macro_score: float = 0.0
    confluence_score: Optional[float] = None
    notes: Optional[str] = None

    # Timestamps
    closed_at: Optional[str] = None
    duration_minutes: Optional[float] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return d

    def calculate_duration(self):
        """Calculate trade duration in minutes."""
        if self.entry_timestamp and self.closed_at:
            entry_dt = datetime.fromisoformat(self.entry_timestamp)
            close_dt = datetime.fromisoformat(self.closed_at)
            self.duration_minutes = (close_dt - entry_dt).total_seconds() / 60


@dataclass
class PerformanceSnapshot:
    """Daily/weekly performance metrics."""

    period: str  # "daily", "weekly", "all"
    period_start: str
    period_end: str

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    win_rate: float = 0.0  # %
    average_win: float = 0.0  # $
    average_loss: float = 0.0  # $
    average_rr: float = 0.0  # Risk/reward ratio

    gross_pnl: float = 0.0  # Total PnL
    net_pnl: float = 0.0  # After commissions

    max_profit: float = 0.0
    max_loss: float = 0.0
    max_drawdown: float = 0.0

    expectancy: float = 0.0  # (win_rate × avg_win) - (loss_rate × avg_loss)

    performance_by_regime: Dict[str, Dict] = field(default_factory=dict)
    performance_by_signal_type: Dict[str, Dict] = field(default_factory=dict)
    performance_by_asset: Dict[str, Dict] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class TradeJournal:
    """
    Complete trade tracking and performance analytics.

    Stores all trades and generates performance reports.
    """

    def __init__(self):
        """Initialize journal."""
        self.entries: Dict[str, JournalEntry] = {}  # trade_id -> JournalEntry
        self.entry_order: List[str] = []  # Chronological order

    def create_entry(self, execution_payload: Dict) -> JournalEntry:
        """Create journal entry from execution payload."""
        trade_id = execution_payload.get("trade_id")

        tp_targets = execution_payload.get("take_profit_targets", [])
        planned_reward = abs(tp_targets[0] - execution_payload.get("entry")) if tp_targets else 0
        planned_risk = abs(execution_payload.get("entry") - execution_payload.get("stop_loss"))

        entry = JournalEntry(
            trade_id=trade_id,
            asset=execution_payload.get("asset"),
            direction=execution_payload.get("direction"),
            created_at=execution_payload.get("timestamp"),
            entry_price_planned=execution_payload.get("entry"),
            stop_loss_planned=execution_payload.get("stop_loss"),
            take_profit_planned=tp_targets,
            position_size_planned=execution_payload.get("position_size"),
            risk_planned=planned_risk,
            reward_planned=planned_reward,
            rr_planned=execution_payload.get("risk_reward_ratio", 0),
            signal_confidence=execution_payload.get("signal_confidence"),
            signal_type=execution_payload.get("signal_type"),
            macro_regime=execution_payload.get("macro_regime"),
            macro_score=execution_payload.get("macro_score"),
            confluence_score=execution_payload.get("confluence_score"),
        )

        self.entries[trade_id] = entry
        self.entry_order.append(trade_id)

        logger.info(f"Created journal entry: {trade_id}")

        return entry

    def mark_entry_filled(self, trade_id: str, fill_price: float, slippage: Optional[float] = None):
        """Mark trade as filled at entry."""
        if trade_id not in self.entries:
            return

        entry = self.entries[trade_id]
        entry.entry_price_actual = fill_price
        entry.entry_timestamp = datetime.utcnow().isoformat()

        if slippage is None:
            slippage = abs(fill_price - entry.entry_price_planned)
        entry.entry_slippage = slippage

        logger.info(f"Trade filled: {trade_id} @ {fill_price:.2f} (slippage: {slippage:.2f})")

    def mark_tp_hit(self, trade_id: str, tp_price: float, tp_level: int = 1):
        """Mark take profit hit."""
        if trade_id not in self.entries:
            return

        entry = self.entries[trade_id]
        entry.exit_price_actual = tp_price
        entry.exit_timestamp = datetime.utcnow().isoformat()
        entry.exit_type = f"tp_level_{tp_level}"
        entry.outcome = TradeOutcome.WIN
        entry.closed_at = datetime.utcnow().isoformat()

        self._calculate_pnl(trade_id)
        logger.info(f"TP hit: {trade_id} @ {tp_price:.2f}")

    def mark_sl_hit(self, trade_id: str, sl_price: float):
        """Mark stop loss hit."""
        if trade_id not in self.entries:
            return

        entry = self.entries[trade_id]
        entry.exit_price_actual = sl_price
        entry.exit_timestamp = datetime.utcnow().isoformat()
        entry.exit_type = "stop_loss"
        entry.outcome = TradeOutcome.LOSS
        entry.closed_at = datetime.utcnow().isoformat()

        self._calculate_pnl(trade_id)
        logger.info(f"SL hit: {trade_id} @ {sl_price:.2f}")

    def close_trade_manual(self, trade_id: str, exit_price: float, notes: str = ""):
        """Close trade manually before TP/SL."""
        if trade_id not in self.entries:
            return

        entry = self.entries[trade_id]
        entry.exit_price_actual = exit_price
        entry.exit_timestamp = datetime.utcnow().isoformat()
        entry.exit_type = "manual"
        entry.closed_at = datetime.utcnow().isoformat()
        entry.notes = notes

        self._calculate_pnl(trade_id)

        # Determine outcome
        if entry.direction == "LONG":
            if exit_price > entry.entry_price_planned:
                entry.outcome = TradeOutcome.WIN
            elif exit_price < entry.entry_price_planned:
                entry.outcome = TradeOutcome.LOSS
            else:
                entry.outcome = TradeOutcome.BREAKEVEN
        else:  # SHORT
            if exit_price < entry.entry_price_planned:
                entry.outcome = TradeOutcome.WIN
            elif exit_price > entry.entry_price_planned:
                entry.outcome = TradeOutcome.LOSS
            else:
                entry.outcome = TradeOutcome.BREAKEVEN

        logger.info(f"Trade closed manually: {trade_id} @ {exit_price:.2f}")

    def _calculate_pnl(self, trade_id: str):
        """Calculate PnL for a trade."""
        if trade_id not in self.entries:
            return

        entry = self.entries[trade_id]

        if entry.entry_price_actual is None or entry.exit_price_actual is None:
            return

        if entry.direction == "LONG":
            price_diff = entry.exit_price_actual - entry.entry_price_actual
        else:  # SHORT
            price_diff = entry.entry_price_actual - entry.exit_price_actual

        position_size = entry.position_size_actual or entry.position_size_planned
        entry.pnl = price_diff * position_size
        entry.pnl_pct = (price_diff / entry.entry_price_actual) * 100

        # Calculate realized risk/reward
        if entry.exit_type and "tp" in entry.exit_type:
            reward_realized = entry.reward_planned
        else:
            reward_realized = abs(entry.exit_price_actual - entry.entry_price_planned)

        entry.rr_realized = reward_realized / entry.risk_planned if entry.risk_planned > 0 else 0

        entry.calculate_duration()

    def get_entry(self, trade_id: str) -> Optional[JournalEntry]:
        """Get journal entry by trade ID."""
        return self.entries.get(trade_id)

    def get_daily_performance(self, date: Optional[str] = None) -> PerformanceSnapshot:
        """Calculate daily performance metrics."""
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")

        trades_on_date = [
            self.entries[tid]
            for tid in self.entry_order
            if self.entries[tid].closure_date == date
            and self.entries[tid].outcome != TradeOutcome.PENDING
        ]

        return self._calculate_performance_snapshot("daily", trades_on_date, date, date)

    def get_performance_summary(self, days: int = 30) -> PerformanceSnapshot:
        """Calculate performance over N days."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        trades_in_period = [
            self.entries[tid]
            for tid in self.entry_order
            if self.entries[tid].closed_at
            and start_date.isoformat() <= self.entries[tid].closed_at <= end_date.isoformat()
            and self.entries[tid].outcome != TradeOutcome.PENDING
        ]

        return self._calculate_performance_snapshot(
            f"last_{days}_days",
            trades_in_period,
            start_date.isoformat(),
            end_date.isoformat(),
        )

    def _calculate_performance_snapshot(
        self,
        period: str,
        trades: List[JournalEntry],
        period_start: str,
        period_end: str,
    ) -> PerformanceSnapshot:
        """Calculate performance metrics for a set of trades."""

        snapshot = PerformanceSnapshot(
            period=period,
            period_start=period_start,
            period_end=period_end,
            total_trades=len(trades),
        )

        if not trades:
            return snapshot

        # Outcome counts
        wins = [t for t in trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in trades if t.outcome == TradeOutcome.LOSS]
        breakevens = [t for t in trades if t.outcome == TradeOutcome.BREAKEVEN]

        snapshot.winning_trades = len(wins)
        snapshot.losing_trades = len(losses)
        snapshot.breakeven_trades = len(breakevens)

        # Win rate
        if snapshot.total_trades > 0:
            snapshot.win_rate = (snapshot.winning_trades / snapshot.total_trades) * 100

        # Average win/loss
        if wins:
            snapshot.average_win = sum(t.pnl for t in wins) / len(wins)
            snapshot.max_profit = max(t.pnl for t in wins)
        if losses:
            snapshot.average_loss = sum(t.pnl for t in losses) / len(losses)
            snapshot.max_loss = min(t.pnl for t in losses)

        # Average R/R
        if trades:
            snapshot.average_rr = sum(t.rr_realized for t in trades) / len(trades)

        # Total PnL
        snapshot.gross_pnl = sum(t.pnl for t in trades)
        snapshot.net_pnl = snapshot.gross_pnl  # TODO: subtract commissions

        # Expectancy (overly simplified)
        if snapshot.total_trades > 0:
            win_rate = snapshot.win_rate / 100
            loss_rate = 1 - win_rate
            avg_win = snapshot.average_win if snapshot.average_win > 0 else 0
            avg_loss = abs(snapshot.average_loss) if snapshot.average_loss < 0 else 0
            snapshot.expectancy = win_rate * avg_win - loss_rate * avg_loss

        # Performance by regime
        snapshot.performance_by_regime = self._performance_by_category(trades, "macro_regime")

        # Performance by signal type
        snapshot.performance_by_signal_type = self._performance_by_category(trades, "signal_type")

        # Performance by asset
        snapshot.performance_by_asset = self._performance_by_category(trades, "asset")

        return snapshot

    def _performance_by_category(
        self, trades: List[JournalEntry], category_key: str
    ) -> Dict[str, Dict]:
        """Calculate performance grouped by category."""
        by_category = {}

        for trade in trades:
            cat = getattr(trade, category_key, "unknown")
            if cat not in by_category:
                by_category[cat] = {"trades": [], "wins": 0, "losses": 0, "pnl": 0}

            by_category[cat]["trades"].append(trade)
            by_category[cat]["pnl"] += trade.pnl
            if trade.outcome == TradeOutcome.WIN:
                by_category[cat]["wins"] += 1
            elif trade.outcome == TradeOutcome.LOSS:
                by_category[cat]["losses"] += 1

        # Add calculated fields
        for cat, stats in by_category.items():
            count = len(stats["trades"])
            stats["win_rate"] = (stats["wins"] / count * 100) if count > 0 else 0
            stats["avg_pnl"] = stats["pnl"] / count if count > 0 else 0

        return by_category

    def get_all_entries(self, filter_status: Optional[str] = None) -> List[Dict]:
        """Get all journal entries (optionally filtered)."""
        entries = [self.entries[tid].to_dict() for tid in self.entry_order]

        if filter_status:
            entries = [e for e in entries if e["outcome"] == filter_status]

        return entries

    @property
    def closure_date(self) -> str:
        """Get closure date from closed_at timestamp."""
        if self.closed_at:
            return datetime.fromisoformat(self.closed_at).strftime("%Y-%m-%d")
        return ""
