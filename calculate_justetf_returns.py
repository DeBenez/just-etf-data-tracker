#!/usr/bin/env python3
"""
Download price history from JustETF using link/ISIN input and calculate
end-of-month returns for each instrument.

Required inputs:
  1) input/instruments.csv with at least:
       ticker,isin_or_url
     Example:
       XDEM,https://www.justetf.com/it/etf-profile.html?isin=IE00BL25JP72
       MVOL,IE00B8FHGS14

  2) Optional input/weights.csv with columns:
       date,ticker,weight
     Example:
       2025-01-31,XDEM,56%
       2025-01-31,MVOL,24%

Usage:
  python calculate_justetf_returns.py \
    --instruments input/instruments.csv \
    --weights input/weights.csv \
    --output output/db_HistoryMonthly.csv \
    --start 2024-09-01 \
    --end 2026-05-31

Dependencies:
  python -m pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import justetf_scraping
except ImportError as exc:
    raise SystemExit(
        "Missing justetf_scraping library. Install dependencies with:\n"
        "python -m pip install -r requirements.txt"
    ) from exc


ISIN_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


@dataclass(frozen=True)
class Instrument:
    ticker: str
    isin: str


def extract_isin(value: str) -> str:
    """Extract the ISIN from either a raw ISIN value or a JustETF URL."""
    value = (value or "").strip().upper()
    match = ISIN_RE.search(value)
    if not match:
        raise ValueError(f"Unable to extract an ISIN from: {value!r}")
    return match.group(0)


def read_instruments(path: Path) -> list[Instrument]:
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}

    if "ticker" not in cols:
        raise ValueError(f"{path} must contain a 'ticker' column.")

    isin_col = None
    for candidate in ("isin_or_url", "isin", "url", "link"):
        if candidate in cols:
            isin_col = cols[candidate]
            break
    if isin_col is None:
        raise ValueError(
            f"{path} must contain one of these columns: "
            "isin_or_url, isin, url, link."
        )

    instruments: list[Instrument] = []
    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        ticker = str(row[cols["ticker"]]).strip().upper()
        if pd.isna(row[cols["ticker"]]) or not ticker:
            raise ValueError(f"{path}, row {row_number}: ticker must not be blank.")
        try:
            isin = extract_isin(str(row[isin_col]))
        except ValueError as exc:
            raise ValueError(f"{path}, row {row_number}: {exc}") from exc
        instruments.append(Instrument(ticker=ticker, isin=isin))

    if not instruments:
        raise ValueError(f"{path} does not contain any instruments.")

    tickers = [instrument.ticker for instrument in instruments]
    duplicates = sorted({ticker for ticker in tickers if tickers.count(ticker) > 1})
    if duplicates:
        raise ValueError(f"{path} contains duplicate ticker(s): {', '.join(duplicates)}.")
    return instruments


def load_chart_for_instrument(
    instrument: Instrument, unclosed: bool = False, retries: int = 3
) -> pd.DataFrame:
    """Download chart data from JustETF and return date, ticker, and price."""
    attempts = max(1, retries)
    chart = None
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            chart = justetf_scraping.load_chart(instrument.isin, unclosed=unclosed)
            break
        except Exception as exc:  # network/library errors vary by scraper version
            last_error = exc
            if attempt == attempts:
                raise ValueError(
                    f"Unable to download data for {instrument.ticker} after "
                    f"{attempts} attempt(s): {exc}"
                ) from exc
            print(
                f"[WARNING] Download attempt {attempt}/{attempts} failed for "
                f"{instrument.ticker}; retrying...",
                file=sys.stderr,
            )
            time.sleep(1)

    if last_error is not None and chart is None:
        raise ValueError(f"Unable to download data for {instrument.ticker}: {last_error}")
    if chart is None or chart.empty:
        raise ValueError(f"No data downloaded for {instrument.ticker} ({instrument.isin}).")

    df = chart.reset_index()
    if "date" not in df.columns:
        # Some versions expose the date as the first unnamed column.
        df = df.rename(columns={df.columns[0]: "date"})

    # Prefer quote_with_reinvested_dividends when available for total return performance.
    # For ETC/ETN or accumulating instruments it often matches quote.
    preferred_columns = [
        "quote_with_reinvested_dividends",
        "quote_with_dividends",
        "quote",
    ]
    price_col: Optional[str] = next((c for c in preferred_columns if c in df.columns), None)
    if price_col is None:
        raise ValueError(
            f"Price column not found for {instrument.ticker}. "
            f"Available columns: {list(df.columns)}"
        )

    out = df[["date", price_col]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["price"] = pd.to_numeric(out[price_col], errors="coerce")
    out["ticker"] = instrument.ticker
    out = out.dropna(subset=["date", "price"])
    return out[["ticker", "date", "price"]]


def month_end_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Take the last available price of each month for each ticker."""
    df = prices.sort_values(["ticker", "date"]).copy()
    df["month"] = df["date"].dt.to_period("M")
    idx = df.groupby(["ticker", "month"])["date"].idxmax()
    monthly = df.loc[idx, ["ticker", "date", "month", "price"]]
    monthly = monthly.sort_values(["ticker", "date"])
    return monthly


