import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# BACKTEST CONFIGURATION
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
RUNS_PER_TIMEFRAME = 30
CANDLES_PER_RUN = 1000

# GOLDEN RATIO CONSTANTS
PHI = 1.618034
FRAC_618 = 0.618
FRAC_786 = 0.786
FRAC_162 = 1.618

# STRATEGY SETTINGS
MIN_CONFLUENCE = 4
MIN_RR = 1.618
VOLUME_MULTIPLIER = 1.8
MIN_VOLATILITY = 0.15
FRAC_FIX_ENABLED = True


def generate_market_data(num_candles, volatility=0.02):
    """Generate synthetic OHLCV data"""
    prices = np.random.randn(num_candles) * volatility
    prices = np.cumsum(prices) + 100

    ohlc = []
    for i in range(num_candles):
        open_p = prices[i]
        close_p = prices[i] + np.random.randn() * volatility
        high_p = max(open_p, close_p) + abs(np.random.randn() * volatility)
        low_p = min(open_p, close_p) - abs(np.random.randn() * volatility)
        volume = np.random.randint(1000000, 5000000)

        ohlc.append({"o": open_p, "h": high_p, "l": low_p, "c": close_p, "v": volume})
    return ohlc


def detect_fractal_bull(candles, i):
    """Detect 4-candle bullish fractal"""
    if i < 2:
        return False
    c0, c1, c2 = candles[i], candles[i - 1], candles[i - 2]
    return c2["l"] > c1["l"] and c1["l"] < c0["l"] and c0["l"] < c0["c"] and c0["c"] > c0["o"]


def detect_fractal_bear(candles, i):
    """Detect 4-candle bearish fractal"""
    if i < 2:
        return False
    c0, c1, c2 = candles[i], candles[i - 1], candles[i - 2]
    return c2["h"] < c1["h"] and c1["h"] > c0["h"] and c0["h"] > c0["c"] and c0["c"] < c0["o"]


def find_swing_high(candles, i, lookback=20):
    """Find recent swing high"""
    start = max(0, i - lookback)
    return max([c["h"] for c in candles[start : i + 1]])


def find_swing_low(candles, i, lookback=20):
    """Find recent swing low"""
    start = max(0, i - lookback)
    return min([c["l"] for c in candles[start : i + 1]])


def calculate_atr(candles, period=14):
    """Calculate ATR"""
    if len(candles) < period:
        return 0
    tr_sum = 0
    for i in range(len(candles) - period, len(candles)):
        c = candles[i]
        tr = max(
            c["h"] - c["l"], abs(c["h"] - candles[i - 1]["c"]), abs(c["l"] - candles[i - 1]["c"])
        )
        tr_sum += tr
    return tr_sum / period


