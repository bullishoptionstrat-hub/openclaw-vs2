"""
Quantum Edge - Standalone Backtest  (no Docker required)
=========================================================
Run:  python backtest_standalone.py

Edges combined:
  1. DUAL MOMENTUM (Antonacci)  — Absolute filter: SPY must beat T-bill proxy
                                  Cross-sectional: hold top-3 US sectors by
                                  risk-adjusted 6-month momentum.
  2. TREND FILTER               — SPY 100-day SMA gates all equity exposure.
  3. RISK-PARITY SIZING         — 1/vol weights normalised across top-3 sectors.
  4. GREENBLATT PROXY           — Blend in a value tilt: penalise high-PE
                                  sectors using Shiller-style P/E relative rank.
  5. LETF DECAY (uptrend only)  — Short SPXU (3x inverse S&P) only when
                                  trend is up; it decays fastest in bull markets.

Universe: 11 SPDR Sector ETFs + SHY (T-bills proxy)
Why sectors?  Sector momentum has the strongest academic evidence for US
equity cross-sectional alpha (Moskowitz & Grinblatt 1999, Mebane Faber 2007).
"""

import warnings, os
warnings.filterwarnings("ignore")
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ─── Parameters ───────────────────────────────────────────────────────────────
START         = "2010-01-01"
END           = "2023-12-31"
CASH          = 100_000
REBAL_DAYS    = 10           # bi-weekly rebalance
MOM_DAYS      = 126          # 6-month momentum window (optimal per research)
SKIP_DAYS     = 21           # skip last month (reversal avoidance)
VOL_LB        = 20           # realized vol for risk-parity
TREND_SMA     = 100          # faster trend filter vs 200-day
ABS_MOM_WIN   = 63           # absolute momentum window (3 months)
TOP_N         = 3            # hold top N sectors
VALUE_WEIGHT  = 0.15         # how much to tilt toward value (Greenblatt proxy)
LETF_W        = 0.05         # SPXU short leg (only in uptrend)

# 11 SPDR Sector ETFs (comprehensive US sector coverage)
SECTORS = [
    "XLK",   # Technology
    "XLV",   # Health Care
    "XLF",   # Financials
    "XLI",   # Industrials
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLE",   # Energy
    "XLB",   # Materials
    "XLU",   # Utilities
    "XLC",   # Communication Services
    "XLRE",  # Real Estate
]
DEFENSIVE = "SHY"             # T-bills proxy (near-cash, safe in rate hikes)
LETF_SHORT = "SPXU"          # 3x inverse S&P

ALL_TICKERS = list(set(SECTORS + [DEFENSIVE, LETF_SHORT, "SPY"]))

# ─── Download ─────────────────────────────────────────────────────────────────
print(f"Downloading {len(ALL_TICKERS)} tickers ({START} to {END})...")
raw   = yf.download(ALL_TICKERS, start=START, end=END,
                    auto_adjust=True, progress=False)
close = raw["Close"].ffill()

cov   = close.notna().mean()
keep  = {t for t in close.columns if cov[t] > 0.55}
SECTORS_OK = [t for t in SECTORS if t in keep]
print(f"  Sectors available: {SECTORS_OK}")

ret    = close.pct_change()
vol20  = ret.rolling(VOL_LB).std()
sma    = close["SPY"].rolling(TREND_SMA).mean()

# Momentum: 6-month return, skip last month (avoids short-term reversal)
mom = close.shift(SKIP_DAYS).pct_change(MOM_DAYS - SKIP_DAYS)

# Absolute momentum: 3-month SPY return vs 0 (proxy for risk-free rate)
abs_mom = close["SPY"].pct_change(ABS_MOM_WIN)

# ─── Greenblatt PROXY: relative PE rank across sectors ───────────────────────
# We don't have EV/EBITDA for ETFs, but we can approximate value using
# relative price performance vs 5-year average — sectors that have
# underperformed long-term trade at cheaper multiples (value proxy).
# Low 5-year rel. return = cheap (value) → boost score
# High 5-year rel. return = expensive (growth) → reduce score
two_yr_mom = close.pct_change(252 * 2)   # 2-year lookback for value proxy

