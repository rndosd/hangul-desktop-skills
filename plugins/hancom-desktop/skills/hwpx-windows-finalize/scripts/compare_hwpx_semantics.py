#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def summarize(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"corrupt ZIP entry: {bad}")
        names = archive.namelist()
        section_names = sorted(
            name for name in names
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        text_parts: list[str] = []
        paragraphs = 0
        tables = 0
        page_breaks = 0
        for name in section_names:
            root = ET.fromstring(archive.read(name))
            for element in root.iter():
                kind = local_name(element.tag)
                if kind == "t" and element.text:
                    text_parts.append(element.text)
                elif kind == "p":
                    paragraphs += 1
                    if element.attrib.get("pageBreak") == "1":
                        page_breaks += 1
                elif kind == "tbl":
                    tables += 1
        text = "".join(text_parts)
        binaries = sum(1 for name in names if name.startswith("BinData/") and not name.endswith("/"))
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sections": len(section_names),
        "paragraphs": paragraphs,
        "tables": tables,
        "pageBreaks": page_breaks,
        "binaries": binaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("final", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    before = summarize(args.candidate.resolve())
    after = summarize(args.final.resolve())
    fields = ["textSha256", "sections", "paragraphs", "tables", "pageBreaks", "binaries"]
    differences = {
        field: {"candidate": before[field], "final": after[field]}
        for field in fields
        if before[field] != after[field]
    }
    result = {
        "status": "PASS_FULL" if not differences else "FAIL_VALIDATION",
        "candidate": before,
        "final": after,
        "differences": differences,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["status"])
    return 0 if not differences else 4


if __name__ == "__main__":
    sys.exit(main())
