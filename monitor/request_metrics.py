"""
request_metrics.py — Parse HTTP request metrics from JSON summaries.

Copy this file to each website repo's monitor/ directory (do not modify).

Reads request_metrics (or stats / top-level aliases) from json-files/*.json
under each scraper partition day.

Public API
----------
count_scraper_request_metrics(r2_client, bucket, r2_base, partition_dt)
    -> per-scraper HTTP metrics + metrics_source

aggregate_site_request_metrics(all_results)
    -> site-level requests_total, requests_failed, error_rate_pct, requests_per_min

build_run_error_summary(all_results, alerts)
    -> error_summary block for report.json root
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

_TOTAL_KEYS: tuple[str, ...] = (
    "requests_total",
    "total_http_requests",
    "scrape_do_requests",
    "request_count",
)
_FAILED_KEYS: tuple[str, ...] = (
    "requests_failed",
    "failed_requests",
    "http_errors",
    "errors_count",
)
_DURATION_KEYS: tuple[str, ...] = (
    "duration_sec",
    "elapsed_seconds",
    "scrape_duration_sec",
)
_RPM_KEYS: tuple[str, ...] = (
    "requests_per_min",
    "req_per_min",
    "avg_requests_per_min",
)


def _list_r2_keys(r2_client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = r2_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _download_bytes(r2_client: Any, bucket: str, key: str) -> bytes:
    resp = r2_client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def _first_numeric(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    return None


def _metric_sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for block in (data.get("request_metrics"), data.get("stats")):
        if isinstance(block, dict):
            sources.append(block)
    sources.append(data)
    return sources


def _extract_metrics_block(data: dict[str, Any]) -> dict[str, Any] | None:
    for source in _metric_sources(data):
        total = _first_numeric(source, _TOTAL_KEYS)
        if total is None:
            continue

        failed = int(_first_numeric(source, _FAILED_KEYS) or 0)
        duration = _first_numeric(source, _DURATION_KEYS)
        rpm = _first_numeric(source, _RPM_KEYS)
        if rpm is None and duration and duration > 0:
            rpm = round(total / (duration / 60), 2)

        error_rate = round(failed / total * 100, 2) if total > 0 else 0.0
        failed_items = source.get("failed_items")
        if not isinstance(failed_items, list):
            failed_items = []

        result: dict[str, Any] = {
            "requests_total": int(total),
            "requests_failed": failed,
            "error_rate_pct": error_rate,
            "duration_sec": int(duration) if duration is not None else None,
            "requests_per_min": rpm,
            "failed_items": failed_items,
        }
        cache_hits = source.get("cache_hits")
        if isinstance(cache_hits, (int, float)):
            result["cache_hits"] = int(cache_hits)
        return result
    return None


def _format_failed_items_summary(failed_items: list[Any]) -> str | None:
    if not failed_items:
        return None

    parts: list[str] = []
    for item in failed_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("slug") or "unknown"
        errors = item.get("errors", 1)
        detail = item.get("detail")
        suffix = f" ({detail})" if detail else ""
        parts.append(f"{name}: {errors} error(s){suffix}")

    return "; ".join(parts) if parts else None


def _fetch_json_request_metrics(r2_client: Any, bucket: str, json_prefix: str) -> dict[str, Any] | None:
    try:
        keys = _list_r2_keys(r2_client, bucket, json_prefix)
    except Exception:
        return None

    merged: dict[str, Any] | None = None
    for key in keys:
        if not key.lower().endswith(".json"):
            continue
        try:
            raw = _download_bytes(r2_client, bucket, key)
            data = json.loads(raw)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        block = _extract_metrics_block(data)
        if block is None:
            continue

        if merged is None:
            merged = {
                "requests_total": 0,
                "requests_failed": 0,
                "duration_sec": 0,
                "failed_items": [],
            }

        merged["requests_total"] += block["requests_total"]
        merged["requests_failed"] += block["requests_failed"]
        if block.get("duration_sec"):
            merged["duration_sec"] = max(merged["duration_sec"], block["duration_sec"])
        merged["failed_items"].extend(block.get("failed_items", []))

    if merged is None:
        return None

    total = merged["requests_total"]
    failed = merged["requests_failed"]
    duration = merged["duration_sec"] or None
    rpm = round(total / (duration / 60), 2) if duration and duration > 0 else None
    merged["error_rate_pct"] = round(failed / total * 100, 2) if total > 0 else 0.0
    merged["requests_per_min"] = rpm
    return merged


def count_scraper_request_metrics(
    r2_client: Any,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
) -> dict[str, Any]:
    """Load HTTP metrics for one scraper / partition day from json-files/."""
    del partition_dt  # reserved for callers passing listing/partition date

    json_prefix = r2_base.rstrip("/") + "/json-files/"
    metrics = _fetch_json_request_metrics(r2_client, bucket, json_prefix)
    if metrics is None:
        return {
            "requests_total": None,
            "requests_failed": None,
            "error_rate_pct": None,
            "requests_per_min": None,
            "duration_sec": None,
            "metrics_source": "none",
        }

    failed_items = metrics.pop("failed_items", [])
    summary = _format_failed_items_summary(failed_items)
    result = {
        **metrics,
        "metrics_source": "json_summary",
    }
    if summary:
        result["failed_items_summary"] = summary
    return result


def aggregate_site_request_metrics(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-scraper HTTP metrics to site totals."""
    total_requests = 0
    total_failed = 0
    total_duration = 0
    has_metrics = False

    for row in all_results:
        req_total = row.get("requests_total")
        if req_total is None:
            continue
        has_metrics = True
        total_requests += int(req_total)
        total_failed += int(row.get("requests_failed") or 0)
        duration = row.get("duration_sec")
        if duration:
            total_duration += int(duration)

    if not has_metrics:
        return {
            "requests_total": None,
            "requests_failed": None,
            "error_rate_pct": None,
            "requests_per_min": None,
        }

    error_rate = round(total_failed / total_requests * 100, 2) if total_requests > 0 else 0.0
    rpm = (
        round(total_requests / (total_duration / 60), 2)
        if total_duration > 0
        else None
    )
    return {
        "requests_total": total_requests,
        "requests_failed": total_failed,
        "error_rate_pct": error_rate,
        "requests_per_min": rpm,
    }


