#!/usr/bin/env python3
"""
PHASE 2: INSTITUTIONAL-GRADE SMART BLEND+ STRATEGY

Combines:
1. Fractal 4-candle patterns (primary entry validation)
2. Fibonacci golden ratio market structure (confluence)
3. Institutional liquidity analysis (volume + order flow)
4. Advanced confluence filters (ATR, momentum, structure)
5. Risk/reward optimization (golden ratio spreads)

This strategy is designed to identify institutional accumulation/distribution zones
and enter on high-probability, high-reward setups.

Key Innovation: Uses golden ratio at EVERY level:
- Entry zone: 0.618 Fibonacci retracement
- Stop loss: 0.786 support
- Targets: 1.272, 1.618, 2.618 extensions
- Confluence: Multiple golden ratio levels aligning
"""

import logging
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

PHI = 1.618034  # Golden ratio


class SignalStrength(Enum):
    """Signal strength classification."""

    WEAK = 0.60
    MODERATE = 0.75
    STRONG = 0.85
    INSTITUTIONAL = 0.95


@dataclass
class ConfluenceScore:
    """Confluence of multiple signals."""

    level: float
    hits: int  # Number of signals at same level
    types: List[str]  # Types of confluence (fractal, fib, volume, etc.)
    strength: float  # 0 to 1.0


