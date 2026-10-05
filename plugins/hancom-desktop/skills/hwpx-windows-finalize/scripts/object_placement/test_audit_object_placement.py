from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SCRIPT = Path(__file__).with_name("audit_object_placement.py")
FROZEN_BUNDLE: Path | None = None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class ObjectPlacementRegression(unittest.TestCase):
    def setUp(self) -> None:
        if FROZEN_BUNDLE is None:
            self.fail("--frozen-bundle is required")
        self.temp = Path(tempfile.mkdtemp(prefix="object-placement-staging-test-"))
        self.bundle = self.temp / "bundle"
        shutil.copytree(FROZEN_BUNDLE, self.bundle)
        self.manifest = self.bundle / "manifest.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def inspect(self, name: str, expected_hash: str | None = None) -> tuple[subprocess.CompletedProcess, Path]:
        output = self.temp / name
        command = [sys.executable, str(SCRIPT), "--manifest", str(self.manifest), "--output", str(output)]
        if expected_hash is not None:
            command.extend(["--expected-manifest-sha256", expected_hash])
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8"), output

    def read_manifest(self) -> dict:
        return json.loads(self.manifest.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        self.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_frozen_matrix_normal3_defect3(self) -> None:
        result, output = self.inspect("matrix.json", sha256(self.manifest))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual((report["normalCount"], report["defectCount"]), (3, 3))
        self.assertEqual(report["normalFalsePositives"], 0)
        self.assertEqual(report["defectsIdentifiedAsStaticCandidates"], 3)
        self.assertEqual(report["nativeDefectsConfirmed"], 0)

    def test_wrong_manifest_hash_refuses_output(self) -> None:
        result, output = self.inspect("wrong-manifest.json", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_source_hash_drift_blocks(self) -> None:
        manifest = self.read_manifest()
        fixture = self.bundle / "fixtures" / manifest["cases"][0]["file"]
        fixture.write_bytes(fixture.read_bytes() + b"tamper")
        result, output = self.inspect("source-drift.json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("SOURCE_HASH_MISMATCH", report["results"][0]["blockers"])

    def test_missing_fixture_blocks(self) -> None:
        manifest = self.read_manifest()
        (self.bundle / "fixtures" / manifest["cases"][0]["file"]).unlink()
        result, output = self.inspect("missing-fixture.json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("MISSING_FIXTURE", report["results"][0]["blockers"])

    def test_missing_asset_evidence_is_not_accepted(self) -> None:
        manifest = self.read_manifest()
        del manifest["assets"]["picture"]
        self.write_manifest(manifest)
        result, output = self.inspect("missing-asset.json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(any(f["code"] == "ASSET_LINK_OR_HASH_MISMATCH" for row in report["results"] for f in row["findings"]))

    def test_duplicate_target_blocks(self) -> None:
        manifest = self.read_manifest()
        case = manifest["cases"][0]
        fixture = self.bundle / "fixtures" / case["file"]
        with zipfile.ZipFile(fixture) as source:
            parts = {name: source.read(name) for name in source.namelist()}
            order = source.namelist()
        section = ET.fromstring(parts["Contents/section0.xml"])
        parent = next(node for node in section.iter() if any(local(child.tag) == "pic" for child in node))
        picture = next(child for child in parent if local(child.tag) == "pic")
        parent.append(ET.fromstring(ET.tostring(picture)))
        parts["Contents/section0.xml"] = ET.tostring(section, encoding="utf-8", xml_declaration=True)
        duplicate = self.bundle / "fixtures" / "duplicate-target.hwpx"
        with zipfile.ZipFile(duplicate, "w", zipfile.ZIP_DEFLATED) as target:
            for name in order:
                target.writestr(name, parts[name])
        case["file"] = duplicate.name
        case["fileEvidence"]["sha256"] = sha256(duplicate)
        self.write_manifest(manifest)
        result, output = self.inspect("duplicate.json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("TARGET_NOT_UNIQUE", report["results"][0]["blockers"])

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.temp / "exists.json"
        output.write_text("sentinel", encoding="utf-8")
        before = sha256(output)
        result = subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(self.manifest), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sha256(output), before)

    def test_missing_bindata_member_is_not_accepted(self) -> None:
        manifest = self.read_manifest()
        case = manifest["cases"][0]
        fixture = self.bundle / "fixtures" / case["file"]
        with zipfile.ZipFile(fixture) as source:
            order = source.namelist()
            parts = {name: source.read(name) for name in order}
        missing_member = next(name for name in order if name.startswith("BinData/"))
        order.remove(missing_member)
        parts.pop(missing_member)
        broken = self.bundle / "fixtures" / "missing-bindata.hwpx"
        with zipfile.ZipFile(broken, "w", zipfile.ZIP_DEFLATED) as target:
            for name in order:
                target.writestr(name, parts[name])
        case["file"] = broken.name
        case["fileEvidence"]["sha256"] = sha256(broken)
        self.write_manifest(manifest)
        result, output = self.inspect("missing-bindata.json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(any(f["code"] == "ASSET_LINK_OR_HASH_MISMATCH" for f in report["results"][0]["findings"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-bundle", type=Path, required=True)
    args, unittest_args = parser.parse_known_args()
    FROZEN_BUNDLE = args.frozen_bundle.resolve()
    if not (FROZEN_BUNDLE / "manifest.json").is_file():
        raise SystemExit("frozen bundle manifest not found")
    unittest.main(argv=[sys.argv[0], *unittest_args], verbosity=2)
