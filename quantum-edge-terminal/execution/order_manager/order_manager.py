"""
ORDER MANAGER - CONVERT EXECUTION PAYLOADS TO BROKER ORDERS

Transforms ExecutionPayload from execution_engine into concrete broker orders.

Responsibilities:
1. Map ExecutionPayload.position_size to actual share quantity
2. Determine order type (market, limit, bracket)
3. Calculate stop loss and take profit levels
4. Apply broker-specific order rules (minimum quantity, symbol validation)
5. Route to BrokerConnection for execution
6. Track order lifecycle (submitted → filled → closed)

Input: ExecutionPayload (from execution_engine)
Output: OrderStatus (from broker_connection)
"""

import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal, ROUND_DOWN

from ..broker_engine.broker_connection import (
    BrokerConnection,
    BrokerMode,
    OrderStatus,
    BrokerConfig,
)

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Types of orders we can place."""

    MARKET = "market"
    LIMIT = "limit"
    BRACKET = "bracket"  # Market entry with TP + SL


@dataclass
class OrderContext:
    """Context for order placement."""

    symbol: str
    current_price: float
    position_size: float  # From ExecutionPayload
    confidence: float  # From ExecutionPayload (0-1)
    entry_price: Optional[float] = None  # Limit price if not market
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    signal_type: str = "ENTRY"  # ENTRY, EXIT, REDUCE


@dataclass
class BrokerOrder:
    """Order ready to submit to broker."""

    symbol: str
    qty: float
    side: str  # buy or sell
    order_type: str  # market, limit, bracket
    time_in_force: str = "gtc"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    extended_hours: bool = False
    order_id: Optional[str] = None
    status: Optional[str] = None


class OrderManager:
    """
    Manages conversion of execution signals into broker orders.

    This layer sits between ExecutionEngine (creates ExecutionPayload)
    and BrokerConnection (submits to market).
    """

    def __init__(self, broker: BrokerConnection):
        """
        Initialize order manager.

        Args:
            broker: BrokerConnection instance for order submission
        """
        self.broker = broker
        self.submitted_orders: Dict[str, OrderStatus] = {}
        self.order_history: List[OrderStatus] = []

        # Broker rules
        self.min_order_qty = 1  # Minimum shares per order
        self.max_order_qty = 10000  # Maximum shares per order
        self.min_price = Decimal("0.01")  # Minimum price per share

        logger.info(
            f"OrderManager initialized | Mode: {broker.mode.value} | Min qty: {self.min_order_qty}"
        )

    def create_order(
        self,
        symbol: str,
        execution_payload: Dict,
        market_price: float,
        order_type: OrderType = OrderType.MARKET,
    ) -> BrokerOrder:
        """
        Create broker order from execution payload.

        Args:
            symbol: Stock symbol
            execution_payload: From execution_engine (includes position_size, confidence)
            market_price: Current market price
            order_type: Type of order to create

        Returns:
            BrokerOrder ready for submission

        Raises:
            ValueError: If order parameters invalid
        """

        position_size = execution_payload.get("position_size", 1000)
        confidence = execution_payload.get("confidence", 0.5)
        signal_type = execution_payload.get("signal_type", "ENTRY")
        direction = execution_payload.get("direction", "LONG")

        # Validate
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol}")

        if market_price <= 0:
            raise ValueError(f"Invalid market price: {market_price}")

        if position_size <= 0:
            raise ValueError(f"Invalid position size: {position_size}")

        # Calculate share quantity
        qty = self._calculate_quantity(position_size, market_price, confidence)

        logger.info(
            f"Creating order | Symbol: {symbol} | Direction: {direction} | "
            f"Qty: {qty} | Type: {order_type.value} | Confidence: {confidence:.2%}"
        )

        # Determine order side
        if signal_type == "EXIT":
            # Exit trade - reverse the entry direction
            side = "sell" if direction == "LONG" else "buy"
        else:
            side = "buy" if direction == "LONG" else "sell"

        # Create order based on type
        if order_type == OrderType.MARKET:
            broker_order = self._create_market_order(symbol, qty, side)
        elif order_type == OrderType.LIMIT:
            limit_price = self._calculate_limit_price(market_price, direction, confidence)
            broker_order = self._create_limit_order(symbol, qty, side, limit_price)
        elif order_type == OrderType.BRACKET:
            sl_price, tp_price = self._calculate_bracket_levels(
                market_price, direction, confidence, execution_payload
            )
            broker_order = self._create_bracket_order(symbol, qty, side, sl_price, tp_price)
        else:
            raise ValueError(f"Unknown order type: {order_type}")

        return broker_order

    def submit_order(self, broker_order: BrokerOrder) -> OrderStatus:
        """
        Submit order to broker.

        Args:
            broker_order: Order to submit

        Returns:
            OrderStatus from broker

        Raises:
            RuntimeError: If broker connection fails
        """

        logger.info(
            f"[{self.broker.mode.value.upper()}] Submitting order to broker | "
            f"Symbol: {broker_order.symbol} | Side: {broker_order.side} | "
            f"Qty: {broker_order.qty}"
        )

        if self.broker.mode == BrokerMode.LIVE:
            logger.critical("⚠️  LIVE MARKET ORDER - REAL EXECUTION AT CURRENT PRICE")

        # Submit to broker
        order_status = self.broker.submit_order(
            symbol=broker_order.symbol,
            qty=broker_order.qty,
            side=broker_order.side,
            order_type=broker_order.order_type,
            time_in_force=broker_order.time_in_force,
            limit_price=broker_order.limit_price,
            stop_price=broker_order.stop_price,
            extended_hours=broker_order.extended_hours,
        )

        # Track order
        self.submitted_orders[order_status.order_id] = order_status
        self.order_history.append(order_status)

        logger.info(
            f"Order submitted | ID: {order_status.order_id} | Status: {order_status.status}"
        )

        return order_status

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        logger.info(f"Canceling order: {order_id}")

        if self.broker.cancel_order(order_id):
            if order_id in self.submitted_orders:
                self.submitted_orders[order_id].status = "canceled"
            return True
        return False

    def close_position(self, symbol: str) -> OrderStatus:
        """Close all open positions in a symbol."""
        logger.info(f"Closing position: {symbol}")

        # Market order to close (opposite side)
        position = self.broker.get_position(symbol)
        if not position:
            raise ValueError(f"No open position in {symbol}")

        side = "sell" if position.side == "long" else "buy"
        qty = position.qty

        order_status = self.broker.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="market",
            time_in_force="day",
        )

        self.submitted_orders[order_status.order_id] = order_status
        self.order_history.append(order_status)

        logger.info(f"Position close order submitted: {order_status.order_id}")

        return order_status

    # ==================== PRIVATE HELPERS ====================

    def _calculate_quantity(
        self, position_size: float, market_price: float, confidence: float
    ) -> float:
        """
        Convert dollar position size to share quantity.

        Args:
            position_size: Dollar amount to invest
            market_price: Current price per share
            confidence: Signal confidence (0-1)

        Returns:
            Number of shares to order (rounded down to whole number)
        """

        # Confidence-based scaling
        # Higher confidence = willingness to size up
        scaled_size = position_size * (0.7 + 0.3 * confidence)

        # Calculate shares
        qty = scaled_size / market_price

        # Validate against broker limits
        qty = max(self.min_order_qty, qty)
        qty = min(self.max_order_qty, qty)

        # Round down to whole shares
        qty = int(qty)

        logger.debug(
            f"Quantity calculated | Position: ${position_size} | "
            f"Price: ${market_price} | Confidence: {confidence:.1%} | "
            f"Qty: {qty} shares"
        )

        return qty

    def _calculate_limit_price(
        self, market_price: float, direction: str, confidence: float
    ) -> float:
        """
        Calculate limit price for order.

        For LONG entries: Slightly below market (0.2% discount)
        For SHORT entries: Slightly above market (0.2% premium)
        Higher confidence = tighter limit (more likely to execute)

        Args:
            market_price: Current market price
            direction: LONG or SHORT
            confidence: Signal confidence (0-1)

        Returns:
            Limit price
        """

        # Limit price offset: 0.1% to 0.5% depending on confidence
        offset_pct = 0.005 - (confidence * 0.004)  # 0.5% - 0.1%

        if direction == "LONG":
            limit_price = market_price * (1 - offset_pct)
        else:  # SHORT
            limit_price = market_price * (1 + offset_pct)

        # Round to nearest cent
        limit_price = round(limit_price, 2)

        return limit_price

    def _calculate_bracket_levels(
        self,
        market_price: float,
        direction: str,
        confidence: float,
        execution_payload: Dict,
    ) -> Tuple[float, float]:
        """
        Calculate stop loss and take profit levels for bracket orders.

        Args:
            market_price: Current price
            direction: LONG or SHORT
            confidence: Signal confidence (0-1)
            execution_payload: May contain risk_reward_ratio

        Returns:
            (stop_loss_price, take_profit_price)
        """

        # Risk/reward ratio from payload or default
        risk_reward_ratio = execution_payload.get("risk_reward_ratio", 1.5)

        # Base risk distance: 2% - 1% depending on confidence
        risk_distance_pct = 0.02 - (confidence * 0.01)

        if direction == "LONG":
            # Buy: SL below, TP above
            sl_price = market_price * (1 - risk_distance_pct)
            tp_price = market_price * (1 + (risk_distance_pct * risk_reward_ratio))
        else:  # SHORT
            # Sell: SL above, TP below
            sl_price = market_price * (1 + risk_distance_pct)
            tp_price = market_price * (1 - (risk_distance_pct * risk_reward_ratio))

        # Round to nearest cent
        sl_price = round(sl_price, 2)
        tp_price = round(tp_price, 2)

        logger.debug(
            f"Bracket levels calculated | Market: ${market_price} | "
            f"SL: ${sl_price} | TP: ${tp_price} | RRR: {risk_reward_ratio}"
        )

        return sl_price, tp_price

    def _create_market_order(self, symbol: str, qty: float, side: str) -> BrokerOrder:
        """Create market order."""
        return BrokerOrder(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="market",
            time_in_force="day",
        )

    def _create_limit_order(
        self, symbol: str, qty: float, side: str, limit_price: float
    ) -> BrokerOrder:
        """Create limit order."""
        return BrokerOrder(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="limit",
            limit_price=limit_price,
            time_in_force="gtc",  # Good til cancel
        )

    def _create_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> BrokerOrder:
        """
        Create bracket order (market entry with TP + SL).

        In production, this would be submitted as:
        1. Primary market order
        2. Contingent stop-loss order (triggers on loss)
        3. Contingent take-profit order (triggers on profit)
        """
        return BrokerOrder(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="bracket",
            time_in_force="gtc",
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Get current status of an order."""
        if order_id in self.submitted_orders:
            return self.submitted_orders[order_id]
        return None

    def get_open_orders(self) -> List[OrderStatus]:
        """Get all currently open orders."""
        open_statuses = ["pending_new", "accepted", "partial_fill"]
        return [order for order in self.order_history if order.status in open_statuses]

    def get_order_history(self) -> List[OrderStatus]:
        """Get complete order history."""
        return self.order_history.copy()
