"""
fib9: Forward-Validation and Operational Signal-Engine Bridge

fib9 is NOT a research phase. It is a deployment-prep lab.

Ground truth locked from fib8:
  xlk_vq_baseline          LIVE-READY    15/17 pts   n=50  +0.194R  100% grid  OOS1+0.247R
  xlk_vq_tr_786_1618       LIVE-READY    13/17 pts   n=38  +0.404R  75% grid   lower replication
  qqq_completion_vol_active SIGNAL-CARD  11/17 pts   n=29  +0.759R  OOS1+0.884R
  qqq_atr_quiet             CONFLUENCE    8/17 pts   n=19  +0.532R  no OOS split
  spy_vol_active_1h_disp    CONFLUENCE    7/17 pts   n=43  +0.382R  no OOS split, intraday dep

New tier: PAPER-LIVE APPROVED -- above LIVE-READY, requires forward evidence.

fib9 phases:
  1  Canonical freeze   -- one canonical winner per instrument, backed by real OOS splits
  2  Forward replay     -- bar-by-bar replay of OOS2 (2023+) period, paper-trade state machine
  3  Promotion update   -- apply forward gate, update promotion tiers, identify PAPER-LIVE candidates
  4  Rotation V3        -- canonical-only selective rotation, hard eligibility gate
  5  Signal package     -- JSON spec + human card export for canonical configs

Decisions expected:
  XLK canonical:  xlk_vq_baseline (expected winner on simplicity + replication)
  QQQ canonical:  qqq_completion_vol_active (expected -- OOS1 confirmed)
  SPY canonical:  spy_vol_active_1h_disp (MONITORED ONLY -- OOS2 too thin for promotion)
  Rotation V3:    top1_canonical approaches single_best_static; top2 shows small cost
  PAPER-LIVE:     xlk_vq_baseline only if OOS2 >= 5 trades and positive (currently 2 trades)

Bottleneck: OOS2 sample thinness. fib9 logs this as a first-class metric.
"""

# Tier hierarchy (updated -- PAPER_LIVE is new)
PAPER_LIVE = "PAPER-LIVE APPROVED"
LIVE_READY = "LIVE-READY CANDIDATE"
SIGNAL_CARD = "SIGNAL-CARD CANDIDATE"
PAPER_TRADE = "PAPER-TRADE CANDIDATE"
CONFLUENCE_ONLY = "CONFLUENCE ONLY"
MAP_ONLY = "MAP ONLY"
RESEARCH_ONLY = "RESEARCH ONLY"

TIER_ORDER = [
    PAPER_LIVE,
    LIVE_READY,
    SIGNAL_CARD,
    PAPER_TRADE,
    CONFLUENCE_ONLY,
    MAP_ONLY,
    RESEARCH_ONLY,
]

TIER_SYMBOLS = {
    PAPER_LIVE: "**** PAPER-LIVE ****",
    LIVE_READY: "*** LIVE-READY ***",
    SIGNAL_CARD: "** SIGNAL-CARD **",
    PAPER_TRADE: "* PAPER-TRADE *",
    CONFLUENCE_ONLY: "CONFLUENCE",
    MAP_ONLY: "MAP",
    RESEARCH_ONLY: "RESEARCH",
}
