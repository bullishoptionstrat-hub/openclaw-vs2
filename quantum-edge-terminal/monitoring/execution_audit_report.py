"""
EXECUTION AUDIT REPORT - DAILY DASHBOARD

Generates daily execution audit reports from ExecutionAuditLog data.

Responsibilities:
1. Query execution audit log for specified period
2. Calculate aggregate statistics
3. Identify anomalies and alerts
4. Generate formatted report
5. Export to JSON/CSV for analysis

Inputs: ExecutionAuditLog data
Outputs: ExecutionAuditReport (JSON-serializable dict)
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class ReportPeriod(Enum):
    """Report time periods."""

    LAST_HOUR = "last_hour"
    LAST_4_HOURS = "last_4_hours"
    LAST_TRADING_DAY = "last_trading_day"
    CUSTOM = "custom"


@dataclass
class ExecutionMetrics:
    """Aggregated execution metrics."""

    period_start: str  # ISO format
    period_end: str  # ISO format
    total_executions: int
    completed_executions: int
    rejected_executions: int
    partial_fills: int
    full_fills: int
    pending_executions: int

    # Fill metrics
    fill_rate_pct: float  # Completed / Total
    avg_fill_delay_ms: float
    min_fill_delay_ms: float
    max_fill_delay_ms: float
    median_fill_delay_ms: float

    # Slippage metrics
    avg_slippage_bps: float  # Basis points
    avg_slippage_pct: float
    min_slippage_pct: float
    max_slippage_pct: float
    median_slippage_pct: float
    positive_slippage_count: int  # Favorable fills
    negative_slippage_count: int  # Unfavorable fills

    # Execution timeline
    avg_submit_to_ack_ms: float
    avg_ack_to_first_fill_ms: float
    avg_first_to_last_fill_ms: float
    max_submit_to_ack_ms: float
    max_ack_to_first_fill_ms: float

    # Quality assessment
    excellent_fills: int
    good_fills: int
    acceptable_fills: int
    poor_fills: int
    bad_fills: int

    # Error tracking
    api_errors: int
    timeout_errors: int
    validation_errors: int
    other_errors: int


@dataclass
class ExecutionAlert:
    """Alert from execution analysis."""

    alert_id: str
    severity: str  # "info", "warning", "critical"
    alert_type: str  # slippage_spike, high_error_rate, timeout, etc.
    message: str
    metric_value: float
    threshold: float
    symbol: Optional[str] = None
    timestamp: str = None  # ISO format

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class ExecutionAuditReport:
    """
    Daily execution audit report generator.

    Analyzes ExecutionAuditLog data and produces comprehensive reports
    with metrics, alerts, and actionable insights.
    """

    def __init__(self):
        """Initialize report generator."""

        self.alerts: List[ExecutionAlert] = []
        self.metrics: Optional[ExecutionMetrics] = None
        self.symbol_breakdown: Dict[str, Dict] = {}
        self.hourly_breakdown: Dict[str, Dict] = {}

        # Alert thresholds
        self.slippage_alert_threshold_bps = 10  # 10 basis points
        self.high_error_rate_threshold = 0.05  # 5%
        self.fill_rate_warning_threshold = 0.90  # 90%
        self.fill_delay_warning_threshold_ms = 5000  # 5 seconds

        logger.info("ExecutionAuditReport initialized")

    def generate_report(
        self,
        audit_log,  # ExecutionAuditLog instance
        report_period: ReportPeriod = ReportPeriod.LAST_TRADING_DAY,
        custom_start: Optional[datetime] = None,
        custom_end: Optional[datetime] = None,
    ) -> Dict:
        """
        Generate comprehensive execution audit report.

        Args:
            audit_log: ExecutionAuditLog instance to analyze
            report_period: Time period for report
            custom_start: Start time for custom period
            custom_end: End time for custom period

        Returns:
            Complete report dict (JSON-serializable)
        """

        # Get time window
        start_time, end_time = self._get_time_window(report_period, custom_start, custom_end)

        logger.info(f"Generating audit report | Period: {start_time} to {end_time}")

        # Get all executions in window
        all_recent = audit_log.get_all_recent(limit=10000)
        executions_in_window = [
            e for e in all_recent
            if start_time <= datetime.fromisoformat(e.created_at) <= end_time
        ]

        if not executions_in_window:
            logger.warning(f"No executions found in period {start_time} to {end_time}")
            return self._empty_report(start_time, end_time)

        # Analyze executions
        self._analyze_executions(executions_in_window)

        # Generate report
        report = {
            "report_generated_at": datetime.utcnow().isoformat(),
            "report_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "period_type": report_period.value,
            },
            "metrics": asdict(self.metrics),
            "alerts": [a.to_dict() for a in self.alerts],
            "symbol_breakdown": self.symbol_breakdown,
            "hourly_breakdown": self.hourly_breakdown,
            "recommendations": self._generate_recommendations(),
            "health_status": self._assess_health_status(),
        }

        logger.info(
            f"✓ Report generated | Executions: {self.metrics.total_executions} | "
            f"Fill rate: {self.metrics.fill_rate_pct:.1%} | "
            f"Alerts: {len(self.alerts)}"
        )

        return report

    def _analyze_executions(self, executions: List[Dict]) -> None:
        """Analyze execution data and calculate metrics."""

        if not executions:
            return

        # Initialize collections
        fill_delays = []
        slippages_bps = []
        slippages_pct = []
        submit_to_ack_times = []
        ack_to_fill_times = []
        first_to_last_fill_times = []

        completed = 0
        rejected = 0
        partial = 0
        full = 0
        pending = 0

        quality_breakdown = {
            "EXCELLENT": 0,
            "GOOD": 0,
            "ACCEPTABLE": 0,
            "POOR": 0,
            "BAD": 0,
        }

        error_breakdown = {
            "api_errors": 0,
            "timeout_errors": 0,
            "validation_errors": 0,
            "other_errors": 0,
        }

        positive_slippage = 0
        negative_slippage = 0

        symbol_data = {}
        hourly_data = {}

        # Process each execution
        for exec_record in executions:
            # Status
            if exec_record.get("last_phase") == "FULLY_FILLED":
                completed += 1
                full += 1
            elif exec_record.get("last_phase") == "PARTIAL_FILL":
                completed += 1
                partial += 1
            elif exec_record.get("last_phase") == "REJECTED":
                rejected += 1
            else:
                pending += 1

            # Timing data
            if exec_record.get("total_delay_ms"):
                fill_delays.append(exec_record["total_delay_ms"])

            if exec_record.get("submit_to_ack_ms"):
                submit_to_ack_times.append(exec_record["submit_to_ack_ms"])

            if exec_record.get("ack_to_first_fill_ms"):
                ack_to_fill_times.append(exec_record["ack_to_first_fill_ms"])

            if exec_record.get("first_to_last_fill_ms"):
                first_to_last_fill_times.append(exec_record["first_to_last_fill_ms"])

            # Slippage
            if exec_record.get("slippage_bps") is not None:
                slippage_bps = exec_record["slippage_bps"]
                slippages_bps.append(slippage_bps)

                if exec_record.get("slippage_pct") is not None:
                    slippage_pct = exec_record["slippage_pct"]
                    slippages_pct.append(slippage_pct)

                    if slippage_pct > 0:
                        positive_slippage += 1
                    else:
                        negative_slippage += 1

            # Quality
            if exec_record.get("fill_quality"):
                quality = exec_record["fill_quality"]
                quality_breakdown[quality] = quality_breakdown.get(quality, 0) + 1

            # Symbol breakdown
            symbol = exec_record.get("symbol", "UNKNOWN")
            if symbol not in symbol_data:
                symbol_data[symbol] = {"count": 0, "fill_rate": 0, "avg_slippage": 0}
            symbol_data[symbol]["count"] += 1

            # Hourly breakdown
            created_at = datetime.fromisoformat(exec_record["created_at"])
            hour_key = created_at.strftime("%Y-%m-%d %H:00")
            if hour_key not in hourly_data:
                hourly_data[hour_key] = {"count": 0, "filled": 0}
            hourly_data[hour_key]["count"] += 1
            if completed:
                hourly_data[hour_key]["filled"] += 1

            # Error tracking
            if exec_record.get("rejection_reason"):
                reason = exec_record["rejection_reason"].lower()
                if "api" in reason or "connection" in reason:
                    error_breakdown["api_errors"] += 1
                elif "timeout" in reason:
                    error_breakdown["timeout_errors"] += 1
                elif "validation" in reason:
                    error_breakdown["validation_errors"] += 1
                else:
                    error_breakdown["other_errors"] += 1

        # Create metrics object
        start_time = datetime.fromisoformat(executions[0]["created_at"])
        end_time = datetime.fromisoformat(executions[-1]["created_at"])

        total = len(executions)
        fill_rate = completed / total if total > 0 else 0

        self.metrics = ExecutionMetrics(
            period_start=start_time.isoformat(),
            period_end=end_time.isoformat(),
            total_executions=total,
            completed_executions=completed,
            rejected_executions=rejected,
            partial_fills=partial,
            full_fills=full,
            pending_executions=pending,
            fill_rate_pct=fill_rate * 100,
            avg_fill_delay_ms=statistics.mean(fill_delays) if fill_delays else 0,
            min_fill_delay_ms=min(fill_delays) if fill_delays else 0,
            max_fill_delay_ms=max(fill_delays) if fill_delays else 0,
            median_fill_delay_ms=statistics.median(fill_delays) if fill_delays else 0,
            avg_slippage_bps=statistics.mean(slippages_bps) if slippages_bps else 0,
            avg_slippage_pct=statistics.mean(slippages_pct) if slippages_pct else 0,
            min_slippage_pct=min(slippages_pct) if slippages_pct else 0,
            max_slippage_pct=max(slippages_pct) if slippages_pct else 0,
            median_slippage_pct=statistics.median(slippages_pct) if slippages_pct else 0,
            positive_slippage_count=positive_slippage,
            negative_slippage_count=negative_slippage,
            avg_submit_to_ack_ms=statistics.mean(submit_to_ack_times) if submit_to_ack_times else 0,
            avg_ack_to_first_fill_ms=statistics.mean(ack_to_fill_times) if ack_to_fill_times else 0,
            avg_first_to_last_fill_ms=statistics.mean(first_to_last_fill_times) if first_to_last_fill_times else 0,
            max_submit_to_ack_ms=max(submit_to_ack_times) if submit_to_ack_times else 0,
            max_ack_to_first_fill_ms=max(ack_to_fill_times) if ack_to_fill_times else 0,
            excellent_fills=quality_breakdown["EXCELLENT"],
            good_fills=quality_breakdown["GOOD"],
            acceptable_fills=quality_breakdown["ACCEPTABLE"],
            poor_fills=quality_breakdown["POOR"],
            bad_fills=quality_breakdown["BAD"],
            api_errors=error_breakdown["api_errors"],
            timeout_errors=error_breakdown["timeout_errors"],
            validation_errors=error_breakdown["validation_errors"],
            other_errors=error_breakdown["other_errors"],
        )

        # Store breakdowns
        self.symbol_breakdown = symbol_data
        self.hourly_breakdown = hourly_data

        # Generate alerts
        self._check_alerts()

    def _check_alerts(self) -> None:
        """Check for alert conditions."""

        self.alerts = []

        if not self.metrics:
            return

        # Alert 1: Slippage spike
        if self.metrics.avg_slippage_bps > self.slippage_alert_threshold_bps:
            self.alerts.append(
                ExecutionAlert(
                    alert_id=f"slippage_spike_{datetime.utcnow().timestamp()}",
                    severity="warning",
                    alert_type="slippage_spike",
                    message=f"Average slippage {self.metrics.avg_slippage_bps:.1f}bps exceeds threshold {self.slippage_alert_threshold_bps}bps",
                    metric_value=self.metrics.avg_slippage_bps,
                    threshold=self.slippage_alert_threshold_bps,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )

        # Alert 2: High error rate
        total_errors = (
            self.metrics.api_errors
            + self.metrics.timeout_errors
            + self.metrics.validation_errors
            + self.metrics.other_errors
        )
        error_rate = total_errors / self.metrics.total_executions if self.metrics.total_executions > 0 else 0

        if error_rate > self.high_error_rate_threshold:
            self.alerts.append(
                ExecutionAlert(
                    alert_id=f"high_error_rate_{datetime.utcnow().timestamp()}",
                    severity="critical",
                    alert_type="high_error_rate",
                    message=f"Error rate {error_rate:.1%} exceeds threshold {self.high_error_rate_threshold:.1%}",
                    metric_value=error_rate * 100,
                    threshold=self.high_error_rate_threshold * 100,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )

        # Alert 3: Low fill rate
        if self.metrics.fill_rate_pct < self.fill_rate_warning_threshold * 100:
            self.alerts.append(
                ExecutionAlert(
                    alert_id=f"low_fill_rate_{datetime.utcnow().timestamp()}",
                    severity="warning",
                    alert_type="low_fill_rate",
                    message=f"Fill rate {self.metrics.fill_rate_pct:.1f}% below threshold {self.fill_rate_warning_threshold * 100:.1f}%",
                    metric_value=self.metrics.fill_rate_pct,
                    threshold=self.fill_rate_warning_threshold * 100,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )

        # Alert 4: High fill delays
        if self.metrics.avg_fill_delay_ms > self.fill_delay_warning_threshold_ms:
            self.alerts.append(
                ExecutionAlert(
                    alert_id=f"high_fill_delay_{datetime.utcnow().timestamp()}",
                    severity="warning",
                    alert_type="high_fill_delay",
                    message=f"Average fill delay {self.metrics.avg_fill_delay_ms:.0f}ms exceeds threshold {self.fill_delay_warning_threshold_ms}ms",
                    metric_value=self.metrics.avg_fill_delay_ms,
                    threshold=self.fill_delay_warning_threshold_ms,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )

        logger.info(f"Alert check complete | Alerts generated: {len(self.alerts)}")

    def _assess_health_status(self) -> Dict:
        """Assess overall execution health."""

        if not self.metrics:
            return {"status": "UNKNOWN", "score": 0}

        score = 100

        # Deductions
        if self.metrics.fill_rate_pct < 95:
            score -= 15
        if self.metrics.avg_slippage_bps > self.slippage_alert_threshold_bps:
            score -= 20
        if self.metrics.avg_fill_delay_ms > self.fill_delay_warning_threshold_ms:
            score -= 10
        if self.metrics.bad_fills > 0:
            score -= 5 * self.metrics.bad_fills

        # Classification
        if score >= 90:
            status = "EXCELLENT"
        elif score >= 75:
            status = "GOOD"
        elif score >= 60:
            status = "ACCEPTABLE"
        elif score >= 40:
            status = "POOR"
        else:
            status = "BAD"

        return {
            "status": status,
            "score": max(0, score),
            "max_score": 100,
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations."""

        recommendations = []

        if not self.metrics:
            return recommendations

        if self.metrics.fill_rate_pct < 90:
            recommendations.append(
                "Fill rate below 90%: Review broker API health and connection stability"
            )

        if self.metrics.avg_slippage_bps > 15:
            recommendations.append(
                "High slippage: Consider using limit orders or trading instruments with lower volatility"
            )

        if self.metrics.avg_fill_delay_ms > 3000:
            recommendations.append(
                "High fill delays: Check network latency and consider using market orders for faster execution"
            )

        if self.metrics.bad_fills > 5:
            recommendations.append(
                "Multiple bad fills detected: Calibrate kill switch thresholds or increase position sizing caution"
            )

        if self.metrics.api_errors > 5:
            recommendations.append(
                "API errors detected: Review broker API rate limits and error handling"
            )

        if not recommendations:
            recommendations.append("Execution health is good. No major issues detected.")

        return recommendations

    def _get_time_window(
        self,
        period: ReportPeriod,
        custom_start: Optional[datetime],
        custom_end: Optional[datetime],
    ) -> Tuple[datetime, datetime]:
        """Get time window for report."""

        end_time = datetime.utcnow()

        if period == ReportPeriod.LAST_HOUR:
            start_time = end_time - timedelta(hours=1)
        elif period == ReportPeriod.LAST_4_HOURS:
            start_time = end_time - timedelta(hours=4)
        elif period == ReportPeriod.LAST_TRADING_DAY:
            start_time = end_time - timedelta(days=1)
        elif period == ReportPeriod.CUSTOM:
            start_time = custom_start or end_time - timedelta(days=1)
            end_time = custom_end or end_time
        else:
            start_time = end_time - timedelta(days=1)

        return start_time, end_time

    def _empty_report(self, start_time: datetime, end_time: datetime) -> Dict:
        """Generate empty report for no data."""

        return {
            "report_generated_at": datetime.utcnow().isoformat(),
            "report_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "period_type": "custom",
            },
            "metrics": None,
            "alerts": [],
            "symbol_breakdown": {},
            "hourly_breakdown": {},
            "recommendations": ["No executions found in period"],
            "health_status": {"status": "UNKNOWN", "score": 0},
        }