def monthly_returns(monthly_prices: pd.DataFrame) -> pd.DataFrame:
    df = monthly_prices.copy()
    df["prev_price"] = df.groupby("ticker")["price"].shift(1)
    df["yield_decimal"] = df["price"] / df["prev_price"] - 1
    df = df.dropna(subset=["yield_decimal"])
    return df


def normalize_weight(value) -> Optional[float]:
    if pd.isna(value):
        return None
    s = str(value).strip().replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        number = float(s)
    except ValueError as exc:
        raise ValueError(f"Invalid weight value: {value!r}") from exc
    if number > 1:
        number = number / 100.0
    if not 0 <= number <= 1:
        raise ValueError(f"Weight must be between 0% and 100%: {value!r}")
    return number


def attach_weights(returns: pd.DataFrame, weights_path: Optional[Path], benchmark_mode: bool = False) -> pd.DataFrame:
    df = returns.copy()
    if weights_path is None:
        if benchmark_mode:
            df["weight"] = "100%"
            df["portfolio_monthly_yield"] = None
        else:
            df["weight"] = ""
            df["portfolio_monthly_yield"] = ""
        return df

    weights = pd.read_csv(weights_path)
    weights.columns = [c.strip().lower() for c in weights.columns]
    required = {"date", "ticker", "weight"}
    missing = required.difference(weights.columns)
    if missing:
        raise ValueError(f"{weights_path} is missing required columns: {sorted(missing)}")

    for row_number, (ticker, date) in enumerate(zip(weights["ticker"], weights["date"]), start=2):
        if pd.isna(ticker) or not str(ticker).strip():
            raise ValueError(f"{weights_path}, row {row_number}: ticker must not be blank.")
        if pd.isna(pd.to_datetime(date, errors="coerce")):
            raise ValueError(f"{weights_path}, row {row_number}: invalid date value {date!r}.")

    weights["ticker"] = weights["ticker"].astype(str).str.upper().str.strip()
    weights["date"] = pd.to_datetime(weights["date"], errors="coerce")
    weights["month"] = weights["date"].dt.to_period("M")
    for row_number, value in enumerate(weights["weight"], start=2):
        try:
            normalize_weight(value)
        except ValueError as exc:
            raise ValueError(f"{weights_path}, row {row_number}: {exc}") from exc
    weights["weight_decimal"] = weights["weight"].apply(normalize_weight)
    weights = weights.dropna(subset=["ticker", "month", "weight_decimal"])

    totals = weights.groupby("month")["weight_decimal"].sum()
    for month, total in totals.items():
        if not 0.9995 <= total <= 1.0005:
            print(
                f"[WARNING] {weights_path}: weights for {month} total "
                f"{format_percent(total)} instead of 100%.",
                file=sys.stderr,
            )

    duplicate_weights = weights.duplicated(["ticker", "month"], keep=False)
    if duplicate_weights.any():
        duplicates = weights.loc[duplicate_weights, ["ticker", "month"]].drop_duplicates()
        labels = ", ".join(f"{row.ticker} ({row.month})" for row in duplicates.itertuples())
        raise ValueError(f"{weights_path} contains duplicate ticker/month entries: {labels}.")

    df = df.merge(weights[["ticker", "month", "weight_decimal"]], on=["ticker", "month"], how="left")
    df["weight"] = df["weight_decimal"].apply(lambda x: "" if pd.isna(x) else f"{x:.0%}")
    df["portfolio_monthly_yield"] = df.apply(
        lambda row: ""
        if pd.isna(row["weight_decimal"])
        else format_percent(row["yield_decimal"] * row["weight_decimal"]),
        axis=1,
    )
    return df


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%".replace(".", ",")


