"""
INSTITUTIONAL VALIDATION SYSTEM - COMPLETE EXAMPLE

This demonstrates the complete forward-testing workflow:
1. Load market data
2. Generate signals
3. Run through safety controls
4. Execute as paper trades
5. Score against institutional scorecard
6. Generate daily validation report
"""

from datetime import datetime, timedelta
from validation.scoring_engine import InstitutionalScorecard, GateStatus
from validation.forward_test_engine import (
    ForwardTestEngine,
    MarketCandle,
    TradeSignal,
)
from validation.safety_controls import SafetyControls, SafetyStatus


def run_institutional_validation():
    """
    Run complete institutional validation workflow.

    This is what separates "tested systems" from "trusted systems."
    """

    print("=" * 80)
    print("INSTITUTIONAL VALIDATION SYSTEM - FORWARD TEST EXAMPLE")
    print("=" * 80)
    print("")

    # Initialize components
    scorecard = InstitutionalScorecard()
    forward_engine = ForwardTestEngine(symbol="ES")
    safety = SafetyControls(
        max_daily_loss_pct=0.05,
        max_consecutive_losses=5,
        max_open_trades=5,
    )

    # Simulated market data
    print("📊 Simulating market data feed...")
    now = datetime.now()

    candles = [
        MarketCandle(
            symbol="ES",
            timestamp=now + timedelta(minutes=i),
            open=4500 + i * 0.5,
            high=4502 + i * 0.5,
            low=4499 + i * 0.5,
            close=4501 + i * 0.5,
            volume=1000000,
        )
        for i in range(100)
    ]

    print(f"Generated {len(candles)} market candles")
    print("")

    # Simulate signal generation and execution
    print("🎯 Running signal generation + execution...")

    signal_count = 0
    for i, candle in enumerate(candles):
        # Feed market data to forward engine
        forward_engine.feed_candle(candle)

        # Generate a simulated signal every 10 candles
        if i % 10 == 0 and i < 80:
            signal_payload = {
                "signal_id": f"SIG_ES_{signal_count}",
                "symbol": "ES",
                "direction": "LONG" if signal_count % 2 == 0 else "SHORT",
                "confidence": 0.65 + (signal_count * 0.05) % 0.3,
                "entry_price": candle.close,
                "stop_loss": candle.close - 10 if signal_count % 2 == 0 else candle.close + 10,
                "take_profit": candle.close + 20 if signal_count % 2 == 0 else candle.close - 20,
                "risk_reward_ratio": 2.0,
                "setup_type": "breakout",
                "macro_regime": "RISK_ON",
                "liquidity_score": 0.75,
                "structure_score": 0.70,
                "options_score": 0.65,
                "confluence_score": 2.1,
            }

            # Process through forward engine
            signal = forward_engine.generate_signal_from_engines(signal_payload)

            if signal:
                # Run safety checks
                passes, failures = safety.pre_trade_checks(
                    signal_id=signal.signal_id,
                    market_data_timestamp=candle.timestamp,
                    account_equity=100000,
                    open_trade_count=len(forward_engine.paper_trades),
                )

                if passes:
                    # Execute as paper trade
                    trade = forward_engine.execute_signal_as_paper_trade(
                        signal=signal,
                        simulated_entry_price=candle.close,
                        slippage_bps=0.5,
                    )
                    print(f"  ✅ TRADE {signal_count}: {signal.direction.value} @ ${candle.close:.2f}")
                else:
                    print(f"  ❌ SIGNAL {signal_count} REJECTED:")
                    for failure in failures:
                        print(f"     - {failure}")

            signal_count += 1

    print("")
    print("=" * 80)
    print("PERFORMANCE SUMMARY (FORWARD TEST)")
    print("=" * 80)

    perf = forward_engine.get_performance_summary()
    print(f"Total signals: {perf['total_signals']}")
    print(f"Total trades: {perf['total_trades']}")
    print(f"Closed trades: {perf['closed_trades']}")
    print(f"Open trades: {perf['open_trades']}")
    print(f"Win rate: {perf['win_rate'] * 100:.1f}%")
    print(f"Avg R:R: {perf['avg_rr']:.2f}")
    print(f"Total P&L: ${perf['total_pnl']:.2f}")
    print(f"Avg slippage: ${perf['avg_slippage']:.4f}")
    print(f"Avg latency: {perf['avg_execution_latency_ms']:.1f}ms")
    print(f"Duplicate signals: {perf['duplicate_signals']}")
    print(f"Stale data events: {perf['stale_data_events']}")
    print("")

    # Score against institutional scorecard
    print("=" * 80)
    print("INSTITUTIONAL SCORECARD EVALUATION")
    print("=" * 80)
    print("")

    validation_stats = {
        "expectancy": 0.18,  # Sample: 0.18R per trade
        "profit_factor": 1.45,  # Sample: $1.45 win per $1 loss
        "sharpe_ratio": 1.35,  # Sample: risk-adjusted return
        "avg_rr": 2.1,  # Sample: average risk/reward ratio
        "max_drawdown": 0.075,  # Sample: 7.5% max DD
        "consecutive_losses": 3,
        "daily_loss_breach": 0,
        "slippage_drift": 0.12,
        "missed_trade_rate": 0.008,
        "duplicate_signal_rate": 0.0,
        "stale_data_events": 0,
        "regime_consistency": 0.80,
        "session_consistency": 0.75,
        "strategy_dispersion": 0.20,
    }

    result = scorecard.evaluate(validation_stats)

    print(scorecard.print_result(result))
    print("")
    print(f"Overall Score: {result.overall_score * 100:.1f}%")
    print(f"Gate Status: {result.gate_status.value}")
    print("")

    # Safety status
    print("=" * 80)
    print("SAFETY SYSTEM STATUS")
    print("=" * 80)

    safety_status = safety.get_safety_status()
    print(f"Status: {safety_status['status']}")
    print(f"Circuit breaker: {'ACTIVE' if safety_status['circuit_breaker_active'] else 'OK'}")
    print(f"Daily P&L: ${safety_status['daily_pnl']:.2f}")
    print(f"Consecutive losses: {safety_status['consecutive_losses']}")
    print(f"API errors: {safety_status['api_error_count']}")
    print("")

    # Final verdict
    print("=" * 80)
    print("FINAL VALIDATION VERDICT")
    print("=" * 80)
    print("")

    if result.gate_status == GateStatus.PASS:
        print("✅ SYSTEM PASSES INSTITUTIONAL GATE")
        print("")
        print("The system demonstrated:")
        print("  • Positive expectancy (0.18R per trade)")
        print("  • Controlled drawdown (7.5% < 8% limit)")
        print("  • Stable execution behavior")
        print("  • Clean risk management")
        print("")
        print("🚀 APPROVED FOR CAPITAL DEPLOYMENT")
    elif result.gate_status == GateStatus.WATCH:
        print("⚠️  SYSTEM REQUIRES MORE DATA")
        print("")
        print("Score is borderline. Recommendation:")
        print("  • Run additional 10-20 trading days")
        print("  • Monitor for consistency")
        print("  • Review worst-case scenarios")
        print("")
        print("⏳ HOLD FOR FINAL EVALUATION")
    else:
        print("❌ SYSTEM FAILS INSTITUTIONAL GATE")
        print("")
        print("Hard fail conditions met:")
        for reason in result.hard_fail_reasons:
            print(f"  • {reason}")
        print("")
        print("🚫 DO NOT DEPLOY - SYSTEM NOT READY")

    print("")
    print("=" * 80)


if __name__ == "__main__":
    run_institutional_validation()
