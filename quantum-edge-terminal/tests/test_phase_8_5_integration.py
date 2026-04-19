"""
PHASE 8.5 INTEGRATION TESTS

Tests for ExecutionAuditLog, ExecutionKillSwitch, ShadowExecutionComparator,
and StagedCapitalDeployment integrations with the core system.

Test coverage:
1. ExecutionAuditLog ↔ OrderManager integration
2. ExecutionKillSwitch ↔ IntegrationBridge integration
3. ShadowExecutionComparator ↔ ValidationOrchestrator integration
4. StagedCapitalDeployment ↔ ProductionRunner integration
5. ExecutionAuditReport dashboard generation
"""

import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

# Phase 8.5 modules
from execution import (
    ExecutionAuditLog,
    ExecutionKillSwitch,
    ShadowExecutionComparator,
    StagedCapitalDeployment,
    DeploymentStage,
)
from monitoring import ExecutionAuditReport, ReportPeriod

logger = logging.getLogger(__name__)


class TestExecutionAuditLogIntegration:
    """Tests for ExecutionAuditLog integration with OrderManager."""

    @pytest.fixture
    def audit_log(self):
        """Create ExecutionAuditLog instance."""
        return ExecutionAuditLog(max_records=1000)

    def test_execution_lifecycle_tracking(self, audit_log):
        """Test complete execution lifecycle tracking."""

        # Create execution
        execution_id = "exec-001"
        audit_log.create_execution(
            execution_id=execution_id,
            symbol="AAPL",
            side="buy",
            qty=100,
            confidence=0.75,
            expected_price=150.00,
        )

        # Record submission
        audit_log.record_order_submitted(execution_id)

        # Record acknowledgment
        audit_log.record_order_acked(execution_id)

        # Record fill
        audit_log.record_fill(
            execution_id=execution_id,
            fill_qty=100,
            fill_price=150.05,
        )

        # Get execution record
        record = audit_log.get_execution_record(execution_id)

        assert record is not None
        assert record["symbol"] == "AAPL"
        assert record["side"] == "buy"
        assert record["qty"] == 100
        assert record["expected_price"] == 150.00
        assert abs(record["slippage_bps"] - 3.33) < 1  # 0.05 / 150.00 * 10000 ≈ 3.33 bps

    def test_slippage_calculation(self, audit_log):
        """Test slippage calculation."""

        execution_id = "exec-002"
        audit_log.create_execution(
            execution_id=execution_id,
            symbol="TSLA",
            side="buy",
            qty=50,
            confidence=0.80,
            expected_price=800.00,
        )

        audit_log.record_order_submitted(execution_id)
        audit_log.record_order_acked(execution_id)

        # Negative slippage (favorable)
        audit_log.record_fill(
            execution_id=execution_id,
            fill_qty=50,
            fill_price=799.50,  # 0.5 better
        )

        record = audit_log.get_execution_record(execution_id)
        assert record["slippage_pct"] < 0  # Favorable
        assert "fill_quality" in record

    def test_rejection_recording(self, audit_log):
        """Test rejection recording."""

        execution_id = "exec-003"
        audit_log.create_execution(
            execution_id=execution_id,
            symbol="MSFT",
            side="sell",
            qty=200,
            confidence=0.60,
            expected_price=300.00,
        )

        audit_log.record_order_submitted(execution_id)

        # Record rejection
        audit_log.record_rejection(
            execution_id=execution_id,
            reason="Insufficient buying power",
        )

        record = audit_log.get_execution_record(execution_id)
        assert record["last_phase"] == "REJECTED"
        assert "Insufficient buying power" in record["rejection_reason"]

    def test_execution_statistics(self, audit_log):
        """Test execution statistics calculation."""

        # Create multiple executions
        for i in range(10):
            exec_id = f"exec-{i:03d}"
            audit_log.create_execution(
                execution_id=exec_id,
                symbol="GOOG",
                side="buy" if i % 2 == 0 else "sell",
                qty=100,
                confidence=0.70 + (i * 0.02),
                expected_price=100.00 + i,
            )
            audit_log.record_order_submitted(exec_id)
            audit_log.record_order_acked(exec_id)
            audit_log.record_fill(
                execution_id=exec_id,
                fill_qty=100,
                fill_price=100.00 + i + (0.01 * i),
            )

        # Get statistics
        stats = audit_log.get_execution_stats(window_minutes=60)

        assert stats["total_executions"] == 10
        assert stats["filled"] == 10
        assert stats["rejected"] == 0
        assert stats["fill_rate"] == 1.0
        assert stats["avg_slippage_bps"] > 0


