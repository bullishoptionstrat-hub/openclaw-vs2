"""
fib5 data contracts.

Fib5Config  — extends Fib4Config with friction params
"""

from __future__ import annotations

from dataclasses import dataclass

from research.fib4.model import Fib4Config


@dataclass
class Fib5Config(Fib4Config):
    """
    All Fib4Config fields plus fib5-specific validation params.

    Friction model:
      slippage_pct          — one-way slippage as fraction of price.
                              Round-trip cost = 2 * slippage_pct.
                              0.0005 = 5bps (realistic for liquid ETFs).
                              0.001  = 10bps (conservative).
      commission_per_trade  — flat commission per round-trip ($).
                              0.0 for modern zero-commission brokers.

    OOS periods (used by walkforward.py, not the backtester):
      is_start / is_end     — in-sample window
      oos1_start / oos1_end — first OOS window
      oos2_start            — second OOS / holdout start (empty = skip)
    """

    # ── Friction ─────────────────────────────────────────────────────────────
    slippage_pct: float = 0.0  # 0.0005 = 5bps per leg
    commission_per_trade: float = 0.0  # $ per round-trip

    # ── OOS split defaults ───────────────────────────────────────────────────
    is_start: str = "20070101"
    is_end: str = "20161231"
    oos1_start: str = "20170101"
    oos1_end: str = "20221231"
    oos2_start: str = "20230101"
    oos2_end: str = ""  # Empty = use all available data from oos2_start
