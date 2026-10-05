#!/usr/bin/env python3
"""Actual positive and eight in-memory rejection regressions."""

from __future__ import annotations

import copy
import argparse
import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location("prototype", Path(__file__).with_name("source_anchored_multiblock_prototype.py"))
prototype = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(prototype)


def expect_unverified(name: str, source: dict, pdf: dict, receipt_reasons: list[str], expected_reason: str, term: str) -> dict:
    result = prototype.evaluate_models(source, pdf, receipt_reasons, term)
    assert result["status"] == "UNVERIFIED", (name, result)
    assert expected_reason in result["reasons"], (name, result)
    return {"name": name, "status": result["status"], "reason": expected_reason}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-hwpx", type=Path, required=True)
    parser.add_argument("--native-pdf", type=Path, required=True)
    parser.add_argument("--native-receipt", type=Path, required=True)
    parser.add_argument("--term", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    hwpx = args.native_hwpx.resolve()
    pdf_path = args.native_pdf.resolve()
    receipt_path = args.native_receipt.resolve()
    term = args.term
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    hwpx_hash = prototype.sha256(hwpx)
    pdf_hash = prototype.sha256(pdf_path)
    receipt_reasons = prototype.verify_receipt(receipt, hwpx, pdf_path, hwpx_hash, pdf_hash)
    assert receipt_reasons == [], receipt_reasons
    source = prototype.extract_source_model(hwpx)
    pdf = prototype.extract_pdf_model(pdf_path)

    positive = prototype.evaluate_models(source, pdf, [], term)
    assert positive["status"] == "OBSERVED_SOURCE_ANCHORED_MULTIBLOCK_RENDERER_FRAGMENT", positive
    assert len(positive["observations"]) == 1
    observation = positive["observations"][0]
    assert observation["blocks"] == [0, 0, 1], observation
    assert observation["lineCount"] == 3, observation

    cases = []

    # 1. The term is split over two source paragraphs: no one-node source anchor.
    altered = copy.deepcopy(source)
    target = next(record for record in altered["records"] if term in record["text"])
    at = target["text"].index(term) + max(1, len(term) - 11)
    left, right = target["text"][:at], target["text"][at:]
    target["text"], target["textNodes"] = left, [left]
    second = copy.deepcopy(target)
    second["text"], second["textNodes"] = right, [right]
    altered["records"].insert(altered["records"].index(target) + 1, second)
    cases.append(expect_unverified("two-source-paragraphs", altered, pdf, [], "SOURCE_TERM_NOT_UNIQUE_SINGLE_TEXT_NODE", term))

    # 2. The same source anchor occurs in two paragraphs.
    altered = copy.deepcopy(source)
    target = next(record for record in altered["records"] if term in record["text"])
    altered["records"].append(copy.deepcopy(target))
    cases.append(expect_unverified("duplicate-source-anchor", altered, pdf, [], "SOURCE_TERM_NOT_UNIQUE_SINGLE_TEXT_NODE", term))

    # 3. A forbidden source structure is declared at the source paragraph.
    altered = copy.deepcopy(source)
    next(record for record in altered["records"] if term in record["text"])["forbiddenStructures"] = ["field"]
    cases.append(expect_unverified("source-structural-seam", altered, pdf, [], "SOURCE_STRUCTURAL_BOUNDARY", term))

    # 4. A PDF character/space/order mutation prevents exact paragraph reconstruction.
    altered_pdf = copy.deepcopy(pdf)
    altered_pdf["pages"][0]["lines"][1]["text"] = altered_pdf["pages"][0]["lines"][1]["text"][:-1]
    cases.append(expect_unverified("pdf-character-loss", source, altered_pdf, [], "PDF_SEQUENCE_NOT_FOUND", term))

    # 5. Geometry consistent with another column/object is rejected.
    altered_pdf = copy.deepcopy(pdf)
    altered_pdf["pages"][0]["lines"][2]["bbox"][0] = altered_pdf["pages"][0]["lines"][1]["bbox"][2] + 20
    altered_pdf["pages"][0]["lines"][2]["bbox"][2] += 500
    cases.append(expect_unverified("other-column-geometry", source, altered_pdf, [], "PDF_SEQUENCE_NOT_FOUND", term))

    # 6. Watched term agreement alone is insufficient when paragraph suffix differs.
    altered_pdf = copy.deepcopy(pdf)
    third_start = observation["splitIndexesInParagraph"][1] - observation["termOffset"]
    altered_pdf["pages"][0]["lines"][2]["text"] = term[third_start:] + " 다른꼬리"
    cases.append(expect_unverified("paragraph-full-mismatch", source, altered_pdf, [], "PDF_SEQUENCE_NOT_FOUND", term))

    # 7. Broken receipt/HWPX/PDF hash binding fails before source/PDF matching.
    cases.append(expect_unverified("receipt-hash-break", source, pdf, ["RECEIPT_ARTIFACT_HASH_OR_PATH"], "RECEIPT_ARTIFACT_HASH_OR_PATH", term))

    # 8. A second valid PDF sequence makes the partition/reading order ambiguous.
    altered_pdf = copy.deepcopy(pdf)
    duplicate_page = copy.deepcopy(altered_pdf["pages"][0])
    duplicate_page["page"] = 3
    altered_pdf["pages"].append(duplicate_page)
    cases.append(expect_unverified("multiple-valid-sequences", source, altered_pdf, [], "PDF_SEQUENCE_AMBIGUOUS", term))

    hardening = []
    altered_receipt = copy.deepcopy(receipt)
    altered_receipt["cleanup"].pop("remaining")
    reasons = prototype.verify_receipt(altered_receipt, hwpx, pdf_path, hwpx_hash, pdf_hash)
    assert "RECEIPT_CLEANUP" in reasons, reasons
    hardening.append("missing-cleanup-remaining-rejected")
    altered_receipt = copy.deepcopy(receipt)
    altered_receipt["artifacts"].append(copy.deepcopy(altered_receipt["artifacts"][0]))
    reasons = prototype.verify_receipt(altered_receipt, hwpx, pdf_path, hwpx_hash, pdf_hash)
    assert "RECEIPT_ARTIFACT_HASH_OR_PATH" in reasons, reasons
    hardening.append("duplicate-required-artifact-rejected")
    benign = prototype.ET.fromstring("<p><run><secPr/><ctrl><colPr colCount='1'/></ctrl></run><run><t>x</t></run></p>")
    assert prototype.unsupported_controls(benign) == []
    hardening.append("known-leading-one-column-control-allowed")
    unknown = prototype.ET.fromstring("<p><run><secPr/><ctrl><colPr colCount='1'/><unknown/></ctrl></run><run><t>x</t></run></p>")
    assert prototype.unsupported_controls(unknown) == ["unsupported-control"]
    hardening.append("unknown-control-payload-rejected")

    payload = {
        "status": "PASS",
        "actualPositive": {
            "status": positive["status"],
            "blocks": observation["blocks"],
            "lineCount": observation["lineCount"],
        },
        "rejectionCount": len(cases),
        "rejections": cases,
        "hardeningCount": len(hardening),
        "hardening": hardening,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
