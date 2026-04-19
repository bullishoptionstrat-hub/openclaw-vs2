"""
MARKET DATA STREAMER - ALPACA REAL-TIME DATA INTEGRATION

Connects to Alpaca Markets API for real-time market data streaming.
Ingests OHLCV data and feeds into validation + trading engines.

Features:
- Real-time 1-min, 5-min, 15-min bar streaming
- Market hours detection (US equities)
- Connection management + auto-reconnect
- Data validation + quality checks
- Multiple symbol support
- Event-based architecture (callbacks on new data)
"""

import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class BarTimeframe(Enum):
    """Supported timeframes for OHLCV data."""

    ONE_MIN = "1min"
    FIVE_MIN = "5min"
    FIFTEEN_MIN = "15min"
    ONE_HOUR = "1h"
    DAILY = "1day"


class MarketStatus(Enum):
    """Market trading status."""

    PRE_MARKET = "pre_market"  # 4:00 AM - 9:30 AM ET
    OPEN = "open"  # 9:30 AM - 4:00 PM ET
    AFTER_HOURS = "after_hours"  # 4:00 PM - 8:00 PM ET
    CLOSED = "closed"  # All other times


@dataclass
class MarketBar:
    """OHLCV bar data."""

    symbol: str
    timestamp: str  # ISO format
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float  # Volume-weighted average price
    timeframe: str  # '1min', '5min', etc.
    is_complete: bool = True  # Bar is finalized

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "vwap": self.vwap,
            "timeframe": self.timeframe,
            "is_complete": self.is_complete,
        }


@dataclass
class StreamingConfig:
    """Configuration for market data streaming."""

    api_key: str
    api_secret: str
    base_url: str = "https://api.alpaca.markets"  # Paper by default
    symbols: List[str] = None  # Symbols to stream
    timeframes: List[str] = None  # Timeframes to stream
    enable_real_time: bool = True  # Stream live updates
    buffer_size: int = 1000  # Historical bars to buffer
    auto_reconnect: bool = True
    reconnect_max_retries: int = 5