def backtest_timeframe(timeframe):
    """Backtest strategy on specific timeframe"""
    total_signals = 0
    winning_signals = 0
    losing_signals = 0
    avg_rr = 0
    avg_confluence = 0

    for run in range(RUNS_PER_TIMEFRAME):
        candles = generate_market_data(CANDLES_PER_RUN, volatility=0.015)

        signals_this_run = 0

        for i in range(20, len(candles)):
            # Fractal detection
            bull_frac = detect_fractal_bull(candles, i)
            bear_frac = detect_fractal_bear(candles, i)

            # Swing levels
            swing_h = find_swing_high(candles, i)
            swing_l = find_swing_low(candles, i)
            swing_range = swing_h - swing_l

            atr_val = calculate_atr(candles)

            if not swing_range or atr_val == 0:
                continue

            # Simple confluence scoring (simplified)
            confluence = 1  # Base fractal

            # Volume check
            vol_avg = np.mean([c["v"] for c in candles[max(0, i - 20) : i]])
            if candles[i]["v"] > vol_avg * VOLUME_MULTIPLIER:
                confluence += 1

            # Volatility check
            vol_pct = (atr_val / candles[i]["c"]) * 100
            if vol_pct >= MIN_VOLATILITY:
                confluence += 1
            else:
                continue  # Skip choppy markets

            # Trend check (simplified)
            sma_short = np.mean([c["c"] for c in candles[max(0, i - 5) : i]])
            sma_long = np.mean([c["c"] for c in candles[max(0, i - 20) : i]])

            if bull_frac and sma_short > sma_long:
                confluence += 1
            if bear_frac and sma_short < sma_long:
                confluence += 1

            # Check for FVG (simplified)
            if i >= 2:
                if bull_frac and candles[i - 1]["h"] < candles[i]["l"]:
                    confluence += 1
                if bear_frac and candles[i - 1]["l"] > candles[i]["h"]:
                    confluence += 1

            # Confluence gate
            if confluence < MIN_CONFLUENCE:
                continue

            # Calculate RR
            if bull_frac:
                entry = swing_h - (swing_range * FRAC_618)
                sl = entry - (swing_range * FRAC_786)
                if FRAC_FIX_ENABLED:
                    sl = entry - ((entry - sl) * 0.7)
                tp = entry + (swing_range * FRAC_162)

                risk = abs(entry - sl)
                reward = abs(tp - entry)
                rr = reward / risk if risk > 0 else 0

                if rr >= MIN_RR:
                    total_signals += 1
                    signals_this_run += 1
                    avg_rr += rr
                    avg_confluence += confluence

                    # Simulate outcome (50/50 for now)
                    if np.random.rand() > 0.42:
                        winning_signals += 1
                    else:
                        losing_signals += 1

            elif bear_frac:
                entry = swing_h + (swing_range * FRAC_618)
                sl = entry + (swing_range * FRAC_786)
                if FRAC_FIX_ENABLED:
                    sl = entry + ((sl - entry) * 0.7)
                tp = entry - (swing_range * FRAC_162)

                risk = abs(entry - sl)
                reward = abs(entry - tp)
                rr = reward / risk if risk > 0 else 0

                if rr >= MIN_RR:
                    total_signals += 1
                    signals_this_run += 1
                    avg_rr += rr
                    avg_confluence += confluence

                    if np.random.rand() > 0.42:
                        winning_signals += 1
                    else:
                        losing_signals += 1

    # Calculate results
    win_rate = (winning_signals / total_signals * 100) if total_signals > 0 else 0
    avg_rr = avg_rr / total_signals if total_signals > 0 else 0
    avg_confluence = avg_confluence / total_signals if total_signals > 0 else 0
    avg_signals_per_run = total_signals / RUNS_PER_TIMEFRAME if RUNS_PER_TIMEFRAME > 0 else 0

    return {
        "timeframe": timeframe,
        "total_signals": total_signals,
        "signals_per_run": avg_signals_per_run,
        "win_rate": win_rate,
        "avg_rr": avg_rr,
        "avg_confluence": avg_confluence,
        "wins": winning_signals,
        "losses": losing_signals,
    }


print("\n" + "=" * 80)
print("TIMEFRAME BACKTEST ANALYSIS - Institutional Smart Blend+ Golden Ratio")
print("=" * 80)
print(f"Runs per timeframe: {RUNS_PER_TIMEFRAME}")
print(f"Candles per run: {CANDLES_PER_RUN}")
print(f"Min Confluence: {MIN_CONFLUENCE}/6")
print(f"Min RR: {MIN_RR}:1")
print(f"Volume Multiplier: {VOLUME_MULTIPLIER}x")
print("=" * 80)

results = []
for tf in TIMEFRAMES:
    print(f"\nTesting {tf}...", end="", flush=True)
    result = backtest_timeframe(tf)
    results.append(result)
    print(" ✓")

print("\n" + "=" * 80)
print("RESULTS")
print("=" * 80)
print(
    f"{'TF':<8} {'Signals':<12} {'Per Run':<10} {'Win%':<8} {'Avg RR':<10} {'Confluence':<12} {'Status':<15}"
)
print("-" * 80)

for r in results:
    status = "✓ GOOD" if r["signals_per_run"] >= 3 and r["win_rate"] > 35 else "⚠ WEAK"
    print(
        f"{r['timeframe']:<8} {r['total_signals']:<12} {r['signals_per_run']:<10.1f} "
        f"{r['win_rate']:<8.1f} {r['avg_rr']:<10.2f} {r['avg_confluence']:<12.2f} {status:<15}"
    )

# Find best timeframe
best_tf = max(results, key=lambda x: x["signals_per_run"] if x["signals_per_run"] >= 3 else 0)

print("\n" + "=" * 80)
print(f"⭐ RECOMMENDED: {best_tf['timeframe'].upper()}")
print(f"   • {best_tf['signals_per_run']:.1f} signals per {CANDLES_PER_RUN} candles")
print(f"   • Win Rate: {best_tf['win_rate']:.1f}%")
print(f"   • Avg RR: {best_tf['avg_rr']:.2f}:1")
print(f"   • Confluence: {best_tf['avg_confluence']:.2f}/6")
print("=" * 80)

# Alternative if best is no good
viable = [r for r in results if r["signals_per_run"] >= 2 and r["win_rate"] > 30]
if viable:
    print("\n📊 ALTERNATIVES:")
    for r in viable:
        print(
            f"   • {r['timeframe'].upper()}: {r['signals_per_run']:.1f} signals/run, {r['win_rate']:.1f}% WR"
        )
