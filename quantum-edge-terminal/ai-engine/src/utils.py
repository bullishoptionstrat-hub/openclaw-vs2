import json
from datetime import datetime


def format_trade_summary(signals: list) -> str:
    """Format trade signals into a readable summary."""
    if not signals:
        return "No signals generated"

    buy_signals = [s for s in signals if s["signal_type"] == "BUY"]
    sell_signals = [s for s in signals if s["signal_type"] == "SELL"]

    summary = f"""
    📊 QUANTUM EDGE - Daily Signal Summary
    Generated: {datetime.now().isoformat()}
    
    ✅ BUY Signals: {len(buy_signals)}
    ❌ SELL Signals: {len(sell_signals)}
    
    Total Active: {len(signals)}
    Avg Confidence: {sum([s["confidence"] for s in signals]) / len(signals) * 100:.1f}%
    """

    return summary.strip()


def calculate_risk_metrics(signals: list) -> dict:
    """Calculate portfolio risk metrics from signals."""
    total_risk = sum([1 - s["confidence"] for s in signals])
    avg_risk_reward = (
        sum([s.get("risk_reward", 0) for s in signals]) / len(signals) if signals else 0
    )

    return {
        "total_portfolio_risk": total_risk,
        "avg_risk_reward_ratio": avg_risk_reward,
        "max_drawdown_estimated": "2.5%",  # Placeholder
        "win_rate_expected": "65%",  # Placeholder
    }
