from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_child(node: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in node if local(child.tag) == name), None)


def nested_text(node: ET.Element) -> str:
    return "".join(node.itertext())


def load_package(path: Path) -> tuple[list[dict], list[dict], str, dict]:
    with zipfile.ZipFile(path) as package:
        members = package.namelist()
        content = ET.fromstring(package.read("Contents/content.hpf"))
        assets: dict[str, dict] = {}
        for item in content.iter():
            if local(item.tag) != "item":
                continue
            item_id, href = item.get("id"), item.get("href")
            if item_id and href and href.startswith("BinData/"):
                assets[item_id] = {
                    "member": href,
                    "present": href in members,
                    "sha256": hashlib.sha256(package.read(href)).hexdigest() if href in members else None,
                }

        section_names = sorted(name for name in members if name.startswith("Contents/section") and name.endswith(".xml"))
        if not section_names:
            raise ValueError("no Contents/section*.xml parts")
        objects: list[dict] = []
        pages: list[dict] = []
        texts: list[str] = []
        for section_name in section_names:
            section = ET.fromstring(package.read(section_name))
            texts.append(nested_text(section))
            page_pr = next((node for node in section.iter() if local(node.tag) == "pagePr"), None)
            if page_pr is not None:
                pages.append({"section": section_name, "width": int(page_pr.get("width", "0")), "height": int(page_pr.get("height", "0"))})
            for node in section.iter():
                tag = local(node.tag)
                if tag not in {"pic", "rect"}:
                    continue
                pos = first_child(node, "pos")
                size = first_child(node, "sz")
                margin = first_child(node, "outMargin")
                draw = first_child(node, "drawText")
                image = next((child for child in node.iter() if local(child.tag) == "img"), None)
                objects.append({
                    "section": section_name,
                    "tag": tag,
                    "id": node.get("id") or node.get("instid"),
                    "zOrder": node.get("zOrder"),
                    "textWrap": node.get("textWrap"),
                    "pos": dict(pos.attrib) if pos is not None else {},
                    "size": {"width": int(size.get("width", "0")), "height": int(size.get("height", "0"))} if size is not None else {},
                    "outMargin": dict(margin.attrib) if margin is not None else {},
                    "drawText": nested_text(draw) if draw is not None else None,
                    "binaryItemIDRef": image.get("binaryItemIDRef") if image is not None else None,
                })
    return objects, pages, "".join(texts), assets


def blocked_result(case: dict, path: Path, code: str) -> dict:
    return {
        "caseId": case.get("caseId", "UNKNOWN"), "class": case.get("class", "unknown"),
        "source": str(path), "sourceSha256": None, "objects": [], "binaryAssets": {},
        "pageGeometry": [], "markerCounts": {}, "findings": [], "blockers": [code],
        "status": "BLOCKED_EVIDENCE", "nativeLayout": "UNVERIFIED",
        "internalAnchorIdentity": "UNVERIFIED", "editingSupport": "NOT_ASSESSED",
    }


