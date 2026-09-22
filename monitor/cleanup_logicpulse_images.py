"""Delete LogicPulse image objects while preserving the coupons category."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

import boto3
from botocore.config import Config


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "category_monitor" / "categories.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".svg"}
DELETE_BATCH_SIZE = 1000


def logicpulse_categories(registry_path: Path, preserve_category: str) -> set[str]:
    """Return LogicPulse category slugs except the explicitly preserved slug."""
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    preserved = preserve_category.strip().lower()
    return {
        slug
        for slug, details in registry.get("categories", {}).items()
        if str(details.get("project", "")).strip().lower() == "logicpulse"
        and slug.strip().lower() != preserved
    }


def category_from_image_key(key: str) -> str | None:
    """Extract the category from a date-partitioned image key."""
    parts = key.strip("/").split("/")
    for index in range(len(parts) - 5):
        if (
            parts[index].startswith("year=")
            and parts[index + 1].startswith("month=")
            and parts[index + 2].startswith("day=")
            and parts[index + 4] == "images"
            and Path(parts[index + 5]).suffix.lower() in IMAGE_EXTENSIONS
        ):
            return parts[index + 3]
    return None


def matching_image_keys(
    pages: Iterable[dict[str, Any]], categories: set[str]
) -> list[str]:
    """Select only image objects in the requested categories."""
    normalized_categories = {category.strip().lower() for category in categories}
    keys: list[str] = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = str(obj.get("Key", ""))
            category = category_from_image_key(key)
            if category and category.lower() in normalized_categories:
                keys.append(key)
    return keys


def delete_keys(client: Any, bucket: str, keys: list[str], *, execute: bool) -> int:
    """Delete keys in S3 batches, or report what would be deleted."""
    if not execute:
        return len(keys)
    for start in range(0, len(keys), DELETE_BATCH_SIZE):
        batch = keys[start : start + DELETE_BATCH_SIZE]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            details = "; ".join(f"{item.get('Key')}: {item.get('Code')}" for item in errors)
            raise RuntimeError(f"Object deletion failed: {details}")
    return len(keys)


def client_for(target: str) -> tuple[Any, str]:
    if target == "r2":
        required = {
            "CF_R2_ACCESS_KEY_ID": os.getenv("CF_R2_ACCESS_KEY_ID"),
            "CF_R2_SECRET_ACCESS_KEY": os.getenv("CF_R2_SECRET_ACCESS_KEY"),
            "CF_R2_BUCKET_NAME": os.getenv("CF_R2_BUCKET_NAME"),
            "CF_R2_ENDPOINT_URL": os.getenv("CF_R2_ENDPOINT_URL"),
        }
        service = "Cloudflare R2"
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing {service} environment variable(s): {', '.join(missing)}")
        client = boto3.client(
            "s3",
            endpoint_url=required["CF_R2_ENDPOINT_URL"],
            aws_access_key_id=required["CF_R2_ACCESS_KEY_ID"],
            aws_secret_access_key=required["CF_R2_SECRET_ACCESS_KEY"],
            region_name="us-east-1",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        bucket = required["CF_R2_BUCKET_NAME"]
    else:
        required = {
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME"),
        }
        service = "AWS S3"
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing {service} environment variable(s): {', '.join(missing)}")
        client = boto3.client(
            "s3",
            aws_access_key_id=required["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=required["AWS_SECRET_ACCESS_KEY"],
        )
        bucket = required["S3_BUCKET_NAME"]

    return client, str(bucket)


def clean_storage(target: str, categories: set[str], *, execute: bool) -> int:
    client, bucket = client_for(target)
    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix="sheeel_data/")
    keys = matching_image_keys(pages, categories)
    action = "Deleting" if execute else "Would delete"
    print(f"{target}: {action} {len(keys)} image object(s) from {sorted(categories)}")
    return delete_keys(client, bucket, keys, execute=execute)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", choices=("r2", "s3", "both"), default="both")
    parser.add_argument("--categories-file", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--preserve-category", default="coupons")
    parser.add_argument("--execute", action="store_true", help="Actually delete objects")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    categories = logicpulse_categories(args.categories_file, args.preserve_category)
    if not categories:
        raise RuntimeError("No non-preserved LogicPulse categories were found in the registry")
    targets = ("r2", "s3") if args.storage == "both" else (args.storage,)
    for target in targets:
        clean_storage(target, categories, execute=args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())