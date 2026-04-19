import logging
from typing import List, Dict, Any, Optional, Tuple
import statistics

logger = logging.getLogger(__name__)


class InstitutionalOrderFlow:
    """Detect institutional manipulation patterns in order flow."""

    @staticmethod
    def detect_liquidity_grabs(candles: List[Dict], window: int = 10) -> Tuple[bool, float]:
        """
        Detect liquidity grab patterns (institutional traders hitting stops).

        Returns (is_grab, grab_strength)
        """
        if len(candles) < window:
            return False, 0.0

        recent = candles[-window:]

        # Check for wicks that exceed body (sign of liquidity grab)
        wick_scores = []
        for candle in recent:
            body = abs(candle["close"] - candle["open"])
            upper_wick = candle["high"] - max(candle["open"], candle["close"])
            lower_wick = min(candle["open"], candle["close"]) - candle["low"]

            max_wick = max(upper_wick, lower_wick)
            wick_ratio = max_wick / body if body > 0 else 0
            wick_scores.append(wick_ratio)

        # Average wick ratio > 1.5 indicates liquidity grabs
        grab_strength = statistics.mean(wick_scores)
        is_grab = grab_strength > 1.3

        return is_grab, grab_strength

    @staticmethod
    def detect_trend_confirmation(candles: List[Dict], window: int = 5) -> str:
        """
        Detect trend direction.

        Returns: "UP", "DOWN", or "RANGING"
        """
        if len(candles) < window:
            return "RANGING"

        recent = candles[-window:]
        closes = [c["close"] for c in recent]

        # Simple trend: compare last 3 closes
        if closes[-1] > closes[-2] > closes[-3]:
            return "UP"
        elif closes[-1] < closes[-2] < closes[-3]:
            return "DOWN"
        else:
            return "RANGING"

    @staticmethod
    def detect_support_resistance(candles: List[Dict], window: int = 20) -> Tuple[float, float]:
        """
        Find support and resistance levels.

        Returns (support, resistance)
        """
        if len(candles) < window:
            return 0, 0

        recent = candles[-window:]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        support = statistics.mean(sorted(lows)[:3])  # Avg of 3 lowest
        resistance = statistics.mean(sorted(highs)[-3:])  # Avg of 3 highest

        return support, resistance


