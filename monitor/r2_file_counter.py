"""
r2_file_counter.py — Count all R2 objects under scraper / site prefixes.

Copy this file to each website repo's monitor/ directory (do not modify).

Uses paginated list_objects_v2 and counts every object, excluding folder markers
(keys ending with /).

Public API
----------
count_scraper_r2_files(r2_client, bucket, r2_base, path_contains=None)
    -> int  cumulative object count under the scraper prefix

count_scraper_r2_inventory(r2_client, bucket, r2_base, path_contains=None)
    -> (int, int)  (object_count, total_bytes) under the scraper prefix

count_site_r2_files(r2_client, bucket, r2_prefix)
    -> int  cumulative object count under the site prefix (includes monitor/)

count_site_r2_inventory(r2_client, bucket, r2_prefix)
    -> (int, int)  (object_count, total_bytes) under the site prefix

count_r2_inventory_by_type(r2_client, bucket, prefix, path_contains=None)
    -> inventory dict with objects, size_bytes, by_type_objects, by_type_bytes

count_daily_r2_inventory_by_type(r2_client, bucket, r2_base, partition_dt, path_contains=None)
    -> same inventory shape for one partition day (padded/unpadded paths deduped by key)

count_scraper_r2_inventory_by_type(r2_client, bucket, r2_base, path_contains=None)
    -> inventory dict under a scraper prefix

count_site_r2_inventory_by_type(r2_client, bucket, r2_prefix)
    -> inventory dict under the site prefix

count_day_partition_category_inventory(r2_client, bucket, r2_prefix, day)
    -> ({category: {"file_count", "size_bytes"}}, total_files, total_size_bytes)
    for one day partition: {prefix}/year=YYYY/month=MM/day=DD/{category}/...
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from typing import Any

FILE_TYPE_CATEGORIES = ("images", "json", "excel", "csv", "parquet", "other")

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".svg"})
_JSON_EXTENSIONS = frozenset({".json"})
_EXCEL_EXTENSIONS = frozenset({".xlsx", ".xls", ".xlsm"})
_CSV_EXTENSIONS = frozenset({".csv"})
_PARQUET_EXTENSIONS = frozenset({".parquet"})

_PARTITION_DAY_RE = re.compile(r"/year=(\d{4})/month=(\d{1,2})/day=(\d{1,2})/")


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip("/")
    return f"{normalized}/" if normalized else ""


def _empty_type_inventory() -> dict[str, Any]:
    return {
        "objects": 0,
        "size_bytes": 0,
        "by_type_objects": {category: 0 for category in FILE_TYPE_CATEGORIES},
        "by_type_bytes": {category: 0 for category in FILE_TYPE_CATEGORIES},
    }


def _classify_file_type(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    if ext in _IMAGE_EXTENSIONS:
        return "images"
    if ext in _JSON_EXTENSIONS:
        return "json"
    if ext in _EXCEL_EXTENSIONS:
        return "excel"
    if ext in _CSV_EXTENSIONS:
        return "csv"
    if ext in _PARQUET_EXTENSIONS:
        return "parquet"
    return "other"


def _key_matches_partition_day(key: str, partition_dt: datetime) -> bool:
    target = (partition_dt.year, partition_dt.month, partition_dt.day)
    for match in _PARTITION_DAY_RE.finditer(key):
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if (y, m, d) == target:
            return True
    return False


def _daily_listing_prefixes(r2_base: str, partition_dt: datetime) -> list[str]:
    base = r2_base.strip("/")
    year = partition_dt.year
    month = partition_dt.month
    day = partition_dt.day
    candidates = [
        f"{base}/year={year}/month={month:02d}/day={day:02d}/",
        f"{base}/year={year}/month={month}/day={day}/",
    ]
    return list(dict.fromkeys(candidates))


def merge_r2_type_inventories(*inventories: dict[str, Any]) -> dict[str, Any]:
    merged = _empty_type_inventory()
    for inventory in inventories:
        merged["objects"] += inventory["objects"]
        merged["size_bytes"] += inventory["size_bytes"]
        for category in FILE_TYPE_CATEGORIES:
            merged["by_type_objects"][category] += inventory["by_type_objects"].get(category, 0)
            merged["by_type_bytes"][category] += inventory["by_type_bytes"].get(category, 0)
    return merged


def _count_objects(
    r2_client: Any,
    bucket: str,
    prefix: str,
    *,
    path_contains: str | None = None,
    label: str | None = None,
) -> int:
    """Return object count under *prefix*, optionally filtered by substring."""
    listing_prefix = _normalize_prefix(prefix)
    display = label or listing_prefix or "(bucket root)"
    count = 0
    pages = 0

    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        pages += 1
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if path_contains is not None and path_contains not in key:
                continue
            count += 1
        if pages % 20 == 0:
            print(f"  R2 inventory [{display}]: {count} objects listed so far...", file=sys.stderr)

    return count


def _count_objects_and_bytes(
    r2_client: Any,
    bucket: str,
    prefix: str,
    *,
    path_contains: str | None = None,
    label: str | None = None,
) -> tuple[int, int]:
    """Return (object_count, total_bytes) under *prefix*, optionally filtered by substring."""
    listing_prefix = _normalize_prefix(prefix)
    display = label or listing_prefix or "(bucket root)"
    count = 0
    total_bytes = 0
    pages = 0

    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        pages += 1
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if path_contains is not None and path_contains not in key:
                continue
            count += 1
            total_bytes += int(obj.get("Size") or 0)
        if pages % 20 == 0:
            print(
                f"  R2 inventory [{display}]: {count} objects listed so far...",
                file=sys.stderr,
            )

    return count, total_bytes


def _count_inventory_by_type(
    r2_client: Any,
    bucket: str,
    prefix: str,
    *,
    path_contains: str | None = None,
    partition_dt: datetime | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Return typed inventory under *prefix* with optional path/day filters."""
    listing_prefixes: list[str]
    if partition_dt is not None:
        listing_prefixes = _daily_listing_prefixes(prefix, partition_dt)
    else:
        listing_prefixes = [_normalize_prefix(prefix)]

    display = label or prefix.strip("/") or "(bucket root)"
    inventory = _empty_type_inventory()
    seen_keys: set[str] = set()
    pages = 0

    paginator = r2_client.get_paginator("list_objects_v2")
    for listing_prefix in listing_prefixes:
        normalized_prefix = _normalize_prefix(listing_prefix)
        for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix):
            pages += 1
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                if key in seen_keys:
                    continue
                if path_contains is not None and path_contains not in key:
                    continue
                if partition_dt is not None and not _key_matches_partition_day(key, partition_dt):
                    continue

                seen_keys.add(key)
                size = int(obj.get("Size") or 0)
                file_type = _classify_file_type(key)
                inventory["objects"] += 1
                inventory["size_bytes"] += size
                inventory["by_type_objects"][file_type] += 1
                inventory["by_type_bytes"][file_type] += size

            if pages % 20 == 0:
                print(
                    f"  R2 inventory [{display}]: {inventory['objects']} objects listed so far...",
                    file=sys.stderr,
                )

    return inventory


