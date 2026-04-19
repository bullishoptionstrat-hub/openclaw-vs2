"""
fib7 live signal readiness specification generator.

For each config that reaches DEPLOYMENT CANDIDATE or LIVE-READY CANDIDATE,
this module generates a structured signal spec card describing:

  1. Signal armed conditions (setup detection rules)
  2. Signal confirmed conditions (entry trigger rules)
  3. Signal invalidated conditions (setup failure / cancellation rules)
  4. Data requirements (what data must be available at signal time)
  5. Latency constraints (how much time between signal and entry)
  6. Risk parameters (stop, target, position size)
  7. Regime check (what vol/ATR state must be true at signal bar)

Signal card output is a structured dict + printable ASCII card.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Signal state machine definitions
# ---------------------------------------------------------------------------

# Supported entry triggers (from fib4/fib6)
TRIGGER_DESCRIPTIONS = {
    "touch_rejection": (
        "Price enters the Fibonacci zone (zone_low–zone_high) and closes "
        "back above zone_low (bullish) or below zone_high (bearish). "
        "Entry at next bar open."
    ),
    "midzone_only": (
        "Price enters the mid-zone (fib_382–fib_618) and a daily bar shows "
        "a wick rejection (close vs open directional signal). "
        "Entry at next bar open."
    ),
    "nextbar_confirm": (
        "After zone touch, wait for next bar to confirm direction with "
        "a close above entry reference. Entry at open after confirm bar."
    ),
    "close_in_zone": ("Price closes within zone_low–zone_high bounds. Entry at next bar open."),
    "displacement_off": (
        "After touching zone, an expansion bar (body > ATR threshold) closes "
        "back in the direction of the trade. Entry at close of expansion bar."
    ),
    "1h_displacement_off": (
        "1-Hour bar version of displacement_off. "
        "Requires intraday data. "
        "Entry at close of 1H expansion bar or open of following 1H bar."
    ),
    "1h_structure_shift": (
        "1-Hour CHoCH (change of character): first 1H bar that closes above "
        "the highest high of the prior 1H consolidation range within the zone."
        "Entry at next 1H open."
    ),
    "1h_rejection": (
        "1-Hour wick rejection within zone: 1H bar wicks into zone but closes "
        "back outside. Entry at next 1H open."
    ),
    "1h_reclaim_after_sweep": (
        "REJECTED in fib6: scan 1H for sweep below zone_low, then reclaim. "
        "Result: -0.201R, 30.6% win rate. DO NOT USE."
    ),
}

STOP_DESCRIPTIONS = {
    "origin": (
        "Stop at origin: below anchor_bar low (bullish) minus stop_buffer ATR. "
        "Provides maximum room for the setup to play out. "
        "Typical distance: 1.0–2.0 ATR below zone_low."
    ),
    "fib_786": (
        "Stop at 78.6% retracement of the leg. Tighter than origin. "
        "Accepts slightly lower win rate for better R/R on targets. "
        "Typical distance: ~0.5 ATR below zone_low."
    ),
}

VOL_GATE_DESCRIPTIONS = {
    "vol_quiet": (
        "Discovery bar volume < 20-bar average volume (ratio < 1.0). "
        "Represents a low-participation setup discovery — the pattern formed "
        "without high-volume confirmation bias."
    ),
    "vol_active": (
        "Discovery bar volume >= 20-bar average volume (ratio >= 1.0). "
        "Represents a high-participation setup discovery."
    ),
    "neutral": "No volume filter applied.",
}


# ---------------------------------------------------------------------------
# Live signal spec card generator
# ---------------------------------------------------------------------------


def generate_signal_spec(
    config_name: str,
    config,
    stats: dict,
    oos_stats: Optional[dict] = None,
    classification: str = "DEPLOYMENT CANDIDATE",
) -> dict:
    """
    Generate a live signal spec for one config.

    Parameters
    ----------
    config_name    : human-readable name (e.g. "xlk_vol_quiet")
    config         : Fib7Config (or Fib6Config) instance
    stats          : full-run stats dict from compute_stats()
    oos_stats      : OOS1 period stats dict (optional, for edge decay estimate)
    classification : current classification tier

    Returns
    -------
    dict with all spec fields + printable card
    """
    trigger = getattr(config, "entry_trigger", "touch_rejection")
    stop = getattr(config, "stop_variant", "origin")
    target = getattr(config, "target_fib", 1.618)
    vol_gate = getattr(config, "vol_regime_gate", "neutral")
    regime_bar = getattr(config, "regime_bar", "discovery")
    quality_min = getattr(config, "quality_min_score", 0.0)
    sweep_min = getattr(config, "quality_min_sweep", 0.0)
    sweep_req = getattr(config, "require_sweep", False)
    disp_atr = getattr(config, "min_displacement_atr", 2.0)
    vol_lookback = getattr(config, "vol_lookback", 20)
    slippage = getattr(config, "slippage_pct", 0.0)

    # --- Armed conditions (setup detection) ---
    armed_conditions = [
        f"Leg displacement >= {disp_atr}x ATR",
        f"Quality score >= {quality_min:.0f}" if quality_min > 0 else "Quality score: all tiers",
    ]
    if sweep_req:
        armed_conditions.append(
            f"Sweep (spring) required: sweep_score >= {sweep_min:.0f}"
            if sweep_min > 0
            else "Sweep (spring) required: any depth"
        )
    armed_conditions.append(
        f"Vol regime: {vol_gate} at {regime_bar}_bar (lookback={vol_lookback} bars, threshold=1.0)"
        if vol_gate != "neutral"
        else "Vol regime: no filter"
    )

    # --- Confirmed conditions (entry trigger) ---
    confirmed_conditions = [
        TRIGGER_DESCRIPTIONS.get(trigger, f"Trigger: {trigger}"),
        f"Stop: {STOP_DESCRIPTIONS.get(stop, stop)}",
        f"Target: {target}x extension of the manipulation leg",
    ]

    # --- Invalidated conditions ---
    invalidated_conditions = [
        f"Price closes below stop_price_{stop} before entry (bullish)",
        f"Price closes above stop_price_{stop} before entry (bearish)",
        f"Setup expires after max_zone_wait_bars without trigger firing",
        f"Vol regime flips (discovery_bar ratio crosses threshold) — note: checked at detection, not entry",
    ]

    # --- Data requirements ---
    needs_hourly = trigger.startswith("1h_")
    data_requirements = [
        "Daily OHLCV data for instrument (adjusted closes preferred)",
        "SPY daily data (for 200-SMA bull/bear regime filter)",
        "ATR(14) computed at real-time (rolling, not fixed)",
        f"Volume 20-bar rolling average at {regime_bar} bar",
    ]
    if needs_hourly:
        data_requirements.append("Hourly OHLCV data for 1H trigger resolution")
    if vol_gate != "neutral":
        data_requirements.append(f"Volume at {regime_bar} bar available BEFORE setup qualification")

    # --- Latency constraints ---
    if trigger in ("touch_rejection", "close_in_zone", "midzone_only"):
        latency = "End-of-day: entry at next open (no intraday required)"
        latency_window = "Entry window: first 30 min of next session open"
    elif trigger == "nextbar_confirm":
        latency = "End-of-day: entry at next bar open (two-bar delay)"
        latency_window = "Entry window: first 30 min of session after confirm bar"
    elif trigger == "displacement_off":
        latency = "End-of-day: entry at close of expansion bar"
        latency_window = "Entry at bar close or MOC order"
    elif trigger.startswith("1h_"):
        latency = "Intraday: entry within 1H of trigger bar close"
        latency_window = "Entry window: open of 1H bar after trigger"
    else:
        latency = "Unknown — review trigger implementation"
        latency_window = "Unknown"

    # --- Risk parameters ---
    n_trades = stats.get("n_trades", 0)
    exp_r = stats.get("expectancy_r", 0.0)
    win_rate = stats.get("win_rate", 0.0)
    sharpe = stats.get("sharpe_r", 0.0)
    max_dd = stats.get("max_drawdown", 0.0)
    slippage_impact = (
        f"~{slippage * 2 * 100:.2f}bps round-trip" if slippage > 0 else "0 (not modeled)"
    )

    oos_note = ""
    if oos_stats and oos_stats.get("n_trades", 0) >= 3:
        oos_r = oos_stats.get("expectancy_r", 0.0)
        oos_note = f"OOS1 validation: {oos_r:+.3f}R ({oos_stats['n_trades']} trades)"
        if oos_r > exp_r * 0.5:
            oos_note += " — HOLDS OOS"
        elif oos_r > 0:
            oos_note += " — degrades but positive"
        else:
            oos_note += " — OOS NEGATIVE"

    spec = {
        "config_name": config_name,
        "classification": classification,
        "trigger": trigger,
        "stop_variant": stop,
        "target_fib": target,
        "vol_gate": vol_gate,
        "regime_bar": regime_bar,
        "quality_min_score": quality_min,
        "require_sweep": sweep_req,
        "min_displacement_atr": disp_atr,
        "armed_conditions": armed_conditions,
        "confirmed_conditions": confirmed_conditions,
        "invalidated_conditions": invalidated_conditions,
        "data_requirements": data_requirements,
        "latency": latency,
        "latency_window": latency_window,
        "risk_parameters": {
            "stop": stop,
            "target": target,
            "typical_rr": round(target, 3),
            "expected_win_rate": round(win_rate, 3),
            "expected_exp_r": round(exp_r, 4),
            "sharpe_r": round(sharpe, 3),
            "max_drawdown": round(max_dd, 4),
            "slippage_modeled": slippage_impact,
        },
        "track_record": {
            "n_trades": n_trades,
            "exp_r": round(exp_r, 4),
            "win_rate": round(win_rate, 3),
            "sharpe_r": round(sharpe, 3),
            "max_drawdown": round(max_dd, 4),
            "oos_note": oos_note,
        },
        "needs_hourly_data": needs_hourly,
    }
    return spec


def print_signal_spec_card(spec: dict) -> None:
    """Print a formatted ASCII signal spec card."""
    w = 76
    cfg = spec["config_name"]
    cls = spec["classification"]

    print(f"\n{'#' * w}")
    print(f"  LIVE SIGNAL SPEC CARD: {cfg}")
    print(f"  Classification: {cls}")
    print(f"{'#' * w}")

    tr = spec["track_record"]
    rp = spec["risk_parameters"]
    print(f"\n  Track Record:")
    print(
        f"    Trades: {tr['n_trades']}  |  ExpR: {tr['exp_r']:+.3f}  |  "
        f"Win%: {tr['win_rate']:.1%}  |  Sharpe: {tr['sharpe_r']:.3f}  |  "
        f"MaxDD: {tr['max_drawdown']:.2%}"
    )
    if tr.get("oos_note"):
        print(f"    {tr['oos_note']}")

    print(f"\n  Parameters:")
    print(f"    Trigger    : {spec['trigger']}")
    print(f"    Stop       : {spec['stop_variant']}")
    print(f"    Target     : {spec['target_fib']}x extension")
    print(f"    Vol gate   : {spec['vol_gate']} at {spec['regime_bar']}_bar")
    print(f"    Quality min: {spec['quality_min_score']:.0f}")
    print(f"    Slippage   : {rp['slippage_modeled']}")

    print(f"\n  ARMED (setup detection):")
    for cond in spec["armed_conditions"]:
        print(f"    + {cond}")

    print(f"\n  CONFIRMED (entry trigger):")
    for cond in spec["confirmed_conditions"]:
        print(f"    + {cond}")

    print(f"\n  INVALIDATED (cancel setup):")
    for cond in spec["invalidated_conditions"]:
        print(f"    - {cond}")

    print(f"\n  DATA REQUIREMENTS:")
    for req in spec["data_requirements"]:
        print(f"    * {req}")

    print(f"\n  LATENCY / EXECUTION:")
    print(f"    {spec['latency']}")
    print(f"    {spec['latency_window']}")
    if spec["needs_hourly_data"]:
        print(f"    NOTE: Requires intraday (1H) data feed")

    print(f"\n{'#' * w}\n")


def print_all_spec_cards(specs: list[dict]) -> None:
    """Print spec cards for all surviving configs."""
    if not specs:
        print("  No live signal specs generated (no DEPLOYMENT+ configs).")
        return
    w = 76
    print(f"\n{'=' * w}")
    print(f"  FIB7 TRACK E -- LIVE SIGNAL READINESS SPECS")
    print(f"  {len(specs)} config(s) reached specification stage")
    print(f"{'=' * w}")
    for spec in specs:
        print_signal_spec_card(spec)
