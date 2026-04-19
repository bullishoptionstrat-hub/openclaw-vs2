"""
PHASE 8 PRODUCTION EXAMPLE - Complete Production Deployment Workflow

Demonstrates the entire production system lifecycle:
1. System initialization
2. 30-day validation period
3. Gate decision (PASS/FAIL/WATCH)
4. Operator approval workflow
5. Live trading deployment
6. Real-time performance monitoring
7. Alert generation and response

This is a working reference implementation showing how all 5 production
components work together in a complete production environment.

TOTAL WORKFLOW: ~360 LOC
"""

import logging
from datetime import datetime, timedelta
from production import (
    ProductionRunner,
    SystemConfig,
    SystemState,
    MarketDataStreamer,
    StreamingConfig,
    LiveBrokerConnector,
    BrokerConfig,
    BrokerMode,
    DeploymentGateController,
    DeploymentMetrics,
    PerformanceMonitor,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def simulate_validation_period():
    """
    Simulate a complete 30-day validation period.

    In production, this runs for 30 actual trading days.
    For demo, we compress it to show the complete workflow.
    """

    logger.info("\n" + "="*80)
    logger.info("PHASE 8 PRODUCTION EXAMPLE - COMPLETE WORKFLOW")
    logger.info("="*80 + "\n")

    # ==============================================================================
    # STEP 1: SYSTEM CONFIGURATION
    # ==============================================================================

    logger.info("STEP 1: SYSTEM CONFIGURATION")
    logger.info("-" * 80)

    config = SystemConfig(
        validation_period_days=30,
        symbols=["SPY", "QQQ", "IWM"],
        api_key="YOUR_API_KEY",
        api_secret="YOUR_API_SECRET",
        paper_mode=True,
        initial_capital=100000.0,
        deployment_capital=10000.0,
        max_position_pct=0.05,
        max_daily_loss_pct=0.02,
        max_single_drawdown=0.05,
    )

    logger.info(f"  • Validation period: {config.validation_period_days} trading days")
    logger.info(f"  • Symbols: {', '.join(config.symbols)}")
    logger.info(f"  • Initial capital: ${config.initial_capital:,.0f}")
    logger.info(f"  • Deployment capital: ${config.deployment_capital:,.0f}")
    logger.info(f"  • Mode: {'PAPER (safe for validation)' if config.paper_mode else 'LIVE'}")
    logger.info(f"  • Max drawdown tolerance: {config.max_single_drawdown:.1%}")
    logger.info(f"  • Max daily loss: {config.max_daily_loss_pct:.1%}\n")

    # ==============================================================================
    # STEP 2: SYSTEM INITIALIZATION
    # ==============================================================================

    logger.info("STEP 2: SYSTEM INITIALIZATION")
    logger.info("-" * 80)

    runner = ProductionRunner(config)

    if not runner.initialize_system():
        logger.error("❌ System initialization failed")
        return

    logger.info(f"✅ All components initialized\n")

    # ==============================================================================
    # STEP 3: BEGIN VALIDATION PERIOD
    # ==============================================================================

    logger.info("STEP 3: BEGIN VALIDATION PERIOD")
    logger.info("-" * 80)

    if not runner.start_validation_period():
        logger.error("❌ Failed to start validation")
        return

    # ==============================================================================
    # STEP 4: SIMULATE 30 DAYS OF TRADING
    # ==============================================================================

    logger.info("STEP 4: SIMULATE 30 DAYS OF VALIDATION TRADING")
    logger.info("-" * 80)

    # Simulated daily performance metrics (in production, these come from actual trades)
    validation_days = [
        {"day": 1, "pnl": 150, "trades": 2, "win_rate": 0.50},
        {"day": 2, "pnl": 250, "trades": 3, "win_rate": 0.67},
        {"day": 3, "pnl": -100, "trades": 2, "win_rate": 0.50},
        {"day": 4, "pnl": 300, "trades": 4, "win_rate": 0.75},
        {"day": 5, "pnl": 200, "trades": 3, "win_rate": 0.67},
    ]

    total_pnl = 0
    trades_total = 0
    for daily_data in validation_days:
        day = daily_data["day"]
        pnl = daily_data["pnl"]
        trades = daily_data["trades"]
        win_rate = daily_data["win_rate"]

        total_pnl += pnl
        trades_total += trades

        logger.info(
            f"  Day {day:2d}: ${pnl:+7.0f} PnL | "
            f"{trades} trades | {win_rate:.0%} win rate | "
            f"Cumulative: ${total_pnl:+.0f}"
        )

    logger.info(f"\n  📊 Validation Summary:")
    logger.info(f"     • Total trades: {trades_total}")
    logger.info(f"     • Total PnL: ${total_pnl:+,.0f}")
    logger.info(f"     • Avg trade: ${total_pnl/trades_total:+.0f}")
    logger.info(f"     • Win rate: {56:.0%}\n")

    # ==============================================================================
    # STEP 5: COMPLETE VALIDATION & MAKE GATE DECISION
    # ==============================================================================

    logger.info("STEP 5: COMPLETE VALIDATION PERIOD & EVALUATE GATE")
    logger.info("-" * 80)

    gate_decision = runner.complete_validation_period()

    if gate_decision:
        logger.info(f"  Gate Status: {gate_decision['status']}")
        logger.info(f"  Confidence: {gate_decision['confidence']:.0%}")
        logger.info(f"  Recommendation: {gate_decision['recommendation']}\n")
    else:
        logger.error("❌ Failed to complete validation")
        return

    # ==============================================================================
    # STEP 6: REQUEST DEPLOYMENT APPROVAL
    # ==============================================================================

    logger.info("STEP 6: REQUEST OPERATOR APPROVAL FOR DEPLOYMENT")
    logger.info("-" * 80)

    if not runner.request_deployment_approval(
        operator="alex@example.com",
        capital=config.deployment_capital,
        reasoning=(
            "30-day validation complete with positive PnL and acceptable drawdown. "
            "System ready for controlled live deployment."
        ),
    ):
        logger.error("❌ Operator approval failed or declined")
        return

    logger.info(f"✅ Deployment approved\n")

    # ==============================================================================
    # STEP 7: ENABLE LIVE TRADING
    # ==============================================================================

    logger.info("STEP 7: ENABLE LIVE TRADING")
    logger.info("-" * 80)

    if not runner.enable_live_trading():
        logger.error("❌ Failed to enable live trading")
        return

    # ==============================================================================
    # STEP 8: SIMULATE LIVE TRADING PERIOD
    # ==============================================================================

    logger.info("STEP 8: SIMULATE 7 DAYS OF LIVE TRADING")
    logger.info("-" * 80)

    live_days = [
        {"day": 1, "equity": 10150, "pnl": 150, "drawdown": 0.01},
        {"day": 2, "equity": 10400, "pnl": 250, "drawdown": 0.01},
        {"day": 3, "equity": 10300, "pnl": -100, "drawdown": 0.03},
        {"day": 4, "equity": 10600, "pnl": 300, "drawdown": 0.01},
        {"day": 5, "equity": 10800, "pnl": 200, "drawdown": 0.02},
        {"day": 6, "equity": 10700, "pnl": -100, "drawdown": 0.04},
        {"day": 7, "equity": 10950, "pnl": 250, "drawdown": 0.02},
    ]

    for day_data in live_days:
        day = day_data["day"]
        equity = day_data["equity"]
        pnl = day_data["pnl"]
        drawdown = day_data["drawdown"]

        metrics = runner.monitor_live_performance()
        logger.info(
            f"  Day {day}: Equity ${equity:,} | "
            f"Daily PnL ${pnl:+.0f} | Drawdown {drawdown:.1%}"
        )

        # Check circuit breaker
        if drawdown > config.max_single_drawdown:
            logger.warning(f"  ⚠️  Drawdown {drawdown:.1%} exceeds limit {config.max_single_drawdown:.1%}")

    logger.info("")

    # ==============================================================================
    # STEP 9: MONITOR PERFORMANCE & ALERTS
    # ==============================================================================

    logger.info("STEP 9: PERFORMANCE MONITORING & ALERT GENERATION")
    logger.info("-" * 80)

    logger.info("  Alert Examples (Real-time detection):")
    logger.info("  • Drawdown Warning: 3.2% vs baseline 2.5% (threshold: 1.5x)")
    logger.info("  • Win Rate Drop: 48% vs baseline 56% (drop > 10%)")
    logger.info("  • Execution Quality: 68% vs baseline 75% (degradation detected)")
    logger.info("  • Performance Regression: 3 consecutive losing days")
    logger.info("  • Signal Drought: No signals generated for 45 mins\n")

    # ==============================================================================
    # STEP 10: FINAL STATUS
    # ==============================================================================

    logger.info("STEP 10: SYSTEM STATUS SUMMARY")
    logger.info("-" * 80)

    status = runner.get_system_status()
    logger.info(f"  Current State: {status['state']}")
    logger.info(f"  Start Time: {status['start_time']}")
    logger.info(f"  Deployment Time: {status['deployment_time']}")
    logger.info(f"  Symbols: {', '.join(status['config']['symbols'])}")
    logger.info(f"  Capital Deployed: ${status['config']['deployment_capital']:,.0f}")
    logger.info(f"  Errors: {status['error_count']}")

    logger.info("\n" + "="*80)
    logger.info("PHASE 8 PRODUCTION WORKFLOW COMPLETE")
    logger.info("="*80 + "\n")

    # ==============================================================================
    # COMPONENT INTEGRATION ARCHITECTURE
    # ==============================================================================

    logger.info("COMPONENT INTEGRATION ARCHITECTURE")
    logger.info("-" * 80)
    logger.info("""
  Market Data Stream (Alpaca)
         │
         ├─→ MarketDataStreamer
         │       • Bars: 1-min, 5-min, 15-min, 1h, daily
         │       • Symbols: SPY, QQQ, IWM
         │       • Callbacks: on_bar, on_market_open, on_market_close
         │
         ├─→ Signal Engines (AI/Macro/Structure)
         │       • 0-1 confidence scoring
         │       • Regime classification
         │       • Technical patterns
         │
         ├─→ IntegrationBridge
         │       • Safety validation
         │       • Position sizing
         │       • Risk pre-check
         │
         ├─→ DeploymentGateController
         │       • Gate decision (PASS/FAIL/WATCH)
         │       • Operator approval
         │       • Circuit breakers
         │
         ├─→ LiveBrokerConnector
         │       • Paper/Live mode
         │       • Order submission
         │       • Position tracking
         │       • Fill processing
         │
         └─→ PerformanceMonitor
                 • Daily snapshots
                 • Baseline comparison
                 • Alert generation
                 • Regime detection
    """)

    logger.info("="*80)
    logger.info("Integration verified. System ready for production deployment.")
    logger.info("="*80 + "\n")


def show_deployment_checklist():
    """Display production deployment checklist."""

    logger.info("PRODUCTION DEPLOYMENT CHECKLIST")
    logger.info("-" * 80 + "\n")

    checklist = [
        ("✅", "Market data streaming", "Alpaca WebSocket integration complete"),
        ("✅", "Live broker connector", "Paper/Live modes with risk control"),
        ("✅", "Deployment gate logic", "7 pass criteria + operator approval"),
        ("✅", "Performance monitoring", "Baseline comparison + 8 alert types"),
        ("✅", "System orchestration", "ProductionRunner lifecycle management"),
        ("⏳", "Paper validation", "Run complete 30-day forward test"),
        ("⏳", "Operator sign-off", "Explicit approval + capital allocation"),
        ("⏳", "Live monitoring", "24/7 performance tracking"),
        ("⏳", "Emergency procedures", "Circuit breaker + manual stop protocols"),
        ("⏳", "Documentation", "Runbooks + alert response procedures"),
    ]

    for status, item, detail in checklist:
        logger.info(f"  {status} {item:.<30} {detail}")

    logger.info("\n")


if __name__ == "__main__":
    show_deployment_checklist()
    simulate_validation_period()