def value_tilt(date, ticker) -> float:
    """Returns a score where 1.0 = cheapest sector, 0.0 = most expensive.
    Proxy: sectors that have underperformed over 2 years trade at cheaper multiples.
    Uses a 2-year window to be available early in the backtest."""
    scores = {}
    for t in SECTORS_OK:
        v = two_yr_mom.loc[date, t] if t in two_yr_mom.columns else np.nan
        if not pd.isna(v):
            scores[t] = v
    if len(scores) < 3:
        return 0.5
    sorted_vals = sorted(scores.keys(), key=lambda x: scores[x])  # ascending = cheap
    rank = sorted_vals.index(ticker) if ticker in sorted_vals else len(sorted_vals) // 2
    return 1.0 - rank / max(len(sorted_vals) - 1, 1)  # 1=cheapest, 0=most expensive

# ─── Build weight matrix ──────────────────────────────────────────────────────
print("Computing weights...")
all_t   = [t for t in keep if t in close.columns]
weights = pd.DataFrame(0.0, index=close.index, columns=all_t)
warmup  = max(252 * 2 + 10, TREND_SMA + 10, MOM_DAYS + SKIP_DAYS + 10)
rebal_c = 0
prev_w: dict[str, float] = {DEFENSIVE: 1.0}

for i, date in enumerate(close.index):
    if i < warmup:
        if DEFENSIVE in weights.columns:
            weights.loc[date, DEFENSIVE] = 1.0
        continue

    rebal_c += 1
    if rebal_c % REBAL_DAYS != 0:
        for t, w in prev_w.items():
            if t in weights.columns:
                weights.loc[date, t] = w
        continue

    # ── Regime checks ────────────────────────────────────────────────────
    spy_p = close.loc[date, "SPY"]   if "SPY" in close.columns else np.nan
    sma_v = sma.loc[date]            if date  in sma.index      else np.nan
    abs_m = abs_mom.loc[date]        if date  in abs_mom.index   else np.nan

    trend_up   = bool(spy_p > sma_v)   if not pd.isna(spy_p) and not pd.isna(sma_v) else True
    abs_pos    = bool(abs_m > 0)       if not pd.isna(abs_m) else True  # SPY up vs 3-months ago
    equity_ok  = trend_up and abs_pos  # BOTH must be true to go risk-on

    new_w: dict[str, float] = {}

    if equity_ok:
        # ── MOMENTUM + VALUE SLEEVE ──────────────────────────────────────
        raw_scores: dict[str, float] = {}
        for t in SECTORS_OK:
            m = mom.loc[date, t] if t in mom.columns else np.nan
            v = vol20.loc[date, t] if t in vol20.columns else np.nan
            if pd.isna(m) or pd.isna(v) or v == 0:
                continue
            mom_score   = m / v                         # risk-adj momentum
            val_score   = value_tilt(date, t)           # cheap = higher score
            # Blend: 80% momentum + 20% value (Greenblatt proxy)
            raw_scores[t] = (1 - VALUE_WEIGHT) * mom_score + VALUE_WEIGHT * val_score

        # Require positive raw score (absolute momentum filter per sector)
        pos_scores = {t: s for t, s in raw_scores.items() if s > 0}

        if not pos_scores:
            new_w[DEFENSIVE] = 1.0
        else:
            # Pick top N sectors
            top = sorted(pos_scores, key=pos_scores.get, reverse=True)[:TOP_N]

            # Risk-parity weights within top-N
            rw = {}
            for t in top:
                v = vol20.loc[date, t] if t in vol20.columns else np.nan
                rw[t] = (1.0 / v) if not pd.isna(v) and v > 0 else 0.0
            total_rw = sum(rw.values()) or 1.0
            for t in top:
                new_w[t] = round(rw[t] / total_rw, 4)

            # LETF decay: short SPXU during uptrend (it decays fastest in bull mkt)
            if LETF_SHORT in keep:
                new_w[LETF_SHORT] = -LETF_W

    else:
        # ── DEFENSIVE: hold SHY (T-bills proxy, stable in all environments) ──
        new_w[DEFENSIVE] = 1.0

    prev_w = dict(new_w)
    for t in all_t:
        weights.loc[date, t] = new_w.get(t, 0.0)

