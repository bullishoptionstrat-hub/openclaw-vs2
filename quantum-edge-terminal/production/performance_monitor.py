"""
PERFORMANCE MONITOR - REAL-TIME TRACKING & ALERTING

Monitors live trading performance, compares vs validation baseline,
and sends alerts for anomalies.

Features:
- Real-time metrics collection
- Comparison with validation period
- Performance degradation detection
- Alert generation + routing
- Daily report generation
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of performance alerts."""

    DRAWDOWN_WARNING = "drawdown_warning"
    DAILY_LOSS = "daily_loss"
    WIN_RATE_DROP = "win_rate_drop"
    SLIPPAGE_INCREASE = "slippage_increase"
    EXECUTION_QUALITY_DROP = "execution_quality_drop"
    REGIME_CHANGE = "regime_change"
    SIGNAL_DROUGHT = "signal_drought"
    PERFORMANCE_REGRESSION = "performance_regression"


@dataclass
class PerformanceAlert:
    """Single performance alert."""

    alert_type: AlertType
    level: AlertLevel
    title: str
    message: str
    metric_name: str
    current_value: float
    baseline_value: float
    threshold: float
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "type": self.alert_type.value,
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "metric": self.metric_name,
            "current": self.current_value,
            "baseline": self.baseline_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
        }


@dataclass
class PerformanceSnapshot:
    """Snapshot of current performance metrics."""

    timestamp: str
    equity: float
    daily_pnl: float
    cumulative_pnl: float
    drawdown_pct: float
    win_rate: float
    trades_today: int
    signals_today: int
    avg_slippage: float
    execution_quality: float
    regime: str


