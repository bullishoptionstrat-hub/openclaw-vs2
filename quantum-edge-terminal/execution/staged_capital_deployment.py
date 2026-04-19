"""
STAGED CAPITAL DEPLOYMENT - STEP-WISE CAPITAL INCREASE WITH VALIDATION GATES

This prevents the "all or nothing" trap:
- Paper trading looks great
- Deploy full capital on day 1
- Gets slaughtered on day 2

Instead:
- Phase 1: Paper only (collect proof)
- Phase 2: 1-5% capital (prove execution)
- Phase 3: 5-10% capital (validate behavior)
- Phase 4: 10-25% capital (prove consistency)
- Phase 5: 25-50% capital (stress test)
- Phase 6: Full capital (only after all gates pass)

Each stage requires explicit validation gates to pass.
NO AUTO-ADVANCE. Operator must approve each stage.
"""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DeploymentStage(Enum):
    """Capital deployment stages."""

    PAPER_ONLY = "paper_only"  # 0% real capital
    MICRO_DEPLOYMENT = "micro_deployment"  # 1-5%
    SMALL_DEPLOYMENT = "small_deployment"  # 5-10%
    MEDIUM_DEPLOYMENT = "medium_deployment"  # 10-25%
    LARGE_DEPLOYMENT = "large_deployment"  # 25-50%
    FULL_DEPLOYMENT = "full_deployment"  # 100%


@dataclass
class StageGateRequirements:
    """Requirements to advance to next stage."""

    min_days_at_stage: int = 7  # Minimum days trading at current stage
    min_trades_required: int = 50  # Minimum trades completed
    min_win_rate: float = 0.55  # Win rate requirement
    max_drawdown: float = 0.08  # 8% max
    max_daily_loss: float = 0.02  # 2% max daily loss
    positive_expectancy_required: bool = True  # Must show positive PnL
    consistency_score_min: float = 0.65  # Consistency metric

    # Optional: shadow execution requirements
    shadow_execution_divergence_max: float = 0.005  # Max 0.5% divergence from sim
    fill_rate_min: float = 0.80  # 80% fill rate


@dataclass
class StageCycleRecord:
    """Record of trading at a deployment stage."""

    stage: DeploymentStage
    capital_allocated: float
    start_time: datetime
    end_time: Optional[datetime] = None
    trades_completed: int = 0
    win_count: int = 0
    loss_count: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    daily_losses: List[float] = field(default_factory=list)

    def get_metrics(self) -> Dict:
        """Get metrics for this stage."""
        return {
            "stage": self.stage.value,
            "capital_allocated": self.capital_allocated,
            "days_at_stage": (self.end_time or datetime.utcnow() - self.start_time).days,
            "trades_completed": self.trades_completed,
            "win_rate": self.win_count / self.trades_completed if self.trades_completed > 0 else 0,
            "total_pnl": self.total_pnl,
            "max_drawdown": self.max_drawdown,
            "avg_daily_loss": sum(self.daily_losses) / len(self.daily_losses) if self.daily_losses else 0,
        }


