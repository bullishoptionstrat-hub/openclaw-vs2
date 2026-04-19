"""
fib7 experiment configs.

Track A: XLK deployment hardening
  - xlk_vol_quiet frozen baseline (same as fib6 winner)
  - Execution neighborhood: 4 trigger x stop x target combinations
  - Friction variants at 5bps / 10bps

Track B: QQQ regime paradox resolution
  - 3 bar types (discovery / completion / anchor) x 3 gates (neutral / quiet / active)
  - = 9 configs, all on QQQ
  - Plus ATR regime gate variants + vol+ATR hybrid

Track C: SPY combined vol gate x 1H trigger
  - 3 gate modes x 4 triggers = 12 configs on SPY
  - Best combo from fib6: spy_vol_quiet + 1h_displacement_off

Track D: Selective rotation engine
  - Uses best configs from Track A (XLK) as the signal universe
  - Rotation run via rotation.py: top1 / top2 / top3 / capped2

OOS_TICKERS: XLK, QQQ, SPY, IWM, XLY (same as fib6)
PORTFOLIO_UNIVERSE: XLK, QQQ, IWM, XLY, XLF (same as fib6)
"""

from __future__ import annotations

from research.fib7.model import Fib7Config

# ---------------------------------------------------------------------------
# Instrument sets
# ---------------------------------------------------------------------------

TRACK_A_TICKER = "XLK"
TRACK_B_TICKER = "QQQ"
TRACK_C_TICKER = "SPY"
ROTATION_UNIVERSE = ["XLK", "QQQ", "IWM", "XLY", "XLF"]
OOS_TICKERS = ["XLK", "QQQ", "SPY", "IWM", "XLY"]
PORTFOLIO_UNIVERSE = ["XLK", "QQQ", "IWM", "XLY", "XLF"]

SLIPPAGE_REALISTIC = 0.0005  # 5 bps
SLIPPAGE_CONSERVATIVE = 0.001  # 10 bps

# ---------------------------------------------------------------------------
# Base style factories
# ---------------------------------------------------------------------------


def _base_xlk_vq(slippage: float = 0.0) -> Fib7Config:
    """Frozen xlk_vol_quiet config from fib6."""
    cfg = Fib7Config()
    cfg.name = "xlk_vol_quiet"
    cfg.quality_min_score = 0.0
    cfg.quality_min_sweep = 15.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "touch_rejection"
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage
    cfg.vol_regime_gate = "vol_quiet"
    cfg.regime_bar = "discovery"
    return cfg


def _base_qqq(
    vol_gate: str = "neutral", regime_bar: str = "discovery", slippage: float = 0.0
) -> Fib7Config:
    """QQQ midzone style with configurable regime bar."""
    cfg = Fib7Config()
    cfg.name = f"qqq_{regime_bar}_{vol_gate}"
    cfg.quality_min_score = 60.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "midzone_only"
    cfg.midzone_tolerance_atr = 0.20
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage
    cfg.vol_regime_gate = vol_gate
    cfg.regime_bar = regime_bar
    return cfg


def _base_spy(vol_gate: str = "neutral", slippage: float = 0.0) -> Fib7Config:
    """SPY base config for Track C combined tests."""
    cfg = Fib7Config()
    cfg.name = f"spy_{vol_gate}"
    cfg.quality_min_score = 60.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "nextbar_confirm"
    cfg.nextbar_confirm_atr = 0.30
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage
    cfg.vol_regime_gate = vol_gate
    cfg.regime_bar = "discovery"
    return cfg


# ---------------------------------------------------------------------------
# Track A: XLK deployment hardening
# ---------------------------------------------------------------------------


