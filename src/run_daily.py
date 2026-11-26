#!/usr/bin/env python3
"""Daily Orchestrator: Download Bhavcopy -> Update History -> Scan -> Email Alert."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd
import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from email_alert import send_gmail_alert
from fetch_nse_bhavcopy import HEADERS, download_bhavcopy_zip, parse_bhavcopy_zip
from scanner import load_fundamentals, scan_market

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "data" / "nse_history.csv.gz"
SCREENER_PATH = ROOT / "data" / "screener_fundamentals.csv"
REPORT_PATH = ROOT / "reports" / "latest_scan.json"
CONFIG_PATH = ROOT / "config.yaml"


def load_history() -> pd.DataFrame:
    if HISTORY_PATH.exists():
        return pd.read_csv(HISTORY_PATH)
    return pd.DataFrame(columns=["date", "symbol", "series", "open", "high", "low", "close", "prev_close", "volume", "turnover_cr"])


def fetch_days(days_back: int, allowed_series: set) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except requests.RequestException:
        pass

    today = datetime.now()
    all_rows: List[dict] = []
    for offset in range(days_back + 1):
        dt = today - timedelta(days=offset)
        if dt.weekday() >= 5:
            continue
        zip_bytes = download_bhavcopy_zip(dt, session=session)
        if zip_bytes:
            rows = parse_bhavcopy_zip(zip_bytes, allowed_series=allowed_series)
            all_rows.extend(rows)
            print(f"Fetched {len(rows)} rows for {dt.strftime('%Y-%m-%d')}")
            if days_back <= 5:
                break
    return pd.DataFrame(all_rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-days", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    allowed_series = set(cfg["universe"]["allowed_series"])
    days_to_fetch = args.backfill_days if args.backfill_days > 0 else 5

    history_df = load_history()
    new_df = fetch_days(days_to_fetch, allowed_series)

    if not new_df.empty:
        combined = pd.concat([history_df, new_df], ignore_index=True)
        combined["date"] = pd.to_datetime(combined["date"]).dt.strftime("%Y-%m-%d")
        combined = combined.drop_duplicates(subset=["symbol", "date"], keep="last")
        # Keep rolling 260 trading dates (~13 months) to stay lightweight in git
        keep_dates = sorted(combined["date"].unique())[-260:]
        combined = combined[combined["date"].isin(keep_dates)].sort_values(["date", "symbol"])
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(HISTORY_PATH, index=False, compression="gzip")
        history_df = combined
        print(f"Updated {HISTORY_PATH} ({len(history_df)} rows across {len(keep_dates)} dates)")

    capital = float(os.environ.get("PORTFOLIO_CAPITAL") or cfg["risk"]["portfolio_capital_inr"])
    fundamentals = load_fundamentals(SCREENER_PATH, cfg)
    result = scan_market(history_df, fundamentals, cfg, portfolio_capital=capital)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Scan complete: {len(result['breakouts'])} breakouts, {len(result['forming'])} forming.")
    if not args.dry_run:
        send_gmail_alert(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
