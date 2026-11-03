"""Assemble every template's reference outline and compare the PDF with its recorded lines.

Each assembly template may hold reproduction/outline.json (a reference outline; for a template made
from a complete plan, that plan's own example content) and reproduction/expected.json (pages and the
position of every text line in the Hangul PDF). A template registered later carries the same two files,
so a change to the assembly tools is checked against all templates the same way.

Usage: check_assembly_reproduction.py WORK_DIR [--template ID ...] [--catalog DIR] [--update]
  --update records the current output as expected (after a reviewed, intended change).
Requires Windows and Hangul; runs one assemble per template through the skill's task launcher.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'plugins/hancom-desktop/skills/hwpx'
CATALOG = SKILL / 'assets/document-templates/assembly'
TOLERANCE_PT = 0.5


def lines(pdf):
    """[page, x, y, text] of every non-empty text line, rounded to 0.1pt."""
    import pymupdf
    out = []
    with pymupdf.open(pdf) as document:
        for number, page in enumerate(document, 1):
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    text = ''.join(span['text'] for span in line['spans']).strip()
                    if text:
                        out.append([number, round(line['bbox'][0], 1), round(line['bbox'][1], 1), text])
    return out


def compare(expected, actual):
    """Differences between two line lists: page count, missing or extra lines, moved lines."""
    found = {}
    for line in actual['lines']:
        found.setdefault(line[3], []).append(line)
    moved, missing = [], []
    for line in expected['lines']:
        candidates = found.get(line[3], [])
        if not candidates:
            missing.append(line)
            continue
        other = candidates.pop(0)
        if other[0] != line[0] or abs(other[1] - line[1]) > TOLERANCE_PT or abs(other[2] - line[2]) > TOLERANCE_PT:
            moved.append(dict(text=line[3], expected=line[:3], actual=other[:3]))
    extra = [line for rest in found.values() for line in rest]
    return dict(pages=[expected['pages'], actual['pages']], missing=missing, extra=extra, moved=moved,
                ok=expected['pages'] == actual['pages'] and not missing and not extra and not moved)


def assemble(template, outline, catalog, work):
    out = work / template
    argv = ['powershell', '-NoProfile', '-File', str(SKILL / 'scripts/Invoke-HangulTask.ps1'), 'assemble', '--template', template,
            '--outline', str(outline), '--output', str(out.with_suffix('.hwpx')), '--pdf', str(out.with_suffix('.pdf')),
            '--run', str(work / f'run-{template}'), '--context', 'ordinary-shell', '--catalog', str(catalog)]
    done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace')
    result = json.loads(done.stdout)
    return result, out.with_suffix('.pdf')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('work'); parser.add_argument('--template', action='append'); parser.add_argument('--catalog', default=str(CATALOG))
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()
    catalog, work = Path(args.catalog).resolve(), Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    report = {}
    for folder in sorted(p for p in catalog.iterdir() if (p / 'reproduction/outline.json').is_file()):
        if args.template and folder.name not in args.template:
            continue
        result, pdf = assemble(folder.name, folder / 'reproduction/outline.json', catalog, work)
        entry = dict(status=result.get('status'), substitutions=result.get('substitutions'))
        if result.get('status') == 'PASS_NATIVE':
            actual = dict(pages=result['pages'], lines=lines(pdf))
            expected_path = folder / 'reproduction/expected.json'
            if args.update:
                expected_path.write_text(json.dumps(actual, ensure_ascii=False) + '\n', encoding='utf-8')
                entry['updated'] = True
            else:
                entry.update(compare(json.loads(expected_path.read_text(encoding='utf-8')), actual))
        report[folder.name] = entry
    ok = all(e.get('ok') or e.get('updated') for e in report.values())
    print(json.dumps(dict(status='PASS' if ok else 'FAIL', templates=report), ensure_ascii=False, indent=1))
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
