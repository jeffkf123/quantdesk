from __future__ import annotations
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path)

def read_parquet(path: Path) -> pd.DataFrame:
    return pq.read_table(path).to_pandas()
