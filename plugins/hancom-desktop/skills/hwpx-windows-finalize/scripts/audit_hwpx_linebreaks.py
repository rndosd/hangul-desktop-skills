#!/usr/bin/env python3
"""Read-only screening of HWPX layout risk and PDF Korean word splits.

The HWPX pass reports structural risk only.  The PDF pass uses character
coordinates from a PDF and reports observed line-boundary splits.  Neither
pass edits its input, uploads content, or treats missing text as a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_new(path: Path, payload: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def parse_expected_totals(values: list[str], terms: list[str]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for value in values:
        term, separator, count_text = value.rpartition("=")
        if not separator or not term or not count_text:
            raise ValueError("--expected-total must use TERM=COUNT")
        if term not in terms:
            raise ValueError(f"--expected-total term is not watched: {term}")
        try:
            count = int(count_text)
        except ValueError as exc:
            raise ValueError(f"--expected-total count must be an integer: {value}") from exc
        if count < 0:
            raise ValueError(f"--expected-total count must be non-negative: {value}")
        if term in expected:
            raise ValueError(f"--expected-total is duplicated for term: {term}")
        expected[term] = count
    return expected


def child_text_without_nested_paragraphs(p: ET.Element) -> str:
    chunks: list[str] = []

    def visit(node: ET.Element) -> None:
        for child in node:
            if child is not p and local(child.tag) == "p":
                continue
            if local(child.tag) == "t":
                chunks.append("".join(child.itertext()))
            else:
                visit(child)

    visit(p)
    return "".join(chunks)


def own_descendants(p: ET.Element, wanted: str) -> list[ET.Element]:
    found: list[ET.Element] = []
    def visit(node: ET.Element) -> None:
        for child in node:
            if child is not p and local(child.tag) == "p":
                continue
            if local(child.tag) == wanted:
                found.append(child)
            visit(child)
    visit(p)
    return found


def header_maps(root: ET.Element) -> tuple[dict[str, dict], dict[str, dict]]:
    chars: dict[str, dict] = {}
    paras: dict[str, dict] = {}
    for e in root.iter():
        kind = local(e.tag)
        ident = e.get("id")
        if kind == "charPr" and ident is not None:
            ratio = None
            spacing = None
            for x in e.iter():
                if local(x.tag) == "ratio" and ratio is None:
                    ratio = x.get("hangul") or x.get("latin")
                if local(x.tag) == "spacing" and spacing is None:
                    spacing = x.get("hangul") or x.get("latin")
            height = e.get("height")
            chars[ident] = {
                "fontSizePt": round(float(height) / 100, 2) if height is not None else None,
                "charRatioPercent": float(ratio) if ratio is not None else None,
                "charSpacingPercent": float(spacing) if spacing is not None else None,
            }
        elif kind == "paraPr" and ident is not None:
            line_wrap = None
            for x in e.iter():
                if local(x.tag) in {"lineWrap", "breakSetting"}:
                    line_wrap = dict(x.attrib)
                    break
            paras[ident] = {"lineWrapSetting": line_wrap}
    return chars, paras


def preflight(args: argparse.Namespace) -> dict:
    source = args.hwpx.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.output.resolve().exists():
        raise FileExistsError(f"output already exists: {args.output.resolve()}")
    source_hash = sha256(source)
    candidates = []
    with zipfile.ZipFile(source) as zf:
        header = ET.fromstring(zf.read("Contents/header.xml"))
        char_map, para_map = header_maps(header)
        sections: list[str] = []
        ordering_source = "numeric-section-fallback"
        try:
            package = ET.fromstring(zf.read("Contents/content.hpf"))
            hrefs = {x.get("id"): x.get("href") for x in package.iter() if local(x.tag) == "item"}
            spine_refs = [x for x in package.iter() if local(x.tag) == "itemref"]
            for ref in spine_refs:
                href = hrefs.get(ref.get("idref"))
                if href and re.fullmatch(r"(?:Contents/)?section\d+\.xml", href):
                    normalized = href if href.startswith("Contents/") else "Contents/" + href
                    if normalized in zf.namelist():
                        sections.append(normalized)
            if spine_refs and not sections:
                raise ValueError("content.hpf spine exists but contains no usable section reference")
            if sections:
                ordering_source = "content.hpf-spine"
        except KeyError:
            pass
        if not sections:
            sections = sorted(
                (n for n in zf.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
                key=lambda n: int(re.search(r"(\d+)", Path(n).stem).group(1)),
            )
        p_index = 0
        for section_no, name in enumerate(sections):
            root = ET.fromstring(zf.read(name))

            def walk(node: ET.Element, cell_width: int | None = None, table_depth: int = 0) -> None:
                nonlocal p_index
                kind = local(node.tag)
                if kind in {"tc", "cell"}:
                    table_depth += 1
                    width_nodes = [x for x in node if local(x.tag) == "cellSz"]
                    if width_nodes and width_nodes[0].get("width"):
                        cell_width = int(width_nodes[0].get("width", "0"))
                if kind == "p":
                    text = child_text_without_nested_paragraphs(node)
                    if text.strip():
                        runs = [x for x in node if local(x.tag) == "run"]
                        styles = [char_map.get(x.get("charPrIDRef", ""), {}) for x in runs]
                        sizes = sorted({s.get("fontSizePt") for s in styles if s.get("fontSizePt")})
                        ratios = sorted({s.get("charRatioPercent") for s in styles if s.get("charRatioPercent") is not None})
                        spacings = sorted({s.get("charSpacingPercent") for s in styles if s.get("charSpacingPercent") is not None})
                        line_widths = [int(x.get("horzsize")) for x in own_descendants(node, "lineseg") if x.get("horzsize")]
                        usable_width = cell_width or (max(line_widths) if line_widths else None)
                        hangul = len(re.findall(r"[가-힣]", text))
                        max_size = max(sizes) if sizes else None
                        # Conservative density signal only; HWPUNIT/pt relation is approximate.
                        estimated_units = None
                        density = None
                        if max_size and usable_width:
                            ratio = max(ratios) / 100 if ratios else 1.0
                            spacing = 1 + ((max(spacings) if spacings else 0) / 100)
                            estimated_units = round(len(text) * max_size * 100 * ratio * spacing)
                            density = round(estimated_units / usable_width, 3)
                        term_hits = [term for term in args.term if term in text]
                        if term_hits or (density is not None and density >= args.density_threshold):
                            candidates.append({
                                "paragraphIndex": p_index,
                                "section": section_no,
                                "inTableDepth": table_depth,
                                "cellWidthHwpUnit": cell_width,
                                "availableWidthHwpUnit": usable_width,
                                "textChars": len(text),
                                "hangulChars": hangul,
                                "fontSizesPt": sizes,
                                "charRatiosPercent": ratios,
                                "charSpacingsPercent": spacings,
                                "lineWrapSetting": para_map.get(node.get("paraPrIDRef", ""), {}).get("lineWrapSetting"),
                                "storedLineSegmentCount": len(line_widths),
                                "estimatedWidthHwpUnit": estimated_units,
                                "estimatedDensity": density,
                                "estimatedParagraphWidthRatio": density,
                                "matchedTerms": term_hits,
                                "riskReasons": (["contains_watched_term"] if term_hits else []) + (["estimated_dense"] if density is not None and density >= args.density_threshold else []),
                            })
                    p_index += 1
                    # Nested paragraphs are walked independently below.
                for child in node:
                    walk(child, cell_width, table_depth)

            walk(root)
    source_unchanged = sha256(source) == source_hash
    result = {
        "schemaVersion": 1,
        "mode": "hwpx-preflight-risk-only",
        "source": {"path": str(source), "sha256": source_hash},
        "sourceUnchanged": source_unchanged,
        "terms": args.term,
        "sectionOrderingSource": ordering_source,
        "status": "RISK_SCREEN_ONLY" if source_unchanged else "UNVERIFIED_SOURCE_CHANGED",
        "paragraphsSeen": p_index,
        "candidateCount": len(candidates),
        "candidates": candidates,
        "limitations": [
            "Width estimation is conservative and does not prove an actual line break.",
            "estimatedDensity/estimatedParagraphWidthRatio compares the whole paragraph estimate with one declared width; multi-line values can exceed 1 without overflow.",
            "Cell width is the raw declared width; margins, indentation, and other usable-width reductions are not modeled.",
            "Stored line segments may be stale until the exact HWPX is laid out by Hancom Hangul.",
        ],
    }
    write_new(args.output, result)
    return result


def pdf_lines(page) -> list[dict]:
    lines = []
    raw = page.get_text("rawdict")
    for block_no, block in enumerate(raw.get("blocks", [])):
        for line_no, line in enumerate(block.get("lines", [])):
            chars = []
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    styled = dict(char)
                    styled["_font"] = span.get("font")
                    styled["_size"] = span.get("size")
                    chars.append(styled)
            visible = [c for c in chars if c.get("c")]
            leading_whitespace = ""
            trailing_whitespace = ""
            while visible and visible[0]["c"].isspace():
                leading_whitespace += visible[0]["c"]
                visible.pop(0)
            while visible and visible[-1]["c"].isspace():
                trailing_whitespace = visible[-1]["c"] + trailing_whitespace
                visible.pop()
            if visible:
                lines.append({"text": "".join(c["c"] for c in visible), "chars": visible, "leadingWhitespace": leading_whitespace, "trailingWhitespace": trailing_whitespace, "bbox": line.get("bbox"), "direction": tuple(line.get("dir") or ()), "block": block_no, "line": line_no})
    lines.sort(key=lambda x: (round(x["bbox"][1], 1), x["bbox"][0]))
    return lines


def same_boundary_style(a: dict, b: dict) -> bool:
    return (
        a["chars"][-1].get("_font") == b["chars"][0].get("_font")
        and abs((a["chars"][-1].get("_size") or 0) - (b["chars"][0].get("_size") or 0)) <= 0.01
    )


def lines_are_adjacent(a: dict, b: dict) -> bool:
    ah = a["bbox"][3] - a["bbox"][1]
    bh = b["bbox"][3] - b["bbox"][1]
    vertically_next = b["bbox"][1] > a["bbox"][1] + min(ah, bh) * 0.5
    vertical_gap = b["bbox"][1] - a["bbox"][3]
    overlap = min(a["bbox"][2], b["bbox"][2]) - max(a["bbox"][0], b["bbox"][0])
    return vertically_next and vertical_gap <= max(ah, bh) * 1.5 and overlap > 0


def boundary_candidates(term: str, a: dict, b: dict, *, safe_only: bool = True) -> list[dict]:
    rendered_boundary_whitespace = a.get("trailingWhitespace", "") + b.get("leadingWhitespace", "")
    same_direction = a.get("direction") == b.get("direction") and a.get("direction") and len(a["direction"]) == 2 and abs(a["direction"][0] - 1.0) <= 0.01 and abs(a["direction"][1]) <= 0.01
    safe_line_pair = a["block"] == b["block"] and b["line"] == a["line"] + 1 and same_direction and same_boundary_style(a, b)
    candidates = [{"leftEnd": cut, "rightStart": cut, "splitKind": None} for cut in range(1, len(term))] if not rendered_boundary_whitespace else []
    one_rendered_boundary_space = (
        (a.get("trailingWhitespace") == " " and b.get("leadingWhitespace") == "")
        or (a.get("trailingWhitespace") == "" and b.get("leadingWhitespace") == " ")
    )
    if (safe_line_pair or not safe_only) and one_rendered_boundary_space:
        for whitespace in re.finditer(r"\s+", term):
            if whitespace.group() == " ":
                candidates.append({
                    "leftEnd": whitespace.start(),
                    "rightStart": whitespace.end(),
                    "splitKind": "AT_SOURCE_WHITESPACE",
                    "boundaryWhitespace": whitespace.group(),
                })
    return candidates


def split_candidates(term: str, a: dict, b: dict) -> list[dict]:
    """Return bounded term splits across two already-related PDF lines.

    ``pdf_lines`` trims boundary whitespace for ordinary matching.  Preserve
    enough metadata to accept exactly one rendered U+0020 that corresponds to
    exactly one U+0020 inside the watched term.  Require the same PDF text
    block and boundary style.  Do not remove whitespace elsewhere or join
    different blocks.
    """
    matches = []
    for boundary in boundary_candidates(term, a, b):
        left, right = term[: boundary["leftEnd"]], term[boundary["rightStart"] :]
        if a["text"].endswith(left) and b["text"].startswith(right):
            match = {"left": left, "right": right, "splitIndex": boundary["leftEnd"], "splitKind": boundary["splitKind"]}
            if boundary.get("boundaryWhitespace") is not None:
                match["boundaryWhitespace"] = boundary["boundaryWhitespace"]
            matches.append(match)
    return matches


def multiline_partitions(term: str, lines: list[dict]) -> list[dict]:
    if len(lines) < 3:
        return []
    matches = []
    boundary_sets = [boundary_candidates(term, a, b, safe_only=False) for a, b in zip(lines, lines[1:])]
    boundary_sets[0] = [item for item in boundary_sets[0] if lines[0]["text"].endswith(term[: item["leftEnd"]])]
    boundary_sets[-1] = [item for item in boundary_sets[-1] if lines[-1]["text"].startswith(term[item["rightStart"] :])]
    if any(not items for items in boundary_sets):
        return []
    for boundaries in itertools.product(*boundary_sets):
        if any(a["rightStart"] >= b["leftEnd"] for a, b in zip(boundaries, boundaries[1:])):
            continue
        segments = [term[: boundaries[0]["leftEnd"]]]
        segments.extend(term[a["rightStart"] : b["leftEnd"]] for a, b in zip(boundaries, boundaries[1:]))
        segments.append(term[boundaries[-1]["rightStart"] :])
        if any(not segment for segment in segments):
            continue
        if not lines[0]["text"].endswith(segments[0]) or not lines[-1]["text"].startswith(segments[-1]):
            continue
        if any(line["text"] != segment for line, segment in zip(lines[1:-1], segments[1:-1])):
            continue
        whitespace = [boundary.get("boundaryWhitespace") for boundary in boundaries]
        matches.append({
            "segments": segments,
            "splitIndexes": [boundary["leftEnd"] for boundary in boundaries],
            "splitKind": "MULTILINE_WITH_SOURCE_WHITESPACE" if any(item is not None for item in whitespace) else "MULTILINE_WITHIN_TERM",
            "boundaryWhitespaces": whitespace,
        })
    return matches


def matched_glyphs(lines: list[dict], segments: list[str]) -> list[dict]:
    glyphs = []
    for index, (line, segment) in enumerate(zip(lines, segments)):
        if index == 0:
            glyphs.extend(line["chars"][-len(segment) :])
        elif index == len(lines) - 1:
            glyphs.extend(line["chars"][: len(segment)])
        else:
            glyphs.extend(line["chars"])
    return glyphs


def multiline_safety_reasons(lines: list[dict], segments: list[str]) -> list[str]:
    reasons = []
    if len({line["block"] for line in lines}) != 1:
        reasons.append("DIFFERENT_BLOCKS")
    elif any(b["line"] != a["line"] + 1 for a, b in zip(lines, lines[1:])):
        reasons.append("NONCONSECUTIVE_BLOCK_LINES")
    directions = [line.get("direction") for line in lines]
    if len(set(directions)) != 1 or not directions or len(directions[0]) != 2 or abs(directions[0][0] - 1.0) > 0.01 or abs(directions[0][1]) > 0.01:
        reasons.append("NON_HORIZONTAL_LTR_OR_MIXED_DIRECTION")
    if not all(lines_are_adjacent(a, b) for a, b in zip(lines, lines[1:])):
        reasons.append("NON_ADJACENT_GEOMETRY")
    glyphs = matched_glyphs(lines, segments)
    fonts = {glyph.get("_font") for glyph in glyphs}
    sizes = [glyph.get("_size") or 0 for glyph in glyphs]
    if len(fonts) != 1 or not sizes or max(sizes) - min(sizes) > 0.01:
        reasons.append("MIXED_MATCHED_GLYPH_STYLE")
    return reasons


def multiline_candidates(term: str, lines: list[dict]) -> list[dict]:
    return [match for match in multiline_partitions(term, lines) if not multiline_safety_reasons(lines, match["segments"])]


def inspect_pdf(args: argparse.Namespace) -> dict:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF/fitz is required for PDF inspection") from exc
    source = args.pdf.resolve()
    max_split_lines = getattr(args, "max_split_lines", 2)
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.output.resolve().exists():
        raise FileExistsError(f"output already exists: {args.output.resolve()}")
    source_hash = sha256(source)
    hwpx = args.source_hwpx.resolve() if args.source_hwpx else None
    if hwpx and not hwpx.is_file():
        raise FileNotFoundError(hwpx)
    hwpx_hash = sha256(hwpx) if hwpx else None
    crop_root = args.crop_dir.resolve() if args.crop_dir else None
    if crop_root and crop_root.exists():
        raise FileExistsError(f"crop directory must be new: {crop_root}")
    findings = []
    multiline_diagnostics = []
    term_counts = Counter()
    page_term_counts = Counter()
    with fitz.open(source) as doc:
        text_pages = 0
        pages_without_text = []
        for page_no, page in enumerate(doc, 1):
            lines = pdf_lines(page)
            if lines:
                text_pages += 1
            else:
                pages_without_text.append(page_no)
            for term in args.term:
                same_line = sum(line["text"].count(term) for line in lines)
                term_counts[(term, "sameLine")] += same_line
                page_term_counts[(page_no, term)] += same_line
                for a, b in zip(lines, lines[1:]):
                    if not lines_are_adjacent(a, b):
                        continue
                    for match in split_candidates(term, a, b):
                        left, right = match["left"], match["right"]
                        cut = match["splitIndex"]
                        boxes = [a["chars"][-len(left)]["bbox"], a["chars"][-1]["bbox"], b["chars"][0]["bbox"], b["chars"][len(right)-1]["bbox"]]
                        bbox = [min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)]
                        if match["splitKind"]:
                            split_kind = match["splitKind"]
                        elif term.startswith("결정"):
                            split_kind = "WITHIN_DECISION" if cut < len("결정") else ("AFTER_DECISION" if cut == len("결정") else "LATER_IN_TERM")
                        else:
                            split_kind = "WITHIN_TERM"
                        finding = {"page": page_no, "term": term, "split": f"{left}/{right}", "splitIndex": cut, "splitIndexes": [cut], "splitKind": split_kind, "lineCount": 2, "bbox": [round(v, 2) for v in bbox]}
                        if match.get("boundaryWhitespace") is not None:
                            finding["boundaryWhitespace"] = match["boundaryWhitespace"]
                        findings.append(finding)
                        term_counts[(term, "splitAcrossLines")] += 1
                        page_term_counts[(page_no, term)] += 1
                        if crop_root:
                            crop_root.mkdir(parents=True, exist_ok=True)
                            crop = crop_root / f"finding-{len(findings):04d}_page-{page_no:04d}.png"
                            rect = fitz.Rect(bbox) + (-18, -12, 18, 12)
                            page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect).save(crop)
                            finding["crop"] = str(crop)
                for line_count in range(3, max_split_lines + 1):
                    for start in range(0, len(lines) - line_count + 1):
                        sequence = lines[start : start + line_count]
                        partitions = multiline_partitions(term, sequence)
                        if len(partitions) > 1:
                            multiline_diagnostics.append({
                                "page": page_no,
                                "term": term,
                                "status": "UNVERIFIED_AMBIGUOUS_SEQUENCE",
                                "lineCount": line_count,
                                "candidatePartitionCount": len(partitions),
                                "blocks": [line["block"] for line in sequence],
                                "blockLines": [line["line"] for line in sequence],
                            })
                            continue
                        for match in partitions:
                            safety_reasons = multiline_safety_reasons(sequence, match["segments"])
                            if safety_reasons:
                                multiline_diagnostics.append({
                                    "page": page_no,
                                    "term": term,
                                    "status": "UNVERIFIED_MULTILINE_UNSAFE_SEQUENCE",
                                    "lineCount": line_count,
                                    "split": "/".join(match["segments"]),
                                    "splitIndexes": match["splitIndexes"],
                                    "blocks": [line["block"] for line in sequence],
                                    "blockLines": [line["line"] for line in sequence],
                                    "reasons": safety_reasons,
                                })
                                continue
                            segments = match["segments"]
                            boxes = []
                            for index, (line, segment) in enumerate(zip(sequence, segments)):
                                if index == 0:
                                    boxes.extend([line["chars"][-len(segment)]["bbox"], line["chars"][-1]["bbox"]])
                                elif index == len(sequence) - 1:
                                    boxes.extend([line["chars"][0]["bbox"], line["chars"][len(segment) - 1]["bbox"]])
                                else:
                                    boxes.extend([line["chars"][0]["bbox"], line["chars"][-1]["bbox"]])
                            bbox = [min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)]
                            finding = {
                                "page": page_no,
                                "term": term,
                                "split": "/".join(segments),
                                "splitIndexes": match["splitIndexes"],
                                "splitKind": match["splitKind"],
                                "lineCount": line_count,
                                "bbox": [round(v, 2) for v in bbox],
                            }
                            if any(item is not None for item in match["boundaryWhitespaces"]):
                                finding["boundaryWhitespaces"] = match["boundaryWhitespaces"]
                            findings.append(finding)
                            term_counts[(term, "splitAcrossLines")] += 1
                            page_term_counts[(page_no, term)] += 1
                            if crop_root:
                                crop_root.mkdir(parents=True, exist_ok=True)
                                crop = crop_root / f"finding-{len(findings):04d}_page-{page_no:04d}.png"
                                rect = fitz.Rect(bbox) + (-18, -12, 18, 12)
                                page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect).save(crop)
                                finding["crop"] = str(crop)
        pages = len(doc)
    pdf_unchanged = sha256(source) == source_hash
    hwpx_hash_after = sha256(hwpx) if hwpx else None
    hwpx_unchanged = hwpx_hash_after == hwpx_hash if hwpx else None
    terms = []
    expectation_mismatch = False
    for term in args.term:
        same = term_counts[(term, "sameLine")]
        split = term_counts[(term, "splitAcrossLines")]
        total = same + split
        expected_total = args.expected_total_map.get(term)
        total_mismatch = expected_total is not None and total != expected_total
        missing_pages = [p for p in range(1, pages + 1) if page_term_counts[(p, term)] == 0]
        unexpected_pages = []
        if args.expected_per_page is not None:
            unexpected_pages = [p for p in range(1, pages + 1) if page_term_counts[(p, term)] != args.expected_per_page]
            expectation_mismatch = expectation_mismatch or bool(unexpected_pages)
        expectation_mismatch = expectation_mismatch or total_mismatch
        status = "SPLIT_FOUND" if split else ("NO_SPLIT_OBSERVED" if same else "UNVERIFIED_TERM_NOT_FOUND")
        if split and total_mismatch:
            status = "SPLIT_FOUND_WITH_EXPECTATION_MISMATCH"
        elif (unexpected_pages or total_mismatch) and not split:
            status = "UNVERIFIED_EXPECTATION_MISMATCH"
        term_diagnostics = [item for item in multiline_diagnostics if item["term"] == term]
        if not split and not same and term_diagnostics:
            diagnostic_statuses = {item["status"] for item in term_diagnostics}
            status = "UNVERIFIED_AMBIGUOUS_SEQUENCE" if "UNVERIFIED_AMBIGUOUS_SEQUENCE" in diagnostic_statuses else "UNVERIFIED_MULTILINE_UNSAFE_SEQUENCE"
        terms.append({"term": term, "status": status, "sameLineOccurrences": same, "splitOccurrences": split, "totalOccurrences": total, "expectedTotalOccurrences": expected_total, "totalExpectationMatched": (total == expected_total if expected_total is not None else None), "pagesWithTerm": [p for p in range(1, pages + 1) if page_term_counts[(p, term)]], "pagesWithoutTerm": missing_pages, "pagesOutsideExpectedCount": unexpected_pages})
    incomplete = bool(pages_without_text) or expectation_mismatch or bool(multiline_diagnostics) or not pdf_unchanged or hwpx_unchanged is False
    overall = ("SPLIT_FOUND_WITH_INCOMPLETE_COVERAGE" if incomplete else "SPLIT_FOUND") if findings else ("UNVERIFIED" if incomplete or any(x["status"].startswith("UNVERIFIED") for x in terms) else "NO_SPLIT_OBSERVED")
    page_counts = Counter(x["page"] for x in findings)
    page_kinds: dict[int, set[str]] = {}
    for finding in findings:
        page_kinds.setdefault(finding["page"], set()).add(finding["splitKind"])
    result = {
        "schemaVersion": 1,
        "mode": "pdf-coordinate-inspection",
        "pdf": {"path": str(source), "sha256": source_hash, "pages": pages, "pagesWithExtractableText": text_pages, "pagesWithoutExtractableText": pages_without_text},
        "pdfSourceUnchanged": pdf_unchanged,
        "coverage": "INCOMPLETE" if incomplete else "COMPLETE_EXTRACTABLE_TEXT",
        "maxSplitLines": max_split_lines,
        "expectedOccurrencesPerPage": args.expected_per_page,
        "expectedTotalOccurrences": args.expected_total_map,
        "sourceHwpx": ({"path": str(hwpx), "sha256": hwpx_hash, "sha256After": hwpx_hash_after, "sourceUnchanged": hwpx_unchanged} if hwpx else None),
        "provenance": {"declaredByOperator": args.provenance_note, "verifiedByThisTool": False},
        "status": overall,
        "terms": terms,
        "findingCount": len(findings),
        "pagesWithFindings": sorted({x["page"] for x in findings}),
        "pageSummary": [{"page": page, "findingCount": page_counts[page], "splitKinds": sorted(page_kinds[page])} for page in sorted(page_counts)],
        "findings": findings,
        "multilineDiagnostics": multiline_diagnostics,
        "limitations": ["PDF extraction can miss outlined, image-only, or font-encoded text.", "Adjacent-line geometry is a bounded heuristic and does not settle complex columns or floating objects.", "The tool records PDF/HWPX hashes but does not prove how the PDF was exported.", "Expected totals validate watched-term coverage only; they do not prove that unrelated document content was preserved."],
    }
    write_new(args.output, result)
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight", help="screen HWPX structure for line-wrap risk")
    pre.add_argument("hwpx", type=Path)
    pre.add_argument("--output", type=Path, required=True)
    pre.add_argument("--term", action="append", default=[])
    pre.add_argument("--density-threshold", type=float, default=0.8)
    pre.set_defaults(run=preflight)
    pdf = sub.add_parser("inspect-pdf", help="detect watched terms split across PDF lines")
    pdf.add_argument("pdf", type=Path)
    pdf.add_argument("--output", type=Path, required=True)
    pdf.add_argument("--term", action="append", default=[])
    pdf.add_argument("--source-hwpx", type=Path)
    pdf.add_argument("--provenance-note", required=True, help="operator's explicit PDF origin statement")
    pdf.add_argument("--crop-dir", type=Path)
    pdf.add_argument("--expected-per-page", type=int, help="optional expected occurrence count for every term on every page")
    pdf.add_argument("--expected-total", action="append", default=[], metavar="TERM=COUNT", help="optional document-wide expected occurrence count for one watched term; repeat per term")
    pdf.add_argument("--max-split-lines", type=int, choices=(2, 3, 4), default=2, help="explicit maximum adjacent line count for one watched term; default preserves the two-line contract")
    pdf.set_defaults(run=inspect_pdf)
    return p


def main() -> int:
    args = parser().parse_args()
    if not args.term:
        args.term = ["결정"]
    if any(not term for term in args.term):
        print(json.dumps({"status": "ERROR", "errorType": "ValueError", "message": "--term must not be empty"}, ensure_ascii=False), file=sys.stderr)
        return 2
    args.term = list(dict.fromkeys(args.term))
    if getattr(args, "expected_per_page", None) is not None and args.expected_per_page < 0:
        print(json.dumps({"status": "ERROR", "errorType": "ValueError", "message": "--expected-per-page must be non-negative"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        args.expected_total_map = parse_expected_totals(getattr(args, "expected_total", []), args.term)
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "errorType": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        result = args.run(args)
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "errorType": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()), "candidateCount": result.get("candidateCount"), "findingCount": result.get("findingCount")}, ensure_ascii=False))
    return 1 if result["status"].startswith(("SPLIT_FOUND", "UNVERIFIED")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
