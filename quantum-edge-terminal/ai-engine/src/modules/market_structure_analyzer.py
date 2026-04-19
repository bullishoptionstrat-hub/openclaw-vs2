#!/usr/bin/env python3
"""
INSTITUTIONAL MARKET STRUCTURE ANALYZER

Identifies key market levels using golden ratio fibonacci analysis:
- Swing highs/lows with fractal confirmation
- Support/resistance using Fibonacci extensions
- Liquidity clusters at key price levels
- Market microstructure patterns (fair value gaps, breakers)
- Institutional accumulation/distribution zones
"""

import statistics
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class PriceLevel(Enum):
    """Market structure price levels."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    GOLDEN_RESISTANCE = "golden_resistance"
    GOLDEN_SUPPORT = "golden_support"
    FVG_UP = "fair_value_gap_up"
    FVG_DOWN = "fair_value_gap_down"
    ORDER_CLUSTER = "order_cluster"
    LIQUIDATION_LEVEL = "liquidation_level"
    BREAKER_HIGH = "breaker_high"
    BREAKER_LOW = "breaker_low"


@dataclass
class MarketLevel:
    """Represents a key market structure level."""

    level: float
    level_type: PriceLevel
    confidence: float  # 0.0 to 1.0
    touches: int  # Number of times price touched/bounced
    last_touch_bar: int  # Bar index of last touch
    strength: float  # 0.0 to 1.0 based on rejection strength
    golden_ratio_multiplier: float = 1.0  # How many Phi ratios up/down from swing

    def __repr__(self):
        return f"{self.level_type.value}@{self.level:.2f}(conf={self.confidence:.2f})"


class MarketStructureAnalyzer:
    """
    Identifies institutional market structure using fibonacci golden ratio analysis.

    Key Concepts:
    - Golden Ratio (Φ) = 1.618 = (1 + √5) / 2
    - Fibonacci levels: 0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618, 2.618
    - Market naturally gravitates to these levels due to institutional order placement
    - Confluence of multiple levels = institutional price targets
    """

    PHI = 1.618034  # Golden ratio
    FRAC_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618, 2.618]

    def __init__(self, min_swing_bars: int = 3, fvg_threshold: float = 0.002):
        """
        Args:
            min_swing_bars: Minimum bars between swings (higher = larger timeframes)
            fvg_threshold: Fair Value Gap threshold as % of ATR
        """
        self.min_swing_bars = min_swing_bars
        self.fvg_threshold = fvg_threshold
        self.levels: List[MarketLevel] = []

    def analyze(self, candles: List[Dict]) -> Dict:
        """
        Comprehensive market structure analysis.

        Args:
            candles: List of candles with 'o', 'h', 'l', 'c', 'v' keys

        Returns:
            Dict with:
            - swing_high: Latest swing high
            - swing_low: Latest swing low
            - levels: All key market levels
            - fair_value_gaps: Current FVGs
            - order_clusters: Institutional activity zones
            - next_targets: Fibonacci targets for current move
        """
        if len(candles) < self.min_swing_bars * 3:
            return {"valid": False, "error": "Insufficient candles"}

        # Extract price data
        highs = [c["h"] for c in candles]
        lows = [c["l"] for c in candles]
        closes = [c["c"] for c in candles]
        volumes = [c.get("v", 0) for c in candles]

        # Find swings
        swings_up, swings_down = self._find_swings(highs, lows)

        # Identify current structure
        last_swing_high = swings_up[-1][0] if swings_up else max(highs)
        last_swing_low = swings_down[-1][0] if swings_down else min(lows)

        # Calculate ATR for normalization
        atr = self._calculate_atr(candles)

        # Find all key levels
        self.levels = []

        # 1. Add swing levels (primary structure)
        self.levels.append(
            MarketLevel(
                level=last_swing_high,
                level_type=PriceLevel.SWING_HIGH,
                confidence=0.95,
                touches=len([1 for h in highs[-20:] if abs(h - last_swing_high) < atr * 0.1]),
                last_touch_bar=len(highs) - 1,
                strength=0.90,
            )
        )

        self.levels.append(
            MarketLevel(
                level=last_swing_low,
                level_type=PriceLevel.SWING_LOW,
                confidence=0.95,
                touches=len([1 for l in lows[-20:] if abs(l - last_swing_low) < atr * 0.1]),
                last_touch_bar=len(lows) - 1,
                strength=0.90,
            )
        )

        # 2. Add golden ratio levels
        golden_levels = self._calculate_golden_levels(last_swing_low, last_swing_high, highs, lows)
        self.levels.extend(golden_levels)

        # 3. Find fair value gaps (institutional inefficiencies)
        fvgs = self._find_fair_value_gaps(candles, atr)
        self.levels.extend(fvgs)

        # 4. Find order clusters (volume-based)
        clusters = self._find_order_clusters(candles)
        self.levels.extend(clusters)

        # 5. Identify breakers (institutional supply/demand blocks)
        breakers = self._find_breakers(candles)
        self.levels.extend(breakers)

        # Calculate targets from current price
        current_price = closes[-1]
        targets = self._calculate_fibonacci_targets(current_price, last_swing_low, last_swing_high)

        return {
            "valid": True,
            "swing_high": last_swing_high,
            "swing_low": last_swing_low,
            "current_price": current_price,
            "swing_range": last_swing_high - last_swing_low,
            "atr": atr,
            "levels": self.levels,
            "fair_value_gaps": fvgs,
            "order_clusters": clusters,
            "breakers": breakers,
            "fibonacci_targets": targets,
            "trend": self._identify_trend(closes),
            "market_structure": self._analyze_market_structure(candles),
        }

    def _find_swings(self, highs: List[float], lows: List[float]) -> Tuple[List, List]:
        """Find swing highs and lows using fractal logic."""
        swings_up = []
        swings_down = []

        for i in range(self.min_swing_bars, len(highs) - self.min_swing_bars):
            # Swing high: highest point surrounded by lower highs
            is_swing_high = (
                highs[i] == max(highs[i - self.min_swing_bars : i + self.min_swing_bars + 1])
                and highs[i] > highs[i - 1]
                and highs[i] > highs[i + 1]
            )
            if is_swing_high:
                swings_up.append((highs[i], i))

            # Swing low: lowest point surrounded by higher lows
            is_swing_low = (
                lows[i] == min(lows[i - self.min_swing_bars : i + self.min_swing_bars + 1])
                and lows[i] < lows[i - 1]
                and lows[i] < lows[i + 1]
            )
            if is_swing_low:
                swings_down.append((lows[i], i))

        return swings_up[-3:] if swings_up else [], swings_down[-3:] if swings_down else []

    def _calculate_golden_levels(
        self, swing_low: float, swing_high: float, highs: List[float], lows: List[float]
    ) -> List[MarketLevel]:
        """Calculate Fibonacci golden ratio levels between swings."""
        levels = []
        swing_range = swing_high - swing_low

        for ratio in self.FRAC_LEVELS:
            # Retracement levels (from high)
            ret_level = swing_high - (swing_range * ratio)

            # Check if price touches this level (confluence)
            touches = len([1 for p in highs + lows if abs(p - ret_level) < swing_range * 0.003])

            if ratio in [0.382, 0.618, 0.786]:  # Key Fibonacci ratios
                confidence = 0.85 + (touches * 0.03)  # More touches = more confidence

                levels.append(
                    MarketLevel(
                        level=ret_level,
                        level_type=PriceLevel.GOLDEN_RESISTANCE
                        if ret_level > swing_low
                        else PriceLevel.GOLDEN_SUPPORT,
                        confidence=min(0.99, confidence),
                        touches=touches,
                        last_touch_bar=len(highs) - 1,
                        strength=confidence,
                        golden_ratio_multiplier=ratio,
                    )
                )

        return levels

    def _find_fair_value_gaps(self, candles: List[Dict], atr: float) -> List[MarketLevel]:
        """Find fair value gaps (institutional inefficiencies)."""
        fvgs = []

        for i in range(1, len(candles) - 1):
            c1, c2, c3 = candles[i - 1], candles[i], candles[i + 1]

            # FVG UP: C1 high < C2 low < C3 range (price jumped up)
            if c1["h"] < c2["l"] and c2["l"] < c3["h"]:
                fvg_level = (c1["h"] + c2["l"]) / 2
                fvgs.append(
                    MarketLevel(
                        level=fvg_level,
                        level_type=PriceLevel.FVG_UP,
                        confidence=0.80,
                        touches=0,
                        last_touch_bar=i,
                        strength=abs(c2["l"] - c1["h"]) / atr * 0.2 if atr > 0 else 0.5,
                    )
                )

            # FVG DOWN: C1 low > C2 high > C3 range (price jumped down)
            if c1["l"] > c2["h"] and c2["h"] > c3["l"]:
                fvg_level = (c1["l"] + c2["h"]) / 2
                fvgs.append(
                    MarketLevel(
                        level=fvg_level,
                        level_type=PriceLevel.FVG_DOWN,
                        confidence=0.80,
                        touches=0,
                        last_touch_bar=i,
                        strength=abs(c1["l"] - c2["h"]) / atr * 0.2 if atr > 0 else 0.5,
                    )
                )

        return fvgs[-5:] if fvgs else []  # Return last 5

    def _find_order_clusters(self, candles: List[Dict]) -> List[MarketLevel]:
        """Find institutional order clusters using volume analysis."""
        clusters = []
        closes = [c["c"] for c in candles]
        volumes = [c.get("v", 0) for c in candles]

        if not volumes or sum(volumes) == 0:
            return []

        avg_vol = statistics.mean(volumes)

        for i, (price, vol) in enumerate(zip(closes[-20:], volumes[-20:])):
            if vol > avg_vol * 2:  # High volume cluster
                clusters.append(
                    MarketLevel(
                        level=price,
                        level_type=PriceLevel.ORDER_CLUSTER,
                        confidence=0.75,
                        touches=1,
                        last_touch_bar=len(closes) - 20 + i,
                        strength=min(0.95, (vol / avg_vol) * 0.5),
                    )
                )

        return clusters

    def _find_breakers(self, candles: List[Dict]) -> List[MarketLevel]:
        """Find breaker blocks (institutional supply/demand)."""
        breakers = []

        for i in range(2, len(candles) - 1):
            c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]

            # Breaker high: previous high that acts as resistance after broken
            if c1["h"] < c2["h"] and c2["l"] > c1["h"] and c3["c"] < c1["h"]:
                breakers.append(
                    MarketLevel(
                        level=c1["h"],
                        level_type=PriceLevel.BREAKER_HIGH,
                        confidence=0.80,
                        touches=1,
                        last_touch_bar=i,
                        strength=0.85,
                    )
                )

            # Breaker low: previous low that acts as support after broken
            if c1["l"] > c2["l"] and c2["h"] < c1["l"] and c3["c"] > c1["l"]:
                breakers.append(
                    MarketLevel(
                        level=c1["l"],
                        level_type=PriceLevel.BREAKER_LOW,
                        confidence=0.80,
                        touches=1,
                        last_touch_bar=i,
                        strength=0.85,
                    )
                )

        return breakers[-5:] if breakers else []

    def _calculate_fibonacci_targets(
        self, current: float, swing_low: float, swing_high: float
    ) -> Dict[str, List[float]]:
        """Calculate Fibonacci targets based on current position."""
        range_size = swing_high - swing_low
        targets = {"upside": [], "downside": []}

        # Upside targets
        for ratio in [1.272, 1.618, 2.0, 2.618]:
            targets["upside"].append(current + (range_size * ratio))

        # Downside targets
        for ratio in [0.618, 0.382, 0.236]:
            targets["downside"].append(current - (range_size * ratio))

        return targets

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

    def _identify_trend(self, closes: List[float]) -> str:
        """Identify overall trend."""
        if len(closes) < 20:
            return "RANGING"

        ma_short = statistics.mean(closes[-5:])
        ma_long = statistics.mean(closes[-20:])

        if ma_short > ma_long * 1.01:
            return "UPTREND"
        elif ma_short < ma_long * 0.99:
            return "DOWNTREND"
        else:
            return "RANGING"

    def _analyze_market_structure(self, candles: List[Dict]) -> str:
        """Analyze market microstructure characteristics."""
        if len(candles) < 10:
            return "INSUFFICIENT_DATA"

        recent_closes = [c["c"] for c in candles[-10:]]
        range_size = max(recent_closes) - min(recent_closes)
        avg_body = statistics.mean([abs(c["c"] - c["o"]) for c in candles[-10:]])

        wick_ratio = range_size / avg_body if avg_body > 0 else 0

        if wick_ratio > 2:
            return "VOLATILE"
        elif wick_ratio < 0.5:
            return "CHOPPY"
        else:
            return "NORMAL"


def get_institutional_levels(candles: List[Dict]) -> Dict:
    """Quick institutional level extraction."""
    analyzer = MarketStructureAnalyzer(min_swing_bars=2)
    return analyzer.analyze(candles)
