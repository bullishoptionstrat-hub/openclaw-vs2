"""
fib4 - Execution-focused Fibonacci research module.

THESIS
------
fib3 proved that high-quality manipulation legs (Tier A/B) DO produce
measurable fib level respect.  But daily-close entries fail to capture
that structural respect as profit.

fib4 tests whether event-driven execution (rejection wicks, next-bar
confirmation, 1H triggers) converts the observed level respect into
actual trading edge.

The core question:
  Does execution precision determine whether the fib strategy is viable?

ARCHITECTURE
------------
fib4 reuses:
  - fib3.detector  — leg detection + quality scoring (QualifiedLeg)
  - fib2._run_trade — trade management (stop/target/partial)

fib4 adds:
  - execution.py   — EntryDecision state machine, all trigger variants
  - backtester.py  — new loop: detect -> decide_entry -> run_trade
  - experiments.py — instrument-specific experiment families
  - analysis.py    — comparison tables, trigger breakdown, skip analysis

EXECUTION VARIANTS
------------------
  touch_rejection    : wick into zone, close above midzone (same-bar)
  nextbar_confirm    : zone touched bar B, bar B+1 close N*ATR directional
  close_in_zone      : close inside zone (fib3/fib2 baseline)
  1h_rejection       : 1H wick into zone + 1H close above midzone
  1h_structure_shift : 1H local pivot in zone
  1h_displacement_off: 1H close beyond zone boundary after wick
  midzone_only       : tight band around 0.5 fib, rejection trigger
  zone_0382_only     : tight band around fib_382 level
  zone_0618_only     : tight band around fib_618 level

INSTRUMENT FAMILIES
-------------------
  SPY  : uses 1H data when available
  XLK  : daily only (sweep-quality focus, high-displacement filter)
  QQQ  : daily only (1H falls back to daily)

FILES CHANGED (fib4 is isolated, no prior modules modified)
  research/fib4/__init__.py
  research/fib4/model.py
  research/fib4/execution.py
  research/fib4/backtester.py
  research/fib4/experiments.py
  research/fib4/analysis.py
  research/fib4/run.py
"""
