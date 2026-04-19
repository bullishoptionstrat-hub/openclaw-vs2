"""
Data loader for fib2 — daily and 1-hour Lean zip files.

Daily format  : YYYYMMDD HH:MM, O*10000, H*10000, L*10000, C*10000, Vol
Hourly format : YYYYMMDD HH:MM, O*10000, H*10000, L*10000, C*10000, Vol

Returns dicts with numpy arrays and an alignment mapping so the backtester
can jump between timeframes by date.
"""

from __future__ import annotations

import os
import zipfile
import numpy as np
from typing import Optional


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def _data_dir(subdir: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    # fib2/ -> research/ -> QuantumEdge/ -> repo_root
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(repo_root, "lean", "Data", "equity", "usa", subdir)


def _load_zip(
    zip_path: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[list, list, list, list, list, list]:
    """Load one Lean OHLCV zip; return (dates, opens, highs, lows, closes, vols)."""
    dates, opens, highs, lows, closes, vols = [], [], [], [], [], []
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV inside {zip_path}")
        with zf.open(csv_names[0]) as f:
            for raw in f:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 6:
                    continue
                dt_str = parts[0].split(" ")[0]  # 'YYYYMMDD'
                if start_date and dt_str < start_date:
                    continue
                if end_date and dt_str > end_date:
                    continue
                try:
                    o = float(parts[1]) / 10000.0
                    h = float(parts[2]) / 10000.0
                    lo = float(parts[3]) / 10000.0
                    c = float(parts[4]) / 10000.0
                    v = float(parts[5])
                except ValueError:
                    continue
                if o <= 0 or h <= 0 or lo <= 0 or c <= 0:
                    continue
                dates.append(dt_str)
                opens.append(o)
                highs.append(h)
                lows.append(lo)
                closes.append(c)
                vols.append(v)
    return dates, opens, highs, lows, closes, vols


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_daily(
    ticker: str,
    data_dir: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Load daily OHLCV for ticker. Returns bars dict."""
    dd = data_dir or _data_dir("daily")
    zp = os.path.join(dd, f"{ticker.lower()}.zip")
    if not os.path.exists(zp):
        raise FileNotFoundError(f"No daily data for {ticker} at {zp}")
    dates, o, h, l, c, v = _load_zip(zp, start_date, end_date)
    if not dates:
        raise ValueError(f"No rows loaded for {ticker} daily")
    return {
        "ticker": ticker,
        "timeframe": "daily",
        "dates": dates,
        "opens": np.array(o, dtype=np.float64),
        "highs": np.array(h, dtype=np.float64),
        "lows": np.array(l, dtype=np.float64),
        "closes": np.array(c, dtype=np.float64),
        "volumes": np.array(v, dtype=np.float64),
        "n": len(dates),
    }


def load_hourly(
    ticker: str,
    data_dir: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[dict]:
    """
    Load 1H OHLCV for ticker.  Returns None if hourly data not available.
    Each hourly 'date' is 'YYYYMMDD HH:MM'.
    """
    hd = data_dir or _data_dir("hour")
    zp = os.path.join(hd, f"{ticker.lower()}.zip")
    if not os.path.exists(zp):
        return None
    try:
        # For hourly, preserve full datetime string (not just date)
        dates_full, o, h, l, c, v = [], [], [], [], [], []
        with zipfile.ZipFile(zp, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                return None
            with zf.open(csv_names[0]) as f:
                for raw in f:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) < 6:
                        continue
                    dt_full = parts[0]  # 'YYYYMMDD HH:MM'
                    dt_str = dt_full.split(" ")[0]  # date portion only
                    if start_date and dt_str < start_date:
                        continue
                    if end_date and dt_str > end_date:
                        continue
                    try:
                        ov = float(parts[1]) / 10000.0
                        hv = float(parts[2]) / 10000.0
                        lv = float(parts[3]) / 10000.0
                        cv = float(parts[4]) / 10000.0
                        vv = float(parts[5])
                    except ValueError:
                        continue
                    if ov <= 0 or hv <= 0 or lv <= 0 or cv <= 0:
                        continue
                    dates_full.append(dt_full)
                    o.append(ov)
                    h.append(hv)
                    l.append(lv)
                    c.append(cv)
                    v.append(vv)
        if not dates_full:
            return None
        date_strs = [d.split(" ")[0] for d in dates_full]
        return {
            "ticker": ticker,
            "timeframe": "1h",
            "datetimes": dates_full,
            "dates": date_strs,
            "opens": np.array(o, dtype=np.float64),
            "highs": np.array(h, dtype=np.float64),
            "lows": np.array(l, dtype=np.float64),
            "closes": np.array(c, dtype=np.float64),
            "volumes": np.array(v, dtype=np.float64),
            "n": len(dates_full),
        }
    except Exception:
        return None


def build_date_to_1h_range(
    daily_bars: dict,
    hourly_bars: dict,
) -> dict[str, tuple[int, int]]:
    """
    Returns a mapping: date_str -> (h_start_idx, h_end_idx_exclusive)
    so that hourly_bars[h_start:h_end] are all bars on that calendar date.
    """
    mapping: dict[str, tuple[int, int]] = {}
    h_dates = hourly_bars["dates"]
    n_h = len(h_dates)

    i = 0
    while i < n_h:
        d = h_dates[i]
        j = i
        while j < n_h and h_dates[j] == d:
            j += 1
        mapping[d] = (i, j)
        i = j

    return mapping


def compute_atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
) -> np.ndarray:
    """Wilder's ATR.  First `period` values are NaN."""
    n = len(closes)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr = np.full(n, np.nan)
    if n < period:
        return atr
    atr[period - 1] = np.mean(tr[:period])
    alpha = 1.0 / period
    for i in range(period, n):
        atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha
    return atr


def compute_sma(closes: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average; first period-1 values are NaN."""
    n = len(closes)
    sma = np.full(n, np.nan)
    if n < period:
        return sma
    cumsum = np.cumsum(closes)
    sma[period - 1] = cumsum[period - 1] / period
    for i in range(period, n):
        sma[i] = sma[i - 1] + (closes[i] - closes[i - period]) / period
    return sma


def available_tickers(timeframe: str = "daily") -> list[str]:
    dd = _data_dir(timeframe)
    if not os.path.isdir(dd):
        return []
    return sorted(os.path.splitext(f)[0].upper() for f in os.listdir(dd) if f.endswith(".zip"))
