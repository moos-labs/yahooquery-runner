# yahooquery-runner

Runs **yahooquery** data fetches via GitHub Actions — part of a one-public-repo-per-tool pattern: each tool gets its own repo, the commands to execute live in a repository variable, runs are triggered manually, and outputs are collected as artifacts.

yahooquery is a Python library for Yahoo Finance data (history + company info) that uses different endpoints than `yfinance`. This runner deliberately does **not** use `yfinance` anywhere — `yfinance` crashes on Africa/Cairo DST timestamps, and testing whether Egyptian tickers work through yahooquery instead is the point of the pilot.

## How to run an analysis

1. **Edit the commands**: repo **Settings → Secrets and variables → Actions → Variables** → set `COMMANDS` to the shell commands you want executed, e.g.
   ```
   mkdir -p results
   python scripts/fetch.py 2>&1 | tee results/run.log
   ```
   Pass different tickers/parameters by editing the command, e.g. `python scripts/fetch.py --tickers AAPL,MSFT --period 1y`.
2. **Trigger manually**: **Actions** tab → **Run analysis** → **Run workflow** (or dispatch it through the GitHub API).
3. **Collect results**: download the `results` artifact from the finished run. It contains a per-ticker CSV of daily history, `summary.json`, and the run log.

## What the tool does

`scripts/fetch.py` uses yahooquery's `Ticker` for each ticker:

- Fetches ~5 years of daily history (default `--period 5y --interval 1d`)
- Fetches basic info (`summary_detail`, `asset_profile`, `price` — whatever the library exposes)
- Writes `results/<TICKER>.csv` per ticker and `results/summary.json` with, per ticker: rows, first date, last date, first close, last close, which info fields were obtained, or the exact error

## Design notes

- **Generic and multi-market.** Tickers and parameters are CLI args (`--tickers`, `--period`, `--interval`, `--output-dir`); nothing in the workflow or script is tied to one exchange. The pilot defaults are `AAPL,POUL.CA` only so a bare dispatch runs the pilot.
- **Pilot question:** does `POUL.CA` (Cairo Poultry, EGX) return history/info through yahooquery, unlike the yfinance Africa/Cairo DST failure?
