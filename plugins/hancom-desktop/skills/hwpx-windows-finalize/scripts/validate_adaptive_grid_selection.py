"""Validate an immutable read-only adaptive merged-grid selection receipt.

This helper never opens or edits HWPX. It checks one receipt against an exact,
bounded branch contract and the package-derived v3 plan used by the run.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


class EvidenceError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def position_tuple(value: dict[str, Any]) -> tuple[int, int, int]:
    return tuple(int(value[key]) for key in ("list", "para", "pos"))


def validate_contract_against_plan(contract: dict[str, Any], plan: dict[str, Any]) -> None:
    require(contract.get("schema") == "hwpx.adaptive-grid-selection-contract.v1", "contract schema")
    require(contract.get("scope") == "read_only_exact_branch_validation", "contract scope")
    require(plan.get("schema") == "hwpx.grid-cell-plan.v3" and plan.get("scope") == "read_only", "v3 read-only plan")
    require(str(contract["sourceSha256"]).lower() == str(plan["source"]["sha256"]).lower(), "contract/plan source hash")
    source_path = Path(plan["source"]["path"]).resolve()
    require(source_path.is_file(), "plan source file missing")
    require(source_path.stat().st_size == int(plan["source"]["bytes"]), "plan source byte size")
    require(sha256(source_path) == str(contract["sourceSha256"]).lower(), "current source hash")
    require(str(contract["tableId"]) == str(plan["tableId"]), "contract/plan table ID")
    require(1 <= int(plan["tableOrdinal"]) <= int(plan["tableCount"]) <= 100, "bounded table ordinal/count")
    require(plan["requested"] == {"row": plan["ownerCell"]["row"], "column": plan["ownerCell"]["column"]}, "plan requested owner")
    require(plan["actions"] == ["TableRightCell", "TableLowerCell"] and len(plan["route"]) == 3, "plan exact action route")
    cells = contract["cells"]
    require(set(cells) == {"anchor", "intermediate", "owner"}, "exact cell roles")
    texts = [str(cells[name]["text"]) for name in ("anchor", "intermediate", "owner")]
    require(len(set(texts)) == len(texts), "same exact text assigned to different roles")
    plan_cells = {"anchor": plan["route"][0], "intermediate": plan["route"][1], "owner": plan["ownerCell"]}
    for key in ("row", "column", "text", "paragraphCount", "nested", "plainFirstParagraph", "emptyFirstParagraph"):
        require(plan["route"][2][key] == plan["ownerCell"][key], f"route owner {key}")
    for role, expected in cells.items():
        actual = plan_cells[role]
        for key in ("row", "column", "text", "paragraphCount"):
            require(actual[key] == expected[key], f"{role}: plan {key}")
        require(actual["nested"] is False and actual["plainFirstParagraph"] is True and actual["emptyFirstParagraph"] is False, f"{role}: supported first paragraph structure")
        require(expected["para"] == 0 and expected["pos"] == 0, f"{role}: first paragraph start")
    branches = contract["allowedBranches"]
    require(len(branches) == 2, "exactly two allowed branches")
    signatures = set()
    for branch in branches:
        steps = branch["steps"]
        require(steps[0] == {"action": "anchor", "cell": "anchor"}, "branch anchor")
        require(steps[-1]["cell"] == "owner", "branch must end at owner")
        signatures.add(tuple((step["action"], step["cell"]) for step in steps))
    canonical = {
        (("anchor", "anchor"), ("TableRightCell", "owner")),
        (("anchor", "anchor"), ("TableRightCell", "intermediate"), ("TableLowerCell", "owner")),
    }
    require(signatures == canonical, "contract exact allowed signatures")


def validate_anchor_evidence(contract: dict[str, Any], receipt: dict[str, Any]) -> dict[str, bool]:
    worker = receipt["worker"]
    require(receipt["status"] == "PASS_READ_ONLY_COMPARE" and worker["status"] == "PASS_READ_ONLY_COMPARE", "anchor receipt status")
    require(receipt.get("failure") is None and worker.get("failure") is None, "anchor receipt failure")
    require(receipt["sourceUnchanged"] is True, "anchor controller source unchanged")
    require(str(worker["sourceSha256Before"]).lower() == str(contract["sourceSha256"]).lower(), "anchor source hash before")
    require(str(worker["sourceSha256After"]).lower() == str(contract["sourceSha256"]).lower(), "anchor source hash after")
    require(worker["mutation"] is None and worker["saveAs"] is False and worker["pdfExport"] is False, "anchor receipt read-only")
    require(worker["cleanup"]["quit"] is True, "anchor worker quit")
    require(receipt["cleanup"]["forced"] is False and receipt["cleanup"]["remaining"] == [], "anchor controller cleanup")
    require(len(worker["variants"]) == 1, "anchor receipt isolated variant")
    first = worker["variants"][0]["steps"][0]
    block = first["blockStart"]
    cell = contract["cells"]["anchor"]
    require(position_tuple(block["position"]) == (cell["list"], cell["para"], cell["pos"]), "anchor block position")
    require(str(block["parentId"]) == str(contract["tableId"]), "anchor parent ID")
    require(block["tableImmediateAnchor"] == contract["tableAnchors"]["immediate"], "immediate table anchor")
    require(block["tableRootAnchor"] == contract["tableAnchors"]["root"], "root table anchor")
    require(int(block["maskedMode"]) != 0, "anchor cell block mode")
    require(block["selectedId"] is None, "anchor selected control")
    read = first["read"]
    require(read["parentMatches"] is True and str(read["restored"]["parentId"]) == str(contract["tableId"]), "anchor read parent")
    anchor_position=(cell["list"], cell["para"], cell["pos"])
    require(position_tuple(read["start"]) == anchor_position and position_tuple(read["restored"]["position"]) == anchor_position, "anchor read coordinate/restore")
    require(int(read["restored"]["selectionMode"]) == 0 and int(read["restored"]["maskedMode"]) == 0 and read["restored"]["selectedId"] is None, "anchor read restored caret")
    require(int(read["end"]["list"]) == cell["list"] and int(read["end"]["para"]) == cell["para"] and int(read["end"]["pos"]) > cell["pos"], "anchor read nonempty paragraph range")
    raw_parent_evidence = "startParentId" in read and "endParentId" in read
    if raw_parent_evidence:
        require(str(read["startParentId"]) == str(contract["tableId"]), "anchor read start raw parent ID")
        require(str(read["endParentId"]) == str(contract["tableId"]), "anchor read end raw parent ID")
    return {"rawParentEvidence": raw_parent_evidence, "explicitEmptyArtifacts": isinstance(worker.get("artifacts"), list) and worker.get("artifacts") == []}


def validate_receipt(contract: dict[str, Any], plan: dict[str, Any], receipt: dict[str, Any], anchor_receipt: dict[str, Any], require_write_pregate: bool = False) -> dict[str, Any]:
    validate_contract_against_plan(contract, plan)
    anchor_flags = validate_anchor_evidence(contract, anchor_receipt)
    worker = receipt["worker"]
    require(receipt["status"] == "PASS_READ_ONLY_COMPARE" and worker["status"] == "PASS_READ_ONLY_COMPARE", "run status")
    require(receipt.get("failure") is None and worker.get("failure") is None, "run failure")
    require(receipt["sourceUnchanged"] is True, "controller source unchanged")
    require(str(worker["sourceSha256Before"]).lower() == str(contract["sourceSha256"]).lower(), "worker source hash")
    require(str(worker["sourceSha256After"]).lower() == str(contract["sourceSha256"]).lower(), "worker final source hash")
    require(worker["mutation"] is None and worker["saveAs"] is False and worker["pdfExport"] is False, "adaptive run read-only")
    require(worker["cleanup"]["quit"] is True, "worker quit")
    require(receipt["cleanup"]["forced"] is False and receipt["cleanup"]["remaining"] == [], "controller cleanup")
    require(len(worker["variants"]) == 1, "one isolated variant")
    variant = worker["variants"][0]
    require(variant["name"] == "adaptive-caret" and variant["allStepsMatch"] is True, "adaptive variant result")

    observed = []
    previous_restored = None
    raw_parent_evidence = True
    for step in variant["steps"]:
        read = step["read"]
        require(read["parentMatches"] is True, "reported parent mismatch")
        require(str(read["restored"]["parentId"]) == str(contract["tableId"]), "restored parent ID")
        require(int(read["restored"]["maskedMode"]) == 0 and int(read["restored"]["selectionMode"]) == 0, "restored caret mode")
        require(read["restored"]["selectedId"] is None, "restored selected control")
        require(position_tuple(read["start"]) == position_tuple(read["restored"]["position"]), "selection restore position")
        require(int(read["end"]["list"]) == int(read["start"]["list"]) and int(read["end"]["para"]) == int(read["start"]["para"]), "paragraph range parent")
        require(int(read["end"]["pos"]) > int(read["start"]["pos"]), "nonempty paragraph range")
        if "startParentId" not in read or "endParentId" not in read:
            raw_parent_evidence = False
        else:
            require(str(read["startParentId"]) == str(contract["tableId"]), "read start raw parent ID")
            require(str(read["endParentId"]) == str(contract["tableId"]), "read end raw parent ID")
        if step["action"] != "anchor":
            for state_name in ("before", "after"):
                state = step[state_name]
                require(str(state["parentId"]) == str(contract["tableId"]), f"movement {state_name} parent ID")
                require(int(state["maskedMode"]) == 0 and int(state["selectionMode"]) == 0, f"movement {state_name} caret mode")
                require(state["selectedId"] is None, f"movement {state_name} selected control")
            if previous_restored is not None:
                require(position_tuple(step["before"]["position"]) == previous_restored, "movement starts at prior restored position")
            require(position_tuple(step["after"]["position"]) == position_tuple(read["start"]), "movement/read position")
        matched_roles = [role for role, cell in contract["cells"].items() if str(cell["text"]) == str(read["text"])]
        require(len(matched_roles) == 1, "text must identify exactly one contracted role")
        role = matched_roles[0]
        cell = contract["cells"][role]
        require(position_tuple(read["start"]) == (cell["list"], cell["para"], cell["pos"]), f"{role}: observed coordinate")
        observed.append((str(step["action"]), role))
        previous_restored = position_tuple(read["restored"]["position"])

    allowed = {
        tuple((str(step["action"]), str(step["cell"])) for step in branch["steps"]): str(branch["name"])
        for branch in contract["allowedBranches"]
    }
    signature = tuple(observed)
    require(signature in allowed, "unexpected adaptive branch")
    require(observed[-1][1] == "owner", "final role is not owner")
    artifacts_evidence = isinstance(worker.get("artifacts"), list) and worker.get("artifacts") == []
    combined_raw_parent_evidence = raw_parent_evidence and anchor_flags["rawParentEvidence"]
    combined_artifacts_evidence = artifacts_evidence and anchor_flags["explicitEmptyArtifacts"]
    if require_write_pregate:
        require(combined_raw_parent_evidence, "write pre-gate requires raw read parent evidence in adaptive and anchor receipts")
        require(combined_artifacts_evidence, "write pre-gate requires explicit empty artifacts in adaptive and anchor receipts")
    return {
        "schema": "hwpx.adaptive-grid-selection-validation.v1",
        "status": "PASS_READ_ONLY_BRANCH",
        "branch": allowed[signature],
        "sourceSha256": str(contract["sourceSha256"]).lower(),
        "tableId": str(contract["tableId"]),
        "observed": [{"action": action, "cell": role} for action, role in observed],
        "writeAuthorized": False,
        "adaptiveRawReadParentEvidence": raw_parent_evidence,
        "anchorRawReadParentEvidence": anchor_flags["rawParentEvidence"],
        "adaptiveExplicitEmptyArtifacts": artifacts_evidence,
        "anchorExplicitEmptyArtifacts": anchor_flags["explicitEmptyArtifacts"],
        "rawReadParentEvidence": combined_raw_parent_evidence,
        "explicitEmptyArtifacts": combined_artifacts_evidence,
        "writePreGateReady": combined_raw_parent_evidence and combined_artifacts_evidence,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--anchor-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-write-pregate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_receipt(*(load_json(path.resolve()) for path in (args.contract, args.plan, args.receipt, args.anchor_receipt)), require_write_pregate=args.require_write_pregate)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.resolve()
        try:
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
        except FileExistsError as exc:
            raise EvidenceError("output exists; refusing overwrite") from exc
    print(encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(json.dumps({"status": "FAIL_VALIDATION", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
