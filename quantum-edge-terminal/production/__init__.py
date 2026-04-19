"""
Production Deployment System for Quantum Edge Terminal

Complete production infrastructure for deploying validated trading systems
to real markets with live broker integration.

COMPONENTS:
-----------

1. MarketDataStreamer
   Real-time market data ingestion from Alpaca (OHLCV bars)
   Multi-symbol support, market hours detection, reconnection logic

2. LiveBrokerConnector
   Real broker order execution with risk enforcement
   Paper/Live mode toggle, position tracking, risk validation

3. DeploymentGateController
   Automated deployment decision system with operator approval
   7-state machine, pass criteria enforcement, circuit breakers

4. PerformanceMonitor
   Real-time performance tracking and anomaly detection
   Baseline comparison, alert generation, daily reporting

5. ProductionRunner
   Complete system orchestration
   Lifecycle management: validation → approval → deployment → monitoring

WORKFLOW:
---------

1. Initialize system components
2. Start 30-day validation period
3. Stream market data + generate signals
4. Forward test on paper
5. Evaluate gate decision
6. Request operator approval
7. Enable live trading
8. Monitor performance vs baseline
9. Alert on anomalies or circuit breaker triggers

USAGE:
------

from production import ProductionRunner, SystemConfig

config = SystemConfig(
    symbols=["SPY", "QQQ"],
    validation_period_days=30,
    initial_capital=100000.0,
    deployment_capital=10000.0,
)

runner = ProductionRunner(config)
runner.initialize_system()
runner.start_validation_period()

# ... 30 days of validation ...

gate_decision = runner.complete_validation_period()
runner.request_deployment_approval("operator@example.com", 10000.0)
runner.enable_live_trading()

# Monitor live performance
while True:
    metrics = runner.monitor_live_performance()
    if metrics["drawdown"] > 0.05:
        runner.suspend_trading("Max drawdown exceeded")
        break

SAFETY:
-------

- Two-stage deployment gate (pass criteria + operator approval)
- Risk validation on every order (position size, cash, daily loss)
- Circuit breakers (5% max drawdown, 2% daily loss limit)
- Emergency stop capability (suspend_trading)
- Real-time anomaly detection vs validation baseline
- Position size limits (5% max per position)

DEPENDENCIES:
--------------

Core modules:
- market_data_streamer (Alpaca WebSocket integration)
- live_broker_connector (Alpaca REST + paper simulator)
- deployment_gate_controller (Gate decision + state machine)
- performance_monitor (Performance tracking + alerts)

External:
- alpaca-trade-api (live broker connection)
- asyncio (streaming)
- datetime, dataclasses, typing (core Python)
"""

from .market_data_streamer import (
    MarketDataStreamer,
    StreamingConfig,
    MarketBar,
    BarTimeframe,
    MarketStatus,
)

from .live_broker_connector import (
    LiveBrokerConnector,
    BrokerConfig,
    LiveOrder,
    OrderStatus,
    BrokerMode,
)

from .deployment_gate_controller import (
    DeploymentGateController,
    DeploymentState,
    DeploymentMetrics,
    DeploymentApproval,
)

from .performance_monitor import (
    PerformanceMonitor,
    PerformanceSnapshot,
    PerformanceAlert,
    AlertType,
    AlertLevel,
)

from .production_runner import ProductionRunner, SystemConfig, SystemState

__all__ = [
    # Market data streaming
    "MarketDataStreamer",
    "StreamingConfig",
    "MarketBar",
    "BarTimeframe",
    "MarketStatus",
    # Live broker connection
    "LiveBrokerConnector",
    "BrokerConfig",
    "LiveOrder",
    "OrderStatus",
    "BrokerMode",
    # Deployment gate
    "DeploymentGateController",
    "DeploymentState",
    "DeploymentMetrics",
    "DeploymentApproval",
    # Performance monitoring
    "PerformanceMonitor",
    "PerformanceSnapshot",
    "PerformanceAlert",
    "AlertType",
    "AlertLevel",
    # Production orchestration
    "ProductionRunner",
    "SystemConfig",
    "SystemState",
]

__version__ = "8.0.0"
__doc__ = """
Production Deployment System for Quantum Edge Terminal
Version 8.0.0 - Complete Production Infrastructure
"""
