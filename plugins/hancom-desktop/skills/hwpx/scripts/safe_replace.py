"""Bounded public-API text replacement; XML is inspected, never edited.

Validated API: python-hwpx 6.3.0 (Apache-2.0), doc.text.replace.
Local E03 evidence: 2026-09-08. No upstream implementation is copied.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from workspace_candidate_directory import workspace_candidate_directory
import zipfile
from importlib.metadata import version
from pathlib import Path
from xml.etree import ElementTree as ET


def local(tag):
    return tag.rsplit('}', 1)[-1]


def snapshot(path, old=None, new=None):
    """Compare all XML structure, text and binary payloads; ignore layout caches."""
    def tree(node):
        if local(node.tag).lower() == 'linesegarray':
            return None
        text = node.text or ''
        if local(node.tag) == 't' and old is not None:
            text = text.replace(old, new)
        children = tuple(v for c in node for v in [tree(c)] if v is not None)
        return node.tag, tuple(sorted(node.attrib.items())), text, children
    parts = {}
    matches = 0
    with zipfile.ZipFile(path) as package:
        if len(package.namelist()) != len(set(package.namelist())):
            raise ValueError('duplicate ZIP members')
        for name in package.namelist():
            data = package.read(name)
            if name.endswith(('.xml', '.hpf')):
                root = ET.fromstring(data)
                if old:
                    matches += sum((n.text or '').count(old) for n in root.iter() if local(n.tag) == 't')
                parts[name] = tree(root)
            elif not name.startswith('Preview/'):
                parts[name] = hashlib.sha256(data).hexdigest()
    return parts, matches


def replace(source, output, old, new):
    from hwpx import HwpxDocument
    from hwpx.tools.package_validator import validate_editor_open_safety
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError('output must be a new path, distinct from source')
    if not old or old == new or any(c in old + new for c in '\r\n'):
        raise ValueError('require distinct nonempty search and single-line replacement')
    installed = version('python-hwpx')
    if installed != '6.3.0':
        raise ValueError(f'unvalidated python-hwpx version: {installed}')
    from diagnose_edit import diagnose
    plan = diagnose(source, 'replace_text', old)
    if plan['decision'] != 'ALLOW':
        raise ValueError('preflight blocked: ' + plan.get('reason', 'unsupported'))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    expected, matches = snapshot(source, old, new)
    if matches != 1:
        raise ValueError(f'exactly one text-node occurrence required, found {matches}')
    with workspace_candidate_directory(prefix='hwpx-safe-',dir=output.parent) as tmp:
        candidate = Path(tmp) / 'candidate.hwpx'
        doc = HwpxDocument.open(source)
        try:
            changed = doc.text.replace(old, new, limit=1)
            if changed != 1:
                raise ValueError('public API did not replace exactly one occurrence')
            doc.save_to_path(candidate)
        finally:
            doc.close()
        reopened = HwpxDocument.open(candidate)
        reopened.close()
        if not validate_editor_open_safety(candidate).ok:
            raise ValueError('editor open-safety validation failed')
        actual, _ = snapshot(candidate)
        if actual != expected:
            raise ValueError('preservation mismatch; candidate not published')
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
            raise ValueError('source changed during operation')
        with output.open('xb') as stream:
            stream.write(candidate.read_bytes())
    return {'status': 'PASS_STRUCTURE', 'replacements': 1,
            'source_sha256': source_hash, 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'python_hwpx': installed, 'render_status': 'not_checked',
            'ignored_comparison_parts': ['Preview/*', 'lineSegArray layout caches']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('--find', required=True)
    parser.add_argument('--replace', required=True)
    args = parser.parse_args()
    try:
        result = replace(args.source, args.output, args.find, args.replace)
    except Exception as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
