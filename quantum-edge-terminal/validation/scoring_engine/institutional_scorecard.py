"""
INSTITUTIONAL-GRADE VALIDATION SCORECARD

This is the gate between "interesting system" and "trusted system."

Scoring framework used by institutional traders to evaluate:
- Returns quality
- Risk control
- Execution quality
- Stability across conditions

Based on SEC execution disclosure framework + prop desk validation standards.
"""

from typing import Dict, Tuple, List
from dataclasses import dataclass, field
from enum import Enum


class GateStatus(Enum):
    """Validation gate status."""

    PASS = "PASS"  # Ready for capital deployment
    WATCH = "WATCH"  # Edge may be real, needs more data
    FAIL = "FAIL"  # System not ready


@dataclass
class MetricResult:
    """Result for a single metric."""

    value: float
    raw_score: float  # 0-1
    weight: int
    weighted_score: float
    status: str  # PASS, WATCH, FAIL


@dataclass
class SectionResult:
    """Result for a scorecard section."""

    section_score: float
    metrics: Dict[str, MetricResult] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Complete validation scorecard result."""

    overall_score: float  # 0-1
    gate_status: GateStatus
    breakdown: Dict[str, SectionResult] = field(default_factory=dict)
    hard_fail_reasons: List[str] = field(default_factory=list)
    timestamp: str = ""


class InstitutionalScorecard:
    """
    Institutional-grade validation scorecard.

    Maximum drawdown is a core downside metric.
    Sharpe remains a standard risk-adjusted gauge.
    """

    def __init__(self):
        """Initialize the scorecard with institutional-grade thresholds."""

        self.scorecard = {
            "returns_quality": {
                "expectancy": {
                    "weight": 20,
                    "pass": 0.15,
                    "watch": 0.05,
                    "direction": "higher",
                },
                "profit_factor": {
                    "weight": 15,
                    "pass": 1.35,
                    "watch": 1.15,
                    "direction": "higher",
                },
                "sharpe_ratio": {
                    "weight": 15,
                    "pass": 1.25,
                    "watch": 0.85,
                    "direction": "higher",
                },
                "avg_rr": {
                    "weight": 10,
                    "pass": 1.60,
                    "watch": 1.20,
                    "direction": "higher",
                },
            },
            "risk_control": {
                "max_drawdown": {
                    "weight": 15,
                    "pass": 0.08,
                    "watch": 0.10,
                    "direction": "lower",
                },
                "consecutive_losses": {
                    "weight": 5,
                    "pass": 4,
                    "watch": 6,
                    "direction": "lower",
                },
                "daily_loss_breach": {
                    "weight": 5,
                    "pass": 0,
                    "watch": 1,
                    "direction": "lower",
                },
            },
            "execution_quality": {
                "slippage_drift": {
                    "weight": 5,
                    "pass": 0.15,
                    "watch": 0.30,
                    "direction": "lower",
                },
                "missed_trade_rate": {
                    "weight": 3,
                    "pass": 0.01,
                    "watch": 0.03,
                    "direction": "lower",
                },
                "duplicate_signal_rate": {
                    "weight": 1,
                    "pass": 0.0,
                    "watch": 0.005,
                    "direction": "lower",
                },
                "stale_data_events": {
                    "weight": 1,
                    "pass": 0,
                    "watch": 1,
                    "direction": "lower",
                },
            },
            "stability": {
                "regime_consistency": {
                    "weight": 3,
                    "pass": 0.70,
                    "watch": 0.55,
                    "direction": "higher",
                },
                "session_consistency": {
                    "weight": 1,
                    "pass": 0.65,
                    "watch": 0.50,
                    "direction": "higher",
                },
                "strategy_dispersion": {
                    "weight": 1,
                    "pass": 0.25,
                    "watch": 0.40,
                    "direction": "lower",
                },
            },
        }

        # Hard fail conditions (overrides scoring)
        self.hard_fail_conditions = [
            "max_drawdown > 0.10",
            "daily_loss_breach > 1",
            "stale_data_events > 1",
            "duplicate_signal_rate > 0.005",
            "expectancy <= 0",
        ]

        # Pass/Watch/Fail thresholds
        self.gate_thresholds = {
            "pass": 0.80,  # Overall score >= 80%
            "watch": 0.65,  # Overall score >= 65%
        }

    def score_metric(
        self, value: float, rule: Dict
    ) -> Tuple[float, str]:
        """
        Score a single metric against pass/watch/fail thresholds.

        Args:
            value: Metric value
            rule: Rule dict with pass/watch thresholds and direction

        Returns:
            (raw_score, status) - raw_score is 0-1, status is PASS/WATCH/FAIL
        """

        direction = rule.get("direction", "higher")
        lower_better = direction == "lower"

        if lower_better:
            if value <= rule["pass"]:
                return 1.0, "PASS"
            elif value <= rule["watch"]:
                return 0.5, "WATCH"
            else:
                return 0.0, "FAIL"
        else:
            if value >= rule["pass"]:
                return 1.0, "PASS"
            elif value >= rule["watch"]:
                return 0.5, "WATCH"
            else:
                return 0.0, "FAIL"

    def evaluate(self, stats: Dict) -> ValidationResult:
        """
        Evaluate stats against institutional scorecard.

        Args:
            stats: Dictionary of metrics

        Returns:
            ValidationResult with overall score, breakdown, and gate status
        """

        breakdown = {}
        total_weight = 0
        total_score = 0
        hard_fail_reasons = []

        # Check hard fail conditions
        for condition in self.hard_fail_conditions:
            if self._check_hard_fail(stats, condition):
                hard_fail_reasons.append(condition)

        # Score each section
        for section, metrics in self.scorecard.items():
            section_result = SectionResult(section_score=0.0)
            section_weight = 0
            section_score = 0

            for metric_name, rule in metrics.items():
                if metric_name not in stats:
                    continue

                value = stats[metric_name]
                raw_score, status = self.score_metric(value, rule)
                weighted = raw_score * rule["weight"]

                metric_result = MetricResult(
                    value=value,
                    raw_score=raw_score,
                    weight=rule["weight"],
                    weighted_score=weighted,
                    status=status,
                )

                section_result.metrics[metric_name] = metric_result

                total_weight += rule["weight"]
                total_score += weighted
                section_score += weighted
                section_weight += rule["weight"]

            if section_weight > 0:
                section_result.section_score = section_score / section_weight

            breakdown[section] = section_result

        # Calculate overall score
        overall_score = (
            total_score / total_weight if total_weight > 0 else 0
        )

        # Apply institutional gate
        gate_status = self._apply_gate(overall_score, hard_fail_reasons)

        return ValidationResult(
            overall_score=round(overall_score, 3),
            gate_status=gate_status,
            breakdown=breakdown,
            hard_fail_reasons=hard_fail_reasons,
        )

    def _check_hard_fail(self, stats: Dict, condition: str) -> bool:
        """
        Check if a hard fail condition is met.

        Args:
            stats: Dictionary of metrics
            condition: Condition string (e.g., "max_drawdown > 0.10")

        Returns:
            True if condition is met (hard fail triggered)
        """

        try:
            # Parse condition "metric op value"
            parts = condition.split()
            metric = parts[0]
            operator = parts[1]
            threshold = float(parts[2])

            if metric not in stats:
                return False

            value = stats[metric]

            if operator == ">":
                return value > threshold
            elif operator == "<":
                return value < threshold
            elif operator == ">=":
                return value >= threshold
            elif operator == "<=":
                return value <= threshold
            elif operator == "==":
                return value == threshold
            elif operator == "!=":
                return value != threshold

        except (ValueError, IndexError):
            pass

        return False

    def _apply_gate(
        self, overall_score: float, hard_fail_reasons: List[str]
    ) -> GateStatus:
        """
        Apply institutional gate to determine status.

        Args:
            overall_score: Overall validation score (0-1)
            hard_fail_reasons: List of hard fail conditions met

        Returns:
            GateStatus: PASS, WATCH, or FAIL
        """

        # Hard fails override everything
        if hard_fail_reasons:
            return GateStatus.FAIL

        # Score-based gate
        if overall_score >= self.gate_thresholds["pass"]:
            return GateStatus.PASS
        elif overall_score >= self.gate_thresholds["watch"]:
            return GateStatus.WATCH
        else:
            return GateStatus.FAIL

    def print_result(self, result: ValidationResult) -> str:
        """
        Generate human-readable validation report.

        Args:
            result: ValidationResult

        Returns:
            Formatted report string
        """

        lines = []

        lines.append("=" * 80)
        lines.append("INSTITUTIONAL VALIDATION SCORECARD")
        lines.append("=" * 80)
        lines.append("")

        # Overall score and gate
        lines.append(f"Overall Score: {result.overall_score * 100:.1f}%")
        lines.append(f"Gate Status:   {result.gate_status.value}")
        lines.append("")

        # Hard fails
        if result.hard_fail_reasons:
            lines.append("🚨 HARD FAIL CONDITIONS:")
            for reason in result.hard_fail_reasons:
                lines.append(f"  ❌ {reason}")
            lines.append("")

        # Section breakdown
        for section_name, section_result in result.breakdown.items():
            lines.append(f"{section_name.upper()} ({section_result.section_score * 100:.1f}%)")
            lines.append("-" * 40)

            for metric_name, metric in section_result.metrics.items():
                status_icon = {
                    "PASS": "✅",
                    "WATCH": "⚠️ ",
                    "FAIL": "❌",
                }.get(metric.status, "?")

                lines.append(
                    f"  {status_icon} {metric_name:30s} = {metric.value:8.3f} "
                    f"(score: {metric.raw_score:.2f}, weight: {metric.weight:2d})"
                )

            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)