@dataclass
class DeploymentGateDecision:
    """Decision on whether to advance stage."""

    approved: bool
    stage: DeploymentStage
    next_stage: Optional[DeploymentStage]
    reason: str
    gate_results: Dict = field(default_factory=dict)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class StagedCapitalDeployment:
    """
    Manages step-wise capital increase with explicit gate approval.

    This is NOT automated. Each stage requires operator sign-off.
    """

    def __init__(self, total_account_capital: float):
        """
        Initialize staged deployment.

        Args:
            total_account_capital: Total available capital
        """
        self.total_capital = total_account_capital
        self.current_stage = DeploymentStage.PAPER_ONLY
        self.current_deployed_capital = 0.0

        # Stage definitions (% of capital)
        self.stage_allocations = {
            DeploymentStage.PAPER_ONLY: 0.0,
            DeploymentStage.MICRO_DEPLOYMENT: 0.03,  # 3%
            DeploymentStage.SMALL_DEPLOYMENT: 0.07,  # 7%
            DeploymentStage.MEDIUM_DEPLOYMENT: 0.15,  # 15%
            DeploymentStage.LARGE_DEPLOYMENT: 0.40,  # 40%
            DeploymentStage.FULL_DEPLOYMENT: 1.0,  # 100%
        }

        # Stage requirements
        self.gate_requirements = {
            DeploymentStage.PAPER_ONLY: StageGateRequirements(min_days_at_stage=0, min_trades_required=0),
            DeploymentStage.MICRO_DEPLOYMENT: StageGateRequirements(
                min_days_at_stage=7, min_trades_required=50, min_win_rate=0.55, positive_expectancy_required=True
            ),
            DeploymentStage.SMALL_DEPLOYMENT: StageGateRequirements(
                min_days_at_stage=7, min_trades_required=100, min_win_rate=0.55, max_drawdown=0.08
            ),
            DeploymentStage.MEDIUM_DEPLOYMENT: StageGateRequirements(
                min_days_at_stage=10, min_trades_required=150, min_win_rate=0.56, max_drawdown=0.07
            ),
            DeploymentStage.LARGE_DEPLOYMENT: StageGateRequirements(
                min_days_at_stage=14, min_trades_required=250, min_win_rate=0.57, max_drawdown=0.06
            ),
            DeploymentStage.FULL_DEPLOYMENT: StageGateRequirements(
                min_days_at_stage=21, min_trades_required=500, min_win_rate=0.58, max_drawdown=0.05
            ),
        }

        self.stage_history: List[StageCycleRecord] = []
        self.current_cycle: Optional[StageCycleRecord] = None

        logger.info(f"StagedCapitalDeployment initialized | Total capital: ${total_account_capital:,.0f}")
        logger.info(f"  Starting: {DeploymentStage.PAPER_ONLY.value} (0% deployed)")

    def start_stage(self, stage: DeploymentStage) -> bool:
        """
        Begin trading at stage.

        Args:
            stage: DeploymentStage to start

        Returns:
            True if transition successful
        """

        if stage == self.current_stage:
            logger.warning(f"Already at stage: {stage.value}")
            return False

        # Save previous cycle if exists
        if self.current_cycle:
            self.current_cycle.end_time = datetime.utcnow()
            self.stage_history.append(self.current_cycle)

            logger.info(
                f"Completed stage: {self.current_cycle.stage.value} | "
                f"Trades: {self.current_cycle.trades_completed} | "
                f"PnL: ${self.current_cycle.total_pnl:+,.0f} | "
                f"Win rate: {self.current_cycle.get_metrics()['win_rate']:.0%}"
            )

        # Create new cycle
        allocated_pct = self.stage_allocations[stage]
        allocated_capital = self.total_capital * allocated_pct

        self.current_cycle = StageCycleRecord(
            stage=stage,
            capital_allocated=allocated_capital,
            start_time=datetime.utcnow(),
        )

        self.current_stage = stage
        self.current_deployed_capital = allocated_capital

        logger.critical(f"🚀 ADVANCED TO STAGE: {stage.value}")
        logger.critical(f"   Capital allocated: ${allocated_capital:,.0f} ({allocated_pct:.0%} of ${self.total_capital:,.0f})")
        logger.critical(f"   Start time: {self.current_cycle.start_time.isoformat()}")

        return True

    def evaluate_stage_gate(self, metrics: Dict) -> DeploymentGateDecision:
        """
        Evaluate if current stage requirements are met.

        Args:
            metrics: Dict with current performance metrics
                - trades_completed
                - win_count
                - total_pnl
                - max_drawdown
                - daily_losses
                - consistency_score
                - days_at_stage

        Returns:
            DeploymentGateDecision with pass/fail and next stage
        """

        requirements = self.gate_requirements.get(self.current_stage)
        if not requirements:
            return DeploymentGateDecision(
                approved=False,
                stage=self.current_stage,
                next_stage=None,
                reason="No gate requirements defined for this stage",
            )

        # Check each requirement
        gate_results = {}

        # Check minimum days at stage
        days_at_stage = metrics.get("days_at_stage", 0)
        gate_results["days_at_stage"] = {
            "requirement": requirements.min_days_at_stage,
            "actual": days_at_stage,
            "pass": days_at_stage >= requirements.min_days_at_stage,
        }

        # Check minimum trades
        trades_completed = metrics.get("trades_completed", 0)
        gate_results["trades_completed"] = {
            "requirement": requirements.min_trades_required,
            "actual": trades_completed,
            "pass": trades_completed >= requirements.min_trades_required,
        }

        # Check win rate
        win_rate = metrics.get("win_rate", 0)
        gate_results["win_rate"] = {
            "requirement": f"{requirements.min_win_rate:.0%}",
            "actual": f"{win_rate:.0%}",
            "pass": win_rate >= requirements.min_win_rate,
        }

        # Check drawdown
        max_drawdown = metrics.get("max_drawdown", 0)
        gate_results["max_drawdown"] = {
            "requirement": f"<{requirements.max_drawdown:.0%}",
            "actual": f"{max_drawdown:.0%}",
            "pass": max_drawdown <= requirements.max_drawdown,
        }

        # Check expectancy
        total_pnl = metrics.get("total_pnl", 0)
        if requirements.positive_expectancy_required:
            gate_results["positive_expectancy"] = {
                "required": True,
                "actual": total_pnl > 0,
                "pass": total_pnl > 0,
            }

        # Determine pass/fail
        all_pass = all(result["pass"] for result in gate_results.values())

        if all_pass:
            # What's the next stage?
            next_stage = self._get_next_stage()
            reason = f"All gate requirements passed for stage: {self.current_stage.value}"
            return DeploymentGateDecision(
                approved=True,
                stage=self.current_stage,
                next_stage=next_stage,
                reason=reason,
                gate_results=gate_results,
            )
        else:
            # Which requirements failed?
            failed_requirements = [k for k, v in gate_results.items() if not v["pass"]]
            reason = f"Failed requirements: {', '.join(failed_requirements)}"
            return DeploymentGateDecision(
                approved=False,
                stage=self.current_stage,
                next_stage=None,
                reason=reason,
                gate_results=gate_results,
            )

    def _get_next_stage(self) -> Optional[DeploymentStage]:
        """Get next deployment stage."""
        stage_order = [
            DeploymentStage.PAPER_ONLY,
            DeploymentStage.MICRO_DEPLOYMENT,
            DeploymentStage.SMALL_DEPLOYMENT,
            DeploymentStage.MEDIUM_DEPLOYMENT,
            DeploymentStage.LARGE_DEPLOYMENT,
            DeploymentStage.FULL_DEPLOYMENT,
        ]

        try:
            current_idx = stage_order.index(self.current_stage)
            if current_idx < len(stage_order) - 1:
                return stage_order[current_idx + 1]
        except ValueError:
            pass

        return None

    def request_stage_advance(self, operator: str, reasoning: str) -> bool:
        """
        Request advancement to next stage.

        Must be explicitly approved by operator.
        """

        next_stage = self._get_next_stage()
        if not next_stage:
            logger.error("Already at full deployment")
            return False

        logger.warning("=" * 80)
        logger.warning("STAGE ADVANCEMENT REQUEST")
        logger.warning("=" * 80)
        logger.warning(f"Current stage: {self.current_stage.value}")
        logger.warning(f"Requested next: {next_stage.value}")
        logger.warning(f"Operator: {operator}")
        logger.warning(f"Capital will increase from ${self.current_deployed_capital:,.0f} to ${self.total_capital * self.stage_allocations[next_stage]:,.0f}")
        logger.warning(f"Reasoning: {reasoning}")
        logger.warning("=" * 80)

        # TODO: Get explicit operator approval

        return True

    def get_status(self) -> Dict:
        """Get current deployment status."""
        current_metrics = self.current_cycle.get_metrics() if self.current_cycle else {}

        return {
            "current_stage": self.current_stage.value,
            "deployed_capital": self.current_deployed_capital,
            "deployment_pct": self.current_deployed_capital / self.total_capital * 100,
            "total_capital": self.total_capital,
            "cycle_metrics": current_metrics,
            "stage_history": [
                {
                    "stage": cycle.stage.value,
                    "capital": cycle.capital_allocated,
                    "trades": cycle.trades_completed,
                    "pnl": cycle.total_pnl,
                }
                for cycle in self.stage_history
            ],
        }
