#!/usr/bin/env python3
"""Fetch price history and basic info via yahooquery.

Generic / multi-market: tickers and period are CLI args, nothing is
hardcoded beyond pilot defaults. This deliberately does NOT use the
yfinance package (which crashes on Africa/Cairo DST timestamps);
yahooquery is a different library using different Yahoo endpoints.

Usage:
  python scripts/fetch.py
  python scripts/fetch.py --tickers AAPL,POUL.CA
  python scripts/fetch.py --tickers AAPL,MSFT --period 5y --interval 1d

Outputs (in results/ by default):
  <TICKER>.csv   daily history per ticker (only when history was obtained)
  summary.json   per ticker: rows, first/last date, first/last close,
                 which info fields were obtained, or the exact error
"""
import argparse
import json
import os
import sys
import traceback


def parse_args():
    p = argparse.ArgumentParser(description="Fetch history + info via yahooquery")
    p.add_argument(
        "--tickers",
        default="AAPL,POUL.CA",
        help="Comma-separated tickers (default: AAPL,POUL.CA - pilot defaults)",
    )
    p.add_argument("--period", default="5y", help="History period, e.g. 1y, 5y, max (default: 5y)")
    p.add_argument("--interval", default="1d", help="History interval (default: 1d)")
    p.add_argument("--output-dir", default="results", help="Output directory (default: results)")
    return p.parse_args()


def safe_info(ticker_obj, attr):
    """Return (value_dict_or_None, error_or_None) for a yahooquery info property."""
    try:
        val = getattr(ticker_obj, attr)
        # yahooquery returns a dict keyed by symbol, or a plain dict/str on error
        if isinstance(val, dict):
            return val, None
        return {"value": val}, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def extract_symbol_info(info_by_attr, ticker):
    """Flatten per-symbol info: report which top-level fields were obtained."""
    obtained = {}
    fields = {}
    for attr, val in info_by_attr.items():
        if val is None:
            obtained[attr] = False
            continue
        # Most yahooquery info dicts are {symbol: {field: value, ...}}
        inner = val.get(ticker) if isinstance(val, dict) else None
        if isinstance(inner, dict):
            # Error payloads look like {"error": "..."} - treat as not obtained
            if set(inner.keys()) == {"error"} or "error" in inner and len(inner) <= 2:
                obtained[attr] = False
                fields[attr] = []
            else:
                obtained[attr] = True
                fields[attr] = sorted(str(k) for k in inner.keys())
        elif isinstance(val, dict) and val:
            # Some endpoints return the fields directly, or {"error": ...}
            if "error" in val and len(val) <= 2:
                obtained[attr] = False
                fields[attr] = []
            else:
                obtained[attr] = True
                fields[attr] = sorted(str(k) for k in val.keys())
        else:
            obtained[attr] = False
            fields[attr] = []
    return obtained, fields


def fetch_one(ticker, period, interval, output_dir):
    from yahooquery import Ticker  # imported here so --help works without deps issues

    result = {
        "ticker": ticker,
        "rows": 0,
        "first_date": None,
        "last_date": None,
        "first_close": None,
        "last_close": None,
        "info_obtained": {},
        "info_fields": {},
        "info_errors": {},
        "error": None,
    }

    try:
        t = Ticker(ticker)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"Ticker construction failed: {type(e).__name__}: {e}"
        return result

    # --- Info ---
    info_by_attr = {}
    for attr in ("summary_detail", "asset_profile", "price"):
        val, err = safe_info(t, attr)
        info_by_attr[attr] = val
        if err:
            result["info_errors"][attr] = err
    obtained, fields = extract_symbol_info(info_by_attr, ticker)
    result["info_obtained"] = obtained
    result["info_fields"] = fields

    # --- History ---
    try:
        hist = t.history(period=period, interval=interval)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"history failed: {type(e).__name__}: {e}"
        return result

    # yahooquery returns a DataFrame on success, or a dict/str with an error
    if hist is None:
        result["error"] = "history returned None"
        return result
    if isinstance(hist, dict):
        result["error"] = f"history returned dict (error payload): {json.dumps(hist, default=str)[:500]}"
        return result
    if isinstance(hist, str):
        result["error"] = f"history returned string (error payload): {hist[:500]}"
        return result

    try:
        import pandas as pd  # noqa: F401
    except Exception as e:  # noqa: BLE001
        result["error"] = f"pandas import failed: {e}"
        return result

    if getattr(hist, "empty", True):
        result["error"] = "history DataFrame was empty"
        return result

    df = hist.reset_index()
    # Normalise column names to strings
    df.columns = [str(c) for c in df.columns]

    # Find date column
    date_col = None
    for cand in ("date", "Date"):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is None:
        date_col = df.columns[0]

    # Find close column (case-insensitive)
    close_col = None
    for c in df.columns:
        if c.lower() == "close":
            close_col = c
            break

    # Sort by date if parseable
    try:
        import pandas as pd

        df["_parsed_date"] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
        df = df.sort_values("_parsed_date")
    except Exception:
        pass

    result["rows"] = int(len(df))
    try:
        result["first_date"] = str(df[date_col].iloc[0])
        result["last_date"] = str(df[date_col].iloc[-1])
    except Exception:
        pass
    if close_col is not None:
        try:
            result["first_close"] = float(df[close_col].iloc[0])
            result["last_close"] = float(df[close_col].iloc[-1])
        except Exception:
            pass

    # Save CSV (drop helper column)
    out_df = df.drop(columns=["_parsed_date"], errors="ignore")
    safe_name = ticker.replace("/", "_")
    csv_path = os.path.join(output_dir, f"{safe_name}.csv")
    out_df.to_csv(csv_path, index=False)
    result["csv_file"] = os.path.basename(csv_path)
    return result


def main():
    args = parse_args()
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    os.makedirs(args.output_dir, exist_ok=True)

    summary = {}
    for ticker in tickers:
        print(f"=== {ticker} ===", flush=True)
        try:
            res = fetch_one(ticker, args.period, args.interval, args.output_dir)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = {
                "ticker": ticker,
                "rows": 0,
                "first_date": None,
                "last_date": None,
                "first_close": None,
                "last_close": None,
                "info_obtained": {},
                "info_fields": {},
                "info_errors": {},
                "error": f"unexpected: {type(e).__name__}: {e}",
            }
        summary[ticker] = res
        print(json.dumps(res, indent=2, default=str), flush=True)

    summary_path = os.path.join(args.output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