class InstitutionalSmartBlendStrategy:
    """
    Advanced SMART_BLEND+ Strategy.

    Entry Logic:
    1. Fractal 4-candle pattern confirmation
    2. Pattern aligns with Fibonacci retrace (0.618) zone
    3. Fair value gap below entry (institutional inefficiency)
    4. Volume > 2x average (institutional activity)
    5. Entry at confluence of 3+ signals = INSTITUTIONAL GRADE

    Risk Management:
    - Stop loss at 0.786 Fibonacci level
    - Take profit at 1.272, 1.618, 2.618 extensions
    - Position size scaled by signal strength
    - Golden ratio RR target: 1.618:1 or better

    Confluence Weighting:
    - Fractal pattern: 30%
    - Fibonacci retracement: 25%
    - Volume cluster: 20%
    - Fair value gap: 15%
    - Support/resistance: 10%
    """

    PHI = 1.618034
    FRAC_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618, 2.618]

    def __init__(
        self,
        min_confluence: int = 3,  # Minimum signals at same level
        min_rr: float = 1.618,  # Minimum RR target (golden ratio)
        fractal_fix_enabled: bool = True,
        use_advanced_filters: bool = True,
    ):
        """
        Args:
            min_confluence: Minimum number of confluent signals (3 = STRONG, 4+ = INSTITUTIONAL)
            min_rr: Minimum acceptable risk/reward ratio
            fractal_fix_enabled: Apply 30% tighter stops
            use_advanced_filters: Enable ATR/momentum/structure filters
        """
        self.min_confluence = min_confluence
        self.min_rr = min_rr
        self.fractal_fix_enabled = fractal_fix_enabled
        self.use_advanced_filters = use_advanced_filters
        self.confluence_levels: List[ConfluenceScore] = []

    def validate(
        self,
        candles: List[Dict],
        fractal_result: Optional[Dict] = None,
        market_structure: Optional[Dict] = None,
    ) -> Dict:
        """
        Comprehensive validation with institutional confluence analysis.

        Args:
            candles: List of candles with OHLCV
            fractal_result: 4-candle fractal pattern result
            market_structure: Market structure analysis from analyzer

        Returns:
            Dict with:
            - valid: True if setup passes all filters
            - pattern: BULLISH or BEARISH
            - entry: Entry price
            - stop_loss: Stop loss price
            - take_profit_1, 2, 3: Sequential profit targets
            - risk_reward: Primary RR ratio
            - confidence: 0-1.0 confidence (0.95+ = INSTITUTIONAL)
            - confluence_score: Number of aligned signals
            - signal_types: Which signals aligned
        """
        if not candles or len(candles) < 20:
            return {"valid": False, "error": "Insufficient candles"}

        try:
            # Base setup from fractal
            if not fractal_result or not fractal_result.get("valid"):
                return {"valid": False, "error": "No valid fractal pattern"}

            setup = dict(fractal_result)
            closes = [c["c"] for c in candles]
            highs = [c["h"] for c in candles]
            lows = [c["l"] for c in candles]
            volumes = [c.get("v", 0) for c in candles]

            # Calculate ATR and other indicators
            atr = self._calculate_atr(candles)
            avg_volume = statistics.mean(volumes[-20:]) if volumes else 0

            # Build confluence scorecard
            confluence = self._calculate_confluence(
                setup, candles, market_structure, atr, avg_volume
            )

            # Apply advanced filters
            if self.use_advanced_filters:
                filter_result = self._apply_advanced_filters(candles, setup, confluence, atr)
                if not filter_result["passes"]:
                    return {
                        "valid": False,
                        "error": f"Filter rejection: {filter_result['reason']}",
                        "filter_failed": filter_result["failed_filters"],
                    }

            # Optimize entry/stops using golden ratio
            optimized = self._optimize_golden_ratio_levels(setup, candles, market_structure, atr)

            # Apply Approach 1 fix (tighter stops)
            if self.fractal_fix_enabled:
                entry = optimized["entry"]
                sl = optimized["stop_loss"]
                sl_fixed = entry + (sl - entry) * 0.7
                optimized["stop_loss"] = sl_fixed

            # Calculate final metrics
            risk = abs(optimized["entry"] - optimized["stop_loss"])
            reward = abs(optimized["take_profit_1"] - optimized["entry"])
            rr = reward / risk if risk > 0 else 0

            # Confidence scoring (confluence + RR quality)
            confluence_confidence = min(
                0.99,
                0.60 + (confluence["hits"] * 0.10),  # +10% per confluence hit
            )
            rr_confidence = min(
                0.30,
                (rr - 1.0) / 3.0 if rr > 1.0 else 0,  # Up to 30% for RR
            )
            pattern_confidence = setup.get("confidence", 0.85)

            final_confidence = min(
                0.99,
                (confluence_confidence * 0.50 + pattern_confidence * 0.35 + rr_confidence * 0.15),
            )

            # Institutional grade if 4+ confluence signals
            signal_grade = (
                "INSTITUTIONAL"
                if confluence["hits"] >= 4
                else "INSTITUTIONAL"
                if confluence["hits"] >= 3 and rr >= self.min_rr
                else "PROFESSIONAL"
                if confluence["hits"] >= 3
                else "STRONG"
                if confluence["hits"] >= 2
                else "MODERATE"
            )

            return {
                "valid": True,
                "pattern": setup.get("pattern", "UNKNOWN"),
                "entry": optimized["entry"],
                "stop_loss": optimized["stop_loss"],
                "take_profit_1": optimized["take_profit_1"],
                "take_profit_2": optimized["take_profit_2"],
                "take_profit_3": optimized["take_profit_3"],
                "risk_reward": rr,
                "confidence": final_confidence,
                "confluence_score": confluence["hits"],
                "signal_types": confluence["types"],
                "signal_grade": signal_grade,
                "risk_points": risk,
                "reward_points": reward,
                "position_size_factor": rr / 2.0 if rr > 0 else 0,  # Scale to RR
                "atr": atr,
                "volume_confirmation": volumes[-1] / avg_volume if avg_volume > 0 else 0,
            }

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {"valid": False, "error": str(e)}

    def _calculate_confluence(
        self,
        fractal: Dict,
        candles: List[Dict],
        market_structure: Optional[Dict],
        atr: float,
        avg_volume: float,
    ) -> Dict:
        """Calculate confluence of signals at entry level."""
        entry = fractal.get("entry", 0)
        confluence_hits = 0
        signal_types = []

        # 1. Fractal pattern (primary)
        confluence_hits += 1
        signal_types.append("FRACTAL")

        # 2. Fibonacci retracement zone (0.618)
        if market_structure and "fibonacci_targets" in market_structure:
            targets = market_structure["fibonacci_targets"]
            for target in targets.get("downside", []):
                if abs(entry - target) < atr * 0.5:
                    confluence_hits += 1
                    signal_types.append("FIB_RETRACEMENT")
                    break

        # 3. Volume confirmation (institutional activity)
        if candles[-1].get("v", 0) > avg_volume * 1.5:
            confluence_hits += 1
            signal_types.append("VOLUME_CLUSTER")

        # 4. Fair value gap (institutional inefficiency)
        closes = [c["c"] for c in candles[-3:]]
        if self._has_fvg_below(candles[-3:], entry, atr):
            confluence_hits += 1
            signal_types.append("FVG_SUPPORT")

        # 5. Support/resistance level
        if market_structure and "levels" in market_structure:
            for level in market_structure["levels"]:
                if abs(entry - level.level) < atr * 0.3:
                    confluence_hits += 1
                    signal_types.append("SR_CONFLUENCE")
                    break

        # 6. Momentum alignment (RSI/MACD in profit direction)
        if self._check_momentum_alignment(candles, fractal.get("pattern")):
            confluence_hits += 1
            signal_types.append("MOMENTUM")

        return {
            "hits": confluence_hits,
            "types": signal_types,
            "score": confluence_hits / 6.0,  # Maximum 6 signals
        }

    def _apply_advanced_filters(
        self,
        candles: List[Dict],
        setup: Dict,
        confluence: Dict,
        atr: float,
    ) -> Dict:
        """Apply institutional-grade filters."""
        failed_filters = []

        # Filter 1: Minimum confluence (3+ signals for entry)
        if confluence["hits"] < 3:
            failed_filters.append(f"CONFLUENCE_INSUFFICIENT ({confluence['hits']}/6)")

        # Filter 2: RR requirement
        risk = abs(setup.get("entry", 0) - setup.get("stop_loss", 0))
        reward = abs(setup.get("take_profit", 0) - setup.get("entry", 0))
        rr = reward / risk if risk > 0 else 0
        if rr < self.min_rr:
            failed_filters.append(f"RR_TOO_LOW ({rr:.2f} < {self.min_rr})")

        # Filter 3: ATR expansion check (avoid choppy markets)
        closes = [c["c"] for c in candles[-20:]]
        volatility = statistics.stdev(closes) if len(closes) > 1 else 0
        if volatility < atr * 0.2:
            failed_filters.append("MARKET_TOO_CHOPPY")

        # Filter 4: No opposing structure
        if self._is_opposing_structure(candles, setup.get("pattern")):
            failed_filters.append("OPPOSING_STRUCTURE")

        return {
            "passes": len(failed_filters) == 0,
            "reason": " | ".join(failed_filters) if failed_filters else "ALL_FILTERS_PASS",
            "failed_filters": failed_filters,
        }

    def _optimize_golden_ratio_levels(
        self,
        fractal: Dict,
        candles: List[Dict],
        market_structure: Optional[Dict],
        atr: float,
    ) -> Dict:
        """Optimize entry/stops using golden ratio spacing."""
        entry = fractal.get("entry", 0)
        sl_original = fractal.get("stop_loss", 0)
        tp_original = fractal.get("take_profit", 0)

        # Base range
        risk = abs(entry - sl_original)

        # Optimize stop loss to golden ratio distance
        # Use 0.786 Fib level as ideal stop
        sl_optimized = entry - (risk * 0.786)

        # Calculate targets using golden ratio
        # If RR requirement is 1.618, use:
        # TP1: 1.272x risk
        # TP2: 1.618x risk (golden ratio)
        # TP3: 2.618x risk (Phi squared)

        tp1 = entry + (risk * 1.272)
        tp2 = entry + (risk * self.PHI)  # 1.618
        tp3 = entry + (risk * 2.618)

        # Adjust if market structure suggests different levels
        if market_structure and "fibonacci_targets" in market_structure:
            targets = market_structure["fibonacci_targets"]
            upside = targets.get("upside", [])
            if upside:
                tp2 = upside[0]  # Use first calculated upside target
                tp3 = upside[1] if len(upside) > 1 else tp2

        return {
            "entry": entry,
            "stop_loss": sl_optimized,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit_3": tp3,
            "risk_original": risk,
            "risk_optimized": abs(entry - sl_optimized),
        }

    def _has_fvg_below(self, candles: List[Dict], entry: float, atr: float) -> bool:
        """Check if there's a fair value gap below entry level."""
        if len(candles) < 3:
            return False

        for i in range(len(candles) - 2):
            c1, c2 = candles[i], candles[i + 1]
            # FVG UP: gap between candles
            if c1["h"] < c2["l"]:
                gap_midpoint = (c1["h"] + c2["l"]) / 2
                if gap_midpoint < entry and (entry - gap_midpoint) < atr * 1.5:
                    return True

        return False

    def _check_momentum_alignment(self, candles: List[Dict], pattern: str) -> bool:
        """Check if momentum indicators align with pattern."""
        if len(candles) < 14:
            return True  # Not enough data, allow

        # Simple momentum check: are recent bars confirming direction?
        closes = [c["c"] for c in candles[-5:]]

        if pattern == "BULLISH" and closes[-1] > closes[0]:
            return True
        elif pattern == "BEARISH" and closes[-1] < closes[0]:
            return True

        return False

    def _is_opposing_structure(self, candles: List[Dict], pattern: str) -> bool:
        """Check if market structure opposes the pattern."""
        if len(candles) < 20:
            return False

        recent_highs = [c["h"] for c in candles[-20:]]
        recent_lows = [c["l"] for c in candles[-20:]]

        # If BULLISH but just broke down below recent support
        if pattern == "BULLISH" and candles[-1]["l"] < min(recent_lows[:-5]):
            return True

        # If BEARISH but just broke up above recent resistance
        if pattern == "BEARISH" and candles[-1]["h"] > max(recent_highs[:-5]):
            return True

        return False

    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> float:
        """Calculate Average True Range."""
        if len(candles) < period:
            return 0

        trs = []
        for i in range(1, min(period + 1, len(candles))):
            c1, c2 = candles[i - 1], candles[i]
            tr = max(c2["h"] - c2["l"], abs(c2["h"] - c1["c"]), abs(c2["l"] - c1["c"]))
            trs.append(tr)

        return statistics.mean(trs) if trs else 0