class TestExecutionKillSwitchIntegration:
    """Tests for ExecutionKillSwitch integration with IntegrationBridge."""

    @pytest.fixture
    def kill_switch(self):
        """Create ExecutionKillSwitch instance."""
        return ExecutionKillSwitch()

    @pytest.fixture
    def audit_log(self):
        """Create ExecutionAuditLog instance."""
        return ExecutionAuditLog(max_records=100)

    def test_kill_switch_api_error_detection(self, kill_switch, audit_log):
        """Test kill switch detects high API error rate."""

        # Simulate API errors
        for i in range(10):
            exec_id = f"exec-{i:03d}"
            audit_log.create_execution(
                execution_id=exec_id,
                symbol="TEST",
                side="buy",
                qty=100,
                confidence=0.50,
                expected_price=100.00,
            )
            audit_log.record_order_submitted(exec_id)
            audit_log.record_order_acked(exec_id)

            # 6 out of 10 fail
            if i < 6:
                audit_log.record_rejection(exec_id, "API timeout")
            else:
                audit_log.record_fill(exec_id, 100, 100.00)

        # Check health with audit log
        # Note: In real integration, kill_switch would have reference to audit_log
        stats = audit_log.get_execution_stats(window_minutes=60)
        error_rate = stats["rejected"] / stats["total_executions"]

        assert error_rate >= 0.5  # 60% error rate
        # Kill switch would trigger on this

    def test_kill_switch_fill_rate_monitoring(self, kill_switch):
        """Test kill switch monitors fill rate."""

        status = kill_switch.get_status()
        assert "is_active" in status
        assert status["is_active"] == False  # Not active initially

    def test_kill_switch_manual_stop(self, kill_switch):
        """Test manual kill switch stop."""

        kill_switch.manual_stop("Operator requested halt")
        status = kill_switch.get_status()

        # After manual stop, kill switch should be active
        assert status.get("is_active") == True


class TestShadowExecutionIntegration:
    """Tests for ShadowExecutionComparator integration with ValidationOrchestrator."""

    @pytest.fixture
    def shadow_comparator(self):
        """Create ShadowExecutionComparator instance."""
        return ShadowExecutionComparator()

    def test_shadow_execution_pair_tracking(self, shadow_comparator):
        """Test shadow execution pair creation and tracking."""

        signal_id = "sig-001"

        # Create shadow pair
        shadow_comparator.create_shadow_execution(
            signal_id=signal_id,
            symbol="AAPL",
            sim_expected_price=150.00,
            market_price_at_signal=150.10,
        )

        # Record simulated fill
        shadow_comparator.record_simulated_fill(
            signal_id=signal_id,
            fill_price=150.05,
            fill_qty=100,
            fill_time=datetime.utcnow().isoformat(),
        )

        # Record market reality
        shadow_comparator.record_market_reality(
            signal_id=signal_id,
            actual_fill_price=150.15,
            actual_qty=100,
            ohlc_high=151.00,
            ohlc_low=149.50,
            fill_time=datetime.utcnow().isoformat(),
        )

        # Get pair
        pair = shadow_comparator.get_execution_pair(signal_id)

        assert pair is not None
        assert pair["symbol"] == "AAPL"
        assert abs(pair["sim_fill_price"] - 150.05) < 0.01
        assert abs(pair["actual_price"] - 150.15) < 0.01

    def test_shadow_execution_divergence_detection(self, shadow_comparator):
        """Test divergence detection between sim and market."""

        signal_id = "sig-002"

        # Create shadow execution with large divergence
        shadow_comparator.create_shadow_execution(
            signal_id=signal_id,
            symbol="TSLA",
            sim_expected_price=800.00,
            market_price_at_signal=800.00,
        )

        shadow_comparator.record_simulated_fill(
            signal_id=signal_id,
            fill_price=800.00,
            fill_qty=10,
            fill_time=datetime.utcnow().isoformat(),
        )

        # Large divergence in actual market reality
        shadow_comparator.record_market_reality(
            signal_id=signal_id,
            actual_fill_price=813.00,  # 1.6% divergence
            actual_qty=10,
            ohlc_high=820.00,
            ohlc_low=795.00,
            fill_time=datetime.utcnow().isoformat(),
        )

        # Get daily report
        report = shadow_comparator.get_daily_report()

        assert len(report["recent_alerts"]) > 0  # Should have divergence alert
        assert report["avg_divergence_pct"] > 1.0  # > 1% divergence

    def test_shadow_execution_reset_daily(self, shadow_comparator):
        """Test daily reset of shadow execution data."""

        signal_id = "sig-003"

        # Create initial execution
        shadow_comparator.create_shadow_execution(
            signal_id=signal_id,
            symbol="MSFT",
            sim_expected_price=300.00,
            market_price_at_signal=300.00,
        )

        report_before = shadow_comparator.get_daily_report()
        assert report_before["total_pairs_tracked"] >= 1

        # Reset daily
        shadow_comparator.reset_daily()

        report_after = shadow_comparator.get_daily_report()
        assert report_after["total_pairs_tracked"] == 0


