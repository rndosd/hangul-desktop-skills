#!/usr/bin/env python3
"""File-based synthetic rejection tests for the read-only prototype.

All generated documents are non-personal, synthetic test fixtures.  Their
receipt schema is intentionally incompatible with native Hancom evidence.
"""

from __future__ import annotations

import argparse
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path


SYNTHETIC_TERM = "ALPHA BETA GAMMA"
SYNTHETIC_PARAGRAPH = SYNTHETIC_TERM + " tail "
SYNTHETIC_NEIGHBOR = "NEXT ANCHOR"


def load_engine(path: Path):
    spec = importlib.util.spec_from_file_location("source_anchored_engine", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def write_synthetic_hwpx(path: Path) -> None:
    content = """<?xml version='1.0' encoding='UTF-8'?>
<package><item id='s0' href='Contents/section0.xml'/><spine><itemref idref='s0'/></spine></package>"""
    section = f"""<?xml version='1.0' encoding='UTF-8'?>
<section>
  <p id='p0' paraPrIDRef='20' styleIDRef='23'>
    <run><secPr/><ctrl><colPr colCount='1'/></ctrl></run>
    <run charPrIDRef='7'><t>{SYNTHETIC_PARAGRAPH}</t></run>
  </p>
  <p id='p1' paraPrIDRef='21' styleIDRef='0'><run charPrIDRef='8'><t>{SYNTHETIC_NEIGHBOR}</t></run></p>
</section>"""
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in (
            ("mimetype", "application/hwp+zip"),
            ("Contents/content.hpf", content),
            ("Contents/section0.xml", section),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, payload)


def write_synthetic_pdf(path: Path, variant: str) -> None:
    import pymupdf as fitz

    document = fitz.open()
    document.new_page(width=600, height=800)
    lines = ["ALPHA ", "BETA ", "GAMMA tail ", SYNTHETIC_NEIGHBOR]
    y_values = [100, 120, 140, 160]
    for index, (text, y) in enumerate(zip(lines, y_values)):
        target_page = document[0]
        font = "helv"
        size = 12
        rotate = 0
        point = (100, y)
        if variant == "direction" and index == 1:
            rotate = 180
            point = (220, y)
        if variant == "font" and index == 1:
            font = "cour"
        if variant == "size" and index == 1:
            size = 14
        if variant == "page" and index == 2:
            document.new_page(width=600, height=800)
            target_page = document[1]
            point = (100, 100)
        if variant == "whitespace" and index == 0:
            text = "ALPHA"
        target_page.insert_text(point, text, fontsize=size, fontname=font, rotate=rotate)
    document.set_metadata({
        "producer": "source-anchored synthetic test",
        "creator": "source-anchored synthetic test",
        "creationDate": "D:20000101000000Z",
        "modDate": "D:20000101000000Z",
    })
    document.save(path, no_new_id=True, reproducible=True)
    document.close()


def write_synthetic_receipt(path: Path, hwpx: Path, pdf: Path) -> None:
    payload = {
        "evidenceSchema": "source-anchored.synthetic-test.v1",
        "syntheticFixture": True,
        "nativeEvidence": False,
        "files": {
            "hwpx": {"path": hwpx.name, "sha256": digest(hwpx)},
            "pdf": {"path": pdf.name, "sha256": digest(pdf)},
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def validate_synthetic_receipt(path: Path, hwpx: Path, pdf: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "evidenceSchema": "source-anchored.synthetic-test.v1",
        "syntheticFixture": True,
        "nativeEvidence": False,
        "files": {
            "hwpx": {"path": hwpx.name, "sha256": digest(hwpx)},
            "pdf": {"path": pdf.name, "sha256": digest(pdf)},
        },
    }


def find_term_lines(pdf_model: dict) -> list[dict]:
    wanted = {"ALPHA ", "BETA ", "GAMMA tail "}
    return [
        line for page in pdf_model["pages"] for line in page["lines"]
        if line["text"] in wanted or line["text"].strip() in {"ALPHA", "BETA", "GAMMA tail"}
    ][:3]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine_path = args.engine.resolve()
    work = args.work_dir.resolve()
    output = args.output.resolve()
    if work.exists():
        raise FileExistsError(f"work directory must be new: {work}")
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    work.mkdir(parents=True)
    engine = load_engine(engine_path)

    hwpx = work / "synthetic-nonpersonal.hwpx"
    write_synthetic_hwpx(hwpx)
    pdf_paths = {}
    for variant in ("baseline", "direction", "font", "size", "page", "whitespace"):
        path = work / f"synthetic-{variant}.pdf"
        write_synthetic_pdf(path, variant)
        pdf_paths[variant] = path
    receipt = work / "synthetic-receipt.json"
    write_synthetic_receipt(receipt, hwpx, pdf_paths["baseline"])
    validate_synthetic_receipt(receipt, hwpx, pdf_paths["baseline"])

    source = engine.extract_source_model(hwpx)
    baseline_model = engine.extract_pdf_model(pdf_paths["baseline"])
    baseline = engine.evaluate_models(source, baseline_model, [], SYNTHETIC_TERM)
    assert baseline["status"] == "OBSERVED_SOURCE_ANCHORED_MULTIBLOCK_RENDERER_FRAGMENT", baseline
    production_receipt_reasons = engine.verify_receipt(
        json.loads(receipt.read_text(encoding="utf-8")), hwpx, pdf_paths["baseline"], digest(hwpx), digest(pdf_paths["baseline"])
    )
    assert "RECEIPT_SCHEMA" in production_receipt_reasons
    production_result = engine.evaluate_models(source, baseline_model, production_receipt_reasons, SYNTHETIC_TERM)
    assert production_result["status"] == "UNVERIFIED"

    rejection_results = []
    for variant, expected_safety in (
        ("direction", "NON_HORIZONTAL_LTR_OR_MIXED_DIRECTION"),
        ("font", "MIXED_MATCHED_GLYPH_STYLE"),
        ("size", "MIXED_MATCHED_GLYPH_STYLE"),
    ):
        model = engine.extract_pdf_model(pdf_paths[variant])
        lines = find_term_lines(model)
        reasons = engine._sequence_safety(lines)
        assert expected_safety in reasons, (variant, reasons, lines)
        result = engine.evaluate_models(source, model, [], SYNTHETIC_TERM)
        assert result["status"] == "UNVERIFIED", (variant, result)
        rejection_results.append({"case": variant, "status": result["status"], "safetyReason": expected_safety})
    for variant in ("page", "whitespace"):
        model = engine.extract_pdf_model(pdf_paths[variant])
        result = engine.evaluate_models(source, model, [], SYNTHETIC_TERM)
        assert result["status"] == "UNVERIFIED", (variant, result)
        rejection_results.append({"case": variant, "status": result["status"], "reason": result["reasons"][0]})

    collision_output = work / "collision-output.json"
    command = [
        sys.executable, str(engine_path), "--source-hwpx", str(hwpx), "--pdf", str(pdf_paths["baseline"]),
        "--receipt", str(receipt), "--term", SYNTHETIC_TERM, "--output", str(collision_output),
    ]
    first = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    assert collision_output.is_file() and first.returncode == 1, (first.returncode, first.stdout, first.stderr)
    collision_hash = digest(collision_output)
    second = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    assert second.returncode == 2 and digest(collision_output) == collision_hash
    assert json.loads(second.stderr)["errorCode"] == "OUTPUT_EXISTS", second.stderr
    rejection_results.append({"case": "output-collision", "status": "REJECTED_EXISTING_OUTPUT_UNCHANGED"})

    race_output = work / "race-output.json"
    original_inspect_for_race = engine.inspect
    def create_output_after_inspection(*inspect_args, **inspect_kwargs):
        result = original_inspect_for_race(*inspect_args, **inspect_kwargs)
        race_output.write_text("RACE_OWNER\n", encoding="utf-8")
        return result
    engine.inspect = create_output_after_inspection
    race_stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(race_stderr), contextlib.redirect_stdout(io.StringIO()):
            race_code = engine.main([
                "--source-hwpx", str(hwpx), "--pdf", str(pdf_paths["baseline"]),
                "--receipt", str(receipt), "--term", SYNTHETIC_TERM, "--output", str(race_output),
            ])
    finally:
        engine.inspect = original_inspect_for_race
    assert race_code == 2 and race_output.read_text(encoding="utf-8") == "RACE_OWNER\n"
    assert json.loads(race_stderr.getvalue())["errorCode"] == "OUTPUT_EXISTS"
    rejection_results.append({"case": "output-race-after-inspection", "status": "REJECTED_EXISTING_OUTPUT_UNCHANGED"})

    empty_output = work / "empty-term-output.json"
    empty_command = [
        sys.executable, str(engine_path), "--source-hwpx", str(hwpx), "--pdf", str(pdf_paths["baseline"]),
        "--receipt", str(receipt), "--term", "", "--output", str(empty_output),
    ]
    empty = subprocess.run(empty_command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    assert empty.returncode == 2 and not empty_output.exists()
    assert json.loads(empty.stderr)["errorCode"] == "EMPTY_TERM" and empty.stdout == ""
    rejection_results.append({"case": "empty-term", "status": "REJECTED", "reason": "EMPTY_TERM"})

    missing_output = work / "missing-input-output.json"
    missing_name = "private-body-must-not-echo.hwpx"
    missing_command = [
        sys.executable, str(engine_path), "--source-hwpx", str(work / missing_name), "--pdf", str(pdf_paths["baseline"]),
        "--receipt", str(receipt), "--term", SYNTHETIC_TERM, "--output", str(missing_output),
    ]
    missing = subprocess.run(missing_command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    assert missing.returncode == 2 and not missing_output.exists()
    assert json.loads(missing.stderr)["errorCode"] == "INPUT_NOT_FOUND" and missing_name not in missing.stderr
    rejection_results.append({"case": "missing-input", "status": "REJECTED", "reason": "INPUT_NOT_FOUND"})

    invalid_receipt = work / "invalid-receipt.json"
    private_marker = "PRIVATE_BODY_MUST_NOT_ECHO"
    invalid_receipt.write_text("{" + private_marker, encoding="utf-8")
    parse_output = work / "parse-error-output.json"
    parse_command = [
        sys.executable, str(engine_path), "--source-hwpx", str(hwpx), "--pdf", str(pdf_paths["baseline"]),
        "--receipt", str(invalid_receipt), "--term", SYNTHETIC_TERM, "--output", str(parse_output),
    ]
    parsed = subprocess.run(parse_command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    assert parsed.returncode == 2 and not parse_output.exists()
    assert json.loads(parsed.stderr)["errorCode"] == "INPUT_PARSE_ERROR" and private_marker not in parsed.stderr
    rejection_results.append({"case": "receipt-parse-error", "status": "REJECTED", "reason": "INPUT_PARSE_ERROR"})

    changing_receipt = work / "synthetic-changing-receipt.json"
    changing_receipt.write_bytes(receipt.read_bytes())
    original_extract = engine.extract_pdf_model
    def mutate_during_read(pdf_path: Path):
        model = original_extract(pdf_path)
        with changing_receipt.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        return model
    engine.extract_pdf_model = mutate_during_read
    try:
        changed = engine.inspect(hwpx, pdf_paths["baseline"], changing_receipt, SYNTHETIC_TERM)
    finally:
        engine.extract_pdf_model = original_extract
    assert changed["status"] == "UNVERIFIED" and changed["reasons"] == ["INPUT_CHANGED_DURING_INSPECTION"], changed
    rejection_results.append({"case": "input-change", "status": changed["status"], "reason": changed["reasons"][0]})

    payload = {
        "status": "PASS",
        "evidenceClass": "SYNTHETIC_TEST_ONLY",
        "nativeEvidence": False,
        "syntheticBaseline": {
            "harnessStatus": baseline["status"],
            "productionStatus": production_result["status"],
            "productionReasons": production_result["reasons"],
        },
        "fileBasedRejectionCount": len(rejection_results),
        "fileBasedRejections": rejection_results,
        "fixtures": {
            path.name: digest(path) for path in [hwpx, *pdf_paths.values(), receipt]
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": payload["status"], "output": str(output), "rejections": len(rejection_results)}))


if __name__ == "__main__":
    main()