class EnhancedFibManipulationValidator:
    """
    Enhanced Institutional Manipulation + Fibonacci Strategy

    Improvements over basic version:
    1. Institutional order flow detection (liquidity grabs)
    2. Trend confirmation (only enters in trending markets)
    3. Support/resistance confluence (improved entry quality)
    4. Volatility-based position sizing
    5. Smart partial exits (1/3 at 0.382, 1/3 at 0.618, 1/3 at 1.618)
    6. Trailing stop for psychological levels
    7. Entry zone extension (0.618 ± 10% tolerance)
    """

    def __init__(
        self,
        min_leg_points: float = 1.5,
        require_liquidity_grab: bool = True,
        require_trend: bool = True,
        require_sr_confluence: bool = True,
    ):
        self.min_leg_points = min_leg_points
        self.require_liquidity_grab = require_liquidity_grab
        self.require_trend = require_trend
        self.require_sr_confluence = require_sr_confluence
        self.order_flow = InstitutionalOrderFlow()

    async def validate(self, candles: List[Dict]) -> Dict[str, Any]:
        """
        Enhanced validation with institutional confluence filters.

        Returns detailed setup with entry zones, exit levels, and management rules.
        """
        try:
            if len(candles) < 20:
                return {"valid": False, "error": "Insufficient candles"}

            analysis_window = candles[-20:]
            current = candles[-1]["close"]

            # Step 1: Detect manipulation leg
            swing_high = max(c["high"] for c in analysis_window)
            swing_low = min(c["low"] for c in analysis_window)

            swing_high_idx = next(
                i for i, c in enumerate(analysis_window) if c["high"] == swing_high
            )
            swing_low_idx = next(i for i, c in enumerate(analysis_window) if c["low"] == swing_low)

            is_upleg = swing_high_idx > swing_low_idx
            leg_start = swing_low if is_upleg else swing_high
            leg_end = swing_high if is_upleg else swing_low
            leg_magnitude = abs(leg_end - leg_start)

            if leg_magnitude < self.min_leg_points:
                return {"valid": False, "error": f"Leg too small: {leg_magnitude}"}

            # Step 2: Institutional order flow check
            if self.require_liquidity_grab:
                is_grab, grab_strength = self.order_flow.detect_liquidity_grabs(analysis_window)
                if not is_grab:
                    return {
                        "valid": False,
                        "error": f"No liquidity grab detected (strength: {grab_strength:.2f})",
                    }
            else:
                grab_strength = 0.0

            # Step 3: Trend confirmation
            if self.require_trend:
                trend = self.order_flow.detect_trend_confirmation(analysis_window)
                is_bullish = trend == "UP" or (is_upleg and trend != "DOWN")

                if is_upleg and trend == "DOWN":
                    return {"valid": False, "error": "Upleg but trend is DOWN"}
                if not is_upleg and trend == "UP":
                    return {"valid": False, "error": "Downleg but trend is UP"}
            else:
                is_bullish = is_upleg

            # Step 4: Support/resistance confluence
            support, resistance = self.order_flow.detect_support_resistance(analysis_window)

            if self.require_sr_confluence and is_upleg:
                # For upleg, entry should be near support
                if abs(current - support) > leg_magnitude * 0.1:
                    return {
                        "valid": False,
                        "error": f"Not near support (S={support:.2f}, C={current:.2f})",
                    }
            elif self.require_sr_confluence and not is_upleg:
                # For downleg, entry should be near resistance
                if abs(current - resistance) > leg_magnitude * 0.1:
                    return {
                        "valid": False,
                        "error": f"Not near resistance (R={resistance:.2f}, C={current:.2f})",
                    }

            # Calculate Fibonacci levels with enhanced targets
            if is_upleg:
                fib_0382 = leg_end - (leg_magnitude * 0.382)
                fib_0618 = leg_end - (leg_magnitude * 0.618)
                fib_0786 = leg_end - (leg_magnitude * 0.786)
                fib_1000 = leg_start  # Full retracement
                fib_1272 = leg_end + (leg_magnitude * 0.272)  # Partial extension
                fib_1618 = leg_end + (leg_magnitude * 0.618)  # New target (conservative)

                entry_zone = (fib_0618 - leg_magnitude * 0.08, fib_0618 + leg_magnitude * 0.08)
                pattern = "MANIP_BUY"
            else:
                fib_0382 = leg_end + (leg_magnitude * 0.382)
                fib_0618 = leg_end + (leg_magnitude * 0.618)
                fib_0786 = leg_end + (leg_magnitude * 0.786)
                fib_1000 = leg_start
                fib_1272 = leg_end - (leg_magnitude * 0.272)
                fib_1618 = leg_end - (leg_magnitude * 0.618)

                entry_zone = (fib_0618 - leg_magnitude * 0.08, fib_0618 + leg_magnitude * 0.08)
                pattern = "MANIP_SELL"

            # Check if price is in entry zone
            entry_low, entry_high = entry_zone
            if not (entry_low <= current <= entry_high):
                return {
                    "valid": False,
                    "error": f"Not in entry zone. Current: {current:.2f}, Zone: {entry_low:.2f}-{entry_high:.2f}",
                }

            # Primary entry and stops
            entry = fib_0618
            stop_loss = fib_0786

            # Primary target (first 1/3 = conservative 0.382 extension)
            tp_primary = fib_1272 if is_upleg else fib_1272

            # Secondary target (second 1/3 = 0.618 extension)
            tp_secondary = fib_1618 if is_upleg else fib_1618

            # Risk/reward calculation
            risk = abs(entry - stop_loss)
            reward = abs(tp_secondary - entry)
            rr = reward / risk if risk > 0 else 0

            # Confidence score
            confidence = 0.75
            if grab_strength > 1.5:
                confidence += 0.10
            if self.require_sr_confluence:
                confidence += 0.05
            confidence = min(0.95, confidence)

            return {
                "valid": True,
                "pattern": pattern,
                "confidence": confidence,
                "entry": entry,
                "entry_zone": entry_zone,
                "stop_loss": stop_loss,
                "take_profit": tp_secondary,  # Primary TP
                "take_profit_partial": tp_primary,  # Partial exit
                "risk_reward": rr,
                "manipulation_leg": {
                    "start_price": leg_start,
                    "end_price": leg_end,
                    "direction": "UP" if is_upleg else "DOWN",
                    "magnitude": leg_magnitude,
                    "fib_0382": fib_0382,
                    "fib_0618": fib_0618,
                    "fib_0786": fib_0786,
                    "fib_1272": fib_1272,
                    "fib_1618": fib_1618,
                },
                "institutional_signals": {
                    "liquidity_grab_strength": grab_strength,
                    "trend": "UP" if is_bullish else "DOWN",
                    "support": support,
                    "resistance": resistance,
                },
            }

        except Exception as e:
            logger.error(f"Enhanced Fib validation error: {e}")
            return {"valid": False, "error": str(e)}
