"""
fib4 data contracts.

Fib4Config     — inherits Fib3Config, adds execution trigger params
EntryDecision  — result of entry state machine (enter/skip + metadata)
"""

from __future__ import annotations

from dataclasses import dataclass

from research.fib3.model import Fib3Config


# ---------------------------------------------------------------------------
# Config (extends Fib3Config)
# ---------------------------------------------------------------------------


@dataclass
class Fib4Config(Fib3Config):
    """
    All Fib3Config fields plus fib4-specific execution params.

    entry_trigger
        The execution variant.  Replaces Fib2/Fib3 entry_confirmation
        for fib4's entry logic.  Supported values:
          "touch_rejection"     — wick into zone, close above midzone
          "nextbar_confirm"     — zone touched bar B, B+1 close moves N*ATR
          "close_in_zone"       — close inside zone (baseline, fib3 behavior)
          "1h_rejection"        — 1H wick + 1H close above midzone
          "1h_structure_shift"  — 1H local pivot in zone
          "1h_displacement_off" — 1H close beyond zone edge after wick
          "midzone_only"        — tight band around fib_50, rejection check
          "zone_0382_only"      — tight band around fib_382
          "zone_0618_only"      — tight band around fib_618

    fallback_trigger
        Used when entry_trigger starts with "1h_" but hourly data is
        unavailable (QQQ, XLK).  Defaults to "close_in_zone".

    nextbar_confirm_atr
        For nextbar_confirm: bar B+1 must close >= B_close + N*ATR.

    midzone_tolerance_atr
        Half-width of tight zone band (midzone_only / zone_*_only).
        Measured in ATR multiples.

    no_passive_max_bars
        If > 0: skip the setup if price drifts passively in zone for
        more than N bars without firing the trigger.
        0 = disabled (default).
    """

    # ── Entry trigger (replaces entry_confirmation for fib4 logic) ─────────
    entry_trigger: str = "touch_rejection"

    # ── 1H fallback ─────────────────────────────────────────────────────────
    fallback_trigger: str = "close_in_zone"

    # ── nextbar_confirm params ───────────────────────────────────────────────
    nextbar_confirm_atr: float = 0.30

    # ── Tight-band zone params ───────────────────────────────────────────────
    midzone_tolerance_atr: float = 0.20  # Half-width: center +/- N*ATR

    # ── No-passive filter ────────────────────────────────────────────────────
    no_passive_max_bars: int = 0  # 0 = disabled


# ---------------------------------------------------------------------------
# Entry decision
# ---------------------------------------------------------------------------


@dataclass
class EntryDecision:
    """
    Result of the entry state machine for one leg.

    If enter=True, the trade begins at entry_bar_daily / entry_price.
    If skipped=True, the setup was seen but rejected by the trigger logic.
    If both are False, no zone interaction occurred within the wait window.
    """

    enter: bool = False
    entry_bar_daily: int = -1  # Daily bar index where trade opens
    entry_price: float = 0.0  # Actual fill price (1H open or daily open)
    trigger_type: str = ""  # Which trigger fired

    skipped: bool = False
    skip_reason: str = ""
    # "passive_timeout"       — drifted in zone without trigger
    # "nextbar_confirm_failed"— zone touch occurred but B+1 didn't confirm
    # "invalidated"           — stop level hit before zone reached
    # "no_trigger_fired"      — zone never reached or trigger never met
    # "no_1h_data"            — 1H trigger requested but no hourly data found