def count_r2_inventory_by_type(
    r2_client: Any,
    bucket: str,
    prefix: str,
    *,
    path_contains: str | None = None,
) -> dict[str, Any]:
    """Count objects and bytes under *prefix*, grouped by file extension category."""
    label = prefix.strip("/") or "(bucket root)"
    if path_contains:
        label = f"{label} *{path_contains}*"
    return _count_inventory_by_type(
        r2_client,
        bucket,
        prefix,
        path_contains=path_contains,
        label=label,
    )


def count_daily_r2_inventory_by_type(
    r2_client: Any,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
    *,
    path_contains: str | None = None,
) -> dict[str, Any]:
    """
    Count one partition day's objects under *r2_base*, grouped by file type.

    Lists both padded and unpadded year/month/day prefixes and dedupes by key.
    """
    label = r2_base.strip("/") or "(bucket root)"
    day_label = partition_dt.strftime("%Y-%m-%d")
    if path_contains:
        label = f"{label} *{path_contains}* ({day_label})"
    else:
        label = f"{label} ({day_label})"
    return _count_inventory_by_type(
        r2_client,
        bucket,
        r2_base,
        path_contains=path_contains,
        partition_dt=partition_dt,
        label=label,
    )


def count_scraper_r2_inventory_by_type(
    r2_client: Any,
    bucket: str,
    r2_base: str,
    *,
    path_contains: str | None = None,
) -> dict[str, Any]:
    """Count objects and bytes under a scraper's R2 prefix, grouped by file type."""
    return count_r2_inventory_by_type(
        r2_client,
        bucket,
        r2_base,
        path_contains=path_contains,
    )


def count_site_r2_inventory_by_type(
    r2_client: Any,
    bucket: str,
    r2_prefix: str,
) -> dict[str, Any]:
    """Count objects and bytes under the site prefix, grouped by file type."""
    return count_r2_inventory_by_type(r2_client, bucket, r2_prefix)


def count_scraper_r2_files(
    r2_client: Any,
    bucket: str,
    r2_base: str,
    *,
    path_contains: str | None = None,
) -> int:
    """
    Count all objects under a scraper's R2 data prefix.

    r2_base:
        Scraper root prefix, e.g. ``boshamlan-data/electronics/``.
        For date-partitioned layouts (category after year/month/day), pass the
        site ``r2_prefix`` and set ``path_contains="/{category}/"``.
    """
    label = r2_base.strip("/")
    if path_contains:
        label = f"{label} *{path_contains}*"
    return _count_objects(
        r2_client,
        bucket,
        r2_base,
        path_contains=path_contains,
        label=label,
    )


def count_scraper_r2_inventory(
    r2_client: Any,
    bucket: str,
    r2_base: str,
    *,
    path_contains: str | None = None,
) -> tuple[int, int]:
    """Count objects and total size in bytes under a scraper's R2 prefix."""
    label = r2_base.strip("/")
    if path_contains:
        label = f"{label} *{path_contains}*"
    return _count_objects_and_bytes(
        r2_client,
        bucket,
        r2_base,
        path_contains=path_contains,
        label=label,
    )