# ─── Simulate ─────────────────────────────────────────────────────────────────
print("Simulating...")
weights   = weights.ffill()
aln_ret   = ret[all_t].reindex(weights.index).fillna(0.0)
daily_pnl = (weights.shift(1) * aln_ret).sum(axis=1)
daily_pnl.iloc[0] = 0.0

equity = CASH * (1 + daily_pnl).cumprod()
spy_eq = CASH * (1 + ret["SPY"].reindex(equity.index).fillna(0.0)).cumprod()
qqq_eq = CASH * (1 + ret["XLK"].reindex(equity.index).fillna(0.0)).cumprod()  # Tech sector benchmark

# ─── Stats ────────────────────────────────────────────────────────────────────
def stats(eq: pd.Series, label: str) -> dict:
    r      = eq.pct_change().dropna()
    total  = (eq.iloc[-1] / eq.iloc[0]) - 1
    yrs    = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr   = (1 + total) ** (1 / yrs) - 1
    sharpe = (r.mean() / r.std()) * np.sqrt(252) if r.std() > 0 else 0
    dd     = (eq - eq.cummax()) / eq.cummax()
    calmar = cagr / abs(dd.min()) if dd.min() != 0 else 0
    vol_a  = r.std() * np.sqrt(252)
    # Sortino (downside deviation)
    neg_r  = r[r < 0]
    sortino = (r.mean() / neg_r.std()) * np.sqrt(252) if len(neg_r) > 0 else 0
    return {
        "Total Return": total,
        "CAGR":         cagr,
        "Ann. Vol":     vol_a,
        "Sharpe":       sharpe,
        "Sortino":      sortino,
        "Calmar":       calmar,
        "Max Drawdown": dd.min(),
        "Avg Drawdown": dd[dd < 0].mean() if (dd < 0).any() else 0,
        "Win Rate":     (r > 0).mean(),
        "Final Value":  eq.iloc[-1],
    }

s  = stats(equity, "Quantum Edge")
b  = stats(spy_eq, "SPY Buy & Hold")
q  = stats(qqq_eq, "XLK (Tech Sector)")

uptrend_days   = sum(1 for d in close.index[warmup:]
                     if not pd.isna(sma.get(d, np.nan)) and close.loc[d, "SPY"] > sma.loc[d])
defensive_days = len(close.index[warmup:]) - uptrend_days
total_d        = max(uptrend_days + defensive_days, 1)

print()
print("=" * 72)
print(f"  QUANTUM EDGE  |  {START[:4]}-{END[:4]}  Sector Rotation + Dual Momentum")
print("=" * 72)
print(f"{'Metric':<18} {'Quantum Edge':>16} {'SPY B&H':>16} {'XLK (Tech)':>16}")
print("-" * 72)
rows = [
    ("Total Return",  "Total Return",  True),
    ("CAGR",          "CAGR",          True),
    ("Ann. Vol",      "Ann. Vol",       True),
    ("Sharpe Ratio",  "Sharpe",        False),
    ("Sortino Ratio", "Sortino",       False),
    ("Calmar Ratio",  "Calmar",        False),
    ("Max Drawdown",  "Max Drawdown",  True),
    ("Avg Drawdown",  "Avg Drawdown",  True),
    ("Win Rate",      "Win Rate",      True),
    ("Final Value",   "Final Value",   False),
]
for label, key, pct in rows:
    sv, bv, qv = s[key], b[key], q[key]
    if key == "Final Value":
        sf, bf, qf = f"${sv:,.0f}", f"${bv:,.0f}", f"${qv:,.0f}"
    elif pct:
        sf, bf, qf = f"{sv:.2%}", f"{bv:.2%}", f"{qv:.2%}"
    else:
        sf, bf, qf = f"{sv:.2f}", f"{bv:.2f}", f"{qv:.2f}"
    print(f"{label:<18} {sf:>16} {bf:>16} {qf:>16}")
