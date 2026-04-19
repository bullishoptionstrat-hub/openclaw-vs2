"""
fib8: Institutional Promotion Framework

fib8 is NOT a new backtest campaign. It is a decision layer on top of fib1-fib7.

Ground truth locked from fib7:
  xlk_vq_baseline          DEPLOYMENT CANDIDATE  +0.194R  Sharpe 0.319  n=50  100% grid
  xlk_vq_tr_786_1618       STANDALONE CANDIDATE  +0.404R  Sharpe 0.551  n=38  on XLK
  qqq_completion_vol_active STANDALONE CANDIDATE  IS +0.759  OOS1 +0.884  n=29
  qqq_atr_quiet             STANDALONE CANDIDATE  +0.532R  Sharpe 0.514  n=19
  spy_vol_active_1h_disp    STANDALONE CANDIDATE  +0.382R  Sharpe 0.374  n=43
  spy_vol_active_1h_struct  CONFLUENCE ONLY       +0.291R  lower density
  Rotation (unthresholded)  FAILS                 XLF dilution -> +0.104R
  OOS2 (2023+)              TOO THIN              xlk_vq 2 trades, cannot upgrade

fib8 tracks:
  A  Promotion scoring  -- all 6 candidates scored on 10-criterion framework
  B  Forward monitor   -- paper-trade harness; scan last 60 bars for live setups
  C  XLK canonical     -- xlk_vq_baseline vs xlk_vq_tr_786_1618 final verdict
  D  QQQ canonical     -- qqq_completion_vol_active vs qqq_atr_quiet
  E  SPY canonical     -- spy_vol_active_1h_disp promotion test
  F  Rotation v2       -- thresholded rotation with eligibility gates
  G  Signal cards      -- generate structured cards for PAPER-TRADE CANDIDATE+

Three questions answered:
  1. Which configs deserve paper-trading promotion now?
     -> xlk_vq_baseline (daily-only, clean, OOS-validated)
     -> qqq_completion_vol_active (strong OOS1, needs OOS2 accumulation)
     -> spy_vol_active_1h_disp (good stats, needs robustness grid before SIGNAL-CARD)

  2. Can a forward harness replace further backtest optimization?
     -> Yes. fib8 forward monitor replaces another round of IS curve-fitting.

  3. Does thresholded rotation beat single-best static?
     -> With eligibility gate (min_exp_r=0.15): pool = {XLK, IWM, XLY, QQQ}
     -> Expected: top2_eligible approaches single-best; diversification cost is small
"""
