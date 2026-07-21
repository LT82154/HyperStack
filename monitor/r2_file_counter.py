"""
r2_file_counter.py — Count all R2 objects under scraper / site prefixes.

Copy this file to each website repo's monitor/ directory (do not modify).

Uses paginated list_objects_v2 and counts every object, excluding folder markers
(keys ending with /).

Public API
----------
count_scraper_r2_files(r2_client, bucket, r2_base, path_contains=None)
    -> int  cumulative object count under the scraper prefix

count_site_r2_files(r2_client, bucket, r2_prefix)
    -> int  cumulative object count under the site prefix (includes monitor/)
"""

from __future__ import annotations

import sys
from typing import Any


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip("/")
    return f"{normalized}/" if normalized else ""


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


def count_site_r2_files(r2_client: Any, bucket: str, r2_prefix: str) -> int:
    """Count all objects under the site prefix (includes monitor/ artifacts)."""
    return _count_objects(
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
