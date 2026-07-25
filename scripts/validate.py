#!/usr/bin/env python3
"""Validate the portable-r v1 registry with the Python standard library."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
R_VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
PLATFORMS = {"windows", "macos", "linux"}
ARCHITECTURES = {"x86_64", "arm64"}
STATUSES = {"prototype", "verified", "deprecated"}
INDEX_FIELDS = {
    "r_version",
    "platform",
    "arch",
    "status",
    "metadata",
}


def fail(message: str) -> None:
    raise ValueError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        fail(f"{path}: cannot read file: {error}")


def validate_schema_value(
    value: Any,
    schema: dict[str, Any],
    location: str,
) -> None:
    """Validate the JSON Schema subset used by metadata v1."""
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            fail(f"{location}: must be an object")
        required = set(schema.get("required", []))
        missing = required - value.keys()
        if missing:
            fail(f"{location}: missing fields: {', '.join(sorted(missing))}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = value.keys() - properties.keys()
            if extra:
                fail(
                    f"{location}: unexpected fields: "
                    f"{', '.join(sorted(extra))}"
                )
        for name, child in properties.items():
            if name in value:
                validate_schema_value(
                    value[name],
                    child,
                    f"{location}.{name}",
                )
        return
    if schema_type == "string" and not isinstance(value, str):
        fail(f"{location}: must be a string")
    if "const" in schema and value != schema["const"]:
        fail(f"{location}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        fail(f"{location}: must be one of {schema['enum']!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            fail(f"{location}: is shorter than minLength")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            fail(f"{location}: does not match {pattern!r}")


def safe_registry_path(value: Any, location: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        fail(f"{location}: must be a non-empty relative POSIX path")
    if "\\" in value:
        fail(f"{location}: must use forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("//"):
        fail(f"{location}: must be relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        fail(f"{location}: must not contain empty, '.' or '..' segments")
    return path


def validate_artifact_contract(value: dict[str, Any], location: str) -> None:
    parsed = urlparse(value["artifact_url"])
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        fail(f"{location}.artifact_url: must use https://github.com")
    if parsed.params or parsed.query or parsed.fragment:
        fail(f"{location}.artifact_url: must not contain params, query, or fragment")

    extension = value["archive_format"]
    artifact = (
        f"portable-r-{value['platform']}-{value['arch']}-"
        f"{value['r_version']}.{extension}"
    )
    expected_path = (
        f"/rpackit/portable-r-{value['platform']}/releases/download/"
        f"v{value['r_version']}/{artifact}"
    )
    if unquote(parsed.path) != expected_path:
        fail(
            f"{location}.artifact_url: expected GitHub release path "
            f"{expected_path!r}"
        )

    r_home = safe_registry_path(value["r_home"], f"{location}.r_home")
    rscript = safe_registry_path(value["rscript"], f"{location}.rscript")
    library = safe_registry_path(value["library"], f"{location}.library")
    artifact_root = artifact[: -(len(extension) + 1)]
    if r_home.parts != (artifact_root,):
        fail(f"{location}.r_home: must equal archive root {artifact_root!r}")
    for field, path in (("rscript", rscript), ("library", library)):
        if path.parts[: len(r_home.parts)] != r_home.parts:
            fail(f"{location}.{field}: must be contained in r_home")
    rscript_suffix = (
        ("bin", "Rscript.exe")
        if value["platform"] == "windows"
        else ("bin", "Rscript")
    )
    if rscript.parts[-2:] != rscript_suffix:
        fail(
            f"{location}.rscript: expected suffix "
            f"{'/'.join(rscript_suffix)!r}"
        )


def validate_metadata(
    path: Path,
    schema: dict[str, Any],
) -> dict[str, Any]:
    value = read_json(path)
    validate_schema_value(value, schema, str(path))
    validate_artifact_contract(value, str(path))
    return value


def validate_index_entry(runtime: Any, index: int) -> None:
    location = f"versions.json.runtimes[{index}]"
    if not isinstance(runtime, dict):
        fail(f"{location}: must be an object")
    missing = INDEX_FIELDS - runtime.keys()
    extra = runtime.keys() - INDEX_FIELDS
    if missing:
        fail(f"{location}: missing fields: {', '.join(sorted(missing))}")
    if extra:
        fail(f"{location}: unexpected fields: {', '.join(sorted(extra))}")
    if (
        not isinstance(runtime["r_version"], str)
        or R_VERSION_PATTERN.fullmatch(runtime["r_version"]) is None
    ):
        fail(f"{location}.r_version: invalid R version")
    if runtime["platform"] not in PLATFORMS:
        fail(f"{location}.platform: invalid platform")
    if runtime["arch"] not in ARCHITECTURES:
        fail(f"{location}.arch: invalid architecture")
    if runtime["status"] not in STATUSES:
        fail(f"{location}.status: invalid status")
    metadata = safe_registry_path(runtime["metadata"], f"{location}.metadata")
    if (
        len(metadata.parts) != 2
        or metadata.parts[0] != "metadata"
        or not metadata.name.endswith(".json")
    ):
        fail(f"{location}.metadata: must name metadata/<file>.json")


def validate_registry(root: Path = ROOT, quiet: bool = False) -> int:
    root = root.resolve()
    versions_path = root / "versions.json"
    versions = read_json(versions_path)
    if not isinstance(versions, dict):
        fail("versions.json: must be an object")
    if set(versions) != {"schema_version", "runtimes"}:
        fail("versions.json: expected only schema_version and runtimes")
    if versions["schema_version"] != "1":
        fail("versions.json: schema_version must be '1'")
    runtimes = versions["runtimes"]
    if not isinstance(runtimes, list):
        fail("versions.json: runtimes must be an array")

    schema_path = root / "schemas" / "portable-r-metadata-v1.schema.json"
    schema = read_json(schema_path)
    if not isinstance(schema, dict):
        fail(f"{schema_path}: schema must be an object")

    seen: set[tuple[str, str, str]] = set()
    referenced_metadata: set[PurePosixPath] = set()
    for index, runtime in enumerate(runtimes):
        validate_index_entry(runtime, index)
        key = (
            runtime["r_version"],
            runtime["platform"],
            runtime["arch"],
        )
        if key in seen:
            fail(f"versions.json: duplicate runtime {key}")
        seen.add(key)

        relative_metadata = safe_registry_path(
            runtime["metadata"],
            f"versions.json.runtimes[{index}].metadata",
        )
        if relative_metadata in referenced_metadata:
            fail(f"versions.json: duplicate metadata {relative_metadata}")
        referenced_metadata.add(relative_metadata)
        metadata_path = root.joinpath(*relative_metadata.parts)
        if not metadata_path.exists():
            if runtime["status"] != "prototype":
                fail(f"versions.json: missing metadata {metadata_path}")
            continue
        metadata = validate_metadata(metadata_path, schema)
        for field in ("r_version", "platform", "arch"):
            if metadata[field] != runtime[field]:
                fail(
                    f"{metadata_path}: {field} {metadata[field]!r} does not "
                    f"match index value {runtime[field]!r}"
                )

    metadata_dir = root / "metadata"
    present_metadata = {
        PurePosixPath("metadata", path.name)
        for path in metadata_dir.glob("*.json")
    }
    orphaned = present_metadata - referenced_metadata
    if orphaned:
        fail(
            "metadata files missing from versions.json: "
            + ", ".join(str(path) for path in sorted(orphaned))
        )

    digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    if not quiet:
        print(f"OK: {len(runtimes)} runtime entries")
        print(f"OK: schema sha256 {digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(validate_registry())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
