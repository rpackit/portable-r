from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "portable_r_validate",
    ROOT / "scripts" / "validate.py",
)
assert SPEC is not None and SPEC.loader is not None
validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate)


class RegistryFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "schemas").mkdir(parents=True)
        (root / "metadata").mkdir()
        self.schema = json.loads(
            (
                ROOT / "schemas" / "portable-r-metadata-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.metadata = {
            "schema_version": "1",
            "r_version": "4.6.1",
            "platform": "windows",
            "arch": "x86_64",
            "artifact_url": (
                "https://github.com/rpackit/runtime-win/releases/"
                "download/v4.6.1/"
                "portable-r-windows-x86_64-4.6.1.zip"
            ),
            "sha256": "a" * 64,
            "archive_format": "zip",
            "r_home": "portable-r-windows-x86_64-4.6.1",
            "rscript": (
                "portable-r-windows-x86_64-4.6.1/bin/Rscript.exe"
            ),
            "library": "portable-r-windows-x86_64-4.6.1/library",
        }
        self.versions = {
            "schema_version": "1",
            "runtimes": [
                {
                    "r_version": "4.6.1",
                    "platform": "windows",
                    "arch": "x86_64",
                    "status": "verified",
                    "metadata": "metadata/windows-x86_64-4.6.1.json",
                }
            ],
        }
        self.write()

    def write(self) -> None:
        (self.root / "versions.json").write_text(
            json.dumps(self.versions),
            encoding="utf-8",
        )
        (
            self.root
            / "schemas"
            / "portable-r-metadata-v1.schema.json"
        ).write_text(json.dumps(self.schema), encoding="utf-8")
        (
            self.root / "metadata" / "windows-x86_64-4.6.1.json"
        ).write_text(json.dumps(self.metadata), encoding="utf-8")


class ValidateRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = RegistryFixture(Path(self.temp.name))

    def assert_invalid(self, pattern: str) -> None:
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, pattern):
            validate.validate_registry(self.fixture.root, quiet=True)

    def test_valid_registry(self) -> None:
        self.assertEqual(
            validate.validate_registry(self.fixture.root, quiet=True),
            0,
        )

    def test_index_and_metadata_must_agree(self) -> None:
        self.fixture.metadata["r_version"] = "4.6.0"
        self.fixture.metadata["artifact_url"] = (
            "https://github.com/rpackit/runtime-win/releases/"
            "download/v4.6.0/portable-r-windows-x86_64-4.6.0.zip"
        )
        self.fixture.metadata["r_home"] = (
            "portable-r-windows-x86_64-4.6.0"
        )
        self.fixture.metadata["rscript"] = (
            "portable-r-windows-x86_64-4.6.0/bin/Rscript.exe"
        )
        self.fixture.metadata["library"] = (
            "portable-r-windows-x86_64-4.6.0/library"
        )
        self.assert_invalid("does not match index")

    def test_unknown_status_is_rejected(self) -> None:
        self.fixture.versions["runtimes"][0]["status"] = "almost-ready"
        self.assert_invalid("invalid status")

    def test_path_traversal_is_rejected(self) -> None:
        self.fixture.metadata["library"] = "../outside"
        self.assert_invalid("must not contain")

    def test_artifact_name_and_release_tag_are_contractual(self) -> None:
        self.fixture.metadata["artifact_url"] = (
            "https://github.com/rpackit/runtime-win/releases/"
            "download/latest/runtime.zip"
        )
        self.assert_invalid("expected GitHub release path")

    def test_schema_required_fields_are_enforced(self) -> None:
        self.fixture.schema = copy.deepcopy(self.fixture.schema)
        self.fixture.schema["required"].append("provenance")
        self.fixture.schema["properties"]["provenance"] = {
            "type": "string",
            "minLength": 1,
        }
        self.assert_invalid("missing fields: provenance")

    def test_orphan_metadata_is_rejected(self) -> None:
        (
            self.fixture.root / "metadata" / "orphan.json"
        ).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing from versions.json"):
            validate.validate_registry(self.fixture.root, quiet=True)


if __name__ == "__main__":
    unittest.main()
