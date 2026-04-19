import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class FibManipulationValidator:
    """
    Institutional Manipulation Leg + Fibonacci Strategy Validator

    Detects significant price moves (institutional manipulation legs),
    waits for 0.62 Fibonacci retracement, enters at that level,
    targets 1.618 Fibonacci extension as take profit.

    Logic:
    1. Identify manipulation leg: significant price swing (swing high/low)
    2. Calculate 0.62 retracement level (entry zone)
    3. Wait for price to reach/touch 0.62 level
    4. Enter when 0.62 is touched with confirmation
    5. Target: 1.618 extension from the manipulation leg range
    """

    def __init__(self, min_leg_points: float = 2.0):
        """
        Args:
            min_leg_points: Minimum price movement to identify as manipulation leg
        """
        self.min_leg_points = min_leg_points

    async def validate(self, candles: List[Dict]) -> Dict[str, Any]:
        """
        Validate institutional manipulation + Fib retracement setup.

        Args:
            candles: List of 4+ candles with OHLC data

        Returns:
            {
                "valid": bool,
                "pattern": "MANIP_BUY | MANIP_SELL",
                "confidence": 0.0-1.0,
                "entry": price at 0.62 retracement,
                "stop_loss": price below/above entry,
                "take_profit": 1.618 extension target,
                "risk_reward": ratio,
                "manipulation_leg": {
                    "start_price": initial price,
                    "end_price": leg completion price,
                    "direction": "UP | DOWN",
                    "magnitude": points moved,
                    "fib_0618": 0.618 level,
                    "fib_0786": 0.786 level,
                    "fib_1618": 1.618 extension
                }
            }
        """
        try:
            if len(candles) < 5:
                return {"valid": False, "error": "Insufficient candles"}

            # Analyze last 10-20 candles to identify manipulation leg
            analysis_window = candles[-20:]

            # Find swing high and swing low (manipulation legs)
            swing_high = max(c["high"] for c in analysis_window)
            swing_low = min(c["low"] for c in analysis_window)

            swing_high_idx = next(
                i for i, c in enumerate(analysis_window) if c["high"] == swing_high
            )
            swing_low_idx = next(i for i, c in enumerate(analysis_window) if c["low"] == swing_low)

            # Determine manipulation leg direction
            if swing_high_idx > swing_low_idx:
                # Swing high came after swing low = UP manipulation leg
                is_upleg = True
                leg_start = swing_low
                leg_end = swing_high
            else:
                # Swing low came after swing high = DOWN manipulation leg
                is_upleg = False
                leg_start = swing_high
                leg_end = swing_low

            leg_magnitude = abs(leg_end - leg_start)

            # Filter: manipulation leg must be significant
            if leg_magnitude < self.min_leg_points:
                return {"valid": False, "error": f"Leg too small: {leg_magnitude}"}

            # Calculate current price vs manipulation leg
            current = candles[-1]["close"]

            # Calculate Fibonacci levels
            if is_upleg:
                # UP leg: retracements below the leg end
                fib_0618 = leg_end - (leg_magnitude * 0.618)  # Retracement level
                fib_0786 = leg_end - (leg_magnitude * 0.786)
                fib_1618 = leg_end + (leg_magnitude * 1.618)  # Extension target

                # Check if price is near/at 0.62 retracement (entry zone)
                retracement_zone_low = fib_0618 - (leg_magnitude * 0.05)  # 5% tolerance
                retracement_zone_high = fib_0618 + (leg_magnitude * 0.05)

                if not (retracement_zone_low <= current <= retracement_zone_high):
                    return {
                        "valid": False,
                        "error": f"Not at 0.62 level. Current: {current}, Target: {fib_0618}",
                    }

                # Setup: BUY at 0.62, SL below 0.786, TP at 1.618
                entry = fib_0618
                stop_loss = fib_0786 - (leg_magnitude * 0.05)  # Slightly below 0.786
                take_profit = fib_1618
                pattern = "MANIP_BUY"

            else:
                # DOWN leg: retracements above the leg end
                fib_0618 = leg_end + (leg_magnitude * 0.618)  # Retracement level
                fib_0786 = leg_end + (leg_magnitude * 0.786)
                fib_1618 = leg_end - (leg_magnitude * 1.618)  # Extension target

                # Check if price is near/at 0.62 retracement (entry zone)
                retracement_zone_low = fib_0618 - (leg_magnitude * 0.05)
                retracement_zone_high = fib_0618 + (leg_magnitude * 0.05)

                if not (retracement_zone_low <= current <= retracement_zone_high):
                    return {
                        "valid": False,
                        "error": f"Not at 0.62 level. Current: {current}, Target: {fib_0618}",
                    }

                # Setup: SELL at 0.62, SL above 0.786, TP at 1.618
                entry = fib_0618
                stop_loss = fib_0786 + (leg_magnitude * 0.05)  # Slightly above 0.786
                take_profit = fib_1618
                pattern = "MANIP_SELL"

            # Calculate risk/reward
            risk = abs(entry - stop_loss)
            reward = abs(take_profit - entry)
            risk_reward = reward / risk if risk > 0 else 0

            return {
                "valid": True,
                "pattern": pattern,
                "confidence": 0.85,
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": risk_reward,
                "manipulation_leg": {
                    "start_price": leg_start,
                    "end_price": leg_end,
                    "direction": "UP" if is_upleg else "DOWN",
                    "magnitude": leg_magnitude,
                    "fib_0618": fib_0618,
                    "fib_0786": fib_0786,
                    "fib_1618": fib_1618,
                },
                "candles": {"analysis_window": analysis_window, "current": candles[-1]},
            }

        except Exception as e:
            logger.error(f"Fib manipulation validation error: {e}")
            return {"valid": False, "error": str(e)}


class FibManipulationBacktester:
    """Backtest support for Fib Manipulation strategy."""

    @staticmethod
    def check_retracement_touch(
        candles: List[Dict], start_idx: int, fib_level: float, tolerance: float = 0.05
    ) -> Optional[int]:
        """
        Find index where price touches the Fib level.

        Args:
            candles: List of candles
            start_idx: Starting candle index
            fib_level: Fibonacci level to check
            tolerance: Tolerance percentage for "touching" the level

        Returns:
            Index where level was touched, or None
        """
        for i in range(start_idx, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]

            # Check if candle touches the level (within tolerance)
            if low <= fib_level <= high:
                return i

        return None
