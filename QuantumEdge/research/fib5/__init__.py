"""
fib5 — Robustness, Replication, and Portfolio Role Validation.

PURPOSE
-------
fib4 produced promising results on specific instrument+trigger combinations:
  - XLK: sweep_deep + touch_rejection  -> +0.187R, 51.4% WR, PF 1.41
  - QQQ: midzone_only (Q>=60)          -> +0.268R, 57.8% WR, PF 1.77
  - SPY: nextbar_confirm (n=16)        -> +0.336R, 75.0% WR (thin sample)

fib5 answers six questions before any deployment decision:
  1. REPLICATION  — does the edge transfer to related instruments?
  2. OOS          — does it survive out-of-sample (IS 2007-2016, OOS 2017-2022)?
  3. ROBUSTNESS   — is it plateau-shaped or one fragile parameter?
  4. FRICTION     — does it survive slippage and commissions?
  5. REGIME       — is it universal or only valid in certain environments?
  6. PORTFOLIO    — standalone, overlay, confluence, or map-only?

AVAILABLE INSTRUMENTS (Lean dataset)
  Tech/Growth  : XLK, QQQ, XLY
  Defensives   : XLV, XLU, XLP, XLRE
  Cyclicals    : XLF, XLE, XLI, XLB, XLC
  Broad market : SPY, IWM
  Note: SOXX, SMH, XBI not in dataset

ARCHITECTURE
  fib5 reuses fib3.detector + fib4.backtester + fib4.execution
  fib5 adds:
    model.py        — Fib5Config with friction params
    backtester.py   — thin wrapper with slippage post-processing
    walkforward.py  — IS/OOS split + rolling walk-forward
    robustness.py   — parameter grid search
    regime.py       — regime decomposition of results
    experiments.py  — replication strategy configs
    analysis.py     — all output tables + verdict
    run.py          — CLI

FILES CHANGED (fib5 is isolated, no prior modules modified)
  research/fib5/__init__.py
  research/fib5/model.py
  research/fib5/backtester.py
  research/fib5/walkforward.py
  research/fib5/robustness.py
  research/fib5/regime.py
  research/fib5/experiments.py
  research/fib5/analysis.py
  research/fib5/run.py
"""