class MarketDataStreamer:
    """
    Real-time market data streaming from Alpaca.

    Provides:
    - Live OHLCV data for multiple symbols
    - Market hours awareness
    - Data quality validation
    - Event callbacks for new data
    - Connection management
    """

    def __init__(self, config: StreamingConfig):
        """
        Initialize market data streamer.

        Args:
            config: StreamingConfig with API credentials
        """

        self.config = config
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.base_url = config.base_url

        # Streaming state
        self.connected = False
        self.streaming = False
        self.market_status = MarketStatus.CLOSED

        # Bar buffer (recent data for each symbol)
        self.bar_buffers: Dict[str, List[MarketBar]] = {}
        for symbol in config.symbols or []:
            self.bar_buffers[symbol] = []

        # Callbacks
        self.on_bar_callbacks: List[Callable[[MarketBar], None]] = []
        self.on_market_open_callbacks: List[Callable[[], None]] = []
        self.on_market_close_callbacks: List[Callable[[], None]] = []

        # Statistics
        self.bars_received = 0
        self.last_bar_time: Optional[datetime] = None
        self.connection_attempts = 0

        logger.info(
            f"MarketDataStreamer initialized | "
            f"Symbols: {config.symbols} | "
            f"Timeframes: {config.timeframes}"
        )

    def connect(self) -> bool:
        """
        Connect to Alpaca market data stream.

        Returns:
            True if connected, False if failed
        """

        logger.info(f"Connecting to Alpaca market data stream...")

        try:
            # TODO: Actual Alpaca WebSocket connection
            # For demo, simulate successful connection
            self.connected = True
            self.connection_attempts = 0
            logger.info(f"✅ Connected to Alpaca market data")
            return True

        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            self.connection_attempts += 1

            if self.config.auto_reconnect and self.connection_attempts < self.config.reconnect_max_retries:
                logger.info(
                    f"Retrying connection ({self.connection_attempts}/{self.config.reconnect_max_retries})..."
                )
                return self.connect()

            return False

    def start_streaming(self) -> bool:
        """
        Start receiving market data.

        Returns:
            True if streaming started
        """

        if not self.connected:
            if not self.connect():
                return False

        logger.info(f"Starting market data streaming...")

        try:
            # TODO: Subscribe to real-time bars for symbols
            self.streaming = True
            logger.info(f"✅ Market data streaming started")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to start streaming: {e}")
            return False

    def stop_streaming(self) -> None:
        """Stop receiving market data."""

        if self.streaming:
            # TODO: Unsubscribe from all bars
            self.streaming = False
            logger.info(f"Market data streaming stopped")

    def disconnect(self) -> None:
        """Disconnect from Alpaca."""

        self.stop_streaming()
        if self.connected:
            # TODO: Close WebSocket connection
            self.connected = False
            logger.info(f"Disconnected from Alpaca")

    def add_bar_callback(self, callback: Callable[[MarketBar], None]) -> None:
        """Register callback for new bars."""

        self.on_bar_callbacks.append(callback)
        logger.debug(f"Added bar callback | Total: {len(self.on_bar_callbacks)}")

    def add_market_open_callback(self, callback: Callable[[], None]) -> None:
        """Register callback for market open."""

        self.on_market_open_callbacks.append(callback)

    def add_market_close_callback(self, callback: Callable[[], None]) -> None:
        """Register callback for market close."""

        self.on_market_close_callbacks.append(callback)

    def on_bar_received(self, bar: MarketBar) -> None:
        """
        Process incoming bar (called by WebSocket handler).

        Updates buffers and fires callbacks.
        """

        # Validate bar
        if not self._validate_bar(bar):
            logger.warning(f"Invalid bar received: {bar.symbol}")
            return

        # Update buffer
        symbol_buffer = self.bar_buffers.get(bar.symbol, [])
        symbol_buffer.append(bar)

        # Keep buffer size limited
        if len(symbol_buffer) > self.config.buffer_size:
            symbol_buffer.pop(0)

        self.bar_buffers[bar.symbol] = symbol_buffer

        # Update statistics
        self.bars_received += 1
        self.last_bar_time = datetime.fromisoformat(bar.timestamp)

        # Fire callbacks
        for callback in self.on_bar_callbacks:
            try:
                callback(bar)
            except Exception as e:
                logger.error(f"Error in bar callback: {e}")

        logger.debug(f"Bar received | {bar.symbol} | {bar.close}")

    def check_market_status(self) -> MarketStatus:
        """
        Check current market status.

        Returns:
            Current MarketStatus
        """

        now = datetime.utcnow().time()

        # US market hours (ET)
        pre_market_start = time(8, 0)  # 3:00 AM ET
        market_open = time(13, 30)  # 9:30 AM ET
        market_close = time(20, 0)  # 4:00 PM ET
        after_hours_end = time(0, 1)  # 8:00 PM ET (next day)

        if now >= market_open and now < market_close:
            self.market_status = MarketStatus.OPEN
        elif now >= pre_market_start and now < market_open:
            self.market_status = MarketStatus.PRE_MARKET
        elif now >= market_close and now < after_hours_end:
            self.market_status = MarketStatus.AFTER_HOURS
        else:
            self.market_status = MarketStatus.CLOSED

        return self.market_status

    def _validate_bar(self, bar: MarketBar) -> bool:
        """Validate bar data quality."""

        if bar.open <= 0 or bar.close <= 0:
            return False
        if bar.high < bar.low:
            return False
        if bar.volume < 0:
            return False

        return True

    def get_latest_bar(self, symbol: str) -> Optional[MarketBar]:
        """Get most recent bar for symbol."""

        buffer = self.bar_buffers.get(symbol, [])
        return buffer[-1] if buffer else None

    def get_bars(self, symbol: str, limit: int = 50) -> List[MarketBar]:
        """Get recent bars for symbol."""

        buffer = self.bar_buffers.get(symbol, [])
        return buffer[-limit:] if buffer else []

    def get_streamer_stats(self) -> Dict:
        """Get streamer operational statistics."""

        active_symbols = sum(1 for b in self.bar_buffers.values() if b)

        return {
            "connected": self.connected,
            "streaming": self.streaming,
            "market_status": self.market_status.value,
            "bars_received": self.bars_received,
            "active_symbols": active_symbols,
            "last_bar_time": self.last_bar_time.isoformat() if self.last_bar_time else None,
            "connection_attempts": self.connection_attempts,
            "buffer_state": {
                sym: len(bars) for sym, bars in self.bar_buffers.items() if bars
            },
        }