print("=" * 72)
print(f"\n  Regime: Equity {uptrend_days/total_d:.0%} | Defensive {defensive_days/total_d:.0%}")
print(f"  Turnover: ~{REBAL_DAYS} trading-day cycle  |  Top {TOP_N} sectors each period")

# ─── Plot ──────────────────────────────────────────────────────────────────────
BG = "#0d1117"
fig, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True,
                          gridspec_kw={"height_ratios": [3, 1, 1]})
fig.patch.set_facecolor(BG)
ax1, ax2, ax3 = axes

ns  = equity / CASH
nb  = spy_eq  / CASH
nq  = qqq_eq  / CASH
ax1.plot(ns.index, ns.values, "#00d4aa", lw=2.2, label="Quantum Edge", zorder=3)
ax1.plot(nb.index, nb.values, "#ff6b6b", lw=1.0, ls="--", alpha=0.85, label="SPY B&H")
ax1.plot(nq.index, nq.values, "#ffd700", lw=0.8, ls=":", alpha=0.7, label="XLK (Tech)")
ax1.set_ylabel("Growth of $1", color="white", fontsize=11)
ax1.set_title(f"Quantum Edge — Sector Rotation + Dual Momentum  "
              f"({START[:4]}-{END[:4]})",
              color="white", fontsize=13, fontweight="bold")
ax1.legend(fontsize=10, facecolor="#1a1a2e", labelcolor="white")
ax1.set_facecolor(BG)
ax1.tick_params(colors="white")
ax1.grid(True, alpha=0.2)
for sp in ax1.spines.values(): sp.set_edgecolor("#444")

dd = (equity - equity.cummax()) / equity.cummax() * 100
dd_spy = (spy_eq - spy_eq.cummax()) / spy_eq.cummax() * 100
ax2.fill_between(dd.index,     dd.values,     0, color="#ff4444", alpha=0.6, label="QE Drawdown")
ax2.fill_between(dd_spy.index, dd_spy.values, 0, color="#ff9999", alpha=0.3, label="SPY Drawdown")
ax2.set_ylabel("DD %", color="white", fontsize=9)
ax2.set_facecolor(BG); ax2.tick_params(colors="white"); ax2.grid(True, alpha=0.2)
ax2.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white")
for sp in ax2.spines.values(): sp.set_edgecolor("#444")

# Rolling 12-month Sharpe
roll_ret  = (weights.shift(1) * aln_ret).sum(axis=1)
roll_s = roll_ret.rolling(252).apply(
    lambda r: (r.mean() / r.std()) * np.sqrt(252) if r.std() > 0 else 0, raw=True
)
ax3.plot(roll_s.index, roll_s.values, "#00aaff", lw=1.2, label="Rolling 12M Sharpe")
ax3.axhline(0, color="#555", lw=0.8, ls="--")
ax3.axhline(1, color="#00d4aa", lw=0.6, ls=":", alpha=0.6, label="Sharpe=1")
ax3.set_ylabel("Sharpe", color="white", fontsize=9)
ax3.set_facecolor(BG); ax3.tick_params(colors="white"); ax3.grid(True, alpha=0.2)
ax3.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white")
for sp in ax3.spines.values(): sp.set_edgecolor("#444")

fig.text(0.5, 0.005,
    f"QE: CAGR={s['CAGR']:.2%} | Sharpe={s['Sharpe']:.2f} | Sortino={s['Sortino']:.2f} "
    f"| MaxDD={s['Max Drawdown']:.2%}  ||  "
    f"SPY: CAGR={b['CAGR']:.2%} | Sharpe={b['Sharpe']:.2f} | MaxDD={b['Max Drawdown']:.2%}",
    ha="center", color="#aaa", fontsize=8.5)

plt.tight_layout(rect=[0, 0.02, 1, 1])
out = "QuantumEdge/quantum_edge_equity.png"
plt.savefig(out, dpi=150, facecolor=BG, bbox_inches="tight")
print(f"\nEquity curve -> {out}")
print()
print("Full Lean backtest (Docker required):")
print("  .venv/Scripts/lean.exe backtest QuantumEdge")
