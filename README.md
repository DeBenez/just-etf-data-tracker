# JustETF Data Tracker

A small Python utility for building monthly performance datasets for an ETF
portfolio and its benchmarks. It downloads historical chart data from
[JustETF](https://www.justetf.com/), takes the final available price in each
month, calculates month-over-month returns, and exports CSV files ready for
reporting or import into another tool.

The project supports both raw ISINs and JustETF product URLs, optional
time-varying portfolio weights, and total-return price series when the data
source provides them.

## What it produces

Running the included script generates two files:

| File | Contents |
| --- | --- |
| `output/db_HistoryMonthly.csv` | Monthly return for every portfolio instrument, its weight, and its weighted contribution to the portfolio return. |
| `output/db_HistoryBenchmark.csv` | Monthly return for every benchmark instrument, formatted as benchmark data. |

The generated data is at instrument level. To obtain a portfolio total for a
month, sum `portfolio_monthly_yield` across the instruments with a weight for
that month.

## How it works

1. The program reads portfolio instruments from `input/instruments.csv` and
   benchmarks from `input/benchmark_instruments.csv`.
2. For each instrument, it extracts the ISIN and downloads JustETF chart data.
3. It prefers a price series with reinvested dividends, then a series with
   dividends, and finally the quoted price when those are unavailable.
4. It keeps the last available observation in each calendar month.
5. It calculates the monthly return as `(current month-end price / previous
   month-end price) - 1`.
6. For portfolio data, it matches weights by ticker and month and calculates
   the weighted monthly contribution.

Only a complete previous month is included by the convenience script, which
avoids publishing a partial current-month result.

## Requirements

- Python 3
- Internet access to download market data and dependencies
- `pandas`
- [`justetf-scraping`](https://github.com/druzsan/justetf-scraping)

The included runner creates a local `.venv` virtual environment and installs
the Python dependencies automatically. Its calculation of the previous
month's last day uses macOS `date` syntax, so it is intended for macOS.

## Quick start

From the project folder:

```bash
chmod +x run_returns.sh
./run_returns.sh
```

The command will:

- create `.venv` if needed;
- install or update the dependencies;
- update `output/db_HistoryMonthly.csv` from `input/instruments.csv` and `input/weights.csv`;
- update `output/db_HistoryBenchmark.csv` from `input/benchmark_instruments.csv`.

If `input/weights.csv` is not present, portfolio returns are still produced, but the
weight and portfolio-contribution fields are empty.

## Input files

### Portfolio instruments — `input/instruments.csv`

Required columns:

```csv
ticker,isin_or_url
XDEM,https://www.justetf.com/it/etf-profile.html?isin=IE00BL25JP72
MVOL,IE00B8FHGS14
```

- `ticker`: your short label for the instrument. It is normalized to uppercase.
- `isin_or_url`: either an ISIN or a JustETF URL containing an ISIN.

The second column may also be named `isin`, `url`, or `link`.

### Portfolio weights — `input/weights.csv` (optional)

```csv
date,ticker,weight
2025-01-31,XDEM,56%
2025-01-31,MVOL,24%
```

- `date`: any valid date in the month to which the allocation applies; the
  program matches weights by calendar month.
- `ticker`: must match the corresponding portfolio ticker.
- `weight`: accepts percentage values (`56%`), decimal percentages (`56`), or
  fractions (`0.56`). Commas are accepted as decimal separators.

Add one row per instrument for every month whose portfolio contribution you
want calculated.

### Benchmark instruments — `input/benchmark_instruments.csv`

This has the same structure as the portfolio instruments file:

```csv
ticker,isin_or_url
VWCE,IE00BK5BQT80
SWDA,IE00B4L5Y983
```

Benchmarks do not need a weights file: each is exported with a `100%` weight.

## Output format

### Portfolio output

`output/db_HistoryMonthly.csv` contains:

| Column | Meaning |
| --- | --- |
| `ticker` | Instrument ticker from the input file. |
| `date` | Last available trading date of the month, in `DD/MM/YYYY` format. |
| `weight` | Matching monthly portfolio allocation, when supplied. |
| `yield` | Instrument monthly return. |
| `type` | Always `Portfolio`. |
| `benchmark_name` | Always `Portfolio`. |
| `portfolio_monthly_yield` | `yield × weight`; sum this field by date for the portfolio monthly return. |

### Benchmark output

`output/db_HistoryBenchmark.csv` contains the same common fields except for
`portfolio_monthly_yield`. Its `type` is `Benchmark`, `benchmark_name` is the
instrument ticker, and `weight` is `100%`.

Percentages are written with a comma decimal separator (for example, `1,63%`)
to suit locales that use this convention.

## Running the Python program directly

Install the dependencies in your preferred environment:

```bash
python3 -m pip install pandas git+https://github.com/druzsan/justetf-scraping.git
```

Generate portfolio data:

```bash
python3 calculate_justetf_returns.py \
  --instruments input/instruments.csv \
  --weights input/weights.csv \
  --output output/db_HistoryMonthly.csv \
  --start 2024-09-01 \
  --end 2026-05-31
```

Generate benchmark data:

```bash
python3 calculate_justetf_returns.py \
  --instruments input/benchmark_instruments.csv \
  --output output/db_HistoryBenchmark.csv \
  --start 2024-09-01 \
  --end 2026-05-31 \
  --benchmark-mode
```

Optional flags:

- `--start YYYY-MM-DD` and `--end YYYY-MM-DD` limit the source data range.
- `--unclosed` includes the current, potentially incomplete trading day.
- Omit `--weights` to export unweighted portfolio instrument returns.
- `--benchmark-mode` sets the benchmark-specific output layout.

## Project layout

```text
calculate_justetf_returns.py  # Download, transform, and export logic
run_returns.sh                # macOS convenience runner
input/                        # Configuration and source CSV files
├── instruments.csv           # Portfolio instruments
├── weights.csv               # Optional monthly portfolio allocations
└── benchmark_instruments.csv # Benchmark instruments
output/                       # Generated CSV files
├── db_HistoryMonthly.csv     # Portfolio history
└── db_HistoryBenchmark.csv   # Benchmark history
```

## Notes and limitations

- Data availability, price currency, and dividend handling depend on JustETF
  and the upstream `justetf-scraping` package.
- The return is calculated from the final available chart observation of each
  month, which can be earlier than calendar month-end when markets are closed.
- This project is a data utility, not investment advice. Validate results
  before using them for investment, tax, or accounting decisions.
