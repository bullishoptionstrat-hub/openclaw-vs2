"""
fib6 -- Regime-Gated, Portfolio-Aware, Execution-Hardened Signal Engine

GROUND TRUTH (from fib5)
------------------------
- xlk_style (sweep_deep + touch_rejection): STANDALONE -- all 4 criteria met
- qqq_style (midzone_only, Q>=60): CONFLUENCE -- 3/4 criteria met
- Critical regime finding: opposite vol dependencies
  * xlk_style/XLK prefers vol_expansion=False (+0.746R quiet vs -0.284R active)
  * qqq_style/QQQ prefers vol_expansion=True  (+0.484R active vs -0.123R quiet)

FIB6 OBJECTIVE
--------------
Convert the regime insight into a deployable vol-gated system.
Answer: does gating on vol regime materially improve edge, OOS stability, drawdown?

TRACKS
------
Track A: Vol Regime Gate
  - xlk_vol_quiet / xlk_vol_active / xlk_neutral
  - qqq_vol_active / qqq_vol_quiet / qqq_neutral
  - spy variants
  Gate: volume at discovery_bar vs trailing 20-bar average
        vol_quiet  = ratio < threshold (default 1.0)
        vol_active = ratio >= threshold

Track B: 1H Execution Layer
  - Only SPY has hourly data (AAPL, IBM, VXX also have 1H but are not in scope)
  - XLK/QQQ: no hourly data; 1H triggers fall back to daily
  - New trigger: 1h_reclaim_after_sweep
    For bullish: price sweeps below zone_low on 1H, then 1H close reclaims zone_low
    This isolates the failed-sweep / liquidity-sweep entry pattern

Track C: Portfolio Construction
  - Universe: XLK, QQQ, IWM, XLY, XLF (all had positive xlk_style in fib5)
  - Methods: equal weight, vol-scaled, capped (40% max per instrument)
  - Baseline: single best instrument

Track D: Robustness / OOS / Friction
  - IS/OOS split for best regime-gated configs
  - 5bps and 10bps friction
  - Parameter neighborhood for best gate config

Track E: Deployment Classification
  - REJECT
  - MAP ONLY
  - CONFLUENCE ONLY
  - STANDALONE CANDIDATE
  - DEPLOYMENT CANDIDATE

AVAILABLE INSTRUMENTS
---------------------
Daily: XLK, QQQ, SPY, IWM, XLV, XLY, XLF, XLE, XLI, XLB, XLP, XLU, XLRE, XLC
       + AAPL, GOOG, IBM, BAC, EEM, IWM and others
Hourly: SPY only (among equity ETF universe)
"""