def get_tracka_configs() -> dict[str, Fib7Config]:
    """
    Tight execution neighborhood around xlk_vol_quiet winner.
    Tests: trigger x stop x target combinations.
    """

    def _xlk_var(trigger: str, stop: str, target: float, name: str) -> Fib7Config:
        cfg = _base_xlk_vq()
        cfg.name = name
        cfg.entry_trigger = trigger
        cfg.stop_variant = stop
        cfg.target_fib = target
        return cfg

    configs = {
        # Frozen baseline (fib6 winner)
        "xlk_vq_baseline": _xlk_var("touch_rejection", "origin", 1.618, "xlk_vq_baseline"),
        # Execution neighborhood
        "xlk_vq_tr_786_1618": _xlk_var("touch_rejection", "fib_786", 1.618, "xlk_vq_tr_786_1618"),
        "xlk_vq_tr_orig_1272": _xlk_var("touch_rejection", "origin", 1.272, "xlk_vq_tr_orig_1272"),
        "xlk_vq_tr_786_1272": _xlk_var("touch_rejection", "fib_786", 1.272, "xlk_vq_tr_786_1272"),
        "xlk_vq_ciz_orig_1618": _xlk_var("close_in_zone", "origin", 1.618, "xlk_vq_ciz_orig_1618"),
        "xlk_vq_ciz_786_1618": _xlk_var("close_in_zone", "fib_786", 1.618, "xlk_vq_ciz_786_1618"),
        "xlk_vq_nbc_orig_1618": _xlk_var(
            "nextbar_confirm", "origin", 1.618, "xlk_vq_nbc_orig_1618"
        ),
        "xlk_vq_disp_orig_1618": _xlk_var(
            "displacement_off", "origin", 1.618, "xlk_vq_disp_orig_1618"
        ),
        # Friction variants (baseline with slippage)
        "xlk_vq_5bps": _base_xlk_vq(SLIPPAGE_REALISTIC),
        "xlk_vq_10bps": _base_xlk_vq(SLIPPAGE_CONSERVATIVE),
    }
    configs["xlk_vq_5bps"].name = "xlk_vq_5bps"
    configs["xlk_vq_10bps"].name = "xlk_vq_10bps"
    return configs


# ---------------------------------------------------------------------------
# Track B: QQQ regime paradox resolution
# ---------------------------------------------------------------------------


def get_trackb_configs() -> dict[str, Fib7Config]:
    """
    9 core configs: 3 bar types x 3 gate modes for QQQ.
    + ATR regime variants + hybrid gate
    """
    configs = {}

    # Core: 3 bar types x 3 gate modes
    for regime_bar in ["discovery", "completion", "anchor"]:
        for gate in ["neutral", "vol_quiet", "vol_active"]:
            name = f"qqq_{regime_bar}_{gate}"
            cfg = _base_qqq(gate, regime_bar)
            cfg.name = name
            configs[name] = cfg

    # ATR regime gate (at discovery bar)
    cfg_atr_active = _base_qqq("neutral", "discovery")
    cfg_atr_active.name = "qqq_atr_active"
    cfg_atr_active.atr_regime_gate = "atr_active"
    cfg_atr_active.atr_ratio_threshold = 1.0
    configs["qqq_atr_active"] = cfg_atr_active

    cfg_atr_quiet = _base_qqq("neutral", "discovery")
    cfg_atr_quiet.name = "qqq_atr_quiet"
    cfg_atr_quiet.atr_regime_gate = "atr_quiet"
    cfg_atr_quiet.atr_ratio_threshold = 1.0
    configs["qqq_atr_quiet"] = cfg_atr_quiet

    # Hybrid: vol_quiet (completion) + atr_active
    cfg_hybrid = _base_qqq("vol_quiet", "completion")
    cfg_hybrid.name = "qqq_hybrid_comp_quiet_atr_active"
    cfg_hybrid.atr_regime_gate = "atr_active"
    cfg_hybrid.require_vol_atr_hybrid = True
    configs["qqq_hybrid_comp_quiet_atr_active"] = cfg_hybrid

    # Hybrid: vol_active (completion) + atr_active
    cfg_hybrid2 = _base_qqq("vol_active", "completion")
    cfg_hybrid2.name = "qqq_hybrid_comp_active_atr_active"
    cfg_hybrid2.atr_regime_gate = "atr_active"
    cfg_hybrid2.require_vol_atr_hybrid = True
    configs["qqq_hybrid_comp_active_atr_active"] = cfg_hybrid2

    return configs


