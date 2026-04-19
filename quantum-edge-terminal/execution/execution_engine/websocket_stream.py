"""
WEBSOCKET TRADE STREAM - REAL-TIME DELIVERY

Provides low-latency WebSocket channel for live trade updates.

Why WebSocket over polling?
- Polling: Client asks server every N seconds = latency + wasted bandwidth
- WebSocket: Client connects once, server pushes updates instantly = true real-time

Flow:
1. Client connects to /ws/trades
2. Server broadcasts new trades instantly
3. Updates pushed for: new trades, status changes, TP/SL hits, closes
4. No polling, no missed signals

Events:
- TRADE_CREATED: New execution payload generated
- TRADE_UPDATED: Status change or price fill
- TRADE_EXECUTED: Confirmed at broker/exchange
- TRADE_FILLED: Entry filled
- TP_HIT: Take profit triggered
- SL_HIT: Stop loss triggered
- TRADE_CLOSED: Trade closed

Consumers:
- Frontend dashboard (live updates)
- Alert system (triggers notifications)
- Mobile apps (push notifications)
- External traders/monitoring (audit trail)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set, Dict, Optional, Callable, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class WebSocketEventType:
    """WebSocket event types."""

    TRADE_CREATED = "trade_created"
    TRADE_UPDATED = "trade_updated"
    TRADE_EXECUTED = "trade_executed"
    TRADE_FILLED = "trade_filled"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    TRADE_CLOSED = "trade_closed"
    ALERT_TRIGGERED = "alert_triggered"
    ALERT_TIER_CHANGED = "alert_tier_changed"
    PERFORMANCE_UPDATE = "performance_update"
    ERROR = "error"


@dataclass
class WSMessage:
    """WebSocket message format."""

    event_type: str
    data: Dict[str, Any]
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    def to_json(self) -> str:
        """Convert to JSON."""
        return json.dumps(
            {
                "event": self.event_type,
                "data": self.data,
                "timestamp": self.timestamp,
            }
        )

    @staticmethod
    def from_json(msg: str) -> "WSMessage":
        """Parse JSON to WSMessage."""
        data = json.loads(msg)
        return WSMessage(
            event_type=data.get("event"),
            data=data.get("data", {}),
            timestamp=data.get("timestamp"),
        )


class TradeStreamManager:
    """
    Manages WebSocket connections and broadcasts.

    Single instance shared across all connected clients.
    Broadcasts all trade events to all connected clients.
    """

    def __init__(self):
        """Initialize stream manager."""
        self.connected_clients: Set[Any] = set()
        self.message_history: list = []  # Last 100 messages
        self.max_history = 100
        self.event_subscribers: Dict[str, list] = {}

    async def register_client(self, websocket):
        """Register a new WebSocket client."""
        self.connected_clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.connected_clients)}")

        # Send connection ACK + recent history
        await self._send_history(websocket)

    async def unregister_client(self, websocket):
        """Unregister a WebSocket client."""
        self.connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.connected_clients)}")

    async def broadcast(self, message: WSMessage):
        """Broadcast message to all connected clients."""
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)

        json_msg = message.to_json()
        logger.debug(f"Broadcasting: {message.event_type}")

        # Send to all connected clients
        disconnected = set()
        for websocket in self.connected_clients:
            try:
                if hasattr(websocket, "send"):
                    await websocket.send(json_msg)
                else:
                    # Fallback for sync websockets
                    websocket.send(json_msg)
            except Exception as e:
                logger.warning(f"Failed to send to client: {str(e)}")
                disconnected.add(websocket)

        # Clean up dead connections
        for ws in disconnected:
            await self.unregister_client(ws)

    async def broadcast_trade_created(self, trade_payload: Dict):
        """Broadcast: New trade created."""
        message = WSMessage(
            event_type=WebSocketEventType.TRADE_CREATED,
            data={
                "trade_id": trade_payload.get("trade_id"),
                "asset": trade_payload.get("asset"),
                "direction": trade_payload.get("direction"),
                "entry": trade_payload.get("entry"),
                "stop_loss": trade_payload.get("stop_loss"),
                "tp": trade_payload.get("take_profit_targets", []),
                "size": trade_payload.get("position_size"),
                "confidence": trade_payload.get("signal_confidence"),
                "macro_regime": trade_payload.get("macro_regime"),
                "signal_type": trade_payload.get("signal_type"),
                "status": trade_payload.get("status"),
            },
        )
        await self.broadcast(message)

    async def broadcast_trade_executed(self, trade_id: str, fill_price: Optional[float] = None):
        """Broadcast: Trade executed at broker."""
        message = WSMessage(
            event_type=WebSocketEventType.TRADE_EXECUTED,
            data={"trade_id": trade_id, "fill_price": fill_price},
        )
        await self.broadcast(message)

    async def broadcast_trade_filled(self, trade_id: str, fill_price: float):
        """Broadcast: Trade entry filled."""
        message = WSMessage(
            event_type=WebSocketEventType.TRADE_FILLED,
            data={"trade_id": trade_id, "fill_price": fill_price},
        )
        await self.broadcast(message)

    async def broadcast_tp_hit(self, trade_id: str, tp_price: float, level: int = 1):
        """Broadcast: Take profit hit."""
        message = WSMessage(
            event_type=WebSocketEventType.TP_HIT,
            data={"trade_id": trade_id, "tp_price": tp_price, "tp_level": level},
        )
        await self.broadcast(message)

    async def broadcast_sl_hit(self, trade_id: str, sl_price: float):
        """Broadcast: Stop loss hit."""
        message = WSMessage(
            event_type=WebSocketEventType.SL_HIT,
            data={"trade_id": trade_id, "sl_price": sl_price},
        )
        await self.broadcast(message)

    async def broadcast_alert_triggered(
        self,
        trade_id: str,
        alert_tier: str,
        alert_title: str,
        alert_body: str,
    ):
        """Broadcast: Alert triggered."""
        message = WSMessage(
            event_type=WebSocketEventType.ALERT_TRIGGERED,
            data={
                "trade_id": trade_id,
                "tier": alert_tier,
                "title": alert_title,
                "body": alert_body,
            },
        )
        await self.broadcast(message)

    async def broadcast_performance_update(self, performance_snapshot: Dict):
        """Broadcast: Performance metrics updated."""
        message = WSMessage(
            event_type=WebSocketEventType.PERFORMANCE_UPDATE,
            data=performance_snapshot,
        )
        await self.broadcast(message)

    async def broadcast_error(self, error_code: str, error_message: str):
        """Broadcast: System error."""
        message = WSMessage(
            event_type=WebSocketEventType.ERROR,
            data={"error_code": error_code, "error_message": error_message},
        )
        await self.broadcast(message)

    async def _send_history(self, websocket):
        """Send recent message history to newly connected client."""
        for message in self.message_history[-10:]:  # Last 10 messages
            try:
                if hasattr(websocket, "send"):
                    await websocket.send(message.to_json())
                else:
                    websocket.send(message.to_json())
            except Exception as e:
                logger.warning(f"Failed to send history: {str(e)}")

    def get_client_count(self) -> int:
        """Get number of connected clients."""
        return len(self.connected_clients)

    def get_recent_messages(self, limit: int = 20) -> list:
        """Get recent messages for dashboards."""
        return [
            {"event": msg.event_type, "data": msg.data, "timestamp": msg.timestamp}
            for msg in self.message_history[-limit:]
        ]


# Global instance (singleton)
_trade_stream_manager = None


def get_trade_stream_manager() -> TradeStreamManager:
    """Get or create the global trade stream manager."""
    global _trade_stream_manager
    if _trade_stream_manager is None:
        _trade_stream_manager = TradeStreamManager()
    return _trade_stream_manager