class PerformanceMonitor:
    """
    Real-time performance monitoring and alerting.

    Tracks:
    - Current metrics vs baseline
    - Performance degradation
    - Anomalies + alerts
    - Daily reports
    """

    def __init__(self):
        """Initialize performance monitor."""

        # Baseline (from validation period)
        self.validation_baseline: Optional[Dict] = None

        # Current performance
        self.live_snapshots: List[PerformanceSnapshot] = []
        self.current_snapshot: Optional[PerformanceSnapshot] = None

        # Alerts
        self.alerts: List[PerformanceAlert] = []
        self.critical_alerts: List[PerformanceAlert] = []

        # Thresholds for alerts
        self.drawdown_warn_threshold = 1.5  # 1.5x baseline drawdown
        self.win_rate_drop_threshold = 0.10  # 10% drop
        self.slippage_increase_threshold = 1.5  # 1.5x baseline
        self.signal_drought_threshold = 30  # Min 30 min without signal

        logger.info("PerformanceMonitor initialized")

    def set_validation_baseline(self, baseline: Dict) -> None:
        """
        Set validation period baseline for comparison.

        Args:
            baseline: Baseline metrics from validation period
        """

        self.validation_baseline = baseline
        logger.info(f"Validation baseline set | Win rate: {baseline.get('win_rate', 0):.1%}")

    def record_snapshot(
        self,
        equity: float,
        daily_pnl: float,
        cumulative_pnl: float,
        win_rate: float,
        trades_today: int,
        signals_today: int,
        avg_slippage: float,
        execution_quality: float,
        regime: str,
    ) -> None:
        """
        Record performance snapshot.

        Args:
            equity: Current account equity
            daily_pnl: Today's profit/loss
            cumulative_pnl: Cumulative P&L since deployment
            win_rate: Current win rate
            trades_today: Trades executed today
            signals_today: Signals generated today
            avg_slippage: Average slippage on fills
            execution_quality: Execution quality score (0-1)
            regime: Current market regime
        """

        baseline_equity = self.validation_baseline.get("equity", 100000.0) if self.validation_baseline else 100000.0
        drawdown = (baseline_equity - equity) / baseline_equity

        snapshot = PerformanceSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            equity=equity,
            daily_pnl=daily_pnl,
            cumulative_pnl=cumulative_pnl,
            drawdown_pct=drawdown,
            win_rate=win_rate,
            trades_today=trades_today,
            signals_today=signals_today,
            avg_slippage=avg_slippage,
            execution_quality=execution_quality,
            regime=regime,
        )

        self.live_snapshots.append(snapshot)
        self.current_snapshot = snapshot

        # Check for alerts
        self._check_performance_metrics(snapshot)

    def _check_performance_metrics(self, snapshot: PerformanceSnapshot) -> None:
        """Check for performance issues and generate alerts."""

        if not self.validation_baseline:
            return

        baseline_win_rate = self.validation_baseline.get("win_rate", 0.55)
        baseline_drawdown = self.validation_baseline.get("max_drawdown", 0.08)
        baseline_slippage = self.validation_baseline.get("avg_slippage", 0.001)

        # Alert 1: Drawdown warning
        if snapshot.drawdown_pct > baseline_drawdown * self.drawdown_warn_threshold:
            alert = PerformanceAlert(
                alert_type=AlertType.DRAWDOWN_WARNING,
                level=AlertLevel.WARNING,
                title="Drawdown increasing",
                message=f"Current drawdown {snapshot.drawdown_pct:.1%} exceeds baseline × {self.drawdown_warn_threshold}",
                metric_name="drawdown",
                current_value=snapshot.drawdown_pct,
                baseline_value=baseline_drawdown,
                threshold=baseline_drawdown * self.drawdown_warn_threshold,
            )
            self.alerts.append(alert)
            logger.warning(f"⚠️  {alert.title}: {alert.message}")

        # Alert 2: Win rate degradation
        if snapshot.win_rate < baseline_win_rate - self.win_rate_drop_threshold:
            alert = PerformanceAlert(
                alert_type=AlertType.WIN_RATE_DROP,
                level=AlertLevel.WARNING,
                title="Win rate declining",
                message=f"Win rate {snapshot.win_rate:.1%} below baseline {baseline_win_rate:.1%}",
                metric_name="win_rate",
                current_value=snapshot.win_rate,
                baseline_value=baseline_win_rate,
                threshold=baseline_win_rate - self.win_rate_drop_threshold,
            )
            self.alerts.append(alert)
            logger.warning(f"⚠️  {alert.title}: {alert.message}")

        # Alert 3: Slippage increase
        if snapshot.avg_slippage > baseline_slippage * self.slippage_increase_threshold:
            alert = PerformanceAlert(
                alert_type=AlertType.SLIPPAGE_INCREASE,
                level=AlertLevel.WARNING,
                title="Slippage increasing",
                message=f"Avg slippage {snapshot.avg_slippage:.4f} exceeds baseline × {self.slippage_increase_threshold}",
                metric_name="slippage",
                current_value=snapshot.avg_slippage,
                baseline_value=baseline_slippage,
                threshold=baseline_slippage * self.slippage_increase_threshold,
            )
            self.alerts.append(alert)
            logger.warning(f"⚠️  {alert.title}: {alert.message}")

        # Alert 4: Execution quality drop
        if snapshot.execution_quality < 0.65:
            alert = PerformanceAlert(
                alert_type=AlertType.EXECUTION_QUALITY_DROP,
                level=AlertLevel.WARNING,
                title="Execution quality poor",
                message=f"Execution quality {snapshot.execution_quality:.1%} below threshold",
                metric_name="execution_quality",
                current_value=snapshot.execution_quality,
                baseline_value=0.70,
                threshold=0.65,
            )
            self.alerts.append(alert)
            logger.warning(f"⚠️  {alert.title}: {alert.message}")

        # Alert 5: Signal drought
        if snapshot.signals_today == 0 and len(self.live_snapshots) > self.signal_drought_threshold:
            alert = PerformanceAlert(
                alert_type=AlertType.SIGNAL_DROUGHT,
                level=AlertLevel.INFO,
                title="No signals today",
                message="No trading signals generated in last hour",
                metric_name="signal_count",
                current_value=0,
                baseline_value=1,
                threshold=0,
            )
            self.alerts.append(alert)
            logger.info(f"ℹ️  {alert.title}: {alert.message}")

    def get_daily_report(self) -> Dict:
        """Generate daily performance report."""

        if not self.current_snapshot:
            return {"status": "no_data"}

        snapshot = self.current_snapshot
        alerts_today = [a for a in self.alerts if a.timestamp.startswith(datetime.utcnow().strftime("%Y-%m-%d"))]
        critical_count = sum(1 for a in alerts_today if a.level == AlertLevel.CRITICAL)
        warning_count = sum(1 for a in alerts_today if a.level == AlertLevel.WARNING)

        return {
            "timestamp": snapshot.timestamp,
            "equity": snapshot.equity,
            "daily_pnl": snapshot.daily_pnl,
            "cumulative_pnl": snapshot.cumulative_pnl,
            "drawdown": snapshot.drawdown_pct,
            "win_rate": snapshot.win_rate,
            "trades_today": snapshot.trades_today,
            "signals_today": snapshot.signals_today,
            "avg_slippage": snapshot.avg_slippage,
            "execution_quality": snapshot.execution_quality,
            "regime": snapshot.regime,
            "alerts": {
                "critical": critical_count,
                "warnings": warning_count,
                "details": [a.to_dict() for a in alerts_today],
            },
            "status": "⚠️ WARNINGS" if warning_count > 0 else "✅ NORMAL",
        }

    def get_performance_summary(self) -> Dict:
        """Get summary of live performance vs baseline."""

        if not self.live_snapshots or not self.validation_baseline:
            return {"status": "insufficient_data"}

        # Calculate live period stats
        live_pnls = [s.daily_pnl for s in self.live_snapshots]
        live_win_rates = [s.win_rate for s in self.live_snapshots]
        max_drawdown = max((s.drawdown_pct for s in self.live_snapshots), default=0.0)

        baseline = self.validation_baseline
        live_avg_win_rate = sum(live_win_rates) / len(live_win_rates) if live_win_rates else 0.0
        cumulative_pnl = sum(live_pnls)

        return {
            "period_days": len(self.live_snapshots),
            "cumulative_pnl": cumulative_pnl,
            "total_trades": sum(s.trades_today for s in self.live_snapshots),
            "live_win_rate": live_avg_win_rate,
            "baseline_win_rate": baseline.get("win_rate", 0.0),
            "win_rate_change": live_avg_win_rate - baseline.get("win_rate", 0.0),
            "max_drawdown": max_drawdown,
            "baseline_drawdown": baseline.get("max_drawdown", 0.0),
            "vs_baseline": (
                "✅ OUTPERFORMING" if cumulative_pnl > 0 else "⚠️  UNDERPERFORMING"
            ),
            "alert_count": len(self.alerts),
            "critical_alerts": len(self.critical_alerts),
        }
