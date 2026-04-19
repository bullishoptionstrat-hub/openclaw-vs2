"""
fib3 analysis helpers — correlation, attribution, formatted output.
"""

from __future__ import annotations

import math
from research.fib3.model import FIB_LEVEL_KEYS, FIB_LEVEL_LABELS


# ---------------------------------------------------------------------------
# Correlation helpers
# ---------------------------------------------------------------------------


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / denom if denom > 0 else float("nan")


def attribution_table(results, legs_by_discovery: dict) -> dict:
    """
    Correlate quality components with R multiple.

    results      — list[StrictTradeResult]
    legs_by_discovery — {discovery_bar: QualifiedLeg}

    Returns dict with correlation coefficients per component.
    """
    scores = {"total": [], "sweep": [], "disp": [], "choch": [], "ctx": []}
    r_vals = []

    for t in results:
        db = t.leg.discovery_bar
        leg = legs_by_discovery.get(db)
        if leg is None:
            continue
        q = leg.quality
        scores["total"].append(q.total)
        scores["sweep"].append(q.sweep_score)
        scores["disp"].append(q.displacement_score)
        scores["choch"].append(q.choch_score)
        scores["ctx"].append(q.context_score)
        r_vals.append(t.r_multiple)

    return {comp: round(pearson(vals, r_vals), 4) for comp, vals in scores.items()}


# ---------------------------------------------------------------------------
# Printed tables
# ---------------------------------------------------------------------------


def print_respect_table(
    aggregate: dict[str, dict[str, dict]],
    ticker: str,
) -> None:
    """Print fib level visit/reaction rates by quality tier."""
    tiers = ["A", "B", "C", "D", "ALL"]
    available = [t for t in tiers if aggregate.get(t)]
    if not available:
        return

    w = 76
    print(f"\n{'=' * w}")
    print(f"  FIB LEVEL RESPECT  |  {ticker}")
    print(f"{'=' * w}")

    # Header
    hdr = f"  {'Level':<12}"
    for t in available:
        n = next(iter(aggregate[t].values()), {}).get("n", 0)
        hdr += f"  {f'Tier-{t}(n={n})':>16}"
    print(hdr)
    print(f"  {'':12}" + "".join(f"  {'Visit / React':>16}" for _ in available))
    print("-" * w)

    for key in FIB_LEVEL_KEYS:
        label = FIB_LEVEL_LABELS[key]
        row = f"  {label:<12}"
        for t in available:
            stats = aggregate.get(t, {}).get(key)
            if stats:
                row += f"  {stats['visit_rate']:>6.1%} / {stats['react_rate']:>6.1%}"
            else:
                row += f"  {'--':>6}   {'--':>6}"
        print(row)

    print(f"{'=' * w}\n")


def print_attribution(attr: dict, ticker: str, exp_name: str) -> None:
    """Print quality component vs R-multiple correlation."""
    print(f"  Quality->R correlation  [{exp_name} / {ticker}]")
    print(f"    Total score : {attr.get('total', float('nan')):+.4f}")
    print(f"    Sweep       : {attr.get('sweep', float('nan')):+.4f}")
    print(f"    Displacement: {attr.get('disp', float('nan')):+.4f}")
    print(f"    CHoCH       : {attr.get('choch', float('nan')):+.4f}")
    print(f"    Context     : {attr.get('ctx', float('nan')):+.4f}")


def print_tier_comparison(rows: list[dict]) -> None:
    """Comparison table across tier experiments."""
    if not rows:
        return
    w = 118
    print(f"\n{'=' * w}")
    print("  FIB3 QUALITY-TIER COMPARISON")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Experiment':<22}  {'Ticker':<5}  {'Legs':>5}  {'Trades':>6}  "
        f"{'WinR':>5}  {'ExpR':>7}  {'PF':>5}  {'Shr':>6}  "
        f"{'Hit1272':>7}  {'Hit1618':>7}  {'Tout':>5}  {'MaxDD':>7}"
    )
    print(hdr)
    print("-" * w)
    for r in rows:
        s = r["stats"]
        if s["n_trades"] == 0:
            print(
                f"  {r['exp']:<22}  {r['ticker']:<5}  {s['n_legs']:>5}  "
                f"{'0':>6}  {'--':>5}  {'--':>7}  {'--':>5}  {'--':>6}  "
                f"{'--':>7}  {'--':>7}  {'--':>5}  {'--':>7}"
            )
            continue
        print(
            f"  {r['exp']:<22}  {r['ticker']:<5}  {s['n_legs']:>5}  "
            f"{s['n_trades']:>6}  {s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>6.3f}  "
            f"{s['hit_rate_1272']:>7.1%}  {s['hit_rate_1618']:>7.1%}  "
            f"{s['timeout_rate']:>5.1%}  {s['max_drawdown']:>7.2%}"
        )
    print(f"{'=' * w}\n")
