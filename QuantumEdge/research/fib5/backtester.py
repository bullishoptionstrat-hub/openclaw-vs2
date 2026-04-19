"""
fib5 backtester — thin wrapper around fib4.backtester with friction adjustment.

Friction model:
  Slippage is applied post-simulation as an R adjustment.
  For each trade:
    friction_r = (2 * slippage_pct * entry_price + commission_per_trade) / risk_per_share
    adj_r = r_multiple - friction_r

  The adjusted_r values are used for friction-adjusted stats.
  Original results are preserved unchanged.
"""

from __future__ import annotations

from typing import Optional

from research.fib4 import backtester as _fib4
from research.fib5.model import Fib5Config


def simulate(
    legs: list,
    daily_bars: dict,
    config: Fib5Config,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
    spy_daily: Optional[dict] = None,
) -> tuple[list, int, int]:
    """
    Simulate using fib4's engine.  Returns (results, n_legs, n_skipped).
    Friction is applied separately via friction_adjusted_r().
    """
    return _fib4.simulate(
        legs=legs,
        daily_bars=daily_bars,
        config=config,
        hourly_bars=hourly_bars,
        date_to_1h=date_to_1h,
        spy_daily=spy_daily,
    )


def friction_adjusted_r(results: list, config: Fib5Config) -> list[float]:
    """
    Return friction-adjusted R multiples for each trade.
    Does not modify the original StrictTradeResult objects.
    """
    if config.slippage_pct == 0.0 and config.commission_per_trade == 0.0:
        return [t.r_multiple for t in results]

    adjusted = []
    for t in results:
        rps = max(t.risk_per_share, 1e-6)
        slip_cost = 2.0 * config.slippage_pct * t.entry_price
        comm_cost = config.commission_per_trade
        friction_r = (slip_cost + comm_cost) / rps
        adjusted.append(t.r_multiple - friction_r)
    return adjusted
