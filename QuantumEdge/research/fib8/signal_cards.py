"""
fib8 signal card generator.

For each PAPER-TRADE CANDIDATE and above, generates a structured signal card
describing exactly how to operate the signal live.

SignalCard     -- structured card dataclass
generate_card()-- builds card from config + promotion score + stats
print_card()   -- ASCII formatted output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from research.fib8.model import PAPER_TRADE, SIGNAL_CARD, LIVE_READY, TIER_ORDER


# ---------------------------------------------------------------------------
# Thesis templates (human-readable summaries for known configs)
# ---------------------------------------------------------------------------

THESES = {
    "xlk_vq_baseline": (
        "Fibonacci retracement spring in XLK during low-volume discovery. "
        "A supply raid below a swing low is followed by a touch-rejection entry, "
        "targeting 1.618x the manipulation leg. "
        "Regime gate: vol at discovery_bar below 20-bar average."
    ),
    "xlk_vq_tr_786_1618": (
        "Same as xlk_vq_baseline but uses the 78.6% retracement as stop "
        "(tighter, accepts slightly lower win rate for same R target). "
        "Higher single-instrument ExpR but narrower cross-instrument stability."
    ),
    "qqq_completion_vol_active": (
        "Fibonacci completion-bar spring in QQQ during high-volume completion. "
        "Entry: midzone only (382-618 zone). "
        "Regime gate: vol at completion_bar above 20-bar average. "
        "Strong OOS1 validation (+0.884R on 2017-2022 data)."
    ),
    "qqq_atr_quiet": (
        "Fibonacci spring in QQQ when daily ATR is below its 20-bar ATR average. "
        "Simpler than the completion-bar variant; no bar-timing dependency. "
        "Thinner sample (n=19) but positive OOS1."
    ),
    "spy_vol_active_1h_disp": (
        "Fibonacci spring in SPY during high-volume discovery, "
        "confirmed by a 1-hour displacement bar closing back in trade direction. "
        "Best SPY combo from fib7 Track C. Requires intraday data."
    ),
    "spy_vol_active_1h_struct": (
        "Fibonacci spring in SPY confirmed by 1-hour change-of-character (CHoCH). "
        "Lower density than 1h_disp variant. "
        "Requires intraday data."
    ),
}

EXPECTED_FREQUENCY = {
    "xlk_vq_baseline": "3-6 trades/year on XLK (daily signal)",
    "xlk_vq_tr_786_1618": "3-5 trades/year on XLK",
    "qqq_completion_vol_active": "2-5 trades/year on QQQ (midzone filter reduces density)",
    "qqq_atr_quiet": "2-4 trades/year on QQQ (ATR quiet filter)",
    "spy_vol_active_1h_disp": "4-8 trades/year on SPY (1H trigger, more frequent)",
    "spy_vol_active_1h_struct": "3-6 trades/year on SPY",
}

EXPECTED_HOLD_TIME = {
    "xlk_vq_baseline": "8-20 days typical (target 1.618x leg; daily bars)",
    "xlk_vq_tr_786_1618": "8-20 days typical",
    "qqq_completion_vol_active": "5-15 days typical",
    "qqq_atr_quiet": "5-15 days typical",
    "spy_vol_active_1h_disp": "3-12 days typical (1H trigger may enter earlier)",
    "spy_vol_active_1h_struct": "3-12 days typical",
}

FAILURE_MODES = {
    "xlk_vq_baseline": [
        "Sector rotation causes XLK to underperform SPY regime -- vol_quiet gate still fires",
        "Tight stop at origin hit by gap open before entry can be placed",
        "Tech earnings event invalidates setup structure mid-hold",
    ],
    "xlk_vq_tr_786_1618": [
        "Tighter 78.6% stop increases stop-out frequency in choppy markets",
        "Less instrument-stable than baseline -- avoid using on IWM/XLY",
    ],
    "qqq_completion_vol_active": [
        "completion_bar timing requires two-bar lookback at detection time -- data latency risk",
        "Thinner historical sample (n=29) means OOS2 accumulation is critical",
        "Vol-active at completion_bar means misses low-vol regime setups entirely",
    ],
    "qqq_atr_quiet": [
        "Thin sample (n=19) -- coin flip risk in short-run",
        "ATR quiet regime can persist during trending markets, causing false signals",
    ],
    "spy_vol_active_1h_disp": [
        "Requires reliable 1H data feed -- execution is intraday",
        "No OOS grid validation yet -- may be curve-fitted to 2007-2024 SPY",
        "1H displacement trigger is market-hours dependent -- gaps can skip trigger",
    ],
    "spy_vol_active_1h_struct": [
        "Lower density than 1h_disp -- fewer opportunities to build confidence",
        "CHoCH detection is discretionary if not programmed precisely",
    ],
}


# ---------------------------------------------------------------------------
# SignalCard dataclass
# ---------------------------------------------------------------------------


@dataclass
class SignalCard:
    config_name: str
    ticker_universe: list[str]
    thesis: str
    regime_gate: str
    armed_conditions: list[str]
    confirmation_trigger: str
    entry_rule: str
    stop_rule: str
    target_rule: str
    invalidation_rules: list[str]
    skip_rules: list[str]
    expected_frequency: str
    expected_hold_time: str
    friction_assumptions: str
    failure_modes: list[str]
    promotion_status: str
    upgrade_evidence: str
    downgrade_evidence: str
    promotion_score: int
    promotion_score_breakdown: dict
    track_record: dict = field(default_factory=dict)
    needs_intraday: bool = False


# ---------------------------------------------------------------------------
# Card generator
# ---------------------------------------------------------------------------


def generate_card(
    config_name: str,
    config,
    stats: dict,
    promotion_score,
    ticker_universe: Optional[list[str]] = None,
) -> SignalCard:
    """
    Generate a signal card for one config.

    Parameters
    ----------
    config_name      : str
    config           : Fib7Config / Fib8Config
    stats            : compute_stats() result for primary period
    promotion_score  : PromotionScore instance
    ticker_universe  : list of instruments this config applies to
    """
    trigger = getattr(config, "entry_trigger", "touch_rejection")
    stop = getattr(config, "stop_variant", "origin")
    target = getattr(config, "target_fib", 1.618)
    vol_gate = getattr(config, "vol_regime_gate", "neutral")
    regime_bar = getattr(config, "regime_bar", "discovery")
    atr_gate = getattr(config, "atr_regime_gate", "neutral")
    disp_atr = getattr(config, "min_displacement_atr", 2.0)
    sweep_req = getattr(config, "require_sweep", False)
    sweep_min = getattr(config, "quality_min_sweep", 0.0)
    quality_min = getattr(config, "quality_min_score", 0.0)
    slippage = getattr(config, "slippage_pct", 0.0)
    needs_intraday = trigger.startswith("1h_")

    if ticker_universe is None:
        ticker_universe = ["XLK"]

    # Regime gate description
    if vol_gate != "neutral" and atr_gate != "neutral":
        regime_gate = f"Vol {vol_gate} at {regime_bar}_bar AND ATR {atr_gate} at discovery_bar"
    elif vol_gate != "neutral":
        regime_gate = f"Vol {vol_gate} at {regime_bar}_bar (vol/avg_vol_20 threshold=1.0)"
    elif atr_gate != "neutral":
        regime_gate = f"ATR {atr_gate} at discovery_bar (atr/avg_atr_20 threshold=1.0)"
    else:
        regime_gate = "No regime filter (neutral)"

    # Armed conditions
    armed = [
        f"Leg displacement >= {disp_atr}x ATR(14)",
        f"Quality score >= {quality_min:.0f}" if quality_min > 0 else "Quality score: all tiers",
    ]
    if sweep_req:
        armed.append(
            f"Sweep required: sweep_score >= {sweep_min:.0f}"
            if sweep_min > 0
            else "Sweep required (any depth)"
        )
    armed.append(regime_gate)

    # Entry rule
    entry_map = {
        "touch_rejection": "Enter at next daily open after zone-touch bar closes back outside zone",
        "midzone_only": "Enter at next daily open after midzone (38.2-61.8%) wick rejection",
        "nextbar_confirm": "Enter at open of bar after confirmation close above reference",
        "close_in_zone": "Enter at next daily open after close within zone",
        "displacement_off": "Enter at close of daily expansion bar (body > ATR threshold)",
        "1h_displacement_off": "Enter at open of 1H bar after 1H expansion bar closes in trade direction",
        "1h_structure_shift": "Enter at next 1H open after CHoCH (close above consolidation high)",
        "1h_rejection": "Enter at next 1H open after 1H wick rejection within zone",
    }
    entry_rule = entry_map.get(trigger, f"Trigger: {trigger}")

    # Stop rule
    stop_map = {
        "origin": f"Stop below anchor_bar low (bullish) or above anchor_bar high (bearish). ~1.0-2.0 ATR from zone.",
        "fib_786": f"Stop at 78.6% retracement of the leg. ~0.5 ATR from zone.",
    }
    stop_rule = stop_map.get(stop, f"Stop: {stop}")

    # Invalidation
    invalidation = [
        f"Price closes below stop level before entry fires (bullish)",
        "Setup expires after 10 bars without trigger (daily), or 20 1H bars (intraday)",
        "Vol regime flips at detection bar re-evaluation (re-check on new data)",
    ]
    if needs_intraday:
        invalidation.append("1H data unavailable at trigger window -- skip setup")

    # Skip rules
    skip = [
        "SPY 200-SMA filter: skip bearish setups when SPY > 200 SMA (bull regime only for reversals)",
        "Earnings window: skip setups with earnings within 3 days of expected entry",
    ]
    if vol_gate == "vol_quiet":
        skip.append("Vol at regime_bar >= avg_vol threshold -- skip (active day, not quiet)")
    if vol_gate == "vol_active":
        skip.append("Vol at regime_bar < avg_vol threshold -- skip (quiet day, not active)")

    # Friction
    if slippage > 0:
        friction_str = f"~{slippage * 2 * 100:.2f}bps round-trip modeled in backtest"
    else:
        friction_str = "0 modeled in backtest; assume 5bps round-trip for live sizing"

    # Upgrade / downgrade evidence
    upgrade = (
        f"Upgrade to next tier: accumulate {max(15 - stats.get('n_trades', 0), 5)} more trades "
        f"in OOS2 (2023+) with positive ExpR; run robustness grid if not done."
    )
    downgrade = (
        f"Downgrade trigger: 3 consecutive losses exceeding 1.5R each, "
        f"OR OOS2 ExpR turns negative after 10+ trades."
    )

    return SignalCard(
        config_name=config_name,
        ticker_universe=ticker_universe,
        thesis=THESES.get(config_name, f"Fibonacci spring setup on {config_name}"),
        regime_gate=regime_gate,
        armed_conditions=armed,
        confirmation_trigger=trigger,
        entry_rule=entry_rule,
        stop_rule=stop_rule,
        target_rule=f"{target}x extension of the manipulation leg",
        invalidation_rules=invalidation,
        skip_rules=skip,
        expected_frequency=EXPECTED_FREQUENCY.get(config_name, "Unknown"),
        expected_hold_time=EXPECTED_HOLD_TIME.get(config_name, "Unknown"),
        friction_assumptions=friction_str,
        failure_modes=FAILURE_MODES.get(config_name, ["Unknown failure modes"]),
        promotion_status=promotion_score.tier,
        upgrade_evidence=upgrade,
        downgrade_evidence=downgrade,
        promotion_score=promotion_score.total_score,
        promotion_score_breakdown=promotion_score.breakdown,
        track_record={
            "n_trades": stats.get("n_trades", 0),
            "exp_r": stats.get("expectancy_r", 0.0),
            "win_rate": stats.get("win_rate", 0.0),
            "sharpe_r": stats.get("sharpe_r", 0.0),
            "max_drawdown": stats.get("max_drawdown", 0.0),
        },
        needs_intraday=needs_intraday,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_card(card: SignalCard) -> None:
    """Print formatted ASCII signal card."""
    w = 80
    print(f"\n{'#' * w}")
    print(f"  SIGNAL CARD: {card.config_name}")
    print(f"  Promotion: {card.promotion_status}  |  Score: {card.promotion_score}/17")
    print(f"{'#' * w}")

    print(f"\n  THESIS:")
    # Word-wrap at ~70 chars
    words = card.thesis.split()
    line = "    "
    for w_word in words:
        if len(line) + len(w_word) + 1 > 74:
            print(line)
            line = "    " + w_word + " "
        else:
            line += w_word + " "
    if line.strip():
        print(line)

    tr = card.track_record
    print(f"\n  TRACK RECORD:")
    print(
        f"    n={tr.get('n_trades', 0)}  ExpR={tr.get('exp_r', 0):+.3f}  "
        f"Win%={tr.get('win_rate', 0):.1%}  Sharpe={tr.get('sharpe_r', 0):.3f}  "
        f"MaxDD={tr.get('max_drawdown', 0):.2%}"
    )

    print(f"\n  UNIVERSE:  {', '.join(card.ticker_universe)}")
    print(f"  FREQUENCY: {card.expected_frequency}")
    print(f"  HOLD TIME: {card.expected_hold_time}")
    print(
        f"  INTRADAY:  {'YES -- requires 1H data' if card.needs_intraday else 'No -- daily bars only'}"
    )
    print(f"  FRICTION:  {card.friction_assumptions}")

    print(f"\n  REGIME GATE:")
    print(f"    {card.regime_gate}")

    print(f"\n  ARMED (setup detection):")
    for cond in card.armed_conditions:
        print(f"    + {cond}")

    print(f"\n  CONFIRMED (entry trigger):")
    print(f"    {card.entry_rule}")

    print(f"\n  EXECUTION:")
    print(f"    Entry  : {card.entry_rule}")
    print(f"    Stop   : {card.stop_rule}")
    print(f"    Target : {card.target_rule}")

    print(f"\n  INVALIDATED:")
    for cond in card.invalidation_rules:
        print(f"    - {cond}")

    print(f"\n  SKIP RULES:")
    for rule in card.skip_rules:
        print(f"    - {rule}")

    print(f"\n  FAILURE MODES:")
    for fm in card.failure_modes:
        print(f"    ! {fm}")

    print(f"\n  UPGRADE PATH:    {card.upgrade_evidence}")
    print(f"  DOWNGRADE ALERT: {card.downgrade_evidence}")

    print(f"\n{'#' * w}\n")


def print_all_cards(cards: list[SignalCard]) -> None:
    """Print all cards with a header."""
    min_tier_order = min(
        (TIER_ORDER.index(c.promotion_status) for c in cards if c.promotion_status in TIER_ORDER),
        default=len(TIER_ORDER),
    )
    w = 80
    print(f"\n{'=' * w}")
    print(f"  FIB8 TRACK G -- SIGNAL CARDS")
    print(f"  {len(cards)} card(s) generated for PAPER-TRADE CANDIDATE and above")
    print(f"{'=' * w}")
    for card in cards:
        print_card(card)
