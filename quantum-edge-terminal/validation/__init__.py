"""Validation Layer - Institutional-grade system validation and risk management.

This layer bridges tested systems and trusted systems:
1. Scoring Engine: Multi-dimensional performance evaluation
2. Forward Test Engine: Real-time paper trading validation
3. Safety Controls: Kill switches and circuit breakers
4. Validation Monitor: Metrics tracking and reporting

The system should ONLY graduate to real capital after:
- 20-30 trading days forward testing with positive expectancy
- Controlled drawdown (< 8%)
- Stable execution behavior
- Pass institutional scorecard gate
"""

from .scoring_engine import (
    InstitutionalScorecard,
    ValidationResult,
    GateStatus,
)
from .forward_test_engine import (
    ForwardTestEngine,
    GeneratedSignal,
    PaperTrade,
)
from .safety_controls import SafetyControls, SafetyStatus
from .validation_orchestrator import (
    ValidationOrchestrator,
    ValidationPhase,
    ValidationMetrics,
    ValidationGateDecision,
)
from .integration_bridge import (
    IntegrationBridge,
    BridgeSignal,
    BridgeExecutionResult,
)
from .live_validation_runner import (
    LiveValidationRunner,
    ValidationRunConfig,
)

__all__ = [
    # Phase 6 - Validation Core
    "InstitutionalScorecard",
    "ValidationResult",
    "GateStatus",
    "ForwardTestEngine",
    "GeneratedSignal",
    "PaperTrade",
    "SafetyControls",
    "SafetyStatus",
    # Phase 7 - Integration & Orchestration
    "ValidationOrchestrator",
    "ValidationPhase",
    "ValidationMetrics",
    "ValidationGateDecision",
    "IntegrationBridge",
    "BridgeSignal",
    "BridgeExecutionResult",
    "LiveValidationRunner",
    "ValidationRunConfig",
]
