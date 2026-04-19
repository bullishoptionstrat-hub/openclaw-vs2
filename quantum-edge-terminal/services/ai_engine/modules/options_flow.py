"""
PHASE 3 - MODULE 3: OPTIONS FLOW ANALYSIS ENGINE

Detects and analyzes options flow (CBOE, large options activity).

Institutional-grade options intelligence:
- PCR (Put/Call Ratio) analysis
- Smart money vs retail flow detection
- IV rank/percentile calculations
- Options volume analysis by strike/expiration
- Flow concentration detection
- Directional bias scoring

Data Sources:
- CBOE (Put/Call data)
- OptionSheriff (volume anomalies)
- Market.io (flow synthesis)
- Internal volume analysis

Integration:
- Feeds into Confluence scoring as +/- bias factor
- Complements macro + structure signals
- Real-time alert system for large flows
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OptionsDirection(Enum):
    """Options flow direction bias."""
    BULLISH = "bullish"     # More calls than puts, aggressive calls
    BEARISH = "bearish"     # More puts than calls, aggressive puts
    NEUTRAL = "neutral"     # Balanced or no clear bias
    HEDGE = "hedge"        # Hedging activity


@dataclass
class OptionsPCR:
    """Put/Call Ratio analysis."""
    
    ratio: float           # Put volume / Call volume
    put_volume: int        # Total put volume
    call_volume: int       # Total call volume
    ratio_change: float    # % change from prior period
    percentile: float      # 0-1, where are we historically
    
    @property
    def is_extreme_bullish(self) -> bool:
        """Very low PCR (lots of calls)."""
        return self.ratio < 0.5
    
    @property
    def is_extreme_bearish(self) -> bool:
        """Very high PCR (lots of puts)."""
        return self.ratio > 2.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "ratio": self.ratio,
            "put_volume": self.put_volume,
            "call_volume": self.call_volume,
            "ratio_change": self.ratio_change,
            "percentile": self.percentile,
        }


@dataclass
class IVMetrics:
    """IV (Implied Volatility) analysis."""
    
    iv_rank: float         # 0-100, where IV is relative to 52-week range
    iv_percentile: float   # 0-1, where IV is percentile-wise
    call_iv: float         # IV for calls
    put_iv: float          # IV for puts
    skew: float            # Put IV - Call IV (negative = fear)
    
    @property
    def is_high_iv(self) -> bool:
        """IV in top percentile (compression traders may short)."""
        return self.iv_percentile > 0.75
    
    @property
    def is_low_iv(self) -> bool:
        """IV in low percentile (expansion play)."""
        return self.iv_percentile < 0.25
    
    @property
    def has_skew(self) -> bool:
        """Put IV > Call IV (market pricing in risk)."""
        return self.skew > 0.5
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "iv_rank": self.iv_rank,
            "iv_percentile": self.iv_percentile,
            "call_iv": self.call_iv,
            "put_iv": self.put_iv,
            "skew": self.skew,
        }


@dataclass
class OptionsFlow:
    """Single flow transaction."""
    
    symbol: str
    timestamp: int         # milliseconds
    side: str              # "call" or "put"
    direction: str         # "buy" or "sell"
    volume: int
    strike: float
    expiration: str        # "monthly", "weekly", "quarterly"
    premium: float         # Total premium * volume
    type_: str             # "aggressive", "neutral", "spread"
    smart_money: bool      # Is this likely institutional?
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "side": self.side,
            "direction": self.direction,
            "volume": self.volume,
            "strike": self.strike,
            "expiration": self.expiration,
            "premium": self.premium,
            "type": self.type_,
            "smart_money": self.smart_money,
        }


@dataclass
class OptionsAnalysis:
    """Complete options flow analysis."""
    
    symbol: str
    timestamp: int
    pcr: Optional[OptionsPCR] = None
    iv: Optional[IVMetrics] = None
    direction_bias: OptionsDirection = OptionsDirection.NEUTRAL
    confidence: float = 0.0  # 0-1
    factors: List[str] = field(default_factory=list)
    recent_flows: List[OptionsFlow] = field(default_factory=list)
    bullish_flow_score: float = 0.0  # 0-1
    bearish_flow_score: float = 0.0  # 0-1
    net_bias: float = 0.0  # -1 to +1
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "pcr": self.pcr.to_dict() if self.pcr else None,
            "iv": self.iv.to_dict() if self.iv else None,
            "direction_bias": self.direction_bias.value,
            "confidence": self.confidence,
            "factors": self.factors,
            "bullish_flow_score": self.bullish_flow_score,
            "bearish_flow_score": self.bearish_flow_score,
            "net_bias": self.net_bias,
            "recent_flows_count": len(self.recent_flows),
        }


class OptionsFlowAnalyzer:
    """Analyze options flow for trading signals."""
    
    # Thresholds
    PCR_EXTREME_LOW = 0.5    # Extreme call buying
    PCR_EXTREME_HIGH = 2.0   # Extreme put buying
    IV_HIGH_PERCENTILE = 0.75
    IV_LOW_PERCENTILE = 0.25
    VOLUME_THRESHOLD = 10000  # Unusual if > this
    
    def __init__(self):
        """Initialize analyzer."""
        self.recent_flows: Dict[str, List[OptionsFlow]] = {}
        self.pcr_history: Dict[str, List[OptionsPCR]] = {}
    
    def ingest_flow(self, flow: OptionsFlow) -> None:
        """Ingest single options flow event."""
        if flow.symbol not in self.recent_flows:
            self.recent_flows[flow.symbol] = []
        
        # Keep last 100 flows per symbol
        self.recent_flows[flow.symbol].append(flow)
        if len(self.recent_flows[flow.symbol]) > 100:
            self.recent_flows[flow.symbol] = self.recent_flows[flow.symbol][-100:]
        
        logger.info(
            f"Ingested options flow: {flow.symbol} {flow.side} "
            f"{flow.volume} vol @ {flow.strike} {flow.expiration}"
        )
    
    def analyze(
        self,
        symbol: str,
        pcr: Optional[OptionsPCR] = None,
        iv: Optional[IVMetrics] = None,
    ) -> OptionsAnalysis:
        """
        Analyze options flow for a symbol.
        
        Args:
            symbol: Ticker symbol
            pcr: Put/Call ratio data
            iv: IV metrics
        
        Returns:
            OptionsAnalysis with direction bias and confidence
        """
        timestamp = int(datetime.now().timestamp() * 1000)
        direction_bias = OptionsDirection.NEUTRAL
        bullish_score = 0.0
        bearish_score = 0.0
        factors = []
        confidence = 0.5
        
        # ========== PCR ANALYSIS ==========
        if pcr:
            if pcr.is_extreme_bullish:
                # Very low PCR = aggressive call buying = bullish
                bullish_score += 0.4
                factors.append(f"Extreme call buying (PCR {pcr.ratio:.2f})")
                confidence = min(1.0, confidence + 0.2)
            
            elif pcr.is_extreme_bearish:
                # Very high PCR = aggressive put buying = bearish
                bearish_score += 0.4
                factors.append(f"Extreme put buying (PCR {pcr.ratio:.2f})")
                confidence = min(1.0, confidence + 0.2)
            
            else:
                # Normal range - check trend
                if pcr.ratio_change < -0.1:
                    # PCR falling = more calls = bullish shift
                    bullish_score += 0.15
                    factors.append(f"PCR declining = call buying ({pcr.ratio_change:+.1%})")
                elif pcr.ratio_change > 0.1:
                    # PCR rising = more puts = bearish shift
                    bearish_score += 0.15
                    factors.append(f"PCR rising = put buying ({pcr.ratio_change:+.1%})")
        
        # ========== IV ANALYSIS ==========
        if iv:
            if iv.is_high_iv:
                # High IV = compression, traders pricing in move
                # Could be either direction depending on skew
                if iv.has_skew:
                    # High IV + skew = fear premium
                    bearish_score += 0.2
                    factors.append("High IV + skew (fear premium)")
                else:
                    # High IV but balanced = expansion possible
                    factors.append("High IV (possible expansion trade)")
            
            elif iv.is_low_iv:
                # Low IV = compression, breakout likely
                bullish_score += 0.15
                factors.append(f"Low IV (IV rank {iv.iv_rank:.0f}), expansion likely")
            
            if iv.has_skew and iv.skew > 1.0:
                # Very high skew = market pricing major downside
                bearish_score += 0.2
                factors.append(f"Significant skew (put IV {iv.skew:.1f}% > call)")
        
        # ========== FLOW ANALYSIS ==========
        if symbol in self.recent_flows:
            flows = self.recent_flows[symbol]
            
            # Count bullish vs bearish flows
            bullish_flows = sum(1 for f in flows if f.side == "call" and f.direction == "buy")
            bearish_flows = sum(1 for f in flows if f.side == "put" and f.direction == "buy")
            
            bullish_premium = sum(
                f.premium for f in flows if f.side == "call" and f.direction == "buy"
            )
            bearish_premium = sum(
                f.premium for f in flows if f.side == "put" and f.direction == "buy"
            )
            
            total_premium = bullish_premium + bearish_premium
            if total_premium > 0:
                bullish_flow_score = bullish_premium / total_premium
                bearish_flow_score = bearish_premium / total_premium
                
                if bullish_flow_score > 0.65:
                    bullish_score += 0.3
                    factors.append(f"Heavy call buying ({bullish_flows} calls)")
                elif bearish_flow_score > 0.65:
                    bearish_score += 0.3
                    factors.append(f"Heavy put buying ({bearish_flows} puts)")
            
            # Check for smart money
            smart_flows = [f for f in flows if f.smart_money]
            if smart_flows:
                smart_bullish = sum(1 for f in smart_flows if f.side == "call")
                smart_bearish = sum(1 for f in smart_flows if f.side == "put")
                
                if smart_bullish > smart_bearish:
                    bullish_score += 0.2
                    factors.append(f"Smart money buying calls ({smart_bullish} transactions)")
                elif smart_bearish > smart_bullish:
                    bearish_score += 0.2
                    factors.append(f"Smart money buying puts ({smart_bearish} transactions)")
        
        # Normalize scores
        total_score = max(bullish_score + bearish_score, 0.1)
        bullish_score = min(1.0, bullish_score)
        bearish_score = min(1.0, bearish_score)
        
        # Determine dominant direction
        net_bias = bullish_score - bearish_score
        
        if net_bias > 0.2:
            direction_bias = OptionsDirection.BULLISH
        elif net_bias < -0.2:
            direction_bias = OptionsDirection.BEARISH
        else:
            direction_bias = OptionsDirection.NEUTRAL
        
        result = OptionsAnalysis(
            symbol=symbol,
            timestamp=timestamp,
            pcr=pcr,
            iv=iv,
            direction_bias=direction_bias,
            confidence=confidence,
            factors=factors,
            bullish_flow_score=bullish_score,
            bearish_flow_score=bearish_score,
            net_bias=net_bias,
            recent_flows=self.recent_flows.get(symbol, [])[-10:],  # Last 10
        )
        
        logger.info(
            f"Options analysis for {symbol}: {direction_bias.value.upper()} "
            f"(bullish={bullish_score:.2f}, bearish={bearish_score:.2f}, conf={confidence:.2f})"
        )
        
        return result
    
    def detect_smart_money_activity(
        self,
        symbol: str,
        volume_threshold: int = VOLUME_THRESHOLD,
    ) -> Optional[OptionsAnalysis]:
        """Detect unusual smart money options activity."""
        if symbol not in self.recent_flows:
            return None
        
        flows = self.recent_flows[symbol]
        unusual_flows = [
            f for f in flows
            if f.volume > volume_threshold and f.smart_money
        ]
        
        if not unusual_flows:
            return None
        
        # Find dominant bias in unusual activity
        bullish_unusual = sum(1 for f in unusual_flows if f.side == "call")
        bearish_unusual = sum(1 for f in unusual_flows if f.side == "put")
        
        logger.warning(
            f"UNUSUAL OPTIONS ACTIVITY: {symbol} - "
            f"{len(unusual_flows)} unusual flows "
            f"({bullish_unusual} calls, {bearish_unusual} puts)"
        )
        
        # Return a mini-analysis
        return self.analyze(symbol)
    
    def get_sentiment_snapshot(self, symbol: str) -> dict:
        """Get current options sentiment."""
        if symbol not in self.recent_flows:
            return {"sentiment": "insufficient_data"}
        
        flows = self.recent_flows[symbol]
        if not flows:
            return {"sentiment": "insufficient_data"}
        
        analysis = self.analyze(symbol)
        
        return {
            "symbol": symbol,
            "sentiment": analysis.direction_bias.value,
            "confidence": analysis.confidence,
            "bullish_score": analysis.bullish_flow_score,
            "bearish_score": analysis.bearish_flow_score,
            "factors": analysis.factors,
            "timestamp": datetime.utcnow().isoformat(),
        }


class OptionsFlowSynthesizer:
    """Synthesize options flow from multiple sources."""
    
    @staticmethod
    def create_demo_flows(symbol: str) -> List[OptionsFlow]:
        """Create demo options flows for testing."""
        flows = []
        
        # Demo: Bearish scenario - heavy put buying
        flows.extend([
            OptionsFlow(
                symbol=symbol,
                timestamp=int(datetime.now().timestamp() * 1000),
                side="put",
                direction="buy",
                volume=50000,
                strike=180.0,
                expiration="weekly",
                premium=2500000,
                type_="aggressive",
                smart_money=True,
            ),
            OptionsFlow(
                symbol=symbol,
                timestamp=int(datetime.now().timestamp() * 1000),
                side="put",
                direction="buy",
                volume=75000,
                strike=175.0,
                expiration="monthly",
                premium=3750000,
                type_="aggressive",
                smart_money=True,
            ),
            OptionsFlow(
                symbol=symbol,
                timestamp=int(datetime.now().timestamp() * 1000),
                side="call",
                direction="sell",
                volume=40000,
                strike=200.0,
                expiration="weekly",
                premium=1200000,
                type_="spread",
                smart_money=False,
            ),
        ])
        
        return flows
    
    @staticmethod
    def create_demo_pcr(
        ratio: float = 1.5,
        put_volume: int = 150000,
        call_volume: int = 100000,
    ) -> OptionsPCR:
        """Create demo PCR data."""
        return OptionsPCR(
            ratio=ratio,
            put_volume=put_volume,
            call_volume=call_volume,
            ratio_change=-0.15,  # Declining (bullish)
            percentile=0.65,
        )
    
    @staticmethod
    def create_demo_iv() -> IVMetrics:
        """Create demo IV metrics."""
        return IVMetrics(
            iv_rank=75,
            iv_percentile=0.75,
            call_iv=18.5,
            put_iv=21.3,
            skew=2.8,  # Skew present (fear)
        )
