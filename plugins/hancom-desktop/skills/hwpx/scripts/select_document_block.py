"""List/match reusable inputs, or verify and copy one reviewed HWPX block."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys


class SelectionError(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


def require(condition: bool, reason: str, detail: str) -> None:
    if not condition:
        raise SelectionError(reason, detail)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVALID_JSON", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def decode_json(data: bytes, role: str):
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SelectionError(f"INVALID_{role}", str(error)) from error


def text(value, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), "INVALID_CATALOG", field)
    return value


def strings(value, field: str, *, nonempty: bool = False) -> list[str]:
    require(isinstance(value, list), "INVALID_CATALOG", field)
    require(not nonempty or bool(value), "INVALID_CATALOG", field)
    for item in value:
        text(item, field)
    return value


def record(value, required: set[str], field: str, optional: set[str] | None = None) -> dict:
    require(isinstance(value, dict), "INVALID_CATALOG", field)
    require(required <= value.keys(), "INVALID_CATALOG", f"Missing fields in {field}")
    require(value.keys() <= required | (optional or set()), "INVALID_CATALOG", f"Unknown fields in {field}")
    return value


@dataclass(frozen=True)
class FileRef:
    path: str
    sha256: str
    external: bool = False

    @classmethod
    def parse(cls, value, role: str):
        value = record(value, {"path", "sha256"}, role)
        location = text(value["path"], role + ".path")
        require("\x00" not in location, "INVALID_CATALOG", role + ".path")
        digest = text(value["sha256"], role + ".sha256")
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "INVALID_CATALOG", role + ".sha256")
        native = Path(location)
        windows = PureWindowsPath(location)
        absolute = native.is_absolute()
        external = role == "origin" and absolute
        if not external:
            require(not absolute and not windows.drive and not windows.root, "PATH_ESCAPE", role)
            require(".." not in windows.parts and ".." not in native.parts, "PATH_ESCAPE", role)
            require(":" not in location, "PATH_ESCAPE", role)
        suffixes = {"document": ".hwpx", "pdf": ".pdf", "preview": ".png", "evidence": ".json"}
        if role in suffixes:
            require(native.suffix.lower() == suffixes[role], "INVALID_CATALOG", role + " extension")
        return cls(location, digest, external)

    def resolve(self, root: Path, role: str) -> Path:
        candidate = Path(self.path) if self.external else root / self.path
        try:
            path = candidate.resolve(strict=True)
        except PermissionError as error:
            prefix = "SOURCE" if role == "origin" else role.upper()
            raise SelectionError(prefix + "_ACCESS_DENIED", f"{candidate}: {error}") from error
        except (OSError, RuntimeError) as error:
            reason = "SOURCE_UNAVAILABLE" if role == "origin" else role.upper() + "_UNAVAILABLE"
            raise SelectionError(reason, str(candidate)) from error
        require(self.external or path.is_relative_to(root), "PATH_ESCAPE", role)
        require(path.is_file(), "SOURCE_UNAVAILABLE" if role == "origin" else role.upper() + "_UNAVAILABLE", str(path))
        return path


@dataclass(frozen=True)
class Block:
    card: dict
    files: dict[str, FileRef]

    @classmethod
    def parse(cls, value):
        required = {"id", "label", "purposes", "keywords", "structure", "state", "content_state", "origin", "document", "pdf", "preview", "verification"}
        card = record(value, required, "block", {"fill", "fill_preview"})
        for key in ("id", "label"):
            text(card[key], key)
        strings(card["purposes"], "purposes", nonempty=True)
        strings(card["keywords"], "keywords")
        structure = record(card["structure"], {"pages", "summary"}, "structure")
        require(type(structure["pages"]) is int and structure["pages"] > 0, "INVALID_CATALOG", "structure.pages")
        text(structure["summary"], "structure.summary")
        require(card["state"] in ("draft", "reviewed"), "INVALID_CATALOG", "state")
        require(card["content_state"] in ("neutral_form", "source_excerpt"), "INVALID_CATALOG", "content_state")
        origin = record(card["origin"], {"file", "selection", "attribution", "reuse_conditions"}, "origin", {"source_id"})
        for key in ("selection", "attribution"):
            text(origin[key], "origin." + key)
        if "source_id" in origin:
            text(origin["source_id"], "origin.source_id")
        strings(origin["reuse_conditions"], "origin.reuse_conditions")
        verification = record(card["verification"], {"evidence", "tested_edits", "limits"}, "verification")
        strings(verification["limits"], "verification.limits")
        require(isinstance(verification["tested_edits"], list), "INVALID_CATALOG", "tested_edits")
        for edit in verification["tested_edits"]:
            record(edit, {"operation", "scope"}, "tested_edit")
            for key in ("operation", "scope"):
                text(edit[key], "tested_edit." + key)
        files = {role: FileRef.parse(card[role], role) for role in ("document", "pdf", "preview")}
        files["origin"] = FileRef.parse(origin["file"], "origin")
        files["evidence"] = FileRef.parse(verification["evidence"], "evidence")
        if "fill" in card:
            files["fill"] = FileRef.parse(card["fill"], "fill")
        if "fill_preview" in card:
            files["fill_preview"] = FileRef.parse(card["fill_preview"], "fill_preview")
        return cls(card, files)

    def evidence_bindings(self):
        return {
            "schema": "hwpx.block-evidence.v1",
            "outcome": "PASS",
            "block_id": self.card["id"],
            **{role + "_sha256": self.files[role].sha256 for role in ("origin", "document", "pdf", "preview")},
            "content_state": self.card["content_state"],
            "pages": self.card["structure"]["pages"],
            "tested_edits": self.card["verification"]["tested_edits"],
        }


class BlockLibrary:
    def __init__(self, catalog: Path):
        try:
            self.catalog = Path(catalog).resolve(strict=True)
            data = decode_json(self.catalog.read_bytes(), "CATALOG")
        except PermissionError as error:
            raise SelectionError("CATALOG_ACCESS_DENIED", f"{catalog}: {error}") from error
        except (OSError, RuntimeError) as error:
            raise SelectionError("CATALOG_UNAVAILABLE", str(catalog)) from error
        require(isinstance(data, dict) and data.get("schema") == "hwpx.block-library.v1", "INVALID_CATALOG", "schema")
        require(isinstance(data.get("blocks"), list), "INVALID_CATALOG", "blocks")
        self.root = self.catalog.parent
        self.blocks = {}
        for value in data["blocks"]:
            block = Block.parse(value)
            identity = block.card["id"]
            require(identity not in self.blocks, "DUPLICATE_ID", identity)
            self.blocks[identity] = block

    def input_model(self, block: Block) -> dict:
        """Read only the hash-bound JSON binding, not every source document."""
        if "fill" not in block.files:
            return {"status": "UNBOUND"}
        try:
            ref = block.files["fill"]
            path = ref.resolve(self.root, "fill")
            raw = path.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == ref.sha256,
                    "FILL_HASH_MISMATCH", block.card["id"])
            manifest = decode_json(raw, "FILL")
            require(isinstance(manifest, dict) and manifest.get("schema") == "hangul.fill.v1"
                    and manifest.get("blockId") == block.card["id"]
                    and manifest.get("sourceDocumentSha256") == block.files["document"].sha256,
                    "INVALID_FILL", block.card["id"])
            slots, repeats = manifest.get("slots"), manifest.get("repeats", {})
            require(isinstance(slots, dict) and isinstance(repeats, dict), "INVALID_FILL", "bindings")
            groups = {}
            for name, repeat in repeats.items():
                require(isinstance(repeat, dict) and isinstance(repeat.get("fields"), dict),
                        "INVALID_FILL", "repeat fields")
                location = repeat.get("path", "")
                layout = ("rows" if re.search(r"/row\[[^/]+\]$", location) else
                          "paragraphs" if re.search(r"/paragraph\[[^/]+\]$", location) else "unknown")
                groups[name] = {"layout": layout, "fields": list(repeat["fields"])}
            return {"status": "BOUND_JSON", "fields": [name for name,binding in slots.items() if 'valueFrom' not in binding], "repeats": groups}
        except (SelectionError, OSError, RuntimeError, TypeError) as error:
            return {"status": "UNAVAILABLE", "reason": getattr(error, "reason", "FILL_UNAVAILABLE"),
                    "detail": str(error)}

    def match_content(self, content: dict) -> dict:
        """Match already-structured facts; never infer semantics or flatten rows."""
        require(isinstance(content, dict) and not set(content) - {"layout", "records", "values", "template", "repeat"},
                "INVALID_CONTENT", "Expected layout and records/values; optional template/repeat.")
        layout = content.get("layout")
        require(isinstance(layout, str) and layout in {"rows", "paragraphs", "form"}, "INVALID_CONTENT", "layout: rows, paragraphs or form")
        if layout == "form":
            require("records" not in content and "repeat" not in content, "INVALID_CONTENT", "form uses values")
            values = content.get("values")
            records = [values]
        else:
            require("values" not in content, "INVALID_CONTENT", "rows/paragraphs use records")
            records = content.get("records")
            require(isinstance(records, list) and 1 <= len(records) <= 100, "INVALID_CONTENT", "1..100 records")
        fields = set()
        for item in records:
            require(isinstance(item, dict) and bool(item), "INVALID_CONTENT", "Nonempty records required")
            for key, value in item.items():
                text(key, "content field")
                require(isinstance(value, str) and not any(c in value for c in "\r\n\t"),
                        "INVALID_CONTENT", "Each value is a single-paragraph string")
                fields.add(key)
        requested = content.get("template")
        if requested is not None:
            text(requested, "content template")
            require(requested in self.blocks, "BLOCK_NOT_FOUND", str(requested))
        if "repeat" in content:
            text(content["repeat"], "content repeat")
        candidates, unavailable = [], []
        for block in self.blocks.values():
            if block.card["state"] != "reviewed" or (requested and block.card["id"] != requested):
                continue
            model = self.input_model(block)
            if model["status"] == "UNAVAILABLE":
                unavailable.append({"template": block.card["id"], "reason": model["reason"]})
                continue
            if model["status"] != "BOUND_JSON":
                continue
            bindings = [(None, {"layout": "form", "fields": model["fields"]})] if layout == "form" else model["repeats"].items()
            for name, binding in bindings:
                if binding["layout"] != layout or ("repeat" in content and content["repeat"] != name):
                    continue
                available = set(binding["fields"])
                if not fields <= available:
                    continue
                fill_values = dict(records[0]) if layout == "form" else {name: records}
                candidates.append({"template": block.card["id"], "label": block.card["label"],
                                   "layout": layout, "repeat": name, "fields": binding["fields"],
                                   "unfilledFields": sorted(available - fields), "values": fill_values})
        candidates.sort(key=lambda item: (len(item["unfilledFields"]), item["template"], item["repeat"] or ""))
        best = [item for item in candidates if len(item["unfilledFields"]) == len(candidates[0]["unfilledFields"])] if candidates else []
        selected = candidates[0] if len(candidates) == 1 and not unavailable else None
        return {"status": "CONTENT_MATCHES", "layout": layout, "inputFields": sorted(fields),
                "selected": selected, "candidates": candidates[:5], "candidateCount": len(candidates),
                "bestCount": len(best), "unavailableBindings": unavailable,
                "nextStep": "Existing fill verifies the selected source and applies these values." if selected else
                            "Choose template/repeat explicitly from compatible candidates, or use another supported source; do not flatten facts to force a match.",
                "current_files": "NOT_CHECKED", "native": "NOT_CHECKED"}

    def list(self, purpose: str | None = None, *, summary: bool = False) -> dict:
        cards = [block.card for block in self.blocks.values()
                 if purpose is None or purpose in block.card["purposes"]]
        if summary:
            cards = [{
                "id": card["id"], "label": card["label"],
                "purposes": card["purposes"], "structure": card["structure"],
                "state": card["state"], "content_state": card["content_state"],
                "preview": card.get("fill_preview",card["preview"])["path"],
                "fillable": "fill" in card,
                "inputModel": self.input_model(self.blocks[card["id"]]),
            } for card in cards]
            for card in cards:
                model = card["inputModel"]
                if "fields" in model:
                    model["fieldCount"] = len(model["fields"])
                    model["fields"] = model["fields"][:6]
        return {
            "status": "BLOCK_LIST",
            "catalog": str(self.catalog),
            "current_files": "NOT_CHECKED",
            **({"view": "summary", "details": "Use --id ID to verify the selected block and read its full constraints before editing."} if summary else {}),
            "blocks": cards,
        }

    def select(self, block_id: str, output: Path | None = None) -> dict:
        require(block_id in self.blocks, "BLOCK_NOT_FOUND", block_id)
        block = self.blocks[block_id]
        require(block.card["state"] == "reviewed", "BLOCK_NOT_REVIEWED", block_id)
        paths, payloads = {}, {}
        for role in ("origin", "document", "pdf", "preview", "evidence"):
            ref = block.files[role]
            path = ref.resolve(self.root, role)
            try:
                data = path.read_bytes()
            except PermissionError as error:
                prefix = "SOURCE" if role == "origin" else role.upper()
                raise SelectionError(prefix + "_ACCESS_DENIED", f"{path}: {error}") from error
            except OSError as error:
                raise SelectionError("SOURCE_UNAVAILABLE" if role == "origin" else role.upper() + "_UNAVAILABLE", str(path)) from error
            digest = hashlib.sha256(data).hexdigest()
            require(digest == ref.sha256, "STALE_SOURCE" if role == "origin" else role.upper() + "_HASH_MISMATCH", str(path))
            paths[role] = path
            if role in ("document", "evidence"):
                payloads[role] = data
        evidence = decode_json(payloads["evidence"], "EVIDENCE")
        require(isinstance(evidence, dict), "INVALID_EVIDENCE", "Expected an evidence object")
        for key, expected in block.evidence_bindings().items():
            actual = evidence.get(key)
            require(type(actual) is type(expected) and actual == expected, "EVIDENCE_BINDING_MISMATCH", key)
        receipt = {
            "status": "VERIFIED_BLOCK",
            "catalog": str(self.catalog),
            "block": block.card,
            "files": {role: {"path": str(path), "sha256": block.files[role].sha256} for role, path in paths.items()},
            "new_content_native": "NOT_CHECKED",
        }
        if output is not None:
            receipt["output"] = str(copy_new(Path(output), payloads["document"]))
        return receipt


def copy_new(output: Path, data: bytes) -> Path:
    require(output.suffix.lower() == ".hwpx", "INVALID_OUTPUT", "Output extension must be .hwpx")
    require(not output.is_symlink(), "OUTPUT_EXISTS", str(output))
    try:
        parent = output.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise SelectionError("INVALID_OUTPUT", "Output parent is unavailable") from error
    require(parent.is_dir(), "INVALID_OUTPUT", "Output parent is not a directory")
    path = parent / output.name
    identity = None
    try:
        with path.open("xb") as handle:
            stat = os.fstat(handle.fileno())
            identity = (stat.st_dev, stat.st_ino)
            handle.write(data)
    except FileExistsError as error:
        raise SelectionError("OUTPUT_EXISTS", str(path)) from error
    except OSError as error:
        if identity is not None:
            try:
                stat = path.lstat()
                if (stat.st_dev, stat.st_ino) == identity:
                    path.unlink()
            except OSError:
                pass
        raise SelectionError("OUTPUT_WRITE_FAILED", str(path)) from error
    return path


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise SelectionError("INVALID_ARGUMENTS", message)


def main(argv=None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--list", action="store_true")
    choice.add_argument("--id", dest="block_id")
    choice.add_argument("--content", type=Path, help="Match structured rows/paragraphs/form values to prepared input bindings.")
    parser.add_argument("--purpose")
    parser.add_argument("--summary", action="store_true", help="Compact candidate list; requires --list. File verification remains --id.")
    parser.add_argument("--catalog", type=Path, default=Path(__file__).absolute().parents[1] / "assets/document-templates/full-plans.json")
    parser.add_argument("--output", type=Path)
    try:
        args = parser.parse_args(argv)
        require(args.list or args.purpose is None, "INVALID_ARGUMENTS", "--purpose requires --list")
        require(args.list or not args.summary, "INVALID_ARGUMENTS", "--summary requires --list")
        require(not args.list or args.output is None, "INVALID_ARGUMENTS", "--output requires --id")
        require(not args.content or args.output is None, "INVALID_ARGUMENTS", "--content is read-only; use fill --content to write")
        library = BlockLibrary(args.catalog)
        if args.list:
            result = library.list(args.purpose, summary=args.summary)
        elif args.content:
            result = library.match_content(decode_json(args.content.read_bytes(), "CONTENT"))
        else:
            result = library.select(args.block_id, args.output)
    except SelectionError as error:
        failure = {"status": "BLOCKED", "reason": error.reason, "detail": str(error)}
        if error.reason.endswith("_ACCESS_DENIED"):
            failure["nextStep"] = (
                "Check path access in the current execution environment. If authorized, "
                "retry the same command in a host-approved context; keep path and hash validation enabled."
            )
        print(json.dumps(failure, ensure_ascii=True))
        return 2
    except (OSError, RuntimeError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": "IO_ERROR", "detail": str(error)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
