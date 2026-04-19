"""
fib7 -- Deployment-oriented signal research.

Ground truth from fib6:
  xlk_vol_quiet  -> DEPLOYMENT CANDIDATE (4/4 criteria, 92% robust grid, OOS strengthens)
  qqq_vol_active -> STANDALONE CANDIDATE (QQQ regime paradox unresolved)
  1h_displacement_off on SPY -> best 1H trigger (+0.165R, +0.112 vs daily baseline)
  Portfolio (equal/vol-scaled/capped) -> CONFLUENCE ONLY (dilution to +0.037R)

fib7 Research Tracks:
  Track A: XLK deployment hardening
           Freeze xlk_vol_quiet spec, tight execution neighborhood,
           friction rerun, OOS rerun, produce live signal spec card.

  Track B: QQQ regime paradox resolution
           fib5 used vol at completion_bar -> vol_active wins for QQQ.
           fib6 used vol at discovery_bar  -> vol_quiet wins for QQQ.
           Test all three bar types (discovery/completion/anchor) head-to-head
           with neutral baseline to definitively resolve which vol timing works.
           Also test ATR regime and vol+ATR hybrid gate.

  Track C: SPY vol_quiet + 1H execution combined test
           Best from fib6: spy_vol_quiet gate + 1h_displacement_off trigger.
           Cross all gate modes x all 1H triggers to find the best combination.

  Track D: Selective top-N rotation engine
           Replace diluted equal/vol-scaled portfolio with quality-scored
           rotation: rank instruments by trailing ExpR + vol regime alignment,
           hold top-1 / top-2 / top-3 at any time. Compare vs single-best.

  Track E: Live signal readiness specification
           For each DEPLOYMENT+ config, produce armed/confirmed/invalidated
           rules, data requirements, and latency constraints.

New classification tier added:
  LIVE-READY CANDIDATE (above DEPLOYMENT CANDIDATE)
  Criteria: all 4 standard + live_spec_complete + OOS2 positive

Available instruments (daily data confirmed in fib5/fib6):
  XLK, QQQ, SPY, IWM, XLY, XLV, XLF, XLE
  (XLI, XLB, XLP, XLU, XLRE, XLC — not tested in prior runs)
  Hourly data: SPY only.
"""
