#!/usr/bin/env python3
"""Independent black-box regression tests for audit_hwpx_linebreaks.py.

Creates only synthetic, non-sensitive fixtures below --work-dir, invokes the
auditor as a subprocess, and preserves JSON evidence there.  It never edits a
school document.  Run with the HWPX runtime that provides PyMuPDF:

  python scripts/test_audit_hwpx_linebreaks.py --work-dir NEW_EMPTY_DIR
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace
import zipfile
from pathlib import Path


AUDITOR = Path(__file__).resolve().with_name("audit_hwpx_linebreaks.py")


def load_auditor():
    spec = importlib.util.spec_from_file_location("audit_hwpx_linebreaks_under_test", AUDITOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {AUDITOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_new_dir(path: Path) -> Path:
    path = path.resolve()
    if path.exists():
        if any(path.iterdir()):
            raise FileExistsError(f"--work-dir must be new or empty: {path}")
    else:
        path.mkdir(parents=True)
    return path


def run(python: str, args: list[str], expected: int, label: str) -> dict:
    completed = subprocess.run([python, "-X", "utf8", str(AUDITOR), *args], text=True, encoding="utf-8", capture_output=True)
    if completed.returncode != expected:
        raise AssertionError(f"{label}: exit {completed.returncode}, expected {expected}; stderr={completed.stderr!r}; stdout={completed.stdout!r}")
    return {"label": label, "exitCode": completed.returncode, "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()}


def payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def create_pdf_pages(path: Path, pages: list[list[tuple[float, float, str]]]) -> None:
    import fitz

    korean_font = Path(r"C:\\Windows\\Fonts\\malgun.ttf")
    if not korean_font.is_file():
        raise FileNotFoundError("Korean test font not found: C:\\Windows\\Fonts\\malgun.ttf")
    document = fitz.open()
    for lines in pages:
        page = document.new_page(width=400, height=300)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontsize=12, fontname="malgun", fontfile=str(korean_font))
    document.save(path)
    document.close()


def create_pdf(path: Path, lines: list[tuple[float, float, str]]) -> None:
    create_pdf_pages(path, [lines])


def create_multiline_pdf(path: Path, text: str) -> None:
    """Use one PDF text object so successive lines share a block."""
    import fitz

    korean_font = Path(r"C:\\Windows\\Fonts\\malgun.ttf")
    document = fitz.open()
    page = document.new_page(width=400, height=300)
    page.insert_text((40, 50), text, fontsize=12, fontname="malgun", fontfile=str(korean_font))
    document.save(path)
    document.close()


def create_hwpx(path: Path) -> None:
    header = '''<hh:head xmlns:hh="urn:head"><hh:charPr id="1" height="1000"><hh:ratio hangul="100"/><hh:spacing hangul="0"/></hh:charPr><hh:paraPr id="1"><hh:lineWrap mode="break"/></hh:paraPr></hh:head>'''
    section = '''<hs:sec xmlns:hs="urn:sec">
      <hs:tc><hs:cellSz width="1000"/><hs:p paraPrIDRef="1"><hs:run charPrIDRef="1"><hs:t>결정</hs:t></hs:run><hs:tc><hs:cellSz width="200"/><hs:p paraPrIDRef="1"><hs:run charPrIDRef="1"><hs:t>결정</hs:t></hs:run></hs:p></hs:tc></hs:p></hs:tc>
      <hs:p paraPrIDRef="1"><hs:run charPrIDRef="1"><hs:t>결정</hs:t></hs:run><hs:p paraPrIDRef="1"><hs:lineseg horzsize="200"/><hs:run charPrIDRef="1"><hs:t>결정</hs:t></hs:run></hs:p></hs:p>
    </hs:sec>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)


def create_spined_hwpx(path: Path) -> None:
    header = '''<h:head xmlns:h="urn:head"><h:charPr id="1" height="1000"/><h:paraPr id="1"/></h:head>'''
    # Real HWPX packages commonly retain the Contents/ prefix in manifest hrefs.
    package = '''<opf:package xmlns:opf="urn:opf"><opf:manifest><opf:item id="zero" href="Contents/section0.xml"/><opf:item id="one" href="Contents/section1.xml"/></opf:manifest><opf:spine><opf:itemref idref="one"/><opf:itemref idref="zero"/></opf:spine></opf:package>'''
    def section(text: str) -> str:
        return f'''<s:sec xmlns:s="urn:sec"><s:p paraPrIDRef="1"><s:run charPrIDRef="1"><s:t>{text}</s:t></s:run></s:p></s:sec>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/content.hpf", package)
        archive.writestr("Contents/section0.xml", section("결정결정"))
        archive.writestr("Contents/section1.xml", section("결정"))


def test_preflight(python: str, work: Path, evidence: list[dict]) -> None:
    fixture = work / "nested-width.hwpx"
    create_hwpx(fixture)
    output = work / "preflight.json"
    evidence.append(run(python, ["preflight", str(fixture), "--output", str(output)], 0, "preflight nested table"))
    report = payload(output)
    assert report["status"] == "RISK_SCREEN_ONLY"
    assert report["paragraphsSeen"] == 4
    candidates = report["candidates"]
    assert len(candidates) == 4
    by_depth = {c["inTableDepth"]: c for c in candidates if c["inTableDepth"] in {1, 2}}
    assert by_depth[1]["cellWidthHwpUnit"] == 1000
    assert by_depth[2]["cellWidthHwpUnit"] == 200
    assert by_depth[1]["textChars"] == 2, "outer paragraph must exclude nested paragraph text"
    top_level_outer = next(c for c in candidates if c["inTableDepth"] == 0 and c["paragraphIndex"] == 2)
    assert top_level_outer["availableWidthHwpUnit"] is None, "outer paragraph must not inherit nested paragraph line segments"
    assert top_level_outer["storedLineSegmentCount"] == 0

    spined = work / "spined-order.hwpx"
    spined_out = work / "spined-order.json"
    create_spined_hwpx(spined)
    evidence.append(run(python, ["preflight", str(spined), "--output", str(spined_out)], 0, "content spine order"))
    spined_candidates = payload(spined_out)["candidates"]
    assert [c["textChars"] for c in spined_candidates] == [2, 4], "content.hpf spine must override lexical section filename order"

    changed = work / "preflight-source-changed.json"
    auditor = load_auditor()
    real_sha256 = auditor.sha256
    hashes = iter(["before", "after"])
    auditor.sha256 = lambda _path: next(hashes)
    try:
        report = auditor.preflight(SimpleNamespace(hwpx=fixture, output=changed, term=["결정"], density_threshold=0.8))
    finally:
        auditor.sha256 = real_sha256
    assert report["status"] == "UNVERIFIED_SOURCE_CHANGED"
    assert report["sourceUnchanged"] is False


def test_pdf_contracts(python: str, work: Path, evidence: list[dict]) -> None:
    cases = {
        "unsplit": ([(40, 50, "결정")], "NO_SPLIT_OBSERVED", 0, 1, 0),
        "split": ([(40, 50, "결"), (40, 75, "정")], "SPLIT_FOUND", 1, 0, 1),
        "decision_then_suffix": ([(40, 50, "결정"), (40, 75, "되었으므로")], "NO_SPLIT_OBSERVED", 0, 1, 0),
        # Same y, separate columns: these fragments are not successive text lines.
        "multi_column_fragments": ([(40, 50, "왼쪽결"), (230, 50, "정오른쪽")], "UNVERIFIED", 1, 0, 0),
    }
    for name, (lines, status, exit_code, same, split) in cases.items():
        source = work / f"{name}.pdf"
        output = work / f"{name}.json"
        if name == "split":
            create_multiline_pdf(source, "결\n정")
        else:
            create_pdf(source, lines)
        evidence.append(run(python, ["inspect-pdf", str(source), "--output", str(output), "--provenance-note", "synthetic test fixture"], exit_code, name))
        report = payload(output)
        assert report["status"] == status, f"{name}: {report}"
        assert report["terms"][0]["sameLineOccurrences"] == same
        assert report["terms"][0]["splitOccurrences"] == split
        assert report["pdfSourceUnchanged"] is True

    different_block_vertical = work / "different-block-vertical.pdf"
    different_block_vertical_out = work / "different-block-vertical.json"
    create_pdf(different_block_vertical, [(40, 50, "결"), (40, 75, "정")])
    evidence.append(run(python, ["inspect-pdf", str(different_block_vertical), "--output", str(different_block_vertical_out), "--term", "결정", "--expected-total", "결정=1", "--provenance-note", "synthetic vertical separate-block fixture"], 1, "legacy two-line cross-block split preserved"))
    different_block_vertical_report = payload(different_block_vertical_out)
    assert different_block_vertical_report["status"] == "SPLIT_FOUND"
    assert different_block_vertical_report["terms"][0]["totalOccurrences"] == 1

    blank = work / "blank.pdf"
    blank_out = work / "blank.json"
    create_pdf(blank, [])
    evidence.append(run(python, ["inspect-pdf", str(blank), "--output", str(blank_out), "--provenance-note", "synthetic blank fixture"], 1, "missing extraction"))
    assert payload(blank_out)["status"] == "UNVERIFIED"

    spaced = work / "spaced-term.pdf"
    spaced_out = work / "spaced-term.json"
    create_pdf(spaced, [(40, 50, "결 정")])
    evidence.append(run(python, ["inspect-pdf", str(spaced), "--output", str(spaced_out), "--provenance-note", "synthetic spaced fixture"], 1, "spaces do not form watched term"))
    assert payload(spaced_out)["status"] == "UNVERIFIED"

    word_boundary = work / "word-boundary-split.pdf"
    word_boundary_out = work / "word-boundary-split.json"
    create_multiline_pdf(word_boundary, "동아리별 \n운영")
    evidence.append(run(python, ["inspect-pdf", str(word_boundary), "--output", str(word_boundary_out), "--term", "동아리별 운영", "--expected-total", "동아리별 운영=1", "--provenance-note", "synthetic one-space boundary fixture"], 1, "one rendered source-space boundary"))
    word_boundary_report = payload(word_boundary_out)
    assert word_boundary_report["status"] == "SPLIT_FOUND"
    assert word_boundary_report["terms"][0]["totalOccurrences"] == 1
    assert word_boundary_report["findings"][0]["splitKind"] == "AT_SOURCE_WHITESPACE"
    assert word_boundary_report["findings"][0]["boundaryWhitespace"] == " "

    two_spaces = work / "two-space-boundary.pdf"
    two_spaces_out = work / "two-space-boundary.json"
    create_multiline_pdf(two_spaces, "동아리별  \n운영")
    evidence.append(run(python, ["inspect-pdf", str(two_spaces), "--output", str(two_spaces_out), "--term", "동아리별 운영", "--expected-total", "동아리별 운영=1", "--provenance-note", "synthetic two-space boundary fixture"], 1, "two rendered spaces rejected"))
    assert payload(two_spaces_out)["status"] == "UNVERIFIED"

    different_blocks = work / "different-block-space-boundary.pdf"
    different_blocks_out = work / "different-block-space-boundary.json"
    create_pdf(different_blocks, [(40, 50, "동아리별 "), (40, 75, "운영")])
    evidence.append(run(python, ["inspect-pdf", str(different_blocks), "--output", str(different_blocks_out), "--term", "동아리별 운영", "--expected-total", "동아리별 운영=1", "--provenance-note", "synthetic separate-block boundary fixture"], 1, "different blocks not joined through space"))
    assert payload(different_blocks_out)["status"] == "UNVERIFIED"

    three_lines = work / "three-line-term.pdf"
    create_multiline_pdf(three_lines, "가나다\n라마바사\n아자차")
    three_default_out = work / "three-line-default-two.json"
    evidence.append(run(python, ["inspect-pdf", str(three_lines), "--output", str(three_default_out), "--term", "가나다라마바사아자차", "--expected-total", "가나다라마바사아자차=1", "--provenance-note", "synthetic three-line default fixture"], 1, "three lines remain unverified by default"))
    assert payload(three_default_out)["status"] == "UNVERIFIED"

    three_enabled_out = work / "three-line-enabled.json"
    evidence.append(run(python, ["inspect-pdf", str(three_lines), "--output", str(three_enabled_out), "--term", "가나다라마바사아자차", "--expected-total", "가나다라마바사아자차=1", "--max-split-lines", "4", "--provenance-note", "synthetic three-line enabled fixture"], 1, "three lines detected when explicitly enabled"))
    three_enabled_report = payload(three_enabled_out)
    assert three_enabled_report["status"] == "SPLIT_FOUND"
    assert three_enabled_report["maxSplitLines"] == 4
    assert three_enabled_report["terms"][0]["totalOccurrences"] == 1
    assert three_enabled_report["findings"][0]["lineCount"] == 3
    assert three_enabled_report["findings"][0]["splitKind"] == "MULTILINE_WITHIN_TERM"
    assert three_enabled_report["findings"][0]["splitIndexes"] == [3, 7]

    three_blocks = work / "three-line-different-blocks.pdf"
    three_blocks_out = work / "three-line-different-blocks.json"
    create_pdf(three_blocks, [(40, 50, "가나다"), (40, 75, "라마바사"), (40, 100, "아자차")])
    evidence.append(run(python, ["inspect-pdf", str(three_blocks), "--output", str(three_blocks_out), "--term", "가나다라마바사아자차", "--expected-total", "가나다라마바사아자차=1", "--max-split-lines", "4", "--provenance-note", "synthetic unsafe multi-block fixture"], 1, "multi-block term is diagnostic not finding"))
    three_blocks_report = payload(three_blocks_out)
    assert three_blocks_report["status"] == "UNVERIFIED"
    assert three_blocks_report["terms"][0]["status"] == "UNVERIFIED_MULTILINE_UNSAFE_SEQUENCE"
    assert three_blocks_report["terms"][0]["totalOccurrences"] == 0
    assert three_blocks_report["multilineDiagnostics"][0]["reasons"] == ["DIFFERENT_BLOCKS"]

    four_lines = work / "four-line-term.pdf"
    create_multiline_pdf(four_lines, "가나\n다라\n마바\n사아")
    four_limited_out = work / "four-line-max-three.json"
    evidence.append(run(python, ["inspect-pdf", str(four_lines), "--output", str(four_limited_out), "--term", "가나다라마바사아", "--expected-total", "가나다라마바사아=1", "--max-split-lines", "3", "--provenance-note", "synthetic four-line limited fixture"], 1, "four lines rejected by max three"))
    assert payload(four_limited_out)["status"] == "UNVERIFIED"

    four_enabled_out = work / "four-line-enabled.json"
    evidence.append(run(python, ["inspect-pdf", str(four_lines), "--output", str(four_enabled_out), "--term", "가나다라마바사아", "--expected-total", "가나다라마바사아=1", "--max-split-lines", "4", "--provenance-note", "synthetic four-line enabled fixture"], 1, "four lines detected when explicitly enabled"))
    four_enabled_report = payload(four_enabled_out)
    assert four_enabled_report["status"] == "SPLIT_FOUND"
    assert four_enabled_report["findings"][0]["lineCount"] == 4
    assert four_enabled_report["findings"][0]["splitIndexes"] == [2, 4, 6]

    partial = work / "partial-no-text.pdf"
    partial_out = work / "partial-no-text.json"
    create_pdf_pages(partial, [[(40, 50, "결정")], []])
    evidence.append(run(python, ["inspect-pdf", str(partial), "--output", str(partial_out), "--provenance-note", "synthetic partial-extraction fixture"], 1, "partial missing extraction"))
    assert payload(partial_out)["status"] == "UNVERIFIED"

    partial_term = work / "partial-term-coverage.pdf"
    partial_term_out = work / "partial-term-coverage.json"
    create_pdf_pages(partial_term, [[(40, 50, "결정")], [(40, 50, "다른 문구")]])
    evidence.append(run(python, ["inspect-pdf", str(partial_term), "--output", str(partial_term_out), "--expected-per-page", "1", "--provenance-note", "synthetic missing-term fixture"], 1, "partial missing term coverage"))
    partial_term_report = payload(partial_term_out)
    assert partial_term_report["status"] == "UNVERIFIED"
    assert partial_term_report["coverage"] == "INCOMPLETE"
    assert partial_term_report["terms"][0]["pagesOutsideExpectedCount"] == [2]

    unmatched = work / "unmatched.json"
    evidence.append(run(python, ["inspect-pdf", str(work / "unsplit.pdf"), "--output", str(unmatched), "--term", "없는말", "--provenance-note", "synthetic test fixture"], 1, "unmatched term"))
    assert payload(unmatched)["status"] == "UNVERIFIED"

    expected_ok = work / "expected-total-ok.json"
    evidence.append(run(python, ["inspect-pdf", str(work / "unsplit.pdf"), "--output", str(expected_ok), "--term", "결정", "--expected-total", "결정=1", "--provenance-note", "synthetic expected-total fixture"], 0, "document total matches"))
    expected_ok_term = payload(expected_ok)["terms"][0]
    assert expected_ok_term["totalOccurrences"] == 1
    assert expected_ok_term["expectedTotalOccurrences"] == 1
    assert expected_ok_term["totalExpectationMatched"] is True

    expected_bad = work / "expected-total-mismatch.json"
    evidence.append(run(python, ["inspect-pdf", str(work / "unsplit.pdf"), "--output", str(expected_bad), "--term", "결정", "--expected-total", "결정=2", "--provenance-note", "synthetic expected-total fixture"], 1, "document total mismatch"))
    expected_bad_report = payload(expected_bad)
    assert expected_bad_report["status"] == "UNVERIFIED"
    assert expected_bad_report["coverage"] == "INCOMPLETE"
    assert expected_bad_report["terms"][0]["totalExpectationMatched"] is False

    invalid_expected = work / "invalid-expected-total.json"
    evidence.append(run(python, ["inspect-pdf", str(work / "unsplit.pdf"), "--output", str(invalid_expected), "--term", "결정", "--expected-total", "다른말=1", "--provenance-note", "synthetic expected-total fixture"], 2, "unwatched expected-total rejected"))
    assert not invalid_expected.exists()

    changed_pdf_out = work / "pdf-source-changed.json"
    linked_hwpx = work / "linked.hwpx"
    create_hwpx(linked_hwpx)
    auditor = load_auditor()
    real_sha256 = auditor.sha256
    hashes = iter(["pdf-before", "hwpx-before", "pdf-after", "hwpx-after"])
    auditor.sha256 = lambda _path: next(hashes)
    try:
        report = auditor.inspect_pdf(SimpleNamespace(pdf=work / "unsplit.pdf", output=changed_pdf_out, source_hwpx=linked_hwpx, crop_dir=None, term=["결정"], expected_per_page=None, expected_total_map={"결정": 1}, provenance_note="synthetic mutation fixture"))
    finally:
        auditor.sha256 = real_sha256
    assert report["status"] == "UNVERIFIED"
    assert report["pdfSourceUnchanged"] is False
    assert report["sourceHwpx"]["sourceUnchanged"] is False


def test_whitespace_boundary_helper() -> None:
    auditor = load_auditor()

    def line(text: str, *, block: int = 0, line_no: int = 0, leading: str = "", trailing: str = "", font: str = "same", size: float = 12.0, x: float = 0.0, y: float = 0.0, direction: tuple[float, float] = (1.0, 0.0)) -> dict:
        return {
            "text": text,
            "block": block,
            "line": line_no,
            "bbox": (x, y, x + 100.0, y + 10.0),
            "direction": direction,
            "leadingWhitespace": leading,
            "trailingWhitespace": trailing,
            "chars": [{"c": c, "bbox": (0, 0, 1, 1), "_font": font, "_size": size} for c in text],
        }

    a = line("동아리별", trailing=" ")
    b = line("운영", line_no=1)
    matches = auditor.split_candidates("동아리별 운영", a, b)
    assert len(matches) == 1 and matches[0]["splitKind"] == "AT_SOURCE_WHITESPACE"

    assert len(auditor.split_candidates("동아리별 운영", line("동아리별"), line("운영", line_no=1, leading=" "))) == 1
    assert not auditor.split_candidates("동아리별 운영", line("동아리별", trailing="  "), b)
    assert not auditor.split_candidates("동아리별 운영", a, line("운영", block=1, line_no=1))
    assert not auditor.split_candidates("동아리별 운영", a, line("운영", line_no=1, font="different"))
    assert not auditor.split_candidates("동아리별 운영", a, line("운영", line_no=1, size=13.0))
    assert not auditor.split_candidates("동아리별  운영", a, b)

    sequence = [line("가나", line_no=0, y=0.0), line("다라", line_no=1, y=15.0), line("마바", line_no=2, y=30.0)]
    matches = auditor.multiline_candidates("가나다라마바", sequence)
    assert len(matches) == 1 and matches[0]["splitIndexes"] == [2, 4]
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=1, y=15.0, block=1), sequence[2]])
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=1, y=15.0, direction=(0.0, 1.0)), sequence[2]])
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=1, y=15.0, font="different"), sequence[2]])
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=1, y=15.0, size=13.0), sequence[2]])
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=2, y=15.0), sequence[2]])
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=1, x=200.0, y=15.0), sequence[2]])
    assert not auditor.multiline_candidates("가나다라마바", [sequence[0], line("다라", line_no=1, y=100.0), line("마바", line_no=2, y=115.0)])


def test_overwrite_rejected(python: str, work: Path, evidence: list[dict]) -> None:
    output = work / "existing-output.json"
    sentinel = "do not overwrite"
    output.write_text(sentinel, encoding="utf-8")
    evidence.append(run(python, ["inspect-pdf", str(work / "unsplit.pdf"), "--output", str(output), "--provenance-note", "synthetic test fixture"], 2, "overwrite rejection"))
    assert output.read_text(encoding="utf-8") == sentinel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable, help="Python executable with PyMuPDF installed")
    args = parser.parse_args()
    if not AUDITOR.is_file():
        raise FileNotFoundError(AUDITOR)
    work = require_new_dir(args.work_dir)
    evidence: list[dict] = []
    try:
        test_preflight(args.python, work, evidence)
        test_whitespace_boundary_helper()
        test_pdf_contracts(args.python, work, evidence)
        test_overwrite_rejected(args.python, work, evidence)
    except Exception as exc:
        (work / "test-result.json").write_text(json.dumps({"status": "FAIL", "error": str(exc), "evidence": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    (work / "test-result.json").write_text(json.dumps({"status": "PASS", "evidence": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {work / 'test-result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