def _failure_reason(scraper_result: dict[str, Any]) -> str:
    if scraper_result.get("files_found", 0) == 0:
        return "no Excel files"

    for file_result in scraper_result.get("files", []):
        for chk in file_result.get("checks", []):
            if not chk.get("passed"):
                return f"{chk.get('check', 'check_failed')}: {chk.get('detail', '')}".strip(": ")
        if file_result.get("error"):
            return str(file_result["error"])

    if scraper_result.get("monitor_status") == "failed":
        return "monitor validation failed"
    return "unknown failure"


def build_run_error_summary(
    all_results: list[dict[str, Any]],
    alerts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build site-level error_summary for report.json."""
    active = [
        row
        for row in all_results
        if row.get("monitor_status") != "skipped_off_site"
    ]
    failed_scrapers: list[dict[str, Any]] = []
    scrapers_failed = 0
    scrapers_passed = 0

    for row in active:
        if row.get("all_passed") and row.get("monitor_status") == "passed":
            scrapers_passed += 1
            continue

        scrapers_failed += 1
        failed_scrapers.append(
            {
                "scraper": row.get("scraper"),
                "reason": _failure_reason(row),
                "requests_failed": row.get("requests_failed"),
            }
        )

    scrapers_total = len(active)
    validation_fail_rate = (
        round(scrapers_failed / scrapers_total * 100, 2) if scrapers_total > 0 else 0.0
    )

    http = aggregate_site_request_metrics(all_results)
    summary: dict[str, Any] = {
        "scrapers_total": scrapers_total,
        "scrapers_failed": scrapers_failed,
        "scrapers_passed": scrapers_passed,
        "validation_fail_rate_pct": validation_fail_rate,
        "failed_scrapers": failed_scrapers,
        "http": {
            "requests_total": http.get("requests_total"),
            "requests_failed": http.get("requests_failed"),
            "error_rate_pct": http.get("error_rate_pct"),
            "requests_per_min": http.get("requests_per_min"),
        },
    }

    for alert in alerts or []:
        if not isinstance(alert, dict):
            continue
        failed_scrapers.append(
            {
                "scraper": alert.get("scraper"),
                "reason": alert.get("reason", "alert"),
                "requests_failed": alert.get("requests_failed"),
            }
        )

    return summary
