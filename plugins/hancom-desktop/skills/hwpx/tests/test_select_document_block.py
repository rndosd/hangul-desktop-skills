from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid


BASE = Path(__file__).absolute().parents[1]
SCRIPT = BASE / "scripts/select_document_block.py"
workspace = os.environ.get("HWPX_TEST_WORKSPACE")
if not workspace or not Path(workspace).is_absolute() or not Path(workspace).is_dir():
    raise SystemExit("Set HWPX_TEST_WORKSPACE to an existing absolute workspace directory.")
RUN_ROOT = Path(workspace) / "test-runs" / uuid.uuid4().hex
RUN_ROOT.mkdir(parents=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


class BlockSelectorBehavior(unittest.TestCase):
    def setUp(self):
        self.root = RUN_ROOT / self._testMethodName
        self.root.mkdir()
        self.library = self.root / "사용자 양식"
        self.library.mkdir()
        self.catalog = self.library / "blocks.json"
        self.document = b"PK\x03\x04\x00\xffexact HWPX fixture\r\n"
        payloads = {
            "origin": ("source.hwpx", b"source bytes"),
            "document": ("meeting.hwpx", self.document),
            "pdf": ("meeting.pdf", b"%PDF fixture"),
            "preview": ("meeting.png", b"\x89PNG fixture"),
        }
        refs = {}
        for role, (name, data) in payloads.items():
            (self.library / name).write_bytes(data)
            refs[role] = {"path": name, "sha256": digest(data)}
        self.edits = [{"operation": "replace_text", "scope": "unmerged body cells"}]
        self.evidence = {
            "schema": "hwpx.block-evidence.v1", "outcome": "PASS",
            "block_id": "meeting-notes", "content_state": "neutral_form", "pages": 1,
            "tested_edits": deepcopy(self.edits),
            **{role + "_sha256": ref["sha256"] for role, ref in refs.items()},
            "native_observation": {"reopened": True},
        }
        self.block = {
            "id": "meeting-notes", "label": "회의 기록",
            "purposes": ["meeting", "summary"], "keywords": ["회의", "안건"],
            "structure": {"pages": 1, "summary": "제목과 본문 표"},
            "state": "reviewed", "content_state": "neutral_form",
            "origin": {"file": refs["origin"], "selection": "table 2",
                       "source_id": "report-1", "attribution": "fixture author",
                       "reuse_conditions": ["keep attribution"]},
            "document": refs["document"], "pdf": refs["pdf"], "preview": refs["preview"],
            "verification": {"evidence": {"path": "proof.json", "sha256": "0" * 64},
                             "tested_edits": deepcopy(self.edits), "limits": ["merged cells untested"]},
        }
        self.data = {"schema": "hwpx.block-library.v1", "blocks": [self.block]}
        self.save_evidence()

    def save_catalog(self):
        self.catalog.write_bytes(json_bytes(self.data))

    def save_evidence(self):
        payload = json_bytes(self.evidence)
        (self.library / "proof.json").write_bytes(payload)
        self.block["verification"]["evidence"]["sha256"] = digest(payload)
        self.save_catalog()

    def cli(self, *args, script=SCRIPT, catalog=True, resolve_failure=None, failure_type="RuntimeError", failure_operation="resolve", stdout_encoding="utf-8"):
        command = [sys.executable, "-X", "utf8", "-B"]
        if resolve_failure is None:
            command.append(str(script))
        else:
            bootstrap = '''
from pathlib import Path
import runpy
import sys
from unittest.mock import patch
script, failure_path, failure_type, failure_operation, *arguments = sys.argv[1:]
original = getattr(Path, failure_operation)
def injected(path, *args, **kwargs):
    if path.absolute() == Path(failure_path).absolute():
        error = PermissionError if failure_type == "PermissionError" else RuntimeError
        raise error("Injected path access failure")
    return original(path, *args, **kwargs)
sys.argv = [script, *arguments]
with patch.object(Path, failure_operation, injected):
    runpy.run_path(script, run_name="__main__")
'''
            command += ["-c", bootstrap, str(script), str(resolve_failure), failure_type, failure_operation]
        if catalog:
            command += ["--catalog", str(self.catalog)]
        environment = dict(os.environ, PYTHONIOENCODING=stdout_encoding + ":strict")
        process = subprocess.run(command + list(map(str, args)), capture_output=True, text=True, encoding=stdout_encoding, env=environment)
        self.assertEqual(process.stderr, "", process.stderr)
        try:
            receipt = json.loads(process.stdout)
        except ValueError:
            self.fail(f"CLI did not return JSON: {process.stdout!r}")
        return process.returncode, receipt

    def accepted(self, *args, **kwargs):
        code, receipt = self.cli(*args, **kwargs)
        self.assertEqual(code, 0, receipt)
        return receipt

    def blocked(self, reason, *args, **kwargs):
        code, receipt = self.cli(*args, **kwargs)
        self.assertNotEqual(code, 0, receipt)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertEqual(receipt["reason"], reason, receipt)
        return receipt

    def test_listing_is_metadata_only(self):
        for ref in [self.block["origin"]["file"], self.block["document"], self.block["pdf"], self.block["preview"], self.block["verification"]["evidence"]]:
            ref["path"] = "never-created/" + ref["path"]
        self.save_catalog()
        receipt = self.accepted("--list")
        self.assertEqual(receipt["current_files"], "NOT_CHECKED")
        self.assertEqual(receipt["blocks"], [self.block])
        self.assertFalse((self.library / "never-created").exists())

    def test_cp949_listing_preserves_unencodable_metadata(self):
        self.block["label"] = "회의 – 계획 😀"
        self.save_catalog()
        receipt = self.accepted("--list", stdout_encoding="cp949")
        self.assertEqual(receipt["blocks"], [self.block])

    def test_cp949_copy_returns_receipt_and_preserves_unicode_path(self):
        self.block["label"] = "회의 – 계획 😀"
        self.save_catalog()
        output = self.root / "회의 – 계획 😀.hwpx"
        receipt = self.accepted("--id", "meeting-notes", "--output", output, stdout_encoding="cp949")
        self.assertEqual(receipt["block"], self.block)
        self.assertEqual(receipt["output"], str(output.resolve()))
        self.assertEqual(output.read_bytes(), self.document)
        self.blocked("OUTPUT_EXISTS", "--id", "meeting-notes", "--output", output, stdout_encoding="cp949")
        self.assertEqual(output.read_bytes(), self.document)

    def test_cp949_failure_preserves_unencodable_detail(self):
        missing_id = "없는 양식 – 😀"
        receipt = self.blocked("BLOCK_NOT_FOUND", "--id", missing_id, stdout_encoding="cp949")
        self.assertEqual(receipt["detail"], missing_id)

    def test_purpose_filter(self):
        self.assertEqual(len(self.accepted("--list", "--purpose", "meeting")["blocks"]), 1)
        self.assertEqual(self.accepted("--list", "--purpose", "budget")["blocks"], [])

    def test_only_selected_files_are_required(self):
        missing = deepcopy(self.block)
        missing["id"] = "unavailable-budget"
        missing["origin"]["file"]["path"] = "absent-source.hwpx"
        missing["document"]["path"] = "absent-form.hwpx"
        self.data["blocks"].append(missing)
        self.save_catalog()
        self.assertEqual(len(self.accepted("--list")["blocks"]), 2)
        receipt = self.accepted("--id", "meeting-notes")
        self.assertEqual(receipt["status"], "VERIFIED_BLOCK")
        self.assertEqual(receipt["new_content_native"], "NOT_CHECKED")
        self.assertNotIn("output", receipt)

    def test_copy_is_exact_and_custom_catalog_is_used(self):
        output = self.root / "새 회의록.hwpx"
        before = {path.name: path.read_bytes() for path in self.library.iterdir()}
        receipt = self.accepted("--id", "meeting-notes", "--output", output)
        self.assertEqual(output.read_bytes(), self.document)
        self.assertEqual(receipt["output"], str(output.resolve()))
        self.assertEqual(receipt["catalog"], str(self.catalog.resolve()))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.library.iterdir()})

    def test_changed_source_prevents_output(self):
        (self.library / "source.hwpx").write_bytes(b"updated source")
        output = self.root / "no.hwpx"
        self.blocked("STALE_SOURCE", "--id", "meeting-notes", "--output", output)
        self.assertFalse(output.exists())

    def test_missing_source_prevents_output(self):
        self.block["origin"]["file"]["path"] = "missing.hwpx"
        self.save_catalog()
        output = self.root / "no.hwpx"
        self.blocked("SOURCE_UNAVAILABLE", "--id", "meeting-notes", "--output", output)
        self.assertFalse(output.exists())

    def test_catalog_resolve_runtime_error_is_json(self):
        before = self.catalog.read_bytes()
        self.blocked("CATALOG_UNAVAILABLE", "--list", resolve_failure=self.catalog)
        self.assertEqual(self.catalog.read_bytes(), before)

    def test_output_parent_resolve_runtime_error_is_json(self):
        output = self.root / "not-created.hwpx"
        before = {path.name: path.read_bytes() for path in self.library.iterdir()}
        self.blocked("INVALID_OUTPUT", "--id", "meeting-notes", "--output", output,
                     resolve_failure=output.parent)
        self.assertFalse(output.exists())
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.library.iterdir()})

    def test_missing_selected_artifacts_have_role_specific_reasons(self):
        refs = {"document": self.block["document"], "pdf": self.block["pdf"], "preview": self.block["preview"], "evidence": self.block["verification"]["evidence"]}
        for role, ref in refs.items():
            with self.subTest(role=role):
                original = ref["path"]
                ref["path"] = "missing/" + original
                self.save_catalog()
                self.blocked(role.upper() + "_UNAVAILABLE", "--id", "meeting-notes")
                ref["path"] = original

    def test_changed_selected_artifacts_have_role_specific_reasons(self):
        refs = {"document": self.block["document"], "pdf": self.block["pdf"], "preview": self.block["preview"], "evidence": self.block["verification"]["evidence"]}
        for role, ref in refs.items():
            with self.subTest(role=role):
                path = self.library / ref["path"]
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                self.blocked(role.upper() + "_HASH_MISMATCH", "--id", "meeting-notes")
                path.write_bytes(original)

    def test_proof_outcome_and_bindings_are_checked_after_hash(self):
        changes = {"outcome": "FAIL", "block_id": "other", "document_sha256": "0" * 64,
                   "origin_sha256": "0" * 64, "pdf_sha256": "0" * 64, "preview_sha256": "0" * 64,
                   "content_state": "source_excerpt", "pages": True, "tested_edits": [],
                   "schema": "unrelated.v1"}
        original = deepcopy(self.evidence)
        for field, value in changes.items():
            with self.subTest(field=field):
                self.evidence = deepcopy(original)
                self.evidence[field] = value
                self.save_evidence()
                output = self.root / (field + ".hwpx")
                self.blocked("EVIDENCE_BINDING_MISMATCH", "--id", "meeting-notes", "--output", output)
                self.assertFalse(output.exists())

    def test_invalid_proof_json_is_rejected(self):
        payload = b"not valid JSON"
        (self.library / "proof.json").write_bytes(payload)
        self.block["verification"]["evidence"]["sha256"] = digest(payload)
        self.save_catalog()
        self.blocked("INVALID_EVIDENCE", "--id", "meeting-notes")

    def test_existing_output_and_self_copy_are_preserved(self):
        output = self.root / "existing.hwpx"
        output.write_bytes(b"user document")
        self.blocked("OUTPUT_EXISTS", "--id", "meeting-notes", "--output", output)
        self.assertEqual(output.read_bytes(), b"user document")
        self.blocked("OUTPUT_EXISTS", "--id", "meeting-notes", "--output", self.library / "meeting.hwpx")
        self.assertEqual((self.library / "meeting.hwpx").read_bytes(), self.document)

    def test_wrong_output_extension_and_missing_parent_are_rejected(self):
        for output in (self.root / "bad.pdf", self.root / "absent" / "new.hwpx"):
            with self.subTest(output=output):
                self.blocked("INVALID_OUTPUT", "--id", "meeting-notes", "--output", output)
                self.assertFalse(output.exists())

    def test_traversal_and_absolute_artifact_paths_are_rejected(self):
        for location in ("../meeting.hwpx", "..\\meeting.hwpx", str(self.root / "outside.hwpx"), "C:relative.hwpx"):
            with self.subTest(location=location):
                self.block["document"]["path"] = location
                self.save_catalog()
                self.blocked("PATH_ESCAPE", "--id", "meeting-notes")

    def test_explicit_absolute_origin_is_allowed(self):
        source = self.root / "outside-source.hwpx"
        source.write_bytes(b"source bytes")
        self.block["origin"]["file"]["path"] = str(source)
        self.save_catalog()
        receipt = self.accepted("--id", "meeting-notes")
        self.assertEqual(receipt["files"]["origin"]["path"], str(source.resolve()))

    def test_relative_origin_cannot_escape(self):
        self.block["origin"]["file"]["path"] = "../outside-source.hwpx"
        self.save_catalog()
        self.blocked("PATH_ESCAPE", "--id", "meeting-notes")

    def test_invalid_file_path_returns_json(self):
        self.block["document"]["path"] = "bad\x00name.hwpx"
        self.save_catalog()
        self.blocked("INVALID_CATALOG", "--id", "meeting-notes")

    def test_directory_link_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "meeting.hwpx").write_bytes(self.document)
        link = self.library / "linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            process = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.block["document"]["path"] = "linked/meeting.hwpx"
        self.save_catalog()
        self.blocked("PATH_ESCAPE", "--id", "meeting-notes")

    def test_draft_and_unknown_block_are_rejected(self):
        self.block["state"] = "draft"
        self.save_catalog()
        self.blocked("BLOCK_NOT_REVIEWED", "--id", "meeting-notes")
        self.blocked("BLOCK_NOT_FOUND", "--id", "unknown")

    def test_duplicate_id_is_rejected(self):
        self.data["blocks"].append(deepcopy(self.block))
        self.save_catalog()
        self.blocked("DUPLICATE_ID", "--list")

    def test_invalid_catalog_schema_and_scalar_types_are_rejected(self):
        valid = deepcopy(self.data)
        for field in ("schema", "pages", "sha256"):
            with self.subTest(field=field):
                self.data = deepcopy(valid)
                if field == "schema":
                    self.data["schema"] = "wrong"
                elif field == "pages":
                    self.data["blocks"][0]["structure"]["pages"] = True
                else:
                    self.data["blocks"][0]["document"]["sha256"] = "invalid"
                self.save_catalog()
                self.blocked("INVALID_CATALOG", "--list")

    def test_duplicate_json_key_is_rejected(self):
        self.catalog.write_text('{"schema":"hwpx.block-library.v1","blocks":[],"blocks":[]}', encoding="utf-8")
        self.blocked("INVALID_JSON", "--list")

    def test_invalid_argument_combinations_are_json_failures(self):
        cases = [(), ("--list", "--id", "meeting-notes"), ("--id", "meeting-notes", "--purpose", "meeting"),
                 ("--list", "--output", str(self.root / "new.hwpx")), ("--force", "--list")]
        for args in cases:
            with self.subTest(args=args):
                self.blocked("INVALID_ARGUMENTS", *args)

    def test_catalog_permission_error_is_distinct_from_missing(self):
        for operation in ("resolve", "read_bytes"):
            with self.subTest(operation=operation):
                code, receipt = self.cli("--list", resolve_failure=self.catalog,
                                         failure_type="PermissionError", failure_operation=operation)
                self.assertNotEqual(code, 0)
                self.assertEqual(receipt["reason"], "CATALOG_ACCESS_DENIED")
                self.assertIn("host-approved", receipt["nextStep"])
        self.catalog.unlink()
        self.blocked("CATALOG_UNAVAILABLE", "--list")

    def test_selected_file_permission_error_does_not_copy(self):
        files = {"origin": "source.hwpx", "document": "meeting.hwpx",
                 "pdf": "meeting.pdf", "preview": "meeting.png", "evidence": "proof.json"}
        original = {p: p.read_bytes() for p in self.library.iterdir()}
        output = self.root / "result.hwpx"
        for role, name in files.items():
            for operation in ("resolve", "read_bytes"):
                with self.subTest(role=role, operation=operation):
                    code, receipt = self.cli("--id", "meeting-notes", "--output", output,
                                             resolve_failure=self.library / name,
                                             failure_type="PermissionError", failure_operation=operation)
                    self.assertNotEqual(code, 0)
                    prefix = "SOURCE" if role == "origin" else role.upper()
                    self.assertEqual(receipt["reason"], prefix + "_ACCESS_DENIED")
                    self.assertIn("host-approved", receipt["nextStep"])
                    self.assertFalse(output.exists())
        self.assertEqual(original, {p: p.read_bytes() for p in self.library.iterdir()})

    def test_default_catalog_is_relative_to_script_installation(self):
        install = self.root / "skill"
        scripts = install / "scripts"
        assets = install / "assets/document-templates"
        scripts.mkdir(parents=True)
        assets.mkdir(parents=True)
        copied = scripts / SCRIPT.name
        shutil.copyfile(SCRIPT, copied)
        (assets / "blocks.json").write_bytes(json_bytes({"schema": "hwpx.block-library.v1", "blocks": []}))
        receipt = self.accepted("--list", script=copied, catalog=False)
        self.assertEqual(receipt["catalog"], str((assets / "blocks.json").resolve()))
        self.assertEqual(receipt["blocks"], [])


if __name__ == "__main__":
    print("Preserved fixtures: " + str(RUN_ROOT), flush=True)
    unittest.main(verbosity=2)
