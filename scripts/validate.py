#!/usr/bin/env python3
"""Validate the portable-r v1 registry without third-party dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "schema_version",
    "r_version",
    "platform",
    "arch",
    "artifact_url",
    "sha256",
    "archive_format",
    "r_home",
    "rscript",
    "library",
}


def fail(message: str) -> None:
    raise ValueError(message)


def validate_metadata(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    missing = REQUIRED - value.keys()
    extra = value.keys() - REQUIRED
    if missing:
        fail(f"{path}: missing fields: {', '.join(sorted(missing))}")
    if extra:
        fail(f"{path}: unexpected fields: {', '.join(sorted(extra))}")
    if value["schema_version"] != "1":
        fail(f"{path}: schema_version must be '1'")
    if not re.fullmatch(r"\d+\.\d+\.\d+", value["r_version"]):
        fail(f"{path}: invalid r_version")
    if value["platform"] not in {"windows", "macos", "linux"}:
        fail(f"{path}: invalid platform")
    if value["arch"] not in {"x86_64", "arm64"}:
        fail(f"{path}: invalid architecture")
    if value["archive_format"] not in {"zip", "tar.zst", "tar.gz"}:
        fail(f"{path}: invalid archive format")
    if not re.fullmatch(r"[a-f0-9]{64}", value["sha256"]):
        fail(f"{path}: sha256 must contain 64 lowercase hexadecimal digits")
    if urlparse(value["artifact_url"]).scheme != "https":
        fail(f"{path}: artifact_url must use HTTPS")
    for field in ("r_home", "rscript", "library"):
        if not isinstance(value[field], str) or not value[field]:
            fail(f"{path}: {field} must be a non-empty string")


def validate_registry() -> int:
    versions_path = ROOT / "versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8"))
    if versions.get("schema_version") != "1":
        fail("versions.json: schema_version must be '1'")
    runtimes = versions.get("runtimes")
    if not isinstance(runtimes, list):
        fail("versions.json: runtimes must be an array")
    seen: set[tuple[str, str, str]] = set()
    for runtime in runtimes:
        key = (
            runtime.get("r_version", ""),
            runtime.get("platform", ""),
            runtime.get("arch", ""),
        )
        if key in seen:
            fail(f"versions.json: duplicate runtime {key}")
        seen.add(key)
        metadata_path = ROOT / runtime["metadata"]
        if metadata_path.exists():
            validate_metadata(metadata_path)
        elif runtime.get("status") != "prototype":
            fail(f"versions.json: missing metadata {metadata_path}")
    schema_path = ROOT / "schemas" / "portable-r-metadata-v1.schema.json"
    json.loads(schema_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    print(f"OK: {len(runtimes)} runtime entries")
    print(f"OK: schema sha256 {digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(validate_registry())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
