#!/usr/bin/env python3
"""NSE UDiFF Bhavcopy Downloader & Parser."""

import csv
import io
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Set

import requests

UDIFF_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)

DEFAULT_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports",
}


def safe_float(val: str, default: float = 0.0) -> float:
    try:
        cleaned = str(val).strip()
        return float(cleaned) if cleaned else default
    except (ValueError, AttributeError):
        return default


def safe_int(val: str, default: int = 0) -> int:
    try:
        cleaned = str(val).strip()
        return int(float(cleaned)) if cleaned else default
    except (ValueError, AttributeError):
        return default


def download_bhavcopy_zip(target_date: datetime, session: Optional[requests.Session] = None, timeout: int = 20) -> Optional[bytes]:
    """Fetch the zipped UDiFF Bhavcopy for a given date from nsearchives.nseindia.com."""
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.headers.update(HEADERS)
        try:
            session.get("https://www.nseindia.com", timeout=10)
        except requests.RequestException:
            pass

    url = UDIFF_URL_TEMPLATE.format(yyyymmdd=target_date.strftime("%Y%m%d"))
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.content[:2] == b"PK":
            return resp.content
    except requests.RequestException:
        return None
    return None


def parse_bhavcopy_zip(zip_bytes: bytes, allowed_series: Optional[Set[str]] = None) -> List[Dict]:
    """Extract and normalize UDiFF Bhavcopy CSV rows into clean dicts."""
    if allowed_series is None:
        allowed_series = DEFAULT_SERIES

    records: List[Dict] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("No CSV file found inside the Bhavcopy ZIP archive.")

        with zf.open(csv_names[0]) as raw_file:
            text_stream = io.TextIOWrapper(raw_file, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text_stream)
            if reader.fieldnames:
                reader.fieldnames = [h.strip() for h in reader.fieldnames]

            for raw_row in reader:
                row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items() if k}
                series = row.get("SctySrs", "")
                if allowed_series and series not in allowed_series:
                    continue

                symbol = row.get("TckrSymb", "")
                if not symbol:
                    continue

                opn = safe_float(row.get("OpnPric", ""))
                high = safe_float(row.get("HghPric", ""))
                low = safe_float(row.get("LwPric", ""))
                close = safe_float(row.get("ClsPric", ""))
                prev_close = safe_float(row.get("PrvsClsgPric", ""))
                volume = safe_int(row.get("TtlTradgVol", ""))
                turnover_inr = safe_float(row.get("TtlTrfVal", ""))

                records.append({
                    "date": row.get("TradDt", ""),
                    "symbol": symbol,
                    "series": series,
                    "open": round(opn, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "prev_close": round(prev_close, 2),
                    "volume": volume,
                    "turnover_cr": round(turnover_inr / 1e7, 4),
                })

    return records
