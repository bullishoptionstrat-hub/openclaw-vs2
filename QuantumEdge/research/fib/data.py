"""
Data loader — reads Lean daily equity zip files into numpy arrays.

Lean daily format (inside zip):
  One CSV file named <ticker>.csv
  Columns: date_time (YYYYMMDD HH:MM), open*10000, high*10000, low*10000, close*10000, volume

Returns a dict with keys: dates, opens, highs, lows, closes, volumes
All prices are divided by 10000 and converted to float64.
Dates are returned as strings (YYYYMMDD) and as sequential integer indices.
"""

from __future__ import annotations

import os
import zipfile
import numpy as np
from typing import Optional


def _lean_data_dir() -> str:
    """Walk up from this file to find lean/Data/equity/usa/daily/."""
    here = os.path.dirname(os.path.abspath(__file__))
    # research/fib/ -> research/ -> QuantumEdge/ -> repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(repo_root, "lean", "Data", "equity", "usa", "daily")


def load_ticker(
    ticker: str,
    data_dir: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Load daily OHLCV data for a single ticker from the Lean data directory.

    Parameters
    ----------
    ticker : str
        Uppercase ticker symbol (e.g. 'SPY').
    data_dir : str, optional
        Override the default Lean data directory.
    start_date : str, optional
        Filter start, inclusive. Format: 'YYYYMMDD'.
    end_date : str, optional
        Filter end, inclusive. Format: 'YYYYMMDD'.

    Returns
    -------
    dict with keys:
        ticker   : str
        dates    : list[str]  — 'YYYYMMDD'
        opens    : np.ndarray[float64]
        highs    : np.ndarray[float64]
        lows     : np.ndarray[float64]
        closes   : np.ndarray[float64]
        volumes  : np.ndarray[float64]
        n        : int  — number of bars

    Raises
    ------
    FileNotFoundError if the zip file does not exist.
    ValueError if the zip contains no readable rows.
    """
    if data_dir is None:
        data_dir = _lean_data_dir()

    zip_path = os.path.join(data_dir, f"{ticker.lower()}.zip")
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"No Lean data found for {ticker} at {zip_path}")

    dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        csv_names = [n for n in names if n.endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV found inside {zip_path}")
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
                volumes.append(v)

    if not dates:
        raise ValueError(f"No valid rows loaded for {ticker}")

    return {
        "ticker": ticker,
        "dates": dates,
        "opens": np.array(opens, dtype=np.float64),
        "highs": np.array(highs, dtype=np.float64),
        "lows": np.array(lows, dtype=np.float64),
        "closes": np.array(closes, dtype=np.float64),
        "volumes": np.array(volumes, dtype=np.float64),
        "n": len(dates),
    }


def compute_atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
) -> np.ndarray:
    """
    Compute Wilder's ATR.  Returns an array of length n; first `period` values
    are NaN during warm-up.
    """
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

    # First ATR = simple average of first `period` TRs
    atr[period - 1] = np.mean(tr[:period])

    # Wilder smoothing
    alpha = 1.0 / period
    for i in range(period, n):
        atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha

    return atr


def available_tickers(data_dir: Optional[str] = None) -> list[str]:
    """List all tickers with daily data in the Lean data directory."""
    if data_dir is None:
        data_dir = _lean_data_dir()
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        os.path.splitext(f)[0].upper() for f in os.listdir(data_dir) if f.endswith(".zip")
    )