def count_site_r2_files(r2_client: Any, bucket: str, r2_prefix: str) -> int:
    """Count all objects under the site prefix (includes monitor/ artifacts)."""
    return _count_objects(
        r2_client,
        bucket,
        r2_prefix,
        label=r2_prefix.strip("/") or "(site root)",
    )


def count_site_r2_inventory(r2_client: Any, bucket: str, r2_prefix: str) -> tuple[int, int]:
    """Count objects and total size in bytes under the site prefix."""
    return _count_objects_and_bytes(
        r2_client,
        bucket,
        r2_prefix,
        label=r2_prefix.strip("/") or "(site root)",
    )


def count_date_partitioned_category_objects(
    r2_client: Any,
    bucket: str,
    r2_prefix: str,
) -> tuple[dict[str, int], int]:
    """
    Count objects by category for keys like:
    {prefix}/year=YYYY/month=MM/day=DD/{category}/...

    Returns:
        ({category: object_count}, total_object_count_under_prefix)
    """
    listing_prefix = _normalize_prefix(r2_prefix)
    category_counts: dict[str, int] = {}
    total = 0
    pages = 0

    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        pages += 1
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue

            total += 1

            if not key.startswith(listing_prefix):
                continue

            rel = key[len(listing_prefix) :]
            parts = rel.split("/")
            if len(parts) < 4:
                continue

            # Expected: year=.../month=.../day=.../{category}/...
            if not (
                parts[0].startswith("year=")
                and parts[1].startswith("month=")
                and parts[2].startswith("day=")
            ):
                continue

            category = parts[3]
            if not category:
                continue
            category_counts[category] = category_counts.get(category, 0) + 1

        if pages % 20 == 0:
            print(
                f"  R2 inventory [{listing_prefix or '(bucket root)'}]: "
                f"{total} objects listed so far...",
                file=sys.stderr,
            )

    return category_counts, total


def count_date_partitioned_category_inventory(
    r2_client: Any,
    bucket: str,
    r2_prefix: str,
) -> tuple[dict[str, dict[str, int]], int, int]:
    """
    Count objects and bytes by category for keys like:
    {prefix}/year=YYYY/month=MM/day=DD/{category}/...

    Returns:
        ({category: {"file_count": int, "size_bytes": int}}, total_files, total_size_bytes)
    """
    listing_prefix = _normalize_prefix(r2_prefix)
    category_inventory: dict[str, dict[str, int]] = {}
    total_files = 0
    total_size_bytes = 0
    pages = 0

    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        pages += 1
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue

            size = int(obj.get("Size") or 0)
            total_files += 1
            total_size_bytes += size

            if not key.startswith(listing_prefix):
                continue

            rel = key[len(listing_prefix) :]
            parts = rel.split("/")
            if len(parts) < 4:
                continue

            if not (
                parts[0].startswith("year=")
                and parts[1].startswith("month=")
                and parts[2].startswith("day=")
            ):
                continue

            category = parts[3]
            if not category:
                continue
            slot = category_inventory.setdefault(category, {"file_count": 0, "size_bytes": 0})
            slot["file_count"] += 1
            slot["size_bytes"] += size

        if pages % 20 == 0:
            print(
                f"  R2 inventory [{listing_prefix or '(bucket root)'}]: "
                f"{total_files} objects listed so far...",
                file=sys.stderr,
            )

    return category_inventory, total_files, total_size_bytes


def day_partition_prefix(r2_prefix: str, day: datetime) -> str:
    """Prefix for a single date partition: {prefix}/year=YYYY/month=MM/day=DD/"""
    return (
        f"{r2_prefix.strip('/')}/year={day.strftime('%Y')}/month={day.strftime('%m')}"
        f"/day={day.strftime('%d')}/"
    )


def count_day_partition_category_inventory(
    r2_client: Any,
    bucket: str,
    r2_prefix: str,
    day: datetime,
) -> tuple[dict[str, dict[str, int]], int, int]:
    """
    Count objects and bytes by category under one day partition:
    {prefix}/year=YYYY/month=MM/day=DD/{category}/...

    Returns:
        ({category: {"file_count": int, "size_bytes": int}}, total_files, total_size_bytes)
    """
    listing_prefix = _normalize_prefix(day_partition_prefix(r2_prefix, day))
    category_inventory: dict[str, dict[str, int]] = {}
    total_files = 0
    total_size_bytes = 0
    pages = 0

    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        pages += 1
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue

            size = int(obj.get("Size") or 0)
            total_files += 1
            total_size_bytes += size

            if not key.startswith(listing_prefix):
                continue

            rel = key[len(listing_prefix) :]
            category = rel.split("/", 1)[0]
            if not category:
                continue
            slot = category_inventory.setdefault(category, {"file_count": 0, "size_bytes": 0})
            slot["file_count"] += 1
            slot["size_bytes"] += size

        if pages % 20 == 0:
            print(
                f"  R2 daily inventory [{listing_prefix}]: "
                f"{total_files} objects listed so far...",
                file=sys.stderr,
            )

    return category_inventory, total_files, total_size_bytes
