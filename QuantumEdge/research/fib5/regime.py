"""
fib5 regime decomposition.

decompose_results() — break results by spy_bull, in_discount, volume_expansion
                      using flags already recorded on StrictTradeResult
"""

from __future__ import annotations


def decompose_results(results: list) -> dict[str, dict]:
    """
    Break results into regime buckets and compute stats per bucket.

    Uses fields already recorded on StrictTradeResult by fib2._run_trade:
      spy_bull_regime  — SPY above 200d SMA at discovery bar
      in_discount      — entry price in discount (bull) / premium (bear)
      volume_expansion — volume above 20-bar avg on leg completion

    Returns dict: regime_key -> {n, win_rate, exp_r, avg_mae_r, avg_mfe_r}
    """
    if not results:
        return {}

    buckets: dict[str, list] = {
        "spy_bull=True": [],
        "spy_bull=False": [],
        "in_discount=True": [],
        "in_discount=False": [],
        "vol_expansion=True": [],
        "vol_expansion=False": [],
        "bull_in_disc": [],  # Best case: bullish regime + in discount
        "bear_premium": [],  # Bearish regime + in premium
    }

    for t in results:
        sb = t.spy_bull_regime
        idc = t.in_discount
        ve = t.volume_expansion
        direction = getattr(t.leg, "direction", None)

        buckets["spy_bull=True" if sb else "spy_bull=False"].append(t)
        buckets["in_discount=True" if idc else "in_discount=False"].append(t)
        buckets["vol_expansion=True" if ve else "vol_expansion=False"].append(t)

        if direction == "bullish" and sb and idc:
            buckets["bull_in_disc"].append(t)
        elif direction == "bearish" and not sb and not idc:
            buckets["bear_premium"].append(t)

    out = {}
    for key, trades in buckets.items():
        if not trades:
            continue
        n = len(trades)
        r_vals = [t.r_multiple for t in trades]
        wins = sum(1 for r in r_vals if r > 0)
        out[key] = {
            "n": n,
            "win_rate": round(wins / n, 4),
            "exp_r": round(sum(r_vals) / n, 4),
            "avg_mae_r": round(sum(t.mae_r for t in trades) / n, 4),
            "avg_mfe_r": round(sum(t.mfe_r for t in trades) / n, 4),
        }
    return out
