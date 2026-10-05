#!/usr/bin/env python3
"""Read-only prototype for source-anchored cross-block PDF line evidence.

This is deliberately separate from the installed/default line-break auditor.
It never exports or edits a document.  A positive observation requires a
Hancom OpenOnly receipt that cryptographically binds the exact HWPX and PDF.
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


FORBIDDEN_SOURCE_TAGS = {
    "br", "lineBreak", "tab", "fieldBegin", "fieldEnd", "field", "tbl",
    "table", "tc", "cell", "shape", "pic", "container", "columnBreak",
}


class CliContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, json.dumps({"status": "ERROR", "errorCode": "CLI_ARGUMENT_ERROR"}) + "\n")


def cli_error_code(exc: Exception) -> str:
    if isinstance(exc, CliContractError):
        return exc.code
    if isinstance(exc, FileExistsError):
        return "OUTPUT_EXISTS"
    if isinstance(exc, FileNotFoundError):
        return "INPUT_NOT_FOUND"
    if isinstance(exc, (json.JSONDecodeError, zipfile.BadZipFile, ET.ParseError, UnicodeDecodeError)):
        return "INPUT_PARSE_ERROR"
    if isinstance(exc, PermissionError):
        return "FILE_ACCESS_ERROR"
    if isinstance(exc, ValueError):
        return "INPUT_CONTRACT_ERROR"
    return "INSPECTION_ERROR"


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _section_names(zf: zipfile.ZipFile) -> list[str]:
    names: list[str] = []
    try:
        package = ET.fromstring(zf.read("Contents/content.hpf"))
        hrefs = {x.get("id"): x.get("href") for x in package.iter() if local(x.tag) == "item"}
        for ref in package.iter():
            if local(ref.tag) != "itemref":
                continue
            href = hrefs.get(ref.get("idref"))
            if href and re.fullmatch(r"(?:Contents/)?section\d+\.xml", href):
                normalized = href if href.startswith("Contents/") else "Contents/" + href
                if normalized in zf.namelist():
                    names.append(normalized)
    except KeyError:
        pass
    if names:
        return names
    return sorted(
        (name for name in zf.namelist() if re.fullmatch(r"Contents/section\d+\.xml", name)),
        key=lambda name: int(re.search(r"(\d+)", Path(name).stem).group(1)),
    )


def extract_source_model(hwpx: Path) -> dict:
    records: list[dict] = []
    with zipfile.ZipFile(hwpx) as zf:
        for section_index, name in enumerate(_section_names(zf)):
            root = ET.fromstring(zf.read(name))
            parent = {child: node for node in root.iter() for child in node}
            paragraph_index = 0
            for paragraph in (node for node in root.iter() if local(node.tag) == "p"):
                # Nested cell paragraphs remain records, but table ancestry is explicit.
                ancestors = []
                cursor = paragraph
                while cursor in parent:
                    cursor = parent[cursor]
                    ancestors.append(local(cursor.tag))
                text_nodes = [node for node in paragraph.iter() if local(node.tag) == "t" and not any(
                    other is not paragraph and local(other.tag) == "p"
                    for other in _ancestors(node, parent, stop=paragraph)
                )]
                texts = ["".join(node.itertext()) for node in text_nodes]
                paragraph_text = "".join(texts)
                if not paragraph_text:
                    paragraph_index += 1
                    continue
                forbidden = sorted({
                    local(node.tag) for node in paragraph.iter()
                    if local(node.tag) in FORBIDDEN_SOURCE_TAGS
                } | ({"table-ancestor"} if any(tag in {"tbl", "table", "tc", "cell"} for tag in ancestors) else set()))
                forbidden.extend(unsupported_controls(paragraph))
                col_counts = [
                    int(node.get("colCount", "1"))
                    for node in paragraph.iter()
                    if local(node.tag) == "colPr" and node.get("colCount", "1").isdigit()
                ]
                if any(count != 1 for count in col_counts):
                    forbidden.append("multi-column")
                records.append({
                    "section": section_index,
                    "sectionPart": name,
                    "paragraphIndex": paragraph_index,
                    "paragraphId": paragraph.get("id"),
                    "paraPrIDRef": paragraph.get("paraPrIDRef"),
                    "styleIDRef": paragraph.get("styleIDRef"),
                    "text": paragraph_text,
                    "textSha256": text_sha256(paragraph_text),
                    "textNodes": texts,
                    "forbiddenStructures": sorted(set(forbidden)),
                })
                paragraph_index += 1
    return {"records": records}


def _ancestors(node: ET.Element, parent: dict, stop: ET.Element | None = None):
    cursor = node
    while cursor in parent:
        cursor = parent[cursor]
        if cursor is stop:
            break
        yield cursor


def unsupported_controls(paragraph: ET.Element) -> list[str]:
    """Allow only the known textless leading section/one-column control run."""
    runs = [node for node in paragraph if local(node.tag) == "run"]
    text_run_indexes = [
        index for index, run in enumerate(runs)
        if any(local(node.tag) == "t" for node in run.iter())
    ]
    first_text_run = min(text_run_indexes) if text_run_indexes else len(runs)
    unsupported: list[str] = []
    controls_seen = 0
    for run_index, run in enumerate(runs):
        controls = [node for node in run.iter() if local(node.tag) == "ctrl"]
        for ctrl in controls:
            controls_seen += 1
            ctrl_tags = {local(node.tag) for node in ctrl.iter()}
            columns = [node for node in ctrl.iter() if local(node.tag) == "colPr"]
            benign = (
                run_index < first_text_run
                and not any(local(node.tag) == "t" for node in run.iter())
                and any(local(node.tag) == "secPr" for node in run)
                and ctrl_tags <= {"ctrl", "colPr"}
                and len(columns) == 1
                and columns[0].get("colCount", "1") == "1"
            )
            if not benign:
                unsupported.append("unsupported-control")
    all_controls = sum(1 for node in paragraph.iter() if local(node.tag) == "ctrl")
    if controls_seen != all_controls:
        unsupported.append("control-outside-direct-run")
    return sorted(set(unsupported))


def extract_pdf_model(pdf: Path) -> dict:
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # type: ignore[no-redef]
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for this read-only prototype") from exc
    pages: list[dict] = []
    with fitz.open(pdf) as document:
        for page_no, page in enumerate(document, 1):
            lines: list[dict] = []
            raw = page.get_text("rawdict")
            for block_no, block in enumerate(raw.get("blocks", [])):
                for line_no, line in enumerate(block.get("lines", [])):
                    chars = []
                    for span in line.get("spans", []):
                        for char in span.get("chars", []):
                            chars.append({
                                "c": char.get("c", ""),
                                "bbox": char.get("bbox"),
                                "font": span.get("font"),
                                "size": span.get("size"),
                            })
                    if chars:
                        lines.append({
                            "text": "".join(char["c"] for char in chars),
                            "chars": chars,
                            "bbox": list(line.get("bbox") or []),
                            "direction": list(line.get("dir") or []),
                            "block": block_no,
                            "blockLine": line_no,
                        })
            lines.sort(key=lambda item: (round(item["bbox"][1], 1), item["bbox"][0]))
            pages.append({"page": page_no, "lines": lines})
    return {"pages": pages}


def verify_receipt(receipt: dict, hwpx: Path, pdf: Path, hwpx_hash: str, pdf_hash: str) -> list[str]:
    reasons: list[str] = []
    if receipt.get("evidenceSchema") != "hwpx.hancom-finalize.v2":
        reasons.append("RECEIPT_SCHEMA")
    if receipt.get("status") != "PASS_FULL" or receipt.get("mode") != "OpenOnly":
        reasons.append("RECEIPT_STATUS_OR_MODE")
    if not receipt.get("firstOpen") or not receipt.get("reopen") or not receipt.get("pdfExport"):
        reasons.append("RECEIPT_OPEN_EXPORT_CONTRACT")
    if not receipt.get("sourceUnchanged"):
        reasons.append("RECEIPT_SOURCE_CHANGED")
    before = str(receipt.get("sourceSha256Before", "")).lower()
    after = str(receipt.get("sourceSha256After", "")).lower()
    if before != hwpx_hash or after != hwpx_hash:
        reasons.append("RECEIPT_SOURCE_HASH")
    cleanup = receipt.get("cleanup") or {}
    if cleanup.get("quit") is not True or cleanup.get("forced") is not False or cleanup.get("remaining") != []:
        reasons.append("RECEIPT_CLEANUP")
    artifacts = receipt.get("artifacts") or []
    expected = {str(hwpx.resolve()).lower(): hwpx_hash, str(pdf.resolve()).lower(): pdf_hash}
    artifact_matches = {
        path: [
            item for item in artifacts
            if item.get("path") and str(Path(item["path"]).resolve()).lower() == path
        ] for path in expected
    }
    if any(
        len(artifact_matches[path]) != 1
        or str(artifact_matches[path][0].get("sha256", "")).lower() != digest
        for path, digest in expected.items()
    ):
        reasons.append("RECEIPT_ARTIFACT_HASH_OR_PATH")
    return sorted(set(reasons))


def _adjacent_geometry(a: dict, b: dict) -> bool:
    if len(a.get("bbox", [])) != 4 or len(b.get("bbox", [])) != 4:
        return False
    ah = a["bbox"][3] - a["bbox"][1]
    bh = b["bbox"][3] - b["bbox"][1]
    gap = b["bbox"][1] - a["bbox"][3]
    overlap = min(a["bbox"][2], b["bbox"][2]) - max(a["bbox"][0], b["bbox"][0])
    return b["bbox"][1] > a["bbox"][1] + min(ah, bh) * 0.5 and gap <= max(ah, bh) * 1.5 and overlap > 0


def _sequence_safety(lines: list[dict]) -> list[str]:
    reasons: list[str] = []
    directions = {tuple(line.get("direction") or []) for line in lines}
    if directions != {(1.0, 0.0)}:
        reasons.append("NON_HORIZONTAL_LTR_OR_MIXED_DIRECTION")
    if not all(_adjacent_geometry(a, b) for a, b in zip(lines, lines[1:])):
        reasons.append("NON_ADJACENT_GEOMETRY")
    glyphs = [char for line in lines for char in line.get("chars", [])]
    fonts = {char.get("font") for char in glyphs}
    sizes = [float(char.get("size") or 0) for char in glyphs]
    if len(fonts) != 1 or not sizes or max(sizes) - min(sizes) > 0.01:
        reasons.append("MIXED_MATCHED_GLYPH_STYLE")
    if len({line.get("block") for line in lines}) < 2:
        reasons.append("NOT_CROSS_BLOCK")
    return reasons


def evaluate_models(source_model: dict, pdf_model: dict, receipt_reasons: list[str], term: str, max_lines: int = 4) -> dict:
    if receipt_reasons:
        return {"status": "UNVERIFIED", "reasons": receipt_reasons, "observations": []}
    records = source_model.get("records", [])
    occurrences = []
    for index, record in enumerate(records):
        for node_index, node_text in enumerate(record.get("textNodes", [])):
            start = 0
            while True:
                found = node_text.find(term, start)
                if found < 0:
                    break
                occurrences.append((index, node_index, found))
                start = found + 1
    if len(occurrences) != 1:
        return {"status": "UNVERIFIED", "reasons": ["SOURCE_TERM_NOT_UNIQUE_SINGLE_TEXT_NODE"], "observations": []}
    record_index, node_index, offset = occurrences[0]
    record = records[record_index]
    if record.get("forbiddenStructures"):
        return {"status": "UNVERIFIED", "reasons": ["SOURCE_STRUCTURAL_BOUNDARY"], "sourceForbiddenStructures": record["forbiddenStructures"], "observations": []}
    paragraph = record["text"]
    if paragraph.count(term) != 1 or record["textNodes"][node_index].count(term) != 1:
        return {"status": "UNVERIFIED", "reasons": ["SOURCE_TERM_AMBIGUOUS_IN_PARAGRAPH"], "observations": []}
    neighbors = []
    for direction, candidate_index in (("previous", record_index - 1), ("next", record_index + 1)):
        if 0 <= candidate_index < len(records):
            neighbor_text = records[candidate_index]["text"]
            if sum(item["text"].count(neighbor_text) for item in records) != 1:
                return {"status": "UNVERIFIED", "reasons": ["SOURCE_NEIGHBOR_NOT_UNIQUE"], "observations": []}
            neighbors.append((direction, neighbor_text))
    if not neighbors:
        return {"status": "UNVERIFIED", "reasons": ["SOURCE_NEIGHBOR_MISSING"], "observations": []}

    candidates = []
    exact_safe_sequence_count = 0
    paragraph_pdf_occurrences = 0
    for page in pdf_model.get("pages", []):
        lines = page.get("lines", [])
        for line in lines:
            paragraph_pdf_occurrences += line.get("text", "").count(paragraph)
        for count in range(2, max_lines + 1):
            for start in range(len(lines) - count + 1):
                sequence = lines[start:start + count]
                joined = "".join(line["text"] for line in sequence)
                if joined != paragraph or term not in joined:
                    continue
                safety = _sequence_safety(sequence)
                if safety:
                    continue
                exact_safe_sequence_count += 1
                neighbor_evidence = []
                valid_neighbors = True
                for direction, neighbor_text in neighbors:
                    neighbor_hits = [
                        (p["page"], i) for p in pdf_model.get("pages", [])
                        for i, line in enumerate(p.get("lines", [])) if line.get("text") == neighbor_text
                    ]
                    if len(neighbor_hits) != 1:
                        valid_neighbors = False
                        break
                    if direction == "previous":
                        valid_neighbors &= start > 0 and lines[start - 1].get("text") == neighbor_text
                    else:
                        valid_neighbors &= start + count < len(lines) and lines[start + count].get("text") == neighbor_text
                    neighbor_evidence.append({"direction": direction, "textSha256": text_sha256(neighbor_text)})
                if not valid_neighbors:
                    continue
                term_start = paragraph.index(term)
                boundaries = []
                cursor = 0
                for line in sequence[:-1]:
                    cursor += len(line["text"])
                    boundaries.append(cursor)
                if not any(term_start < boundary < term_start + len(term) for boundary in boundaries):
                    continue
                candidates.append({
                    "page": page["page"],
                    "lineCount": count,
                    "blocks": [line["block"] for line in sequence],
                    "blockLines": [line["blockLine"] for line in sequence],
                    "splitIndexesInParagraph": boundaries,
                    "paragraphTextSha256": record["textSha256"],
                    "termOffset": offset,
                    "source": {
                        "sectionPart": record["sectionPart"],
                        "paragraphIndex": record["paragraphIndex"],
                        "paragraphId": record["paragraphId"],
                        "paraPrIDRef": record["paraPrIDRef"],
                        "styleIDRef": record["styleIDRef"],
                        "textNodeIndex": node_index,
                    },
                    "neighborEvidence": neighbor_evidence,
                })
    if exact_safe_sequence_count > 1:
        return {"status": "UNVERIFIED", "reasons": ["PDF_SEQUENCE_AMBIGUOUS"], "candidateSequenceCount": exact_safe_sequence_count, "observations": []}
    if paragraph_pdf_occurrences:
        return {"status": "UNVERIFIED", "reasons": ["PARAGRAPH_NOT_MULTILINE_UNIQUE"], "observations": []}
    if len(candidates) != 1:
        reason = "PDF_SEQUENCE_NOT_FOUND" if not candidates else "PDF_SEQUENCE_AMBIGUOUS"
        return {"status": "UNVERIFIED", "reasons": [reason], "candidateSequenceCount": len(candidates), "observations": []}
    return {
        "status": "OBSERVED_SOURCE_ANCHORED_MULTIBLOCK_RENDERER_FRAGMENT",
        "reasons": [],
        "observations": candidates,
    }


def inspect(hwpx: Path, pdf: Path, receipt_path: Path, term: str, max_lines: int = 4) -> dict:
    hwpx = hwpx.resolve()
    pdf = pdf.resolve()
    receipt_path = receipt_path.resolve()
    before = {"hwpx": sha256(hwpx), "pdf": sha256(pdf), "receipt": sha256(receipt_path)}
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    source_model = extract_source_model(hwpx)
    pdf_model = extract_pdf_model(pdf)
    receipt_reasons = verify_receipt(receipt, hwpx, pdf, before["hwpx"], before["pdf"])
    result = evaluate_models(source_model, pdf_model, receipt_reasons, term, max_lines=max_lines)
    after = {"hwpx": sha256(hwpx), "pdf": sha256(pdf), "receipt": sha256(receipt_path)}
    if before != after:
        result = {"status": "UNVERIFIED", "reasons": ["INPUT_CHANGED_DURING_INSPECTION"], "observations": []}
    result.update({
        "schemaVersion": 1,
        "mode": "source-anchored-multiblock-read-only-prototype",
        "termSha256": text_sha256(term),
        "inputs": {
            "hwpx": {"path": str(hwpx), "sha256": before["hwpx"]},
            "pdf": {"path": str(pdf), "sha256": before["pdf"]},
            "receipt": {"path": str(receipt_path), "sha256": before["receipt"]},
        },
        "inputsUnchanged": before == after,
        "limitations": [
            "This observation describes extracted native-PDF coordinates; it does not prove exporter internals.",
            "Outlined, image-only, or incorrectly decoded PDF text remains UNVERIFIED.",
            "No natural-language awkwardness judgment is made.",
        ],
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--source-hwpx", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--term", required=True)
    parser.add_argument("--max-lines", type=int, choices=(2, 3, 4), default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.term:
            raise CliContractError("EMPTY_TERM")
        if args.output.exists():
            raise FileExistsError
        result = inspect(args.source_hwpx, args.pdf, args.receipt, args.term, args.max_lines)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "errorCode": cli_error_code(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result["status"].startswith("OBSERVED_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
