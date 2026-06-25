"""
ads_counter.py — Count unique ads for one scraper / listing day.

Copy this file to each website repo's monitor/ directory (do not modify).

Count priority
--------------
1. Unique listing IDs from Excel (deduped across all sheets/files)
2. total_listings / total_ads / listings_count from JSON summary in json-files/
3. Sum of Excel data rows (excluding Info / No Data sheets)

Public API
----------
count_scraper_ads(r2_client, bucket, r2_base, partition_dt, excel_downloads)
    -> {"unique_ads": int, "total_rows": int, "ads_source": str}

ads_source values: "excel_ids" | "json_summary" | "excel_rows" | "none"
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

import pandas as pd

_ID_COLUMNS: frozenset[str] = frozenset(
    {"id", "listing id", "listing_id", "user_adv_id", "user adv id", "ad_id", "ad id"}
)
_SKIP_SHEETS: frozenset[str] = frozenset({"info", "no data"})
_JSON_COUNT_KEYS: tuple[str, ...] = ("total_listings", "total_ads", "listings_count")


# ---------------------------------------------------------------------------
# R2 helpers
# ---------------------------------------------------------------------------


def _list_r2_keys(r2_client: Any, bucket: str, prefix: str) -> list[str]:
    """Return all object keys under *prefix* (handles pagination)."""
    keys: list[str] = []
    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _download_bytes(r2_client: Any, bucket: str, key: str) -> bytes:
    resp = r2_client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


# ---------------------------------------------------------------------------
# Excel helpers
# ---------------------------------------------------------------------------


def _read_excel_ids(raw_bytes: bytes) -> tuple[set[str], int]:
    """Return (unique_ids_set, total_data_rows) for one Excel file.

    Scans every non-skip sheet for a standard ID column.  If found, collects
    all non-null values.  Rows are counted across all data sheets regardless.
    """
    ids: set[str] = set()
    total_rows = 0
    try:
        xl = pd.ExcelFile(io.BytesIO(raw_bytes), engine="openpyxl")
        for sheet in xl.sheet_names:
            if sheet.strip().lower() in _SKIP_SHEETS:
                continue
            df = xl.parse(sheet)
            if df.empty:
                continue
            col_map = {str(c).strip().lower(): c for c in df.columns}
            id_col = next((col_map[k] for k in _ID_COLUMNS if k in col_map), None)
            if id_col is not None:
                ids.update(str(v) for v in df[id_col].dropna())
            total_rows += len(df)
    except Exception:
        pass
    return ids, total_rows


# ---------------------------------------------------------------------------
# JSON summary helpers
# ---------------------------------------------------------------------------


def _json_count_from_data(data: dict[str, Any]) -> int | None:
    """Extract a count integer from a parsed JSON summary dict."""
    for k in _JSON_COUNT_KEYS:
        v = data.get(k)
        if isinstance(v, (int, float)) and v >= 0:
            return int(v)
    # Sum subcategories if present
    subs = data.get("subcategories")
    if isinstance(subs, list) and subs:
        total = 0
        found = False
        for sub in subs:
            for k in _JSON_COUNT_KEYS:
                v = sub.get(k)
                if isinstance(v, (int, float)):
                    total += int(v)
                    found = True
                    break
        if found:
            return total
    return None


def _fetch_json_summary_count(r2_client: Any, bucket: str, json_prefix: str) -> int | None:
    """Return first usable count found in any .json file under *json_prefix*."""
    try:
        keys = _list_r2_keys(r2_client, bucket, json_prefix)
    except Exception:
        return None
    for key in keys:
        if not key.lower().endswith(".json"):
            continue
        try:
            raw = _download_bytes(r2_client, bucket, key)
            data = json.loads(raw)
        except Exception:
            continue
        count = _json_count_from_data(data)
        if count is not None:
            return count
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def count_scraper_ads(
    r2_client: Any,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
    excel_downloads: list[tuple[str, bytes]],
) -> dict[str, Any]:
    """Count unique ads for one scraper / listing day.

    Parameters
    ----------
    r2_client:
        boto3 S3 client (or R2-compatible).
    bucket:
        R2 bucket name.
    r2_base:
        Day-specific base path **without** the excel-files / json-files suffix,
        e.g. ``"{r2_prefix}/year=YYYY/month=MM/day=DD/{category}/"``.
        JSON summaries are expected at ``{r2_base}json-files/``.
    partition_dt:
        Listing date being inspected (used only when r2_base is not yet
        day-specific; pass the day datetime for future extensibility).
    excel_downloads:
        List of ``(r2_key, raw_bytes)`` pairs already downloaded for this
        scraper.  Pass ``[]`` if no Excel files were found so the function
        can still try the JSON summary path.
    """
    all_ids: set[str] = set()
    total_rows = 0
    has_id_col = False

    for _key, raw in excel_downloads:
        ids, rows = _read_excel_ids(raw)
        if ids:
            has_id_col = True
            all_ids.update(ids)
        total_rows += rows

    # 1. Unique IDs from Excel
    if has_id_col and all_ids:
        return {
            "unique_ads": len(all_ids),
            "total_rows": total_rows,
            "ads_source": "excel_ids",
        }

    # 2. JSON summary
    json_prefix = r2_base.rstrip("/") + "/json-files/"
    json_count = _fetch_json_summary_count(r2_client, bucket, json_prefix)
    if json_count is not None:
        return {
            "unique_ads": json_count,
            "total_rows": total_rows,
            "ads_source": "json_summary",
        }

    # 3. Excel row-count fallback
    if total_rows > 0:
        return {
            "unique_ads": total_rows,
            "total_rows": total_rows,
            "ads_source": "excel_rows",
        }

    return {
        "unique_ads": 0,
        "total_rows": 0,
        "ads_source": "none",
    }