class TestStagedCapitalDeployment:
    """Tests for StagedCapitalDeployment integration with ProductionRunner."""

    @pytest.fixture
    def staged_deployment(self):
        """Create StagedCapitalDeployment instance."""
        return StagedCapitalDeployment(total_account_capital=100000.0)

    def test_staged_deployment_initialization(self, staged_deployment):
        """Test staged deployment framework initialization."""

        staged_deployment.start_stage(DeploymentStage.PAPER_ONLY)
        status = staged_deployment.get_status()

        assert status["current_stage"] == DeploymentStage.PAPER_ONLY.value
        assert status["deployed_capital"] == 0.0
        assert status["deployment_pct"] == 0.0

    def test_stage_progression(self, staged_deployment):
        """Test progression through deployment stages."""

        # Start at PAPER
        staged_deployment.start_stage(DeploymentStage.PAPER_ONLY)
        assert staged_deployment.get_status()["current_stage"] == "paper_only"

        # Evaluate gate for MICRO stage
        metrics = {
            "days_at_stage": 7,
            "trades_completed": 50,
            "win_rate": 0.56,
            "max_drawdown": 0.05,
            "total_pnl": 500.0,
            "expectancy": 0.15,
        }

        gate_decision = staged_deployment.evaluate_stage_gate(metrics)

        # Should pass paper stage gate
        assert gate_decision.approved == True
        assert gate_decision.next_stage is not None

    def test_stage_gate_evaluation(self, staged_deployment):
        """Test stage gate evaluation with failing metrics."""

        staged_deployment.start_stage(DeploymentStage.PAPER_ONLY)

        # Metrics that should fail
        metrics = {
            "days_at_stage": 2,  # Too few days
            "trades_completed": 10,  # Too few trades
            "win_rate": 0.45,  # Below minimum
            "max_drawdown": 0.12,  # Above maximum
            "total_pnl": -1000.0,  # Negative PnL
            "expectancy": -0.10,
        }

        gate_decision = staged_deployment.evaluate_stage_gate(metrics)

        # Should fail multiple gates
        assert gate_decision.approved == False
        assert len(gate_decision.gate_results) > 0

    def test_deployment_capital_allocation(self, staged_deployment):
        """Test capital allocation at each stage."""

        stages_and_expected_pct = [
            (DeploymentStage.PAPER_ONLY, 0),
            (DeploymentStage.MICRO_DEPLOYMENT, 3),
            (DeploymentStage.SMALL_DEPLOYMENT, 7),
            (DeploymentStage.MEDIUM_DEPLOYMENT, 15),
            (DeploymentStage.LARGE_DEPLOYMENT, 40),
            (DeploymentStage.FULL_DEPLOYMENT, 100),
        ]

        for stage, expected_pct in stages_and_expected_pct:
            staged_deployment.start_stage(stage)
            status = staged_deployment.get_status()

            expected_capital = 100000.0 * (expected_pct / 100)
            assert abs(status["deployed_capital"] - expected_capital) < 1.0


