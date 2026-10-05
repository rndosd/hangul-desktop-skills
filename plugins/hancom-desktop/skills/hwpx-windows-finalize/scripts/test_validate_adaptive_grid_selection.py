import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("validator", ROOT / "validate_adaptive_grid_selection.py")
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

def pos(list_id, para=0, offset=0):
    return {"list": list_id, "para": para, "pos": offset}

def state(list_id, parent="T1", mode=0):
    return {"position": pos(list_id), "parentId": parent, "selectionMode": mode, "maskedMode": mode, "selectedId": None}

def read(list_id, text, parent="T1", raw_parent=False):
    value = {"start": pos(list_id), "end": pos(list_id, offset=len(text)), "text": text,
             "parentMatches": parent == "T1", "restored": state(list_id, parent=parent)}
    if raw_parent:
        value.update({"startParentId": parent, "endParentId": parent})
    return value

class AdaptiveGridEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / "synthetic.hwpx"
        self.source.write_bytes(b"synthetic non-personal HWPX fixture")
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        base = {"rowSpan": 1, "columnSpan": 1, "nested": False, "plainFirstParagraph": True, "emptyFirstParagraph": False}
        anchor = {**base, "row": 1, "column": 1, "text": "ANCHOR", "paragraphCount": 1}
        middle = {**base, "row": 1, "column": 2, "text": "MIDDLE", "paragraphCount": 1}
        owner = {**base, "row": 2, "column": 2, "text": "OWNER", "paragraphCount": 1}
        self.plan = {"schema": "hwpx.grid-cell-plan.v3", "scope": "read_only",
                     "source": {"path": str(self.source), "sha256": self.source_hash, "bytes": self.source.stat().st_size},
                     "tableId": "T1", "tableOrdinal": 1, "tableCount": 1, "requested": {"row": 2, "column": 2},
                     "ownerCell": owner, "route": [anchor, middle, copy.deepcopy(owner)],
                     "actions": ["TableRightCell", "TableLowerCell"]}
        self.contract = {"schema": "hwpx.adaptive-grid-selection-contract.v1", "scope": "read_only_exact_branch_validation",
                         "sourceSha256": self.source_hash, "tableId": "T1",
                         "tableAnchors": {"immediate": pos(0, 1), "root": pos(0, 1)},
                         "cells": {
                             "anchor": {"row": 1, "column": 1, "text": "ANCHOR", "paragraphCount": 1, "list": 10, "para": 0, "pos": 0},
                             "intermediate": {"row": 1, "column": 2, "text": "MIDDLE", "paragraphCount": 1, "list": 11, "para": 0, "pos": 0},
                             "owner": {"row": 2, "column": 2, "text": "OWNER", "paragraphCount": 1, "list": 12, "para": 0, "pos": 0}},
                         "allowedBranches": [
                             {"name": "direct", "steps": [{"action": "anchor", "cell": "anchor"}, {"action": "TableRightCell", "cell": "owner"}]},
                             {"name": "through", "steps": [{"action": "anchor", "cell": "anchor"}, {"action": "TableRightCell", "cell": "intermediate"}, {"action": "TableLowerCell", "cell": "owner"}]}]}
        self.anchor_receipt = self.base_receipt({"name": "cell-block", "allStepsMatch": False, "steps": [{
            "blockStart": {**state(10, mode=3), "tableImmediateAnchor": pos(0, 1), "tableRootAnchor": pos(0, 1)},
            "read": read(10, "ANCHOR")} ]})
        self.direct = self.base_receipt({"name": "adaptive-caret", "allStepsMatch": True, "steps": [
            {"action": "anchor", "read": read(10, "ANCHOR")},
            {"action": "TableRightCell", "before": state(10), "after": state(12), "read": read(12, "OWNER")} ]})
        self.through = copy.deepcopy(self.direct)
        self.through["worker"]["variants"][0]["steps"] = [
            {"action": "anchor", "read": read(10, "ANCHOR")},
            {"action": "TableRightCell", "before": state(10), "after": state(11), "read": read(11, "MIDDLE")},
            {"action": "TableLowerCell", "before": state(11), "after": state(12), "read": read(12, "OWNER")}]

    def tearDown(self): self.temp.cleanup()

    def base_receipt(self, variant):
        return {"status": "PASS_READ_ONLY_COMPARE", "failure": None, "sourceUnchanged": True,
                "cleanup": {"forced": False, "remaining": []}, "worker": {
                    "status": "PASS_READ_ONLY_COMPARE", "failure": None,
                    "sourceSha256Before": self.source_hash, "sourceSha256After": self.source_hash,
                    "mutation": None, "saveAs": False, "pdfExport": False, "cleanup": {"quit": True}, "variants": [variant]}}

    def validate(self, receipt=None, contract=None, plan=None, anchor=None, require_write_pregate=False):
        return validator.validate_receipt(contract or copy.deepcopy(self.contract), plan or copy.deepcopy(self.plan),
            receipt or copy.deepcopy(self.direct), anchor or copy.deepcopy(self.anchor_receipt),
            require_write_pregate=require_write_pregate)

    def complete_pregate_evidence(self):
        receipt, anchor = copy.deepcopy(self.direct), copy.deepcopy(self.anchor_receipt)
        for document in (receipt, anchor):
            document["worker"]["artifacts"] = []
            for step in document["worker"]["variants"][0]["steps"]:
                step["read"].update({"startParentId": "T1", "endParentId": "T1"})
        return receipt, anchor

    def test_direct_and_intermediate_branches_pass(self):
        self.assertEqual(self.validate()["branch"], "direct")
        self.assertEqual(self.validate(receipt=copy.deepcopy(self.through))["branch"], "through")

    def test_duplicate_text_rejected(self):
        contract = copy.deepcopy(self.contract); contract["cells"]["intermediate"]["text"] = "OWNER"
        with self.assertRaisesRegex(validator.EvidenceError, "same exact text"): self.validate(contract=contract)

    def test_parent_guards(self):
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["read"]["parentMatches"] = False
        with self.assertRaisesRegex(validator.EvidenceError, "parent mismatch"): self.validate(receipt=receipt)
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["read"]["restored"]["parentId"] = "OTHER"
        with self.assertRaisesRegex(validator.EvidenceError, "restored parent"): self.validate(receipt=receipt)
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["after"]["parentId"] = "OTHER"
        with self.assertRaisesRegex(validator.EvidenceError, "movement after parent ID"): self.validate(receipt=receipt)

    def test_unexpected_text_and_action_rejected(self):
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["read"]["text"] = "UNKNOWN"
        with self.assertRaisesRegex(validator.EvidenceError, "exactly one contracted role"): self.validate(receipt=receipt)
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["action"] = "TableLowerCell"
        with self.assertRaisesRegex(validator.EvidenceError, "unexpected adaptive branch"): self.validate(receipt=receipt)

    def test_restore_and_owner_coordinates_rejected(self):
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["read"]["restored"]["position"]["pos"] = 1
        with self.assertRaisesRegex(validator.EvidenceError, "selection restore"): self.validate(receipt=receipt)
        receipt = copy.deepcopy(self.direct); step = receipt["worker"]["variants"][0]["steps"][-1]
        for value in (step["read"]["start"], step["read"]["end"], step["read"]["restored"]["position"], step["after"]["position"]): value["list"] = 13
        with self.assertRaisesRegex(validator.EvidenceError, "owner: observed coordinate"): self.validate(receipt=receipt)

    def test_anchor_raw_guards(self):
        anchor = copy.deepcopy(self.anchor_receipt); anchor["worker"]["variants"][0]["steps"][0]["blockStart"]["parentId"] = "OTHER"
        with self.assertRaisesRegex(validator.EvidenceError, "anchor parent"): self.validate(anchor=anchor)
        anchor = copy.deepcopy(self.anchor_receipt); anchor["worker"]["variants"][0]["steps"][0]["read"]["start"]["list"] = 11
        with self.assertRaisesRegex(validator.EvidenceError, "anchor read coordinate"): self.validate(anchor=anchor)
        anchor = copy.deepcopy(self.anchor_receipt); anchor["worker"]["variants"][0]["steps"][0]["read"]["restored"]["maskedMode"] = 3
        with self.assertRaisesRegex(validator.EvidenceError, "anchor read restored caret"): self.validate(anchor=anchor)
        anchor = copy.deepcopy(self.anchor_receipt); anchor["worker"]["variants"][0]["steps"][0]["read"]["end"]["pos"] = 0
        with self.assertRaisesRegex(validator.EvidenceError, "anchor read nonempty"): self.validate(anchor=anchor)

    def test_anchor_binding_guards(self):
        anchor = copy.deepcopy(self.anchor_receipt); anchor["worker"]["sourceSha256Before"] = "0" * 64
        with self.assertRaisesRegex(validator.EvidenceError, "anchor source hash before"): self.validate(anchor=anchor)
        anchor = copy.deepcopy(self.anchor_receipt); anchor["cleanup"]["remaining"] = [1]
        with self.assertRaisesRegex(validator.EvidenceError, "anchor controller cleanup"): self.validate(anchor=anchor)
        anchor = copy.deepcopy(self.anchor_receipt); anchor["worker"]["variants"][0]["steps"][0]["blockStart"]["tableRootAnchor"]["para"] = 9
        with self.assertRaisesRegex(validator.EvidenceError, "root table anchor"): self.validate(anchor=anchor)

    def test_mode_range_contract_plan_and_source_guards(self):
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["before"].update({"maskedMode": 3, "selectionMode": 3})
        with self.assertRaisesRegex(validator.EvidenceError, "movement before caret mode"): self.validate(receipt=receipt)
        receipt = copy.deepcopy(self.direct); receipt["worker"]["variants"][0]["steps"][-1]["read"]["end"]["pos"] = 0
        with self.assertRaisesRegex(validator.EvidenceError, "nonempty paragraph range"): self.validate(receipt=receipt)
        contract = copy.deepcopy(self.contract); contract["allowedBranches"][0]["steps"][1]["action"] = "TableLowerCell"
        with self.assertRaisesRegex(validator.EvidenceError, "exact allowed signatures"): self.validate(contract=contract)
        plan = copy.deepcopy(self.plan); plan["route"][2]["text"] = "OTHER"
        with self.assertRaisesRegex(validator.EvidenceError, "route owner text"): self.validate(plan=plan)
        with mock.patch.object(validator, "sha256", return_value="f" * 64):
            with self.assertRaisesRegex(validator.EvidenceError, "current source hash"): self.validate()

    def test_raw_read_parent_and_write_pregate_boundary(self):
        receipt = copy.deepcopy(self.direct)
        for step in receipt["worker"]["variants"][0]["steps"]: step["read"].update({"startParentId": "T1", "endParentId": "T1"})
        receipt["worker"]["variants"][0]["steps"][-1]["read"]["endParentId"] = "OTHER"
        with self.assertRaisesRegex(validator.EvidenceError, "read end raw parent ID"): self.validate(receipt=receipt)
        result = self.validate(); self.assertFalse(result["writePreGateReady"])
        with self.assertRaisesRegex(validator.EvidenceError, "raw read parent evidence"): self.validate(require_write_pregate=True)

    def test_complete_adaptive_and_anchor_evidence_passes_write_pregate(self):
        receipt, anchor = self.complete_pregate_evidence()
        result = self.validate(receipt=receipt, anchor=anchor, require_write_pregate=True)
        self.assertTrue(result["writePreGateReady"])
        self.assertTrue(result["rawReadParentEvidence"])
        self.assertTrue(result["explicitEmptyArtifacts"])

    def test_missing_or_nonempty_artifacts_fail_write_pregate(self):
        receipt, anchor = self.complete_pregate_evidence()
        del anchor["worker"]["artifacts"]
        with self.assertRaisesRegex(validator.EvidenceError, "explicit empty artifacts"):
            self.validate(receipt=receipt, anchor=anchor, require_write_pregate=True)
        receipt, anchor = self.complete_pregate_evidence()
        receipt["worker"]["artifacts"] = [{"unexpected": "output"}]
        with self.assertRaisesRegex(validator.EvidenceError, "explicit empty artifacts"):
            self.validate(receipt=receipt, anchor=anchor, require_write_pregate=True)

    def test_cli_exclusive_create_and_write_pregate_exit2(self):
        fixture_paths = {}
        for name, value in {"contract": self.contract, "plan": self.plan, "receipt": self.direct, "anchor": self.anchor_receipt}.items():
            path = Path(self.temp.name) / f"{name}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            fixture_paths[name] = path
        output = Path(self.temp.name) / "validation.json"
        command = [sys.executable, str(ROOT / "validate_adaptive_grid_selection.py"),
                   "--contract", str(fixture_paths["contract"]), "--plan", str(fixture_paths["plan"]),
                   "--receipt", str(fixture_paths["receipt"]), "--anchor-receipt", str(fixture_paths["anchor"])]
        first = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
        second = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
        pregate = subprocess.run(command + ["--require-write-pregate"], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 2, second.stderr)
        self.assertEqual(pregate.returncode, 2, pregate.stderr)

if __name__ == "__main__": unittest.main()
