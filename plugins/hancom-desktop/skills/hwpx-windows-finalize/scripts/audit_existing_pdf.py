#!/usr/bin/env python3
"""Read-only PDF content audit for an already-rendered HWPX candidate.

This helper never starts Hancom, writes HWPX/PDF, or invokes a renderer.  It
compares exact, pre-enumerated labels from source HWPX text with PDF extraction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_labels(path: Path, pattern: str) -> list[str]:
    """Enumerate expected labels from source HWPX; raw XML is read, never edited."""
    with zipfile.ZipFile(path) as archive:
        sections = [name for name in archive.namelist() if name.startswith("Contents/section") and name.endswith(".xml")]
        labels: list[str] = []
        for name in sections:
            root = ET.fromstring(archive.read(name))
            # Attributes, style IDs, and non-text controls are deliberately not
            # source inventory. Only visible text nodes may supply labels.
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] == "t":
                    labels.extend(re.findall(pattern, element.text or ""))
    return labels


def extract_pages(path: Path) -> list[str]:
    from pypdf import PdfReader  # Optional dependency; import only for extraction.
    return [(page.extract_text() or "") for page in PdfReader(str(path)).pages]


def audit_pdf(pdf: Path, expected_labels: list[str], extractor: Callable[[Path], list[str]] = extract_pages) -> dict:
    result: dict = {
        "schema": "hwpx.existing-pdf-audit.v1",
        "pdf": str(pdf),
        "pdf_sha256": None,
        "inspection_state": "not_checked",
        "extraction_status": "not_performed",
        "render_status": "render_not_performed",
        "expected_label_counts": dict(Counter(expected_labels)),
        "observed_label_counts": {},
        "findings": [],
    }
    if not expected_labels:
        result["reason"] = "empty_expected_labels"
        return result
    ambiguous = sorted({label for label in expected_labels for other in expected_labels if label != other and label in other})
    if ambiguous:
        result.update(reason="ambiguous_expected_labels", ambiguous_labels=ambiguous)
        return result
    if not pdf.is_file():
        result["reason"] = "missing_pdf"
        return result
    result["pdf_sha256"] = sha256(pdf)
    try:
        pages = extractor(pdf)
    except ModuleNotFoundError as error:
        result.update(reason="missing_dependency", dependency=error.name)
        return result
    except Exception as error:
        result.update(reason="extraction_failed", error_type=type(error).__name__)
        return result

    expected = Counter(expected_labels)
    observed = Counter()
    page_results = []
    for number, text in enumerate(pages, start=1):
        # Match the source-provided strings exactly.  Do not infer clipping from
        # an ungrounded number regex; PDF extractors can concatenate cell text.
        counts = {label: text.count(label) for label in expected}
        observed.update(counts)
        sparse = len(text.strip()) < 80
        page_results.append({"page": number, "characters": len(text.strip()), "label_counts": counts, "sparse": sparse})
        if sparse:
            result["findings"].append({"kind": "sparse_page", "severity": "warning", "page": number})
    missing = {label: expected[label] - observed[label] for label in expected if observed[label] < expected[label]}
    duplicates = {label: observed[label] - expected[label] for label in expected if observed[label] > expected[label]}
    if missing:
        result["findings"].append({"kind": "source_labels_missing_from_pdf", "severity": "error", "counts": missing})
    if duplicates:
        result["findings"].append({"kind": "source_labels_duplicated_in_pdf", "severity": "error", "counts": duplicates})
    result.update(
        inspection_state="checked",
        extraction_status="performed",
        pages=page_results,
        observed_label_counts=dict(observed),
        missing_label_counts=missing,
        duplicate_label_counts=duplicates,
        outcome="content_mismatch" if missing or duplicates else "checked_no_source_label_mismatch",
    )
    return result


def unsafe_output_reason(output: Path | None, inputs: list[Path]) -> str | None:
    if output is None:
        return None
    resolved = output.resolve()
    if any(resolved == path.resolve() for path in inputs):
        return "unsafe_output_matches_input"
    if output.exists():
        return "unsafe_output_already_exists"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of an existing PDF against source HWPX labels.")
    parser.add_argument("pdf", type=Path)
    labels = parser.add_mutually_exclusive_group(required=True)
    labels.add_argument("--expected-label", action="append", help="Exact expected label; repeat for each source label.")
    labels.add_argument("--source-hwpx", type=Path, help="Source HWPX from which labels are enumerated.")
    parser.add_argument("--source-label-regex", help="Regex used only to enumerate source labels; required with --source-hwpx.")
    parser.add_argument("--output", type=Path, help="Write the same JSON to this path.")
    args = parser.parse_args()
    if args.source_hwpx and not args.source_label_regex:
        parser.error("--source-label-regex is required with --source-hwpx")
    unsafe = unsafe_output_reason(args.output, [args.pdf, args.source_hwpx] if args.source_hwpx else [args.pdf])
    if unsafe:
        result = {"schema": "hwpx.existing-pdf-audit.v1", "inspection_state": "not_checked", "reason": unsafe, "render_status": "render_not_performed"}
    else:
      try:
        expected = args.expected_label or source_labels(args.source_hwpx, args.source_label_regex)
      except (OSError, zipfile.BadZipFile, ET.ParseError, re.error) as error:
        result = {"schema": "hwpx.existing-pdf-audit.v1", "inspection_state": "not_checked", "reason": "source_label_inventory_failed", "error_type": type(error).__name__, "render_status": "render_not_performed"}
      else:
        result = audit_pdf(args.pdf, expected)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output and not unsafe:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text + "\n")
    if result["inspection_state"] != "checked":
        return 2
    return 3 if result.get("outcome") == "content_mismatch" else 0


if __name__ == "__main__":
    sys.exit(main())