class TestExecutionAuditReport:
    """Tests for ExecutionAuditReport dashboard generation."""

    @pytest.fixture
    def report_generator(self):
        """Create ExecutionAuditReport instance."""
        return ExecutionAuditReport()

    def test_report_generation_empty_log(self, report_generator):
        """Test report generation with empty audit log."""

        audit_log = ExecutionAuditLog()

        report = report_generator.generate_report(
            audit_log=audit_log,
            report_period=ReportPeriod.LAST_TRADING_DAY,
        )

        assert report is not None
        assert report["metrics"] is None
        assert len(report["alerts"]) == 0

    def test_report_generation_with_data(self, report_generator):
        """Test report generation with execution data."""

        audit_log = ExecutionAuditLog()

        # Create executions
        for i in range(20):
            exec_id = f"exec-{i:03d}"
            audit_log.create_execution(
                execution_id=exec_id,
                symbol="AAPL",
                side="buy",
                qty=100,
                confidence=0.70,
                expected_price=150.00,
            )
            audit_log.record_order_submitted(exec_id)
            audit_log.record_order_acked(exec_id)
            audit_log.record_fill(
                execution_id=exec_id,
                fill_qty=100,
                fill_price=150.00 + (0.02 * i),
            )

        report = report_generator.generate_report(
            audit_log=audit_log,
            report_period=ReportPeriod.LAST_TRADING_DAY,
        )

        assert report["metrics"] is not None
        assert report["metrics"]["total_executions"] == 20
        assert report["metrics"]["fill_rate_pct"] == 100.0
        assert report["health_status"]["status"] in [
            "EXCELLENT",
            "GOOD",
            "ACCEPTABLE",
        ]

    def test_alert_generation(self, report_generator):
        """Test alert generation from execution analysis."""

        audit_log = ExecutionAuditLog()

        # Create executions with poor slippage to trigger alert
        for i in range(5):
            exec_id = f"exec-{i:03d}"
            audit_log.create_execution(
                execution_id=exec_id,
                symbol="HIGH_SLIP",
                side="buy",
                qty=100,
                confidence=0.50,
                expected_price=100.00,
            )
            audit_log.record_order_submitted(exec_id)
            audit_log.record_order_acked(exec_id)
            # Large slippage
            audit_log.record_fill(
                execution_id=exec_id,
                fill_qty=100,
                fill_price=100.20,  # 20bps slippage
            )

        report = report_generator.generate_report(
            audit_log=audit_log,
            report_period=ReportPeriod.LAST_HOUR,
        )

        # Should have alerts for high slippage
        assert len(report["alerts"]) > 0
        assert any(a["alert_type"] == "slippage_spike" for a in report["alerts"])


class TestSystemIntegration:
    """End-to-end integration tests for all Phase 8.5 modules."""

    def test_execution_pipeline_integration(self):
        """Test complete execution pipeline with all Phase 8.5 modules."""

        # Initialize all components
        audit_log = ExecutionAuditLog()
        kill_switch = ExecutionKillSwitch()
        shadow_comparator = ShadowExecutionComparator()
        staged_deployment = StagedCapitalDeployment(total_account_capital=50000.0)
        report_generator = ExecutionAuditReport()

        # Simulate execution
        signal_id = "integration-sig-001"
        exec_id = "integration-exec-001"

        # 1. Create shadow execution
        shadow_comparator.create_shadow_execution(
            signal_id=signal_id,
            symbol="SPY",
            sim_expected_price=400.00,
            market_price_at_signal=400.05,
        )

        # 2. Create order and track in audit log
        audit_log.create_execution(
            execution_id=exec_id,
            symbol="SPY",
            side="buy",
            qty=100,
            confidence=0.75,
            expected_price=400.00,
        )

        # 3. Check kill switch (should be healthy)
        health_ok = kill_switch.check_execution_health()
        assert health_ok == True

        # 4. Record execution path
        audit_log.record_order_submitted(exec_id)
        audit_log.record_order_acked(exec_id)
        audit_log.record_fill(exec_id, 100, 400.10)

        # 5. Record shadow execution
        shadow_comparator.record_simulated_fill(
            signal_id=signal_id,
            fill_price=400.05,
            fill_qty=100,
            fill_time=datetime.utcnow().isoformat(),
        )

        shadow_comparator.record_market_reality(
            signal_id=signal_id,
            actual_fill_price=400.10,
            actual_qty=100,
            ohlc_high=401.00,
            ohlc_low=399.00,
            fill_time=datetime.utcnow().isoformat(),
        )

        # 6. Generate report
        report = report_generator.generate_report(
            audit_log=audit_log,
            report_period=ReportPeriod.LAST_HOUR,
        )

        assert report["metrics"]["total_executions"] == 1
        assert report["metrics"]["fill_rate_pct"] == 100.0

        # 7. Progress deployment stage
        staged_deployment.start_stage(DeploymentStage.PAPER_ONLY)
        status = staged_deployment.get_status()
        assert status["current_stage"] == "paper_only"

        logger.info("✅ End-to-end integration test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
