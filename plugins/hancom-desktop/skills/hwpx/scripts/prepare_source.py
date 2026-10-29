"""Cache source analysis by document bytes and the selected analysis runtime."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import tempfile

from candidate_runtime import activate

SCHEMA = "hangul.source-analysis.v1"
ANALYSIS_CONTRACT = "template-style-table-map.v1"
ROOT = Path(__file__).resolve().parents[1]


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _source(path):
    source = Path(path).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".hwpx":
        raise ValueError("HWPX 원본이 필요합니다. HWP는 구형 HWP 변환 경로로 사본을 만든 뒤 연결하세요.")
    return source


def _identity(source):
    core = activate()
    return {
        "sourceSha256": _digest(source.read_bytes()),
        "analysisContract": ANALYSIS_CONTRACT,
        "coreVersion": version("python-hwpx"),
        "automationVersion": version("python-hwpx-automation"),
        "parserSha256": _digest((core.parent / "opc/xml_utils.py").read_bytes()),
        "preparerSha256": _digest(Path(__file__).read_bytes()),
    }


def _analyze(source, source_sha):
    from hwpx import HwpxDocument
    from hwpx_automation.office.authoring.template_analyzer import analyze_template
    from hwpx_automation.office.authoring.style_profile import extract_style_profile

    analysis = replace(analyze_template(source), source_name=f"sha256:{source_sha}.hwpx")
    with HwpxDocument.open(source) as document:
        tables = document.tables.map()
        body_paragraph_count = len(document.paragraphs)
    table_list = tables["tables"]
    summary = {
        "sectionCount": len(analysis.section_paths),
        "bodyParagraphCount": body_paragraph_count,
        "tableCount": len(table_list),
        "tables": [
            {
                "tableIndex": table["table_index"],
                "rows": table["rows"],
                "cols": table["cols"],
                "heading": (table["header_text"] or table["caption_text"])[:100],
                "firstRow": [text[:80] for text in table["first_row_preview"][:4]],
            }
            for table in table_list[:8]
        ],
        "omittedTables": max(0, len(table_list) - 8),
    }
    return {
        "templateAnalysis": asdict(analysis),
        "styleProfile": extract_style_profile(analysis),
        "tableMap": tables,
        "summary": summary,
    }


def _read_record(path):
    if path.is_symlink():
        raise ValueError("분석 파일은 심볼릭 링크일 수 없습니다.")
    record = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("분석 캐시 형식이 다릅니다. 기존 파일은 보존하고 다른 캐시 위치를 사용하세요.")
    payload = record.get("payload")
    if not isinstance(record.get("identity"), dict) or not isinstance(payload, dict):
        raise ValueError("분석 캐시의 식별자 또는 내용이 없습니다.")
    if set(payload) != {"templateAnalysis", "styleProfile", "tableMap", "summary"}:
        raise ValueError("분석 캐시 내용 형식이 다릅니다.")
    if _digest(_json_bytes(payload)) != record.get("payloadSha256"):
        raise ValueError("분석 캐시 무결성 불일치. 기존 파일을 덮어쓰지 않습니다.")
    if not all(isinstance(value, dict) for value in payload.values()):
        raise ValueError("분석 캐시 내용 형식이 다릅니다.")
    return record


def _unchanged(source, identity):
    if _digest(source.read_bytes()) != identity["sourceSha256"]:
        raise ValueError("분석 중 원본이 바뀌었습니다. 현재 원본으로 다시 연결하세요.")


def _result(source, path, identity, payload, status, cache_hit):
    return {
        "status": status,
        "source": str(source),
        "sourceSha256": identity["sourceSha256"],
        "analysisKey": _digest(_json_bytes(identity)),
        "analysisPath": str(path),
        "cacheHit": cache_hit,
        "summary": payload["summary"],
        "native": "NOT_CHECKED",
    }


def prepare_source(source, cache_root):
    """Return reusable analysis. Never edit the source or replace existing cache data."""
    source = _source(source)
    cache = Path(cache_root).resolve()
    installed = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"
    if cache.is_relative_to(ROOT) or cache.is_relative_to(installed.resolve()):
        raise ValueError("사용자 원본 분석은 스킬 폴더 밖의 업무 폴더에 저장하세요.")
    if cache == source or (cache.exists() and not cache.is_dir()):
        raise ValueError("원본과 다른 캐시 폴더가 필요합니다.")
    identity = _identity(source)
    directory = cache / _digest(_json_bytes(identity))
    path = directory / "analysis.json"
    if directory.is_symlink():
        raise ValueError("분석 키 폴더는 심볼릭 링크일 수 없습니다.")
    if path.exists() or path.is_symlink():
        record = _read_record(path)
        if record["identity"] != identity:
            raise ValueError("분석 캐시와 현재 원본 또는 엔진이 다릅니다.")
        _unchanged(source, identity)
        return _result(source, path, identity, record["payload"], "REUSED", True)

    payload = _analyze(source, identity["sourceSha256"])
    _unchanged(source, identity)
    record = {"schema": SCHEMA, "identity": identity, "payload": payload,
              "payloadSha256": _digest(_json_bytes(payload))}
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=directory, prefix=".analysis-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_json_bytes(record))
            stream.flush()
            os.fsync(stream.fileno())
        _unchanged(source, identity)
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = _read_record(path)
            if existing != record:
                raise ValueError("동시에 생성된 분석이 다릅니다. 기존 캐시를 보존합니다.")
            return _result(source, path, identity, payload, "REUSED", True)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return _result(source, path, identity, payload, "ANALYZED", False)


def check_source(source, analysis_path):
    """Check whether a saved analysis still describes this source and runtime."""
    source = _source(source)
    supplied_path = Path(analysis_path).absolute()
    if supplied_path.is_symlink():
        raise ValueError("분석 파일은 심볼릭 링크일 수 없습니다.")
    path = supplied_path.resolve(strict=True)
    record = _read_record(path)
    identity = _identity(source)
    _unchanged(source, identity)
    if record["identity"] != identity:
        return {"status": "STALE", "source": str(source), "sourceSha256": identity["sourceSha256"],
                "analysisPath": str(path), "reason": "원본 또는 분석 엔진이 바뀌었습니다. 이전 위치와 계획을 재사용하지 마세요.",
                "native": "NOT_CHECKED"}
    return _result(source, path, identity, record["payload"], "CURRENT", True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("source")
    prepare.add_argument("--cache", required=True)
    check = commands.add_parser("check")
    check.add_argument("source")
    check.add_argument("--analysis", required=True)
    args = parser.parse_args()
    try:
        result = prepare_source(args.source, args.cache) if args.command == "prepare" else check_source(args.source, args.analysis)
    except (OSError, ValueError, RuntimeError) as error:
        result = {"status": "BLOCKED", "reason": str(error), "native": "NOT_CHECKED"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] in {"STALE", "BLOCKED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
