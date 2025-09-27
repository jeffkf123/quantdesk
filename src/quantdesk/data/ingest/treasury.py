# Treasury Par Yield Curve Ingestor

from __future__ import annotations

import argparse
import datetime as dt
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import httpx
import pandas as pd

TREASURY_XML_BASE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
)

# Map XML field names -> tenor in years (includes newer short tenors)
BC_TO_TENOR_YRS: Dict[str, float] = {
    "BC_1MONTH": 1.0 / 12.0,
    "BC_1_5MONTH": 1.5 / 12.0,  # added 2025-02-18
    "BC_2MONTH": 2.0 / 12.0,
    "BC_3MONTH": 3.0 / 12.0,
    "BC_4MONTH": 4.0 / 12.0,    # added 2022-10-19
    "BC_6MONTH": 6.0 / 12.0,
    "BC_1YEAR": 1.0,
    "BC_2YEAR": 2.0,
    "BC_3YEAR": 3.0,
    "BC_5YEAR": 5.0,
    "BC_7YEAR": 7.0,
    "BC_10YEAR": 10.0,
    "BC_20YEAR": 20.0,
    "BC_30YEAR": 30.0,
}

@dataclass
class FetchResult:
    month: str  # YYYYMM
    url: str
    n_rows: int

def month_range(start: dt.date, end: dt.date) -> List[str]:
    """Inclusive list of YYYYMM months between dates."""
    if end < start:
        raise ValueError("end < start")
    res: List[str] = []
    y, m = start.year, start.month
    while (y < end.year) or (y == end.year and m <= end.month):
        res.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return res

def _parse_month_xml(xml_text: str) -> List[Dict]:
    """Parse one month of Treasury XML into per-date records (yield fields may be missing)."""
    root = ET.fromstring(xml_text)

    def local(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    entries: List[Dict] = []
    # Each <entry> contains <content><m:properties>...</m:properties></content>
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        content = entry.find("{http://www.w3.org/2005/Atom}content")
        if content is None:
            continue
        props = None
        for child in content.iter():
            if local(child.tag) == "properties":
                props = child
                break
        if props is None:
            continue

        record: Dict[str, Optional[float]] = {}
        for field in props:
            name = local(field.tag)  # NEW_DATE, BC_10YEAR, ...
            text = (field.text or "").strip()
            if not text:
                record[name] = None
                continue
            if name == "NEW_DATE":
                # Normalize to date
                try:
                    record["date"] = dt.datetime.fromisoformat(text.replace("Z", "")).date()
                except Exception:
                    record["date_raw"] = text
                continue
            try:
                record[name] = float(text)  # yields are in percent
            except Exception:
                record[name] = None

        if "date" in record:
            entries.append(record)

    entries.sort(key=lambda r: r.get("date"))
    return entries

def _month_endpoint(yyyymm: str) -> str:
    return (
        f"{TREASURY_XML_BASE}?data=daily_treasury_yield_curve&field_tdr_date_value_month={yyyymm}"
    )

def fetch_month(client: httpx.Client, yyyymm: str) -> Tuple[List[Dict], str]:
    url = _month_endpoint(yyyymm)
    r = client.get(url, timeout=20.0)
    r.raise_for_status()
    return _parse_month_xml(r.text), url

def fetch_range(
    start: dt.date,
    end: dt.date,
    client: Optional[httpx.Client] = None,
) -> Tuple[pd.DataFrame, List[FetchResult]]:
    """Fetch [start, end] inclusive; return tidy DataFrame + fetch provenance."""
    months = month_range(start, end)
    close_client = False
    if client is None:
        client = httpx.Client(headers={"user-agent": "quantdesk/0.1 treas-ingestor"})
        close_client = True

    results: List[FetchResult] = []
    all_rows: List[Dict] = []
    try:
        for yyyymm in months:
            rows, url = fetch_month(client, yyyymm)
            results.append(FetchResult(month=yyyymm, url=url, n_rows=len(rows)))
            for rec in rows:
                d = rec.get("date")
                if not isinstance(d, dt.date):
                    continue
                if d < start or d > end:
                    continue
                # Emit row per available tenor
                for bc, tenor in BC_TO_TENOR_YRS.items():
                    val = rec.get(bc)
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        continue
                    par_pct = float(val)  # percent per annum
                    cc_rate = math.log1p(par_pct / 100.0)  # convenience approx
                    all_rows.append(
                        {
                            "date": d,
                            "bc_code": bc,
                            "tenor_years": tenor,
                            "par_yield_pct": par_pct,
                            "cc_rate_approx": cc_rate,
                            "source": "treasury_xml",
                        }
                    )
    finally:
        if close_client:
            client.close()

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df.sort_values(["date", "tenor_years"]).reset_index(drop=True)
    return df, results

def write_parquet(df: pd.DataFrame, out_path: str) -> None:
    if df.empty:
        raise ValueError("No data to write.")
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)

def write_partitioned(df: pd.DataFrame, out_dir: str) -> list[str]:
    """Write one Parquet per day under out_dir/YYYY/MM/DD.parquet."""
    if df.empty:
        raise ValueError("No data to write.")
    paths: list[str] = []
    for date, g in df.groupby("date"):
        p = os.path.join(out_dir, f"{date.year:04d}", f"{date.month:02d}", f"{date.day:02d}.parquet")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        g.to_parquet(p, index=False)
        paths.append(p)
    return paths

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingest official U.S. Treasury daily par yield curve (CMT)."
    )
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD")

    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--out", help="Write a single Parquet file to this path")
    out.add_argument("--out-dir", help="Write partitioned daily Parquet files under this directory")

    p.add_argument(
        "--show-summary",
        action="store_true",
        help="Print a brief summary and fetch log",
    )
    return p.parse_args(argv)

def main(argv: Optional[list[str]] = None) -> None:
    ns = _parse_args(argv)
    start = dt.date.fromisoformat(ns.start)
    end = dt.date.fromisoformat(ns.end)

    df, fetches = fetch_range(start, end)

    if ns.out:
        write_parquet(df, ns.out)
    else:
        write_partitioned(df, ns.out_dir)

    if ns.show_summary:
        print(f"Fetched rows: {len(df):,}")
        if not df.empty:
            print("Sample:")
            print(df.head(12).to_string(index=False))
        print("\nFetch log (first few):")
        for f in fetches[:5]:
            print(f" {f.month}: {f.n_rows} rows from {f.url}")

if __name__ == "__main__":
    main()