def inspect_case(root: Path, case: dict, manifest_assets: dict) -> dict:
    path = root / "fixtures" / case["file"]
    if not path.is_file():
        return blocked_result(case, path, "MISSING_FIXTURE")
    actual_hash = sha256(path)
    blockers: list[str] = []
    findings: list[dict] = []
    if actual_hash != case.get("fileEvidence", {}).get("sha256"):
        blockers.append("SOURCE_HASH_MISMATCH")
    try:
        objects, pages, text, binary_assets = load_package(path)
    except Exception as exc:
        result = blocked_result(case, path, f"PACKAGE_READ_ERROR:{type(exc).__name__}")
        result["sourceSha256"] = actual_hash
        return result

    expected = case["expected"]
    candidates = [obj for obj in objects if obj["tag"] == expected["tag"]]
    expected_unique = int(expected.get("uniqueObjectCount", 1))
    if len(candidates) != expected_unique or len(candidates) != 1:
        blockers.append("TARGET_NOT_UNIQUE")
    anchor_expected = int(case.get("expectedAnchorMarkerCount", 4))
    object_expected = int(case.get("expectedObjectMarkerCount", 1))
    marker_counts = {"anchor": text.count(case["anchorMarker"]), "object": text.count(case["objectMarker"])}
    if marker_counts["anchor"] != anchor_expected:
        blockers.append("ANCHOR_MARKER_COUNT_MISMATCH")
    if marker_counts["object"] != object_expected:
        blockers.append("OBJECT_MARKER_COUNT_MISMATCH")

    actual = candidates[0] if len(candidates) == 1 else None
    if actual is not None:
        pos = actual["pos"]
        for key in ("treatAsChar", "horzRelTo", "vertRelTo", "horzOffset", "vertOffset"):
            if key in expected and str(pos.get(key)) != str(expected[key]):
                findings.append({"code": "ANCHOR_MODE_MISMATCH" if key == "treatAsChar" else "POSITION_MISMATCH", "field": key, "expected": str(expected[key]), "actual": pos.get(key)})
        if "drawText" in expected and actual["drawText"] != expected["drawText"]:
            findings.append({"code": "DRAWTEXT_MISMATCH", "expected": expected["drawText"], "actual": actual["drawText"]})
        for key in ("width", "height"):
            if key in expected and int(actual["size"].get(key, -1)) != int(expected[key]):
                findings.append({"code": "SIZE_MISMATCH", "field": key, "expected": expected[key], "actual": actual["size"].get(key)})
        if actual["outMargin"] != expected.get("outMargin", {}):
            findings.append({"code": "OUT_MARGIN_MISMATCH", "expected": expected.get("outMargin"), "actual": actual["outMargin"]})
        if actual["textWrap"] != expected.get("textWrap"):
            findings.append({"code": "WRAP_MISMATCH", "expected": expected.get("textWrap"), "actual": actual["textWrap"]})
        if actual["zOrder"] != expected.get("zOrder"):
            findings.append({"code": "Z_ORDER_MISMATCH", "expected": expected.get("zOrder"), "actual": actual["zOrder"]})
        asset_key = expected.get("assetKey")
        if asset_key is None:
            if actual["binaryItemIDRef"] is not None:
                findings.append({"code": "UNEXPECTED_BINARY_ASSET"})
        else:
            declared = manifest_assets.get(asset_key)
            packaged = binary_assets.get(actual["binaryItemIDRef"])
            if not declared or not packaged or not packaged.get("present") or packaged.get("sha256") != declared.get("sha256"):
                findings.append({"code": "ASSET_LINK_OR_HASH_MISMATCH", "assetKey": asset_key, "binaryItemIDRef": actual["binaryItemIDRef"]})
        if expected.get("mustFitPage") and pages:
            page = pages[0]
            x, y = int(pos.get("horzOffset", "0")), int(pos.get("vertOffset", "0"))
            width, height = actual["size"].get("width", 0), actual["size"].get("height", 0)
            if x < 0 or y < 0 or x + width > page["width"] or y + height > page["height"]:
                findings.append({"code": "PAGE_BOUNDARY_OVERFLOW", "bounds": [x, y, x + width, y + height], "page": page})
        if expected.get("expectedStaticFinding") == "OVERLAP_CAPABLE_TEXTBOX" or case.get("expectedFinding") == "OVERLAP_CAPABLE_TEXTBOX":
            if actual["tag"] == "rect" and pos.get("treatAsChar") == "0" and pos.get("allowOverlap") == "1":
                findings.append({"code": "OVERLAP_CAPABLE_TEXTBOX", "basis": "floating rect and allowOverlap=1; actual obscuring is native-unverified"})

    codes = {item["code"] for item in findings}
    expected_finding = case.get("expectedFinding") or expected.get("expectedStaticFinding")
    static_match = not blockers and (expected_finding in codes if expected_finding else not findings)
    if blockers:
        status = "BLOCKED_EVIDENCE"
    elif case["class"] == "defect":
        status = "STATIC_DEFECT_CANDIDATE_NATIVE_UNVERIFIED" if static_match else "UNVERIFIED_EXPECTED_DEFECT_NOT_IDENTIFIED"
    else:
        status = "STATIC_CONTRACT_MATCH_NATIVE_UNVERIFIED" if static_match else "FALSE_POSITIVE_OR_CONTRACT_DRIFT"
    return {
        "caseId": case["caseId"], "class": case["class"], "source": str(path),
        "sourceSha256": actual_hash, "objects": objects, "binaryAssets": binary_assets,
        "pageGeometry": pages, "markerCounts": marker_counts, "findings": findings,
        "blockers": blockers, "status": status, "nativeLayout": "UNVERIFIED",
        "internalAnchorIdentity": "UNVERIFIED", "editingSupport": "NOT_ASSESSED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only HWPX object-placement contract inspector")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    manifest_path, output = args.manifest.resolve(), args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite inspection output: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError("output parent must already exist")
    manifest_hash = sha256(manifest_path)
    if args.expected_manifest_sha256 and manifest_hash != args.expected_manifest_sha256.lower():
        raise ValueError("manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest.get("cases"), list) or not manifest["cases"]:
        raise ValueError("manifest must contain non-empty cases")
    root = manifest_path.parent
    results = [inspect_case(root, case, manifest.get("assets", {})) for case in manifest["cases"]]
    normals = [item for item in results if item["class"] == "normal"]
    defects = [item for item in results if item["class"] == "defect"]
    blocked = sum(bool(item["blockers"]) for item in results)
    normal_false_positives = sum(item["status"] != "STATIC_CONTRACT_MATCH_NATIVE_UNVERIFIED" for item in normals)
    defects_identified = sum(item["status"] == "STATIC_DEFECT_CANDIDATE_NATIVE_UNVERIFIED" for item in defects)
    summary = {
        "schemaVersion": "object-placement-static-inspection.v2",
        "manifest": str(manifest_path), "manifestSha256": manifest_hash,
        "normalCount": len(normals), "defectCount": len(defects), "blockedCases": blocked,
        "normalFalsePositives": normal_false_positives,
        "defectsIdentifiedAsStaticCandidates": defects_identified,
        "nativeDefectsConfirmed": 0, "nativeStatus": "NOT_RUN",
        "supportBoundary": "Read-only contract screening only; no native layout, internal anchor identity, or editing support conclusion.",
        "results": results,
    }
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", errors="strict")
    print(json.dumps({"output": str(output), "sha256": sha256(output), "normalFalsePositives": normal_false_positives, "staticDefects": defects_identified, "blockedCases": blocked}, ensure_ascii=False))
    return 0 if blocked == 0 and normal_false_positives == 0 and defects_identified == len(defects) else 1


if __name__ == "__main__":
    raise SystemExit(main())
