#!/usr/bin/env python3
"""
R2 Excel schema monitor for sheeel.com scrapers (all repos, single HyperStack runner).

Validates .xlsx files uploaded to Cloudflare R2 against websites-config.yml excel_schema.
Reports and rolling stats are written back to R2 only — never to the repo.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import pandas as pd
import yaml
from botocore.config import Config
from botocore.exceptions import ClientError
from openpyxl import load_workbook

MONITOR_SUBPATH = "monitor"
DEFAULT_R2_PREFIX = os.environ.get("R2_PREFIX", "sheeel_data")
CONFIG_R2_KEY = os.environ.get(
    "WEBSITES_CONFIG_R2_KEY",
    f"{DEFAULT_R2_PREFIX}/{MONITOR_SUBPATH}/websites-config.yml",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate sheeel.com Excel files in R2")
    parser.add_argument(
        "--date",
        help="End date YYYY-MM-DD (default: yesterday UTC)",
    )
    parser.add_argument(
        "--days-lookback",
        type=int,
        default=1,
        help="Number of days to inspect ending at --date (default: 1)",
    )
    parser.add_argument(
        "--update-stats",
        action="store_true",
        help="Merge observations into monitor_stats.yml in R2",
    )
    parser.add_argument(
        "--quality",
        action="store_true",
        help="Run pandas data-quality checks on listing sheets",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit 1 if any check failed",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Local websites-config.yml path (default: load from R2 sheeel_data/monitor/)",
    )
    return parser.parse_args()


def load_config_local(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config_from_r2(client: Any, bucket: str, key: str) -> dict[str, Any]:
    try:
        raw = download_bytes(client, bucket, key)
        return yaml.safe_load(raw) or {}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            raise FileNotFoundError(f"Config not found at r2://{bucket}/{key}") from exc
        raise


def resolve_config(
    client: Any, bucket: str, args: argparse.Namespace
) -> tuple[dict[str, Any], str]:
    local_path = os.environ.get("WEBSITES_CONFIG") or args.config
    if local_path:
        return load_config_local(local_path), f"local:{local_path}"

    source = f"r2://{bucket}/{CONFIG_R2_KEY}"
    print(f"Loading config from {source}")
    return load_config_from_r2(client, bucket, CONFIG_R2_KEY), source


def flatten_scrapers(config: dict[str, Any]) -> list[dict[str, Any]]:
    scrapers: list[dict[str, Any]] = []
    for project in config.get("projects", []):
        repo = project.get("repo", "")
        for scraper in project.get("scrapers", []):
            scrapers.append({**scraper, "repo": repo})
    return scrapers


def schema_by_scraper(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for entry in config.get("excel_schema", []):
        mapping[entry["scraper"]] = entry
    return mapping


def build_r2_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=os.environ["CF_R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def strip_bucket_placeholder(r2_path: str) -> str:
    path = r2_path.strip("/")
    path = re.sub(r"^\{r2_bucket\}/", "", path)
    path = re.sub(r"^\{bucket\}/", "", path)
    return path


def partition_prefix(base_path: str, day: datetime) -> str:
    return (
        f"{base_path}/year={day.strftime('%Y')}/month={day.strftime('%m')}"
        f"/day={day.strftime('%d')}/excel-files/"
    )


def iter_dates(end_date: datetime, days: int) -> list[datetime]:
    return [end_date - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def list_xlsx_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".xlsx"):
                keys.append(key)
    return keys


def download_bytes(client: Any, bucket: str, key: str) -> bytes:
    buf = io.BytesIO()
    client.download_fileobj(bucket, key, buf)
    return buf.getvalue()


def inspect_workbook(data: bytes) -> dict[str, dict[str, Any]]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets: dict[str, dict[str, Any]] = {}
    try:
        for name in wb.sheetnames:
            ws = wb[name]
            rows = ws.iter_rows(min_row=1, max_row=1, values_only=True)
            header_row = next(rows, None)
            headers = [str(c).strip() if c is not None else "" for c in (header_row or [])]
            headers = [h for h in headers if h]
            row_count = max(ws.max_row - 1, 0) if ws.max_row else 0
            sheets[name] = {"headers": headers, "row_count": row_count}
    finally:
        wb.close()
    return sheets


def is_pattern_name(name: str) -> bool:
    return name.startswith("{") and name.endswith("}")


def match_sheet_rules(
    sheet_rules: list[dict[str, Any]], actual_sheets: set[str]
) -> list[tuple[dict[str, Any], str | None]]:
    """Return (rule, matched_sheet_name) pairs to validate."""
    matched: list[tuple[dict[str, Any], str | None]] = []
    used_sheets: set[str] = set()

    for rule in sheet_rules:
        expected = rule["name"]
        if is_pattern_name(expected):
            pattern_label = expected.strip("{}")
            candidates = [
                s
                for s in actual_sheets
                if s not in used_sheets and s != "ALL_PRODUCTS"
            ]
            if pattern_label == "subcategory":
                for sheet in sorted(candidates):
                    matched.append((rule, sheet))
                    used_sheets.add(sheet)
            continue
        if expected in actual_sheets:
            matched.append((rule, expected))
            used_sheets.add(expected)
        else:
            matched.append((rule, None))

    return matched


def check_result(name: str, passed: bool, detail: str, severity: str = "critical") -> dict[str, Any]:
    return {
        "check": name,
        "passed": passed,
        "detail": detail,
        "severity": severity,
    }


def validate_file(
    *,
    key: str,
    size_kb: float,
    schema: dict[str, Any],
    sheet_data: dict[str, dict[str, Any]],
    inspect_date: datetime,
) -> dict[str, Any]:
    filename = os.path.basename(key)
    checks: list[dict[str, Any]] = []
    actual_sheets = set(sheet_data.keys())

    pattern = schema.get("excel_file_pattern", "*.xlsx")
    checks.append(
        check_result(
            "filename_pattern",
            fnmatch.fnmatch(filename, pattern),
            f"file={filename}, pattern={pattern}",
            "high",
        )
    )

    min_kb = schema.get("min_file_size_kb", 0)
    checks.append(
        check_result(
            "min_file_size_kb",
            size_kb >= min_kb,
            f"size_kb={size_kb:.1f}, min={min_kb}",
            "medium",
        )
    )

    checks.append(
        check_result(
            "file_readable",
            bool(sheet_data),
            "openpyxl read succeeded" if sheet_data else "no sheets found",
            "critical",
        )
    )

    for rule, matched_sheet in match_sheet_rules(schema.get("sheets", []), actual_sheets):
        expected_name = rule["name"]
        if matched_sheet is None:
            if is_pattern_name(expected_name):
                continue
            checks.append(
                check_result(
                    "sheet_exists",
                    False,
                    f"missing sheet '{expected_name}'",
                    "critical",
                )
            )
            continue

        info = sheet_data[matched_sheet]
        headers = set(info["headers"])
        required = rule.get("required_columns", [])
        missing = [col for col in required if col not in headers]
        checks.append(
            check_result(
                "required_columns",
                not missing,
                f"sheet={matched_sheet}, missing={missing or 'none'}",
                "critical",
            )
        )

        row_count = info["row_count"]
        lo, hi = rule.get("row_count_range", [0, 999999])
        checks.append(
            check_result(
                "row_count_range",
                lo <= row_count <= hi,
                f"sheet={matched_sheet}, rows={row_count}, range=[{lo},{hi}]",
                "high",
            )
        )

    quality_results: dict[str, Any] = {}

    all_passed = all(c["passed"] for c in checks)

    return {
        "key": key,
        "filename": filename,
        "size_kb": round(size_kb, 2),
        "sheets": {
            name: {"headers": data["headers"], "row_count": data["row_count"]}
            for name, data in sheet_data.items()
        },
        "checks": checks,
        "quality": quality_results,
        "all_passed": all_passed,
    }


def run_quality_on_bytes(
    data: bytes, sheet_name: str, inspect_date: datetime
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    try:
        df = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:
        return {
            "read_dataframe": {
                "passed": False,
                "detail": str(exc),
                "severity": "high",
            }
        }

    if df.empty:
        return {
            "non_empty": {
                "passed": False,
                "detail": "sheet has zero data rows",
                "severity": "high",
            }
        }

    def null_pct(col: str) -> float | None:
        if col not in df.columns:
            return None
        return float(df[col].isna().mean() * 100)

    if "product_id" in df.columns:
        null_id = null_pct("product_id") or 0
        dupes = int(df["product_id"].duplicated().sum())
        results["null_product_id_pct"] = {
            "passed": null_id <= 5.0,
            "detail": f"{null_id:.1f}% null product_id",
            "severity": "critical",
        }
        results["duplicate_product_id"] = {
            "passed": dupes == 0,
            "detail": f"{dupes} duplicate product_id values",
            "severity": "high",
        }

    if "name" in df.columns:
        null_name = null_pct("name") or 0
        results["null_name_pct"] = {
            "passed": null_name <= 2.0,
            "detail": f"{null_name:.1f}% null name",
            "severity": "high",
        }

    if "special_price" in df.columns:
        null_price = null_pct("special_price") or 0
        results["null_price_pct"] = {
            "passed": null_price <= 10.0,
            "detail": f"{null_price:.1f}% null special_price",
            "severity": "medium",
        }

    if "scraped_at" in df.columns:
        target = inspect_date.strftime("%Y-%m-%d")
        try:
            dates = pd.to_datetime(df["scraped_at"], errors="coerce").dt.strftime("%Y-%m-%d")
            stale_pct = float((dates != target).mean() * 100)
        except Exception:
            stale_pct = 100.0
        results["stale_scraped_at_pct"] = {
            "passed": stale_pct <= 5.0,
            "detail": f"{stale_pct:.1f}% scraped_at not on {target}",
            "severity": "medium",
        }

    return results


def load_existing_stats(client: Any, bucket: str, key: str) -> dict[str, Any]:
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        return yaml.safe_load(obj["Body"].read()) or {}
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return {}
        raise


def merge_stats(
    existing: dict[str, Any],
    scraper_name: str,
    file_results: list[dict[str, Any]],
) -> dict[str, Any]:
    stats = existing.setdefault("scrapers", {})
    entry = stats.setdefault(scraper_name, {"files": 0, "sheets": {}})

    for fr in file_results:
        entry["files"] = entry.get("files", 0) + 1
        size_kb = fr.get("size_kb", 0)
        entry["min_file_size_kb"] = min(entry.get("min_file_size_kb", size_kb), size_kb)
        entry["max_file_size_kb"] = max(entry.get("max_file_size_kb", size_kb), size_kb)

        for sheet_name, sheet_info in fr.get("sheets", {}).items():
            sh = entry["sheets"].setdefault(sheet_name, {"columns": [], "row_count_min": None, "row_count_max": None})
            rows = sheet_info.get("row_count", 0)
            sh["row_count_min"] = rows if sh["row_count_min"] is None else min(sh["row_count_min"], rows)
            sh["row_count_max"] = rows if sh["row_count_max"] is None else max(sh["row_count_max"], rows)
            cols = set(sh.get("columns", []))
            cols.update(sheet_info.get("headers", []))
            sh["columns"] = sorted(cols)

    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    return existing


def upload_text(client: Any, bucket: str, key: str, body: str, content_type: str) -> None:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType=content_type,
    )


def write_step_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


def print_summary_table(results: list[dict[str, Any]]) -> None:
    print(f"\n{'Scraper':<35} {'Files':>5} {'Pass':>5} {'Total':>5} {'OK':>3}")
    print("-" * 58)
    for row in results:
        ok = "YES" if row["all_passed"] else "NO"
        print(
            f"{row['scraper']:<35} {row['files_found']:>5} "
            f"{row['checks_passed']:>5} {row['checks_total']:>5} {ok:>3}"
        )


def main() -> int:
    args = parse_args()

    bucket = os.environ.get("CF_R2_BUCKET_NAME")
    if not bucket:
        print("ERROR: CF_R2_BUCKET_NAME not set", file=sys.stderr)
        return 1

    client = build_r2_client()

    try:
        config, config_source = resolve_config(client, bucket, args)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    scrapers = flatten_scrapers(config)
    schemas = schema_by_scraper(config)

    bucket = bucket or config.get("meta", {}).get("r2_bucket")
    r2_prefix = config.get("meta", {}).get("r2_prefix", DEFAULT_R2_PREFIX).strip("/")

    if args.date:
        end_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_date = datetime.now(timezone.utc) - timedelta(days=1)

    dates = iter_dates(end_date, args.days_lookback)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_source": config_source,
        "inspect_dates": [d.strftime("%Y-%m-%d") for d in dates],
        "scrapers": [],
    }

    summary_rows: list[dict[str, Any]] = []
    any_failure = False
    stats_blob: dict[str, Any] = {}

    if args.update_stats:
        stats_key = f"{r2_prefix}/{MONITOR_SUBPATH}/monitor_stats.yml"
        stats_blob = load_existing_stats(client, bucket, stats_key)

    for scraper in scrapers:
        name = scraper["name"]
        schema = schemas.get(name)
        if not schema:
            print(f"WARN: no excel_schema for scraper '{name}'", file=sys.stderr)
            continue

        base = strip_bucket_placeholder(scraper["r2_path"])
        scraper_result: dict[str, Any] = {
            "scraper": name,
            "slug": scraper.get("slug"),
            "repo": scraper.get("repo"),
            "files": [],
            "files_found": 0,
            "checks_passed": 0,
            "checks_total": 0,
            "all_passed": True,
        }

        file_results_for_stats: list[dict[str, Any]] = []

        for day in dates:
            prefix = partition_prefix(base, day)
            keys = list_xlsx_keys(client, bucket, prefix)

            for key in keys:
                try:
                    head = client.head_object(Bucket=bucket, Key=key)
                    size_kb = head["ContentLength"] / 1024
                    raw = download_bytes(client, bucket, key)
                    sheet_data = inspect_workbook(raw)

                    file_result = validate_file(
                        key=key,
                        size_kb=size_kb,
                        schema=schema,
                        sheet_data=sheet_data,
                        inspect_date=day,
                    )

                    if args.quality:
                        target = (
                            "ALL_PRODUCTS"
                            if "ALL_PRODUCTS" in sheet_data
                            else next(iter(sheet_data), "Sheet1")
                        )
                        file_result["quality"] = run_quality_on_bytes(raw, target, day)
                        q_ok = all(q.get("passed", True) for q in file_result["quality"].values())
                        file_result["all_passed"] = file_result["all_passed"] and q_ok

                    scraper_result["files"].append(file_result)
                    file_results_for_stats.append(file_result)
                    scraper_result["files_found"] += 1

                    for chk in file_result["checks"]:
                        scraper_result["checks_total"] += 1
                        if chk["passed"]:
                            scraper_result["checks_passed"] += 1
                        else:
                            scraper_result["all_passed"] = False
                            any_failure = True

                    for q in file_result.get("quality", {}).values():
                        scraper_result["checks_total"] += 1
                        if q.get("passed", True):
                            scraper_result["checks_passed"] += 1
                        else:
                            scraper_result["all_passed"] = False
                            any_failure = True

                except Exception as exc:
                    any_failure = True
                    scraper_result["all_passed"] = False
                    scraper_result["files_found"] += 1
                    scraper_result["checks_total"] += 1
                    scraper_result["files"].append(
                        {
                            "key": key,
                            "error": str(exc),
                            "all_passed": False,
                            "checks": [
                                check_result("file_processing", False, str(exc), "critical")
                            ],
                        }
                    )

        if scraper_result["files_found"] == 0:
            scraper_result["all_passed"] = False
            any_failure = True
            scraper_result["checks_total"] += 1
            scraper_result["files"].append(
                {
                    "checks": [
                        check_result(
                            "files_found",
                            False,
                            f"no .xlsx under prefix for {dates[-1].strftime('%Y-%m-%d')}",
                            "critical",
                        )
                    ],
                    "all_passed": False,
                }
            )

        if args.update_stats and file_results_for_stats:
            stats_blob = merge_stats(stats_blob, name, file_results_for_stats)

        report["scrapers"].append(scraper_result)
        summary_rows.append(scraper_result)

    report_date = end_date.strftime("%Y-%m-%d")
    report_key = f"{r2_prefix}/{MONITOR_SUBPATH}/{report_date}/report.json"
    upload_text(client, bucket, report_key, json.dumps(report, indent=2), "application/json")

    if args.update_stats:
        stats_key = f"{r2_prefix}/{MONITOR_SUBPATH}/monitor_stats.yml"
        upload_text(client, bucket, stats_key, yaml.dump(stats_blob, sort_keys=False), "text/yaml")

    print_summary_table(summary_rows)
    print(f"\nReport uploaded: r2://{bucket}/{report_key}")

    summary_lines = [
        "## R2 Excel Schema Monitor",
        "",
        f"Dates: {', '.join(d.strftime('%Y-%m-%d') for d in dates)}",
        "",
        "| Scraper | Files | Passed | Total | OK |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in summary_rows:
        summary_lines.append(
            f"| {row['scraper']} | {row['files_found']} | {row['checks_passed']} | "
            f"{row['checks_total']} | {'✅' if row['all_passed'] else '❌'} |"
        )
    summary_lines.append("")
    summary_lines.append(f"Report: `r2://{bucket}/{report_key}`")
    write_step_summary(summary_lines)

    if args.fail_on_error and any_failure:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
