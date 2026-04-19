import numpy as np
import pandas as pd
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MarketStructureDetector:
    """Detect market structure: BOS, CHoCH, FVG, sweeps, order blocks."""

    async def detect(self, symbol: str, timeframe: str, candles: List[Dict]) -> Dict[str, Any]:
        """
        Analyze candles for market structure patterns.

        Returns:
        {
            "bos": [{level, direction, confidence}],
            "choch": [{level, confidence}],
            "fvg": [{level, gap_size}],
            "sweeps": [{level, type}],
            "order_blocks": [{zone, type}]
        }
        """
        try:
            df = pd.DataFrame(candles)

            # Normalize price data
            df["high"] = pd.to_numeric(df["high"])
            df["low"] = pd.to_numeric(df["low"])
            df["close"] = pd.to_numeric(df["close"])
            df["volume"] = pd.to_numeric(df["volume"])

            results = {
                "symbol": symbol,
                "timeframe": timeframe,
                "bos": self._detect_bos(df),
                "choch": self._detect_choch(df),
                "fvg": self._detect_fvg(df),
                "sweeps": self._detect_sweeps(df),
                "order_blocks": self._detect_order_blocks(df),
                "swing_highs": self._find_swings(df, "high"),
                "swing_lows": self._find_swings(df, "low"),
            }

            return results
        except Exception as e:
            logger.error(f"Market structure detection error: {e}")
            raise

    def _detect_bos(self, df: pd.DataFrame) -> List[Dict]:
        """Break of Structure: Previous swing high/low breached."""
        bos = []

        if len(df) < 5:
            return bos

        for i in range(5, len(df)):
            # Uptrend BOS: Previous swing high broken
            if df.iloc[i]["high"] > df.iloc[i - 2 : i]["high"].max():
                bos.append(
                    {
                        "level": df.iloc[i - 2 : i]["high"].max(),
                        "direction": "UP",
                        "confidence": 0.85,
                        "timestamp": df.iloc[i].get("timestamp"),
                    }
                )

            # Downtrend BOS: Previous swing low broken
            if df.iloc[i]["low"] < df.iloc[i - 2 : i]["low"].min():
                bos.append(
                    {
                        "level": df.iloc[i - 2 : i]["low"].min(),
                        "direction": "DOWN",
                        "confidence": 0.85,
                        "timestamp": df.iloc[i].get("timestamp"),
                    }
                )

        return bos[-5:] if bos else []  # Return last 5

    def _detect_choch(self, df: pd.DataFrame) -> List[Dict]:
        """Change of Character: Directional shift."""
        choch = []

        if len(df) < 10:
            return choch

        # Simple trend reversal detection
        for i in range(5, len(df) - 1):
            uptrend = df.iloc[i - 5 : i]["close"].is_monotonic_increasing
            downtrend = df.iloc[i - 5 : i]["close"].is_monotonic_decreasing

            if uptrend and not df.iloc[i]["close"] > df.iloc[i - 1]["close"]:
                choch.append({"level": df.iloc[i]["close"], "confidence": 0.75})

        return choch[-3:] if choch else []

    def _detect_fvg(self, df: pd.DataFrame) -> List[Dict]:
        """Fair Value Gap: Unmitigated price gap."""
        fvg = []

        for i in range(1, len(df) - 1):
            gap_up = df.iloc[i]["low"] > df.iloc[i - 1]["high"]
            gap_down = df.iloc[i]["high"] < df.iloc[i - 1]["low"]

            if gap_up:
                gap_size = df.iloc[i]["low"] - df.iloc[i - 1]["high"]
                fvg.append({"level": df.iloc[i]["low"], "gap_size": gap_size, "type": "UP"})

            if gap_down:
                gap_size = df.iloc[i - 1]["low"] - df.iloc[i]["high"]
                fvg.append({"level": df.iloc[i]["high"], "gap_size": gap_size, "type": "DOWN"})

        return fvg[-5:] if fvg else []

    def _detect_sweeps(self, df: pd.DataFrame) -> List[Dict]:
        """Liquidity Sweep: Swing high/low touched and reversed."""
        sweeps = []

        if len(df) < 5:
            return sweeps

        for i in range(3, len(df)):
            # Check if current high touches previous swing
            prev_high = df.iloc[i - 3 : i - 1]["high"].max()
            current_high = df.iloc[i]["high"]

            if current_high > prev_high * 0.995:  # 0.5% tolerance
                sweeps.append({"level": prev_high, "type": "HIGH_SWEEP"})

        return sweeps[-3:] if sweeps else []

    def _detect_order_blocks(self, df: pd.DataFrame) -> List[Dict]:
        """Order Block: Institutional accumulation zone."""
        blocks = []

        for i in range(2, len(df)):
            # Simple: reversal candle body = order block
            if i > 0:
                prev_close = df.iloc[i - 1]["close"]
                curr_open = df.iloc[i]["open"]

                if abs(prev_close - curr_open) > df.iloc[i - 2 : i]["close"].std() * 2:
                    blocks.append(
                        {
                            "zone": (df.iloc[i]["low"], df.iloc[i]["high"]),
                            "type": "REVERSAL",
                        }
                    )

        return blocks[-3:] if blocks else []

    def _find_swings(self, df: pd.DataFrame, col: str) -> List[Dict]:
        """Find swing highs and lows."""
        swings = []

        for i in range(2, len(df) - 2):
            if col == "high":
                if df.iloc[i][col] > df.iloc[i - 1][col] and df.iloc[i][col] > df.iloc[i + 1][col]:
                    swings.append({"level": df.iloc[i][col], "type": "HIGH"})
            else:  # low
                if df.iloc[i][col] < df.iloc[i - 1][col] and df.iloc[i][col] < df.iloc[i + 1][col]:
                    swings.append({"level": df.iloc[i][col], "type": "LOW"})

        return swings[-5:] if swings else []
