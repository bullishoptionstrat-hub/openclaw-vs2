"""
Generate Lean-format data files for QuantumEdge sector ETFs.
Downloads from yfinance, converts to Lean zip format (OHLCV × 10000).
Also creates minimal map files and factor files (factor=1 since we use adjusted prices).
Run: python QuantumEdge/generate_lean_data.py
"""
import os, zipfile, io, warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd

BASE = r"C:\Users\alexm\OneDrive\Documents\GitHub\openclaw-vs2\lean\Data\equity\usa"
DAILY_DIR   = os.path.join(BASE, "daily")
MAP_DIR     = os.path.join(BASE, "map_files")
FACTOR_DIR  = os.path.join(BASE, "factor_files")

# All tickers needed by the QuantumEdge algorithm
TICKERS = [
    "XLK", "XLV", "XLF", "XLI", "XLY", "XLP",
    "XLE", "XLB", "XLU", "XLC", "XLRE",
    "SHY", "SPXU", "VXX",
]

START = "2009-01-01"   # extra year for warmup coverage
END   = "2024-12-31"

print(f"Downloading {len(TICKERS)} tickers {START} to {END}...")
raw = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=True)
close_df = raw["Close"]
open_df  = raw["Open"]
high_df  = raw["High"]
low_df   = raw["Low"]
vol_df   = raw["Volume"]

coverage = close_df.notna().mean()
print("\nData coverage:")
for t in TICKERS:
    if t in coverage.index:
        print(f"  {t}: {coverage[t]:.1%}")
    else:
        print(f"  {t}: NOT FOUND")

generated = []
for ticker in TICKERS:
    if ticker not in close_df.columns:
        print(f"  SKIP {ticker} — not in download result")
        continue

    df = pd.DataFrame({
        "Open":   open_df[ticker],
        "High":   high_df[ticker],
        "Low":    low_df[ticker],
        "Close":  close_df[ticker],
        "Volume": vol_df[ticker],
    }).dropna(subset=["Close"])

    if len(df) < 100:
        print(f"  SKIP {ticker} — only {len(df)} rows")
        continue

    # ── Daily zip ──────────────────────────────────────────────────────────
    rows = []
    for date, row in df.iterrows():
        dt_str = date.strftime("%Y%m%d") + " 00:00"
        o = int(round(row["Open"]  * 10000))
        h = int(round(row["High"]  * 10000))
        l = int(round(row["Low"]   * 10000))
        c = int(round(row["Close"] * 10000))
        v = int(row["Volume"])
        rows.append(f"{dt_str},{o},{h},{l},{c},{v}")

    csv_content = "\n".join(rows)
    zip_path = os.path.join(DAILY_DIR, f"{ticker.lower()}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{ticker.lower()}.csv", csv_content)

    # ── Map file ────────────────────────────────────────────────────────────
    start_date = df.index[0].strftime("%Y%m%d")
    map_path = os.path.join(MAP_DIR, f"{ticker.lower()}.csv")
    with open(map_path, "w") as f:
        f.write(f"{start_date},{ticker.lower()},P\n")
        f.write(f"20501231,{ticker.lower()},P\n")

    # ── Factor file (factor=1 — prices already adjusted by yfinance) ────────
    # Format: date,price_factor,split_factor,closing_price
    factor_path = os.path.join(FACTOR_DIR, f"{ticker.lower()}.csv")
    with open(factor_path, "w") as f:
        f.write(f"{start_date},1,1,{df['Close'].iloc[0]:.4f}\n")
        f.write(f"20501231,1,1,0\n")

    print(f"  OK  {ticker:6s}  {len(df)} rows  {zip_path}")
    generated.append(ticker)

print(f"\nDone. Generated {len(generated)} tickers: {generated}")
print(f"\nData dir: {DAILY_DIR}")
