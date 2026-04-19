import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class AlgoDetector:
    """Detect algorithmic manipulation: false breakouts, stop hunts, traps."""

    async def detect(self, symbol: str, candles: List[Dict]) -> Dict[str, Any]:
        """
        Detect algo manipulation patterns.

        Returns:
        {
            "market_state": "ACCUMULATION | MANIPULATION | DISTRIBUTION | TRENDING",
            "detections": [
                {
                    "type": "FALSE_BREAKOUT | STOP_HUNT | OTE_TRAP | DEEP_SWEEP | JUDAS",
                    "severity": 0.0-1.0,
                    "description": str
                }
            ]
        }
        """
        try:
            if len(candles) < 5:
                return {"market_state": "UNKNOWN", "detections": []}

            detections = []

            # Check for false breakouts
            false_breakout = self._detect_false_breakout(candles)
            if false_breakout:
                detections.append(false_breakout)

            # Check for stop hunts
            stop_hunt = self._detect_stop_hunt(candles)
            if stop_hunt:
                detections.append(stop_hunt)

            # Check for OTE trap
            ote_trap = self._detect_ote_trap(candles)
            if ote_trap:
                detections.append(ote_trap)

            # Classify market state
            market_state = self._classify_market_state(candles)

            return {
                "symbol": symbol,
                "market_state": market_state,
                "detections": detections,
                "risk_level": self._assess_risk(detections),
            }
        except Exception as e:
            logger.error(f"Algo detection error: {e}")
            raise

    def _detect_false_breakout(self, candles: List[Dict]) -> Dict | None:
        """False breakout: breaks resistance/support, reverses in 2-5 candles."""
        if len(candles) < 7:
            return None

        # Check last 5 candles for a reversal pattern
        high5 = max([c["high"] for c in candles[-5:-1]])
        if candles[-1]["close"] < high5 * 0.99:  # Reversed below high
            return {
                "type": "FALSE_BREAKOUT",
                "severity": 0.85,
                "description": "Price broke resistance but reversed sharply",
                "trap_level": high5,
            }

        return None

    def _detect_stop_hunt(self, candles: List[Dict]) -> Dict | None:
        """Stop hunt: tags swing high/low with volume spike, reverses."""
        if len(candles) < 4:
            return None

        prev_high = max([c["high"] for c in candles[:-3]])
        current = candles[-1]

        # High volume tag of swing + reversal
        if (
            current["high"] > prev_high * 0.995
            and current["volume"]
            > sum([c["volume"] for c in candles[:-1]]) / len(candles[:-1]) * 1.5
        ):
            if current["close"] < current["high"] * 0.99:
                return {
                    "type": "STOP_HUNT",
                    "severity": 0.80,
                    "description": "Spike to previous swing with high volume, then reversal",
                    "hunt_level": prev_high,
                }

        return None

    def _detect_ote_trap(self, candles: List[Dict]) -> Dict | None:
        """OTE trap: Price retraces to 0.618-0.705 Fibonacci level, bounces."""
        if len(candles) < 10:
            return None

        # Simple implementation: check if retracement is in Fib zone
        low = min([c["low"] for c in candles[-10:]])
        high = max([c["high"] for c in candles[-10:]])
        range_size = high - low

        fib_618 = high - (range_size * 0.618)
        fib_705 = high - (range_size * 0.705)

        current = candles[-1]
        if fib_705 <= current["close"] <= fib_618:
            return {
                "type": "OTE_TRAP",
                "severity": 0.75,
                "description": "Price in Golden Ratio retracement zone (potential trap)",
                "zone": (fib_705, fib_618),
            }

        return None

    def _classify_market_state(self, candles: List[Dict]) -> str:
        """Classify market into 4 states."""
        avg_volume = (
            sum([c["volume"] for c in candles[-20:]]) / min(20, len(candles)) if candles else 0
        )
        closes = [c["close"] for c in candles[-20:]]

        volatility = max(closes) - min(closes) if closes else 0
        recent_trend = (
            "UP" if closes[-1] > closes[0] else "DOWN" if closes[0] > closes[-1] else "FLAT"
        )

        if volatility < 0.5 and candles[-1]["volume"] < avg_volume:
            return "ACCUMULATION"
        elif volatility > 2.0:
            return "MANIPULATION"
        elif candles[-1]["volume"] > avg_volume * 1.5 and recent_trend != "FLAT":
            return "DISTRIBUTION"
        else:
            return "TRENDING"

    def _assess_risk(self, detections: List[Dict]) -> str:
        """Assess overall risk from detections."""
        if not detections:
            return "LOW"
        severity = sum([d["severity"] for d in detections]) / len(detections)
        if severity > 0.80:
            return "HIGH"
        elif severity > 0.65:
            return "MEDIUM"
        else:
            return "LOW"
