"""
fib3 backtester — thin adapter around fib2's simulation engine.

QualifiedLeg is duck-type compatible with ManipulationLeg:
all attribute names used by fib2's _simulate_leg_daily() and _run_trade()
are present on QualifiedLeg.

The Fib3Config inherits from StrictFibConfig so it can be passed directly
to fib2's simulate() without conversion.
"""

from __future__ import annotations

from typing import Optional

from research.fib3.model import Fib3Config, QualifiedLeg
import research.fib2.backtester as _fib2


def simulate(
    legs: list[QualifiedLeg],
    daily_bars: dict,
    config: Fib3Config,
    spy_daily: Optional[dict] = None,
) -> list:
    """
    Simulate all qualified legs using fib2's daily-bar trade engine.

    QualifiedLeg objects pass through duck-typing — fib2 only accesses
    fields that QualifiedLeg also carries.

    Returns list[StrictTradeResult] (from fib2.model).
    """
    return _fib2.simulate(
        legs=legs,
        daily_bars=daily_bars,
        config=config,  # Fib3Config IS-A StrictFibConfig
        hourly_bars=None,
        date_to_1h=None,
        spy_daily=spy_daily,
    )
