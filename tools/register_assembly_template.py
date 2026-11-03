"""Register one source HWPX as an assembly template in one command, with the acceptance checks.

  1. propose_assembly_map.py: part map and self-reproduction outline
  2. build_assembly_template.py: parts and manifest; a part that fails to build is redrawn as a block
     (its role, or its paragraph for a table) and the build runs again
  3. check 1, self reproduction, no large misalignment: about the source's page count (source pages from its saved
     line positions), no empty page, chapter numbers as in the source; lines may move between pages
  4. check 2, other lengths: "more", "fewer" and "long" outlines must assemble (PASS_NATIVE)
  5. report.json: the checks, the blocks and their source wording to review, pages to look at
Checks 3 to 5 of tools/assembly-maps/README.md (source wording, describe-only use, approval) stay with the person.

Usage: register_assembly_template.py SOURCE.hwpx WORK_DIR --id ID [--retries 4]
Requires Windows, Hangul and the reviewed security module of the installed skill.
"""
import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
TASK = ROOT / 'plugins/hancom-desktop/skills/hwpx/scripts/Invoke-HangulTask.ps1'
sys.path.insert(0, str(ROOT / 'tools'))
from propose_assembly_map import propose  # noqa: E402
from build_assembly_template import native  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')


def build(work, attempt, part_map, source):
    folder = work / f'build-{attempt}'
    folder.mkdir()
    write(folder / 'map.json', part_map)
    done = subprocess.run([PYTHON, '-X', 'utf8', str(ROOT / 'tools/build_assembly_template.py'), str(folder / 'map.json'), str(source),
                           str(folder / 'work'), '--out', str(folder / 'catalog' / part_map['id'])],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    (folder / 'build.log').write_text(done.stdout + done.stderr, encoding='utf-8')
    failed = re.findall(r'part ([\w-]+): (.*)', done.stderr)
    return folder / 'catalog', (done.returncode == 0), failed[-1] if failed else (None, done.stderr.strip().splitlines()[-1:] or [''])


def assemble(catalog, template_id, outline, work, name):
    path = work / f'{name}.json'
    write(path, outline)
    done = subprocess.run(['powershell', '-NoProfile', '-File', str(TASK), 'assemble', '--template', template_id, '--outline', str(path),
                           '--output', str(work / f'{name}.hwpx'), '--pdf', str(work / f'{name}.pdf'), '--run', str(work / f'run-{name}'),
                           '--context', 'ordinary-shell', '--catalog', str(catalog)],
                          capture_output=True, text=True, encoding='utf-8-sig', errors='replace')
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        return dict(status='FAIL_RUN', error=(done.stdout + done.stderr)[-600:])
    return dict(status=result.get('status'), pages=result.get('pages'), assembly=result.get('assembly'),
                blocks=result.get('blocks', []), substitutions=result.get('substitutions', []),
                error=result.get('error') or result.get('reason'), pdf=str(work / f'{name}.pdf'))


def source_page_starts(source):
    """Text of the paragraph that starts each page of the source, from the line positions Hangul saved
    (they restart at 0 on every page); a PDF of the source may print two pages per sheet."""
    import zipfile
    from lxml import etree
    hp = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
    with zipfile.ZipFile(source) as package:
        section = etree.fromstring(package.read('Contents/section0.xml'))
    starts, last = [], None
    for p in section.findall(hp + 'p'):
        lines = p.find(hp + 'linesegarray')
        if lines is None or not len(lines):
            continue
        if last is None or int(lines[0].get('vertpos')) < last:
            starts.append(re.sub(r'\s+', '', ''.join(p.itertext())))
        last = int(lines[-1].get('vertpos'))
    return starts


def same_start(found, expected):
    """A page's top line and the source paragraph that starts the page name the same text."""
    return bool(found) and bool(expected) and (found[:6] in expected or expected[:6] in found)


def page_starts(pdf):
    """Top text line of every page, page numbers left out."""
    import pymupdf
    starts = []
    with pymupdf.open(pdf) as document:
        for page in document:
            for clip in [page.rect]:
                rows = {}  # words on one visual line, by height; the topmost line that is not a page number
                for word in page.get_text('words', clip=clip):
                    rows.setdefault(round(word[1] / 3), []).append(word)
                lines = [''.join(w[4] for w in sorted(rows[y], key=lambda w: w[0])) for y in sorted(rows)]
                lines = [line for line in lines if not re.fullmatch(r'-?\d+-?', line)]
                starts.append(lines[0][:12] if lines else '')  # an empty page counts, and matches no source page
    return starts


def variants(outline, part_map):
    """Other-length outlines: more lines and rows, fewer chapters and rows, longer texts."""
    def repeats(node):
        return node['t'] == 'table' and 'rows' in node and part_map['parts'][node['part']]['table'].get('repeat', True)

    def more(o):
        nodes = []
        for node in o['nodes']:
            nodes.append(node)
            if node['t'] in ('subhead', 'item', 'dash', 'dot', 'note', 'lead') or node['t'] == 'heading' and node['level'] > 1:
                nodes.append(dict(node, text=node['text'] + ' (추가)', **({'pageBreakBefore': False} if 'pageBreakBefore' in node else {})))
            if repeats(node):
                node['rows'] = node['rows'] * 3
        o['nodes'] = [{k: v for k, v in n.items() if not (k == 'pageBreakBefore' and v is False)} for n in nodes]

    def fewer(o):
        chapters = [i for i, n in enumerate(o['nodes']) if n['t'] == 'chapter']
        if len(chapters) >= 3:
            o['nodes'] = o['nodes'][:chapters[1]] + o['nodes'][chapters[2]:]
        for node in o['nodes']:
            if repeats(node):
                node['rows'] = node['rows'][:1]
            if node['t'] == 'table' and 'values' in node:
                node['values'] = dict(list(node['values'].items())[:max(1, len(node['values']) // 2)])

    def long(o):
        for node in o['nodes']:
            if node['t'] == 'chapter':
                node['text'] += ' 및 세부 운영 방안'
            elif 'text' in node:
                node['text'] = node['text'] + ', ' + node['text']
        o['cover']['title'] += '(세부 운영 계획)'

    out = {}
    for name, change in (('more', more), ('fewer', fewer), ('long', long)):
        value = copy.deepcopy(outline)
        change(value)
        out[name] = value
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source')
    parser.add_argument('work')
    parser.add_argument('--id', required=True)
    parser.add_argument('--retries', type=int, default=4)
    args = parser.parse_args()
    source, work = Path(args.source).resolve(strict=True), Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    report, exclude = dict(source=str(source), id=args.id, demoted=[]), []
    for attempt in range(1, args.retries + 2):
        part_map, outline, summary = propose(source, args.id, exclude)
        catalog, ok, (failed, message) = build(work, attempt, part_map, source)
        if ok:
            break
        if failed in (None, 'cover', 'chapter', 'chapter_first') or failed not in part_map['parts']                 or part_map['parts'][failed]['kind'] == 'block' or attempt > args.retries:  # a block has nothing to fall back to
            report.update(status='FAIL_BUILD', part=failed, error=message, proposal=summary)
            write(work / 'report.json', report)
            print(json.dumps(report, ensure_ascii=False, indent=1))
            return 1
        spec = part_map['parts'][failed]
        exclude.append(f'p{spec["range"][0]}' if spec['kind'] in ('table', 'block') else failed)
        report['demoted'].append(dict(part=failed, error=message[:200], now=exclude[-1]))
    write(work / 'map.json', part_map)
    write(work / 'outline.json', outline)
    report.update(proposal=summary, catalog=str(catalog))
    # check 1: self reproduction against the source's own pages
    native(dict(source=str(source), blocks=[], renders=[dict(part=str(source), pdf=str(work / 'source.pdf'))]), work, 'render-source')
    repro = assemble(catalog, args.id, outline, work, 'repro')
    check1 = dict(status=repro['status'], pages=repro['pages'], blocks=repro['blocks'])
    if repro['status'] == 'PASS_NATIVE':
        expected = source_page_starts(source)
        found = page_starts(work / 'repro.pdf')
        # Lines may move between pages (letter spacing an author squeezed by hand does not carry over); only large
        # misalignments fail: another page count, an empty page, or chapter numbers that differ from the source's.
        numbers = summary.get('chapterNumbers', [])
        problems = []
        if abs(len(found) - len(expected)) > max(1, round(len(expected) * 0.1)):
            problems.append(f'쪽 수가 크게 다름: 원본 {len(expected)}, 재현 {len(found)}')
        if '' in found:
            problems.append(f'빈 쪽: {[i + 1 for i, f in enumerate(found) if not f]}')
        if numbers and numbers != [str(n) for n in range(1, len(numbers) + 1)]:
            problems.append(f'장 번호가 원본과 다름: 원본 {numbers}, 조립은 1부터 차례로')
        check1.update(sourcePages=len(expected), sourcePageStarts=[e[:16] for e in expected], pageStarts=found,
                      sameStarts=sum(same_start(f, e) for f, e in zip(found, expected)), problems=problems, ok=not problems)
    else:
        check1.update(ok=False, error=repro['error'])
    report['check1'] = check1
    # check 2: other lengths
    report['check2'] = {name: (lambda r: dict(status=r['status'], pages=r['pages'], ok=r['status'] == 'PASS_NATIVE', error=r['error']))(
        assemble(catalog, args.id, value, work, f'v-{name}')) for name, value in variants(outline, part_map).items()}
    report['status'] = 'PASS' if check1['ok'] and all(v['ok'] for v in report['check2'].values()) else 'REVIEW'
    report['toReview'] = dict(blocks=[dict(part=b['used'], texts=b['texts'][:12], reviewTexts=b.get('reviewTexts', []),
                                           numberedLines=b.get('numberedLines', [])) for b in check1['blocks']],
                              pdfs=[str(work / f'{n}.pdf') for n in ('source', 'repro', 'v-more', 'v-fewer', 'v-long')])
    write(work / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'demoted', 'check2')} | {'check1': {k: v for k, v in check1.items() if k != 'blocks'}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
