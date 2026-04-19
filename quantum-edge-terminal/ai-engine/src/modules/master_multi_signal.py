import logging
from typing import List, Dict, Any, Optional
import statistics

logger = logging.getLogger(__name__)


class MasterMultiSignalValidator:
    """
    MASTER TRADING SYSTEM - Combines 2 Strategies for Confirmation

    Strategies:
    1. FRACTAL: 4-candle pattern validation (high accuracy, lower frequency)
    2. FIB: Institutional manipulation legs with Fibonacci levels (confirmation)

    Modes:
    - FRACTAL_ONLY: Pure 4-candle patterns (primary, currently deployed)
    - FIB_ONLY: Fibonacci institutional levels (secondary)
    - DUAL_CONFIRMATION: Only take trades when BOTH strategies align
    - BEST_OF_BOTH: Take either signal, use best risk/reward
    - SMART_BLEND: Use FRACTAL as primary, FIB for additional confirmation

    This creates a robust, multi-layered trading system with reduced false signals.
    """

    def __init__(
        self,
        mode: str = "SMART_BLEND",
        fractal_fix_enabled: bool = True,  # Approach 1: Tighter stops
        min_fib_confidence: float = 0.70,
        min_fractal_confidence: float = 0.85,
    ):
        """
        Args:
            mode: Trading mode (FRACTAL_ONLY, FIB_ONLY, DUAL_CONFIRMATION, BEST_OF_BOTH, SMART_BLEND)
            fractal_fix_enabled: Apply 30% tighter stops (Approach 1)
            min_fib_confidence: Minimum confidence for Fib signals
            min_fractal_confidence: Minimum confidence for Fractal signals
        """
        self.mode = mode
        self.fractal_fix_enabled = fractal_fix_enabled
        self.min_fib_confidence = min_fib_confidence
        self.min_fractal_confidence = min_fractal_confidence

    async def validate(
        self,
        candles: List[Dict],
        fractal_result: Optional[Dict] = None,
        fib_result: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Multi-signal validation combining Fractal + Fib strategies.

        Args:
            candles: List of candles
            fractal_result: Result from FractalValidator (pre-computed)
            fib_result: Result from EnhancedFibManipulationValidator (pre-computed)

        Returns:
            Combined signal with:
            - valid: True if signal passes mode criteria
            - pattern: Trade direction
            - entry: Best entry from combined signals
            - stop_loss: Best stop loss
            - take_profit: Best target
            - risk_reward: Best RR
            - signal_sources: Which strategies triggered
            - confidence: Combined confidence score
        """
        try:
            signals = []

            # Collect Fractal signals
            if fractal_result and fractal_result.get("valid"):
                if fractal_result.get("confidence", 0) >= self.min_fractal_confidence:
                    signals.append(("FRACTAL", fractal_result))

            # Collect Fib signals
            if fib_result and fib_result.get("valid"):
                if fib_result.get("confidence", 0) >= self.min_fib_confidence:
                    signals.append(("FIB", fib_result))

            # Apply mode logic
            if self.mode == "FRACTAL_ONLY":
                if not any(s[0] == "FRACTAL" for s in signals):
                    return {"valid": False, "error": "No FRACTAL signal"}
                result = signals[0][1]
                signal_source = "FRACTAL"

            elif self.mode == "FIB_ONLY":
                if not any(s[0] == "FIB" for s in signals):
                    return {"valid": False, "error": "No FIB signal"}
                result = next(s[1] for s in signals if s[0] == "FIB")
                signal_source = "FIB"

            elif self.mode == "DUAL_CONFIRMATION":
                # Both signals must trigger
                fractal_signal = next((s[1] for s in signals if s[0] == "FRACTAL"), None)
                fib_signal = next((s[1] for s in signals if s[0] == "FIB"), None)

                if not (fractal_signal and fib_signal):
                    return {"valid": False, "error": "No dual signal confirmation"}

                if fractal_signal.get("pattern") != fib_signal.get("pattern"):
                    return {"valid": False, "error": "Pattern mismatch between signals"}

                # Use FRACTAL as primary (better accuracy)
                result = fractal_signal
                signal_source = "DUAL_CONFIRMED"

            elif self.mode == "BEST_OF_BOTH":
                # Take whichever has better risk/reward
                if not signals:
                    return {"valid": False, "error": "No valid signals"}

                best_signal = max(signals, key=lambda s: s[1].get("risk_reward", 0))
                signal_source = best_signal[0]
                result = best_signal[1]

            elif self.mode == "SMART_BLEND":
                # Fractal is primary, Fib is confirmation
                fractal_signal = next((s[1] for s in signals if s[0] == "FRACTAL"), None)
                fib_signal = next((s[1] for s in signals if s[0] == "FIB"), None)

                if not fractal_signal:
                    return {"valid": False, "error": "No FRACTAL signal (primary required)"}

                result = fractal_signal
                signal_source = "FRACTAL"

                # If Fib confirms, boost confidence
                if fib_signal and fib_signal.get("pattern") == fractal_signal.get("pattern"):
                    signal_source = "FRACTAL+FIB_CONFIRMED"
                    result["confidence"] = min(0.99, result.get("confidence", 0.90) + 0.05)

            else:
                return {"valid": False, "error": f"Unknown mode: {self.mode}"}

            # Apply Approach 1 fix if enabled (tighter stops)
            if self.fractal_fix_enabled and signal_source.startswith("FRACTAL"):
                entry = result["entry"]
                sl_orig = result["stop_loss"]
                sl_fixed = entry + (sl_orig - entry) * 0.7  # 30% tighter
                result = dict(result)
                result["stop_loss"] = sl_fixed

                # Recalculate RR
                risk = abs(entry - sl_fixed)
                reward = abs(result["take_profit"] - entry)
                result["risk_reward"] = reward / risk if risk > 0 else 0

            # Final validation
            result["valid"] = True
            result["signal_sources"] = signal_source
            result["combined_confidence"] = result.get("confidence", 0.90)

            return result

        except Exception as e:
            logger.error(f"Multi-signal validation error: {e}")
            return {"valid": False, "error": str(e)}


class StrategyPerformanceTracker:
    """Track and optimize multi-strategy performance."""

    def __init__(self):
        self.fractal_trades = []
        self.fib_trades = []
        self.dual_trades = []
        self.rejected_trades = []

    def record_trade(self, trade: Dict, source: str, outcome: str, pnl: float):
        """Record trade outcome."""
        record = {
            "source": source,
            "outcome": outcome,
            "pnl": pnl,
            "rr": trade.get("risk_reward", 0),
        }

        if "FRACTAL" in source and "FIB" not in source:
            self.fractal_trades.append(record)
        elif "FIB" in source and "FRACTAL" not in source:
            self.fib_trades.append(record)
        elif "FRACTAL" in source and "FIB" in source:
            self.dual_trades.append(record)

    def get_stats(self, source_filter: str = None) -> Dict[str, Any]:
        """Get performance statistics."""
        if source_filter == "FRACTAL":
            trades = self.fractal_trades
        elif source_filter == "FIB":
            trades = self.fib_trades
        elif source_filter == "DUAL":
            trades = self.dual_trades
        else:
            trades = self.fractal_trades + self.fib_trades + self.dual_trades

        if not trades:
            return {}

        wins = [t for t in trades if t["outcome"] == "WIN"]
        losses = [t for t in trades if t["outcome"] == "LOSS"]

        total_pnl = sum(t["pnl"] for t in trades)
        win_pnl = sum(t["pnl"] for t in wins) if wins else 0
        loss_pnl = abs(sum(t["pnl"] for t in losses)) if losses else 1

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(trades) * 100 if trades else 0,
            "profit_factor": win_pnl / loss_pnl if loss_pnl > 0 else 0,
            "total_pnl": total_pnl,
            "expectancy": total_pnl / len(trades) if trades else 0,
        }