def ensure_output_directory(output_path: Path) -> None:
    """Create the output directory, or explain why it cannot be used."""
    parent = output_path.parent
    if parent.exists() and not parent.is_dir():
        raise ValueError(f"Output directory is not a directory: {parent}")
    parent.mkdir(parents=True, exist_ok=True)


def print_completion_summary(output_path: Path, output: pd.DataFrame) -> None:
    if output.empty:
        coverage = "no monthly returns in the selected date range"
    else:
        dates = pd.to_datetime(output["date"], format="%d/%m/%Y")
        coverage = f"coverage={dates.min():%d/%m/%Y} to {dates.max():%d/%m/%Y}"
    print(f"[SUCCESS] Created {output_path}: rows={len(output)}, {coverage}.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate monthly returns from JustETF link/ISIN input.")
    parser.add_argument("--instruments", required=True, help="CSV with ticker and JustETF link/ISIN")
    parser.add_argument("--weights", help="Optional CSV with date,ticker,weight")
    parser.add_argument("--output", required=True, help="Output CSV file")
    parser.add_argument("--start", help="Start date inclusive, e.g. 2024-09-01")
    parser.add_argument("--end", help="End date inclusive, e.g. 2026-05-31")
    parser.add_argument("--unclosed", action="store_true", help="Include the current unclosed day")
    parser.add_argument("--benchmark-mode", action="store_true", help="Format output as benchmark data")
    parser.add_argument("--retries", type=int, default=3, help="Download attempts per instrument (default: 3)")
    args = parser.parse_args()

    instruments_path = Path(args.instruments)
    output_path = Path(args.output)
    instruments = read_instruments(instruments_path)
    ensure_output_directory(output_path)
    ticker_order = {instrument.ticker: index for index, instrument in enumerate(instruments)}

    all_prices = []
    for index, instrument in enumerate(instruments, start=1):
        print(
            f"[INFO] Downloading {index}/{len(instruments)}: "
            f"{instrument.ticker} ({instrument.isin})...",
            file=sys.stderr,
        )
        all_prices.append(
            load_chart_for_instrument(instrument, unclosed=args.unclosed, retries=args.retries)
        )

    prices = pd.concat(all_prices, ignore_index=True)

    if args.start:
        prices = prices[prices["date"] >= pd.to_datetime(args.start)]
    if args.end:
        prices = prices[prices["date"] <= pd.to_datetime(args.end)]

    monthly = month_end_prices(prices)
    returns = monthly_returns(monthly)
    returns = attach_weights(
        returns,
        Path(args.weights) if args.weights else None,
        benchmark_mode=args.benchmark_mode,
    )

    output_data = {
        "ticker": returns["ticker"],
        "date": returns["date"].dt.strftime("%d/%m/%Y"),
        "weight": returns["weight"],
        "yield": returns["yield_decimal"].apply(format_percent),
        "type": "Benchmark" if args.benchmark_mode else "Portfolio",
        "benchmark_name": returns["ticker"] if args.benchmark_mode else "Portfolio",
        "_date_sort": returns["date"],
    }
    if not args.benchmark_mode:
        output_data["portfolio_monthly_yield"] = returns["portfolio_monthly_yield"]

    output = pd.DataFrame(output_data)
    output["_ticker_sort"] = output["ticker"].map(ticker_order)
    output = output.sort_values(["_date_sort", "_ticker_sort"]).drop(columns=["_date_sort", "_ticker_sort"])

    output.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print_completion_summary(output_path, output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
