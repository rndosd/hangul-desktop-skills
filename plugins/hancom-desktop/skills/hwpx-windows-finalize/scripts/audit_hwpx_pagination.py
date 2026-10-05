"""Read-only HWPX/PDF pagination audit.

HWPX mode inventories structural pagination signals without predicting Hancom's
actual layout. PDF mode checks page-level visible-content proxies and expected
text labels. Existing outputs are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
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


def write_new(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def own_text(paragraph: ET.Element) -> str:
    chunks: list[str] = []

    def visit(element: ET.Element, root: bool = False) -> None:
        if not root and local(element.tag) == "p":
            return
        if local(element.tag) == "t":
            chunks.append(element.text or "")
        for child in element:
            visit(child)

    visit(paragraph, root=True)
    return "".join(chunks)


def section_spine(package: zipfile.ZipFile) -> list[str]:
    names = set(package.namelist())
    if "Contents/content.hpf" not in names:
        raise ValueError("content.hpf is missing")
    root = ET.fromstring(package.read("Contents/content.hpf"))
    manifest: dict[str, str] = {}
    spine_ids: list[str] = []
    for element in root.iter():
        name = local(element.tag)
        if name == "item" and element.get("id") and element.get("href"):
            manifest[element.get("id", "")] = element.get("href", "")
        elif name == "itemref" and element.get("idref"):
            spine_ids.append(element.get("idref", ""))
    missing = [item_id for item_id in spine_ids if item_id not in manifest]
    if missing:
        raise ValueError(f"spine references missing manifest items: {missing}")
    sections = [manifest[item_id] for item_id in spine_ids if re.fullmatch(r"Contents/section\d+\.xml", manifest[item_id])]
    if not sections or len(sections) != len(set(sections)):
        raise ValueError("section spine is missing or duplicated")
    absent = [name for name in sections if name not in names]
    if absent:
        raise ValueError(f"spine section parts are missing: {absent}")
    return sections


def audit_hwpx(path: Path) -> dict:
    source_before = sha256(path)
    paragraphs: list[dict] = []
    counts: dict[str, int] = {}
    section_files: list[str] = []
    structure_error: str | None = None
    with zipfile.ZipFile(path) as package:
        try:
            section_files = section_spine(package)
        except ValueError as error:
            source_after = sha256(path)
            return {
                "schemaVersion": 1,
                "mode": "hwpx-preflight",
                "source": str(path.resolve()),
                "sourceSha256": source_before,
                "sourceSha256Before": source_before,
                "sourceSha256After": source_after,
                "sourceUnchanged": source_before == source_after,
                "status": "UNVERIFIED_STRUCTURE",
                "layoutConclusion": "NOT_RENDERED",
                "error": str(error),
            }
        for section_name in section_files:
            root = ET.fromstring(package.read(section_name))
            if local(root.tag) not in {"sec", "section"}:
                structure_error = f"unrecognized section root: {local(root.tag)}"
                break
            for element in root.iter():
                name = local(element.tag)
                counts[name] = counts.get(name, 0) + 1
            for element in list(root):
                if local(element.tag) != "p":
                    continue
                text = own_text(element)
                descendants = [local(node.tag) for node in element.iter()]
                has_table = "tbl" in descendants
                has_picture = "pic" in descendants
                has_control = any(
                    item in descendants
                    for item in ("ctrl", "secd", "pageBreak", "colPr", "header", "footer")
                )
                paragraphs.append(
                    {
                        "section": section_name,
                        "index": len(paragraphs),
                        "text": text,
                        "blank": not text.strip() and not has_table and not has_picture and not has_control,
                        "hasTable": has_table,
                        "hasPicture": has_picture,
                        "hasControl": has_control,
                    }
                )
    if not structure_error and not paragraphs:
        structure_error = "no section-owned paragraphs found"
    trailing = paragraphs[-1] if paragraphs else None
    source_after = sha256(path)
    unchanged = source_before == source_after
    status = (
        "UNVERIFIED_SOURCE_CHANGED"
        if not unchanged
        else "UNVERIFIED_STRUCTURE"
        if structure_error
        else "PREFLIGHT_COMPLETE"
    )
    return {
        "schemaVersion": 1,
        "mode": "hwpx-preflight",
        "source": str(path.resolve()),
        "sourceSha256": source_before,
        "sourceSha256Before": source_before,
        "sourceSha256After": source_after,
        "sourceUnchanged": unchanged,
        "status": status,
        "error": structure_error,
        "layoutConclusion": "NOT_RENDERED",
        "warning": "Structural signals do not determine actual Hancom pagination.",
        "sections": section_files,
        "counts": {
            "paragraphs": len(paragraphs),
            "tables": counts.get("tbl", 0),
            "pictures": counts.get("pic", 0),
            "sectionDefinitions": counts.get("secd", 0),
            "explicitPageBreakElements": counts.get("pageBreak", 0),
        },
        "trailingParagraph": trailing,
        "trailingBlankParagraph": bool(trailing and trailing["blank"]),
    }


def audit_pdf(
    path: Path,
    expected_labels: list[str],
    expected_counts: dict[str, int] | None = None,
    expected_order: list[str] | None = None,
) -> dict:
    import fitz

    expected_counts = {label: 1 for label in expected_labels} | (expected_counts or {})
    expected_order = expected_order or []
    all_labels = list(dict.fromkeys([*expected_labels, *expected_counts, *expected_order]))
    if any(not label for label in all_labels):
        raise ValueError("expected labels and order markers must be non-empty")
    source_before = sha256(path)
    document = fitz.open(path)
    pages: list[dict] = []
    observed = {label: [] for label in all_labels}
    occurrences = {label: [] for label in all_labels}
    for number, page in enumerate(document, start=1):
        text = page.get_text("text")
        drawings = page.get_drawings()
        images = page.get_images(full=True)
        words = page.get_text("words")
        for label in all_labels:
            start = 0
            while True:
                offset = text.find(label, start)
                if offset < 0:
                    break
                occurrences[label].append({"page": number, "textOffset": offset})
                start = offset + len(label)
            if occurrences[label] and occurrences[label][-1]["page"] == number:
                observed[label].append(number)
        pages.append(
            {
                "page": number,
                "textChars": len("".join(text.split())),
                "wordCount": len(words),
                "imageCount": len(images),
                "drawingCount": len(drawings),
                "blankCandidate": not text.strip() and not images and not drawings,
                "nonTextVisualCandidate": not text.strip() and bool(images or drawings),
            }
        )
    document.close()
    source_after = sha256(path)
    source_unchanged = source_before == source_after
    occurrence_counts = {label: len(items) for label, items in occurrences.items()}
    count_mismatches = {
        label: {"expected": count, "actual": occurrence_counts.get(label, 0)}
        for label, count in expected_counts.items()
        if occurrence_counts.get(label, 0) != count
    }
    missing = [
        label
        for label, count in occurrence_counts.items()
        if count == 0 and (expected_counts.get(label, 1) > 0 or label in expected_order)
    ]
    duplicate = {
        label: {"count": count, "pages": [item["page"] for item in occurrences[label]]}
        for label, count in occurrence_counts.items()
        if count > expected_counts.get(label, 1)
    }
    order_positions = {
        label: (
            occurrences[label][0]["page"],
            occurrences[label][0]["textOffset"],
        )
        for label in expected_order
        if occurrences.get(label)
    }
    order_checked = len(order_positions) == len(expected_order)
    order_matched = order_checked and all(
        order_positions[left] < order_positions[right]
        for left, right in zip(expected_order, expected_order[1:])
    )
    order_mismatch = bool(expected_order) and (not order_checked or not order_matched)
    blank_pages = [item["page"] for item in pages if item["blankCandidate"]]
    non_text_pages = [item["page"] for item in pages if item["nonTextVisualCandidate"]]
    return {
        "schemaVersion": 1,
        "mode": "pdf-observation",
        "source": str(path.resolve()),
        "sourceSha256": source_before,
        "sourceSha256Before": source_before,
        "sourceSha256After": source_after,
        "sourceUnchanged": source_unchanged,
        "pageCount": len(pages),
        "pages": pages,
        "expectedLabels": all_labels,
        "expectedLabelCounts": expected_counts,
        "expectedOrder": expected_order,
        "labelPages": observed,
        "labelOccurrences": occurrences,
        "labelOccurrenceCounts": occurrence_counts,
        "labelCountMismatches": count_mismatches,
        "missingLabels": missing,
        "duplicateLabels": duplicate,
        "orderPositions": {label: list(position) for label, position in order_positions.items()},
        "orderChecked": order_checked,
        "orderMatched": order_matched if expected_order else None,
        "blankCandidates": blank_pages,
        "nonTextVisualCandidates": non_text_pages,
        "status": "UNVERIFIED"
        if not source_unchanged or missing or count_mismatches or order_mismatch or blank_pages or non_text_pages
        else "OBSERVED",
        "warning": (
            "Blank candidates require review of native Hancom PDF page images. "
            "Expected order uses extracted page/text sequence only and does not prove visual reading "
            "order in multi-column or independently positioned blocks."
        ),
    }


def parse_expected_counts(values: list[str]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected label count must be LABEL=COUNT: {value}")
        label, raw_count = value.rsplit("=", 1)
        count = int(raw_count)
        if not label or count < 0 or label in parsed:
            raise ValueError(f"invalid or duplicate expected label count: {value}")
        parsed[label] = count
    return parsed


def result_exit_code(payload: dict) -> int:
    return 0 if payload.get("status") in {"OBSERVED", "PREFLIGHT_COMPLETE"} else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    hwpx_parser = subparsers.add_parser("hwpx")
    hwpx_parser.add_argument("source", type=Path)
    hwpx_parser.add_argument("--output", type=Path, required=True)
    pdf_parser = subparsers.add_parser("pdf")
    pdf_parser.add_argument("source", type=Path)
    pdf_parser.add_argument("--expected-label", action="append", default=[])
    pdf_parser.add_argument("--expected-label-count", action="append", default=[])
    pdf_parser.add_argument("--expected-order", action="append", default=[])
    pdf_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.source.is_file():
            raise FileNotFoundError(args.source)
        payload = (
            audit_hwpx(args.source)
            if args.mode == "hwpx"
            else audit_pdf(
                args.source,
                args.expected_label,
                parse_expected_counts(args.expected_label_count) or None,
                args.expected_order,
            )
        )
        write_new(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return result_exit_code(payload)
    except Exception as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