# ---------------------------------------------------------------------------
# Track C: SPY vol gate x 1H trigger combinations
# ---------------------------------------------------------------------------


def get_trackc_configs(spy_has_hourly: bool = True) -> dict[str, Fib7Config]:
    """
    3 gate modes x 4 entry triggers = 12 SPY configs.
    Triggers: touch_rejection (daily), 1h_displacement_off, 1h_structure_shift, 1h_rejection
    """
    configs = {}

    triggers = [
        ("touch_rejection", "tr"),
        ("1h_displacement_off", "1h_disp"),
        ("1h_structure_shift", "1h_struct"),
        ("1h_rejection", "1h_rej"),
    ]

    gates = ["neutral", "vol_quiet", "vol_active"]

    for gate in gates:
        for trigger, tshort in triggers:
            name = f"spy_{gate}_{tshort}"
            cfg = _base_spy(gate)
            cfg.name = name
            cfg.entry_trigger = trigger
            configs[name] = cfg

    return configs


# ---------------------------------------------------------------------------
# OOS configs: Track A best with date splits
# ---------------------------------------------------------------------------


def get_oos_configs() -> dict[str, Fib7Config]:
    """OOS-split versions of best xlk/qqq configs."""
    configs = {}

    for name, cfg in [
        ("xlk_vq_baseline", _base_xlk_vq()),
        ("xlk_vq_5bps", _base_xlk_vq(SLIPPAGE_REALISTIC)),
    ]:
        cfg.name = name
        cfg.is_start = "20070101"
        cfg.is_end = "20161231"
        cfg.oos1_start = "20170101"
        cfg.oos1_end = "20221231"
        cfg.oos2_start = "20230101"
        cfg.oos2_end = None
        configs[name] = cfg

    # QQQ with best regime_bar (to be determined by Track B; use completion as fib5 hypothesis)
    for regime_bar in ["discovery", "completion"]:
        for gate in ["vol_active", "vol_quiet"]:
            name = f"qqq_{regime_bar}_{gate}_oos"
            cfg = _base_qqq(gate, regime_bar)
            cfg.name = name
            cfg.is_start = "20070101"
            cfg.is_end = "20161231"
            cfg.oos1_start = "20170101"
            cfg.oos1_end = "20221231"
            cfg.oos2_start = "20230101"
            cfg.oos2_end = None
            configs[name] = cfg

    return configs


# ---------------------------------------------------------------------------
# Track A: robustness grid (tighter neighborhood than fib6)
# ---------------------------------------------------------------------------


def build_xlk_tight_grid() -> list[Fib7Config]:
    """
    Tight grid around xlk_vol_quiet winner.
    sweep_min x disp_atr x stop x target = 3x2x2x2 = 24 configs.
    """
    configs = []
    for sweep_min in [10.0, 15.0, 20.0]:
        for disp_atr in [1.5, 2.0]:
            for stop in ["origin", "fib_786"]:
                for target in [1.272, 1.618]:
                    cfg = Fib7Config()
                    cfg.quality_min_score = 0.0
                    cfg.quality_min_sweep = sweep_min
                    cfg.require_sweep = True
                    cfg.min_displacement_atr = disp_atr
                    cfg.entry_trigger = "touch_rejection"
                    cfg.stop_variant = stop
                    cfg.target_fib = target
                    cfg.vol_regime_gate = "vol_quiet"
                    cfg.regime_bar = "discovery"
                    cfg.name = (
                        f"xlk_vq_tight_sw{sweep_min:.0f}_d{disp_atr:.1f}"
                        f"_st{stop[:3]}_tgt{target:.3f}"
                    )
                    configs.append(cfg)
    return configs
