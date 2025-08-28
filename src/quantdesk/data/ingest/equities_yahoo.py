"""Lightweight equities OHLCV downloader (Yahoo-style).

Notes:
- This module intentionally avoids hard-coding unofficial endpoints.
- Implement the actual HTTP calls respecting the data source ToS, or plug in a paid/free API key source.
- Demonstrates the shape of fetch()/save() without binding to a specific provider.
"""
from __future__ import annotations
from datetime import datetime
from typing import Iterable, List, Dict
from pathlib import Path
import csv

from .base import Ingestor
from quantdesk.config import settings

class YahooLikeEquities(Ingestor):
    def __init__(self, parquet_dir: Path | None = None):
        self.outdir = (parquet_dir or settings.parquet_dir) / "equities"
        self.outdir.mkdir(parents=True, exist_ok=True)

    def fetch(self, symbols: List[str], start: datetime, end: datetime) -> Iterable[Dict]:
        # TODO: implement actual HTTP download and parsing.
        # For now, yield an empty iterator as a placeholder.
        if False:  # pragma: no cover
            yield {}
        return []

    def save(self, records: Iterable[Dict]) -> int:
        # Stub: write CSV to show persistence path; replace with Parquet in real use.
        count = 0
        csv_path = self.outdir / "placeholder.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["symbol","ts","open","high","low","close","volume"])
            w.writeheader()
            for r in records:
                w.writerow(r)
                count += 1
        return count
