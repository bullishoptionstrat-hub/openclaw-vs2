"""
PHASE 7 - INSTITUTIONAL VALIDATION INTEGRATION

Complete end-to-end example of validation orchestration, integration bridge,
and live validation runner working together.

Demonstrates:
1. Initialize all components
2. Feed market data into validation system
3. Generate signals and process through integration
4. Track metrics daily
5. Make gate decisions
6. Output deployment recommendations

This is production-ready code for institutional-grade forward testing.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from validation import (
    ValidationOrchestrator,
    IntegrationBridge,
    LiveValidationRunner,
    ValidationRunConfig,
    BridgeSignal,
    SignalSource,
    BridgeExecutionMode,
    ValidationPhase,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("PHASE7_INTEGRATION")


def generate_mock_market_data(symbol: str, num_candles: int = 100) -> list:
    """Generate mock OHLCV candles for demo."""

    candles = []
    base_price = 150.0

    for i in range(num_candles):
        price = base_price + (i * 0.1) + (i % 3) * 0.5
        candles.append(
            {
                "symbol": symbol,
                "timestamp": (datetime.utcnow() + timedelta(minutes=5 * i)).isoformat(),
                "open": price,
                "high": price + 1.5,
                "low": price - 0.5,
                "close": price + 0.75,
                "volume": 100000 + (i * 1000),
            }
        )

    return candles


def generate_mock_signal(
    symbol: str, direction: str, confidence: float, regime: str, source: SignalSource
) -> BridgeSignal:
    """Generate mock trading signal."""

    entry_price = 150.0
    if direction == "LONG":
        stop_loss = entry_price - 2.0
        take_profit = entry_price + 5.0
    else:
        stop_loss = entry_price + 2.0
        take_profit = entry_price - 5.0

    return BridgeSignal(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        position_size=5000.0,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
        signal_source=source,
        regime=regime,
        timestamp=datetime.utcnow().isoformat(),
        signal_id=f"{symbol}-{int(datetime.utcnow().timestamp() * 1000)}",
    )


def run_phase7_integration_demo():
    """Run complete Phase 7 integration demonstration."""

    logger.info("\n" + "=" * 80)
    logger.info("PHASE 7: INSTITUTIONAL VALIDATION INTEGRATION")
    logger.info("=" * 80 + "\n")

    # ==========================================================================
    # STEP 1: Configure Validation Run
    # ==========================================================================

    logger.info("STEP 1: Configuring validation run...")

    config = ValidationRunConfig(
        mode="FORWARD_TEST",
        market_data_source="alpaca",
        validation_period_days=30,
        symbols=["SPY", "QQQ", "IWM"],
        initial_capital=100000.0,
        risk_per_trade_pct=1.0,
        enable_live_mode_at_gate_pass=False,
        deployment_capital=10000.0,
        daily_report_enabled=True,
    )

    logger.info(f"  ✓ Mode: {config.mode}")
    logger.info(f"  ✓ Period: {config.validation_period_days} days")
    logger.info(f"  ✓ Symbols: {config.symbols}")
    logger.info(f"  ✓ Initial Capital: ${config.initial_capital:,.0f}")
    logger.info(f"  ✓ Deployment Capital: ${config.deployment_capital:,.0f}\n")

    # ==========================================================================
    # STEP 2: Initialize Components
    # ==========================================================================

    logger.info("STEP 2: Initializing validation components...")

    # Orchestrator: Central command
    orchestrator = ValidationOrchestrator(
        min_validation_days=30,
        max_consecutive_losses_allowed=5,
    )

    # Integration Bridge: Connects engines to validation
    bridge = IntegrationBridge(
        execution_mode=BridgeExecutionMode.PAPER_VALIDATION,
        paper_trading_enabled=True,
        enable_safety_controls=True,
        enable_scoring=True,
    )

    # Live Validation Runner: Orchestrates entire workflow
    runner = LiveValidationRunner(config)

    logger.info(f"  ✓ Orchestrator initialized")
    logger.info(f"  ✓ Integration bridge initialized (mode: {bridge.execution_mode.value})")
    logger.info(f"  ✓ Live validation runner initialized\n")

    # ==========================================================================
    # STEP 3: Start Validation Period
    # ==========================================================================

    logger.info("STEP 3: Starting validation period...")

    if not orchestrator.initialize_validation():
        logger.error("Failed to initialize validation")
        return

    if not runner.start_validation_run():
        logger.error("Failed to start validation run")
        return

    logger.info(f"  ✓ Validation phase: {orchestrator.phase.value}")
    logger.info(f"  ✓ Start time: {orchestrator.start_time.isoformat()}\n")

    # ==========================================================================
    # STEP 4: Simulate Daily Trading Sessions (Mini Version)
    # ==========================================================================

    logger.info("STEP 4: Simulating trading sessions (demo: 5 days)...\n")

    demo_days = 5  # Demo: 5 days instead of 30
    symbols = config.symbols or ["SPY"]

    for day in range(1, demo_days + 1):
        current_date = (datetime.utcnow() + timedelta(days=day)).strftime("%Y-%m-%d")
        logger.info(f"\n{'='*80}")
        logger.info(f"VALIDATION DAY {day} | {current_date}")
        logger.info(f"{'='*80}")

        # Start daily snapshot
        orchestrator.start_daily_snapshot(current_date, day)

        # Simulate market data
        total_day_signals = 0
        total_day_trades = 0
        day_pnl = 0.0

        for symbol in symbols:
            logger.info(f"\n  Symbol: {symbol}")

            # Generate mock market data (100 candles = 500 min = ~1 trading day)
            market_data = generate_mock_market_data(symbol, num_candles=100)

            # Process some signals (every 20 candles = 100 min)
            for i, candle in enumerate(market_data):
                if i % 20 == 0 and i > 0:  # Signal every 20 candles
                    # Vary signal source and regime
                    sources = [SignalSource.AI_ENGINE, SignalSource.MACRO_ENGINE]
                    regimes = ["NORMAL", "BULL", "BEAR"]
                    confidences = [0.65, 0.75, 0.85]

                    source = sources[i % len(sources)]
                    regime = regimes[i % len(regimes)]
                    confidence = confidences[i % len(confidences)]
                    direction = "LONG" if (i % 2 == 0) else "SHORT"

                    signal = generate_mock_signal(symbol, direction, confidence, regime, source)

                    # Process through integration bridge
                    result = bridge.process_signal(signal)

                    if result.signal_accepted:
                        total_day_signals += 1
                        total_day_trades += 1

                        # Record in orchestrator
                        orchestrator.record_signal(
                            symbol, direction, confidence, regime
                        )
                        orchestrator.record_trade(
                            symbol,
                            entry_price=signal.entry_price,
                            exit_price=signal.entry_price + (2.0 if direction == "LONG" else -2.0),
                            pnl=200.0 if i % 3 == 0 else -100.0,  # Simulated PnL
                            slippage=0.002,
                            latency_ms=45,
                        )

                        day_pnl += 200.0 if i % 3 == 0 else -100.0

                        logger.info(
                            f"    → Signal accepted | {signal.direction} | "
                            f"Confidence: {confidence:.2%} | Gate: {result.gate_status}"
                        )
                    else:
                        logger.debug(
                            f"    ✗ Signal rejected | {result.rejection_reason}"
                        )

        # Record duplicate signal (for tracking)
        orchestrator.record_duplicate_signal()

        # End day snapshot
        daily_snapshot = orchestrator.end_daily_snapshot(
            daily_gate_status="WATCH" if day_pnl >= 0 else "FAIL",
            daily_sharpe=1.3 + (day * 0.1),
            max_drawdown=0.03 + (day * 0.01),
        )

        logger.info(f"\n  Daily Summary:")
        logger.info(f"    Signals: {total_day_signals}")
        logger.info(f"    Trades: {total_day_trades}")
        logger.info(f"    Daily PnL: ${day_pnl:,.2f}")
        logger.info(f"    Gate Status: {daily_snapshot.gate_status}")

    # ==========================================================================
    # STEP 5: Check Validation Status
    # ==========================================================================

    logger.info(f"\n\n{'='*80}")
    logger.info("STEP 5: Checking current validation status...")
    logger.info(f"{'='*80}")

    phase, progress = orchestrator.check_validation_status()
    logger.info(f"  Phase: {phase.upper()}")
    logger.info(f"  Progress: {progress:.1%}")
    logger.info(f"  Days completed: {orchestrator.validation_start_date}\n")

    # ==========================================================================
    # STEP 6: Get Bridge Statistics
    # ==========================================================================

    logger.info(f"{'='*80}")
    logger.info("STEP 6: Integration bridge statistics...")
    logger.info(f"{'='*80}")

    stats = bridge.get_bridge_stats()
    logger.info(f"  Total signals processed: {stats['total_signals']}")
    logger.info(f"  Accepted signals: {stats['accepted_signals']}")
    logger.info(f"  Rejected signals: {stats['rejected_signals']}")
    logger.info(f"  Acceptance rate: {stats['acceptance_rate']:.2%}")
    logger.info(f"  Safety violations: {stats['safety_violations']}")
    logger.info(f"  Avg confidence score: {stats['avg_confidence']:.2%}")
    logger.info(f"  Execution mode: {stats['execution_mode']}\n")

    # ==========================================================================
    # STEP 7: Show Sample Daily Report
    # ==========================================================================

    if runner.daily_reports:
        logger.info(f"{'='*80}")
        logger.info("STEP 7: Sample daily report (Day 1)...")
        logger.info(f"{'='*80}")

        report = runner.daily_reports[0]
        logger.info(f"  Date: {report['date']}")
        logger.info(f"  Signals: {report['metrics']['signals_generated']}")
        logger.info(f"  Trades: {report['metrics']['trades_executed']}")
        logger.info(f"  Daily PnL: ${report['metrics']['daily_pnl']:,.2f}")
        logger.info(f"  Gate Status: {report['validation']['gate_status']}")
        logger.info(f"  Confidence: {report['validation']['confidence_score']:.2%}\n")

    # ==========================================================================
    # STEP 8: Demonstrate Mode Switch (Paper → Live)
    # ==========================================================================

    logger.info(f"{'='*80}")
    logger.info("STEP 8: Demonstrating execution mode switch (Paper → Live)...")
    logger.info(f"{'='*80}")

    logger.info(f"  Current mode: {bridge.execution_mode.value}")
    logger.info(f"  Attempting switch to LIVE_TRADING...")

    success = bridge.switch_execution_mode(BridgeExecutionMode.LIVE_TRADING)
    if success:
        logger.info(f"  ✓ Mode switched successfully")
        logger.info(f"  ⚠️  WARNING: Real capital at risk in LIVE mode")
        logger.info(f"  New mode: {bridge.execution_mode.value}\n")
    else:
        logger.info(f"  Switch aborted (demo only)\n")

    # ==========================================================================
    # STEP 9: Output Summary Report
    # ==========================================================================

    logger.info(f"{'='*80}")
    logger.info("PHASE 7 INTEGRATION SUMMARY")
    logger.info(f"{'='*80}")

    logger.info(f"\n✅ Validation Orchestrator:")
    logger.info(f"   • Days in validation: {len(orchestrator.daily_snapshots)}")
    logger.info(f"   • Phase: {orchestrator.phase.value}")
    logger.info(f"   • Scoreboard path: {orchestrator.scoreboard_path}")

    logger.info(f"\n✅ Integration Bridge:")
    logger.info(f"   • Mode: {bridge.execution_mode.value}")
    logger.info(f"   • Total signals: {bridge.total_signals}")
    logger.info(f"   • Acceptance rate: {stats['acceptance_rate']:.2%}")

    logger.info(f"\n✅ Live Validation Runner:")
    logger.info(f"   • Trading sessions: {runner.trading_sessions}")
    logger.info(f"   • Total signals: {runner.total_signals}")
    logger.info(f"   • Total trades: {runner.total_trades}")
    logger.info(f"   • Cumulative PnL: ${runner.cumulative_pnl:,.2f}")

    logger.info(f"\n{'='*80}")
    logger.info("✅ PHASE 7 INTEGRATION COMPLETE")
    logger.info(f"{'='*80}\n")

    logger.info("📊 What's Now In Place:")
    logger.info("   1. ValidationOrchestrator: Lifecycle management & metrics")
    logger.info("   2. IntegrationBridge: Signal routing & safety validation")
    logger.info("   3. LiveValidationRunner: End-to-end orchestration")
    logger.info("   4. Complete gate decision logic (PASS/WATCH/FAIL)")
    logger.info("   5. Daily reporting + final scoreboard")
    logger.info("   6. Mode switching (Paper → Live deployment)")

    logger.info("\n📝 Next Steps:")
    logger.info("   1. Connect actual market data stream (Alpaca API)")
    logger.info("   2. Integrate with real trading engines")
    logger.info("   3. Deploy to production validation runner")
    logger.info("   4. Monitor daily metrics + gate progression")
    logger.info("   5. Deploy capital once gate passes for 30 days")


if __name__ == "__main__":
    run_phase7_integration_demo()
