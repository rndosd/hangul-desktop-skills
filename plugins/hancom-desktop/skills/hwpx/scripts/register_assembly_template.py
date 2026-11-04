"""Register one source HWPX as an assembly template in one command, with the acceptance checks.

  1. propose_assembly_map.py: part map and self-reproduction outline
  2. build_assembly_template.py: parts and manifest; a part that fails to build is redrawn as a block
     (its role, or its paragraph for a table) and the build runs again
  3. check 1, self reproduction, no large misalignment: about the source's page count (source pages from its saved
     line positions), no empty page, chapter numbers as in the source; lines may move between pages
  4. check 2, other lengths: a "more" outline (more lines and rows, longer texts) and a "fewer" one must assemble
     (PASS_NATIVE). Each step opens Hangul once; the source PDF is printed inside the build's run.
  5. report.json: the checks, the blocks and their source wording to review, pages to look at
Checks 3 to 5 of tools/assembly-maps/README.md (source wording, describe-only use, approval) stay with the person.

Usage: register_assembly_template.py SOURCE.hwpx WORK_DIR --id ID [--retries 4] [--start TEXT]
Requires Windows, Hangul and the reviewed security module of the installed skill.
"""
import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
TASK = HERE / 'Invoke-HangulTask.ps1'
sys.path.insert(0, str(HERE))
from propose_assembly_map import propose  # noqa: E402
from build_assembly_template import NO_WINDOW  # noqa: E402


def settle(limit=60):
    """Wait until no Hangul process is left: the previous step's own instance may still be closing, and every native
    step refuses to start beside a running Hangul. Nothing is closed here; a Hangul the person opened stays."""
    import time
    for _ in range(limit):
        done = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Hwp.exe', '/NH'], capture_output=True, text=True, errors='replace',
                              creationflags=NO_WINDOW)
        if 'Hwp.exe' not in done.stdout:
            return
        time.sleep(1)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')


def build(work, attempt, part_map, source, source_pdf):
    folder = work / f'build-{attempt}'
    folder.mkdir()
    write(folder / 'map.json', part_map)
    settle()
    # the source's own PDF (check 1) is printed in the build's calibration run instead of opening Hangul once more
    done = subprocess.run([PYTHON, '-X', 'utf8', str(HERE / 'build_assembly_template.py'), str(folder / 'map.json'), str(source),
                           str(folder / 'work'), '--out', str(folder / 'catalog' / part_map['id']), '--render-source', str(source_pdf)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
    (folder / 'build.log').write_text(done.stdout + done.stderr, encoding='utf-8')
    failed = re.findall(r'part ([\w-]+): (.*)', done.stderr)
    return folder / 'catalog', (done.returncode == 0), failed[-1] if failed else (None, done.stderr.strip().splitlines()[-1:] or [''])


def assemble(catalog, template_id, outline, work, name):
    path = work / f'{name}.json'
    write(path, outline)
    settle()
    done = subprocess.run(['powershell', '-NoProfile', '-File', str(TASK), 'assemble', '--template', template_id, '--outline', str(path),
                           '--output', str(work / f'{name}.hwpx'), '--pdf', str(work / f'{name}.pdf'), '--run', str(work / f'run-{name}'),
                           '--context', 'ordinary-shell', '--catalog', str(catalog)],
                          capture_output=True, text=True, encoding='utf-8-sig', errors='replace', creationflags=NO_WINDOW)
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        return dict(status='FAIL_RUN', error=(done.stdout + done.stderr)[-600:])
    return dict(status=result.get('status'), pages=result.get('pages'), assembly=result.get('assembly'),
                blocks=result.get('blocks', []), substitutions=result.get('substitutions', []),
                error=result.get('error') or result.get('reason'), pdf=str(work / f'{name}.pdf'))


def source_page_starts(source, start=0):
    """Text of the paragraph that starts each page of the source, from the line positions Hangul saved
    (they restart at 0 on every page); a PDF of the source may print two pages per sheet. With start (a top
    paragraph index), only the pages from the one that paragraph opens."""
    import zipfile
    from lxml import etree
    hp = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
    with zipfile.ZipFile(source) as package:
        section = etree.fromstring(package.read('Contents/section0.xml'))
    starts, last = [], None
    for index, p in enumerate(section.findall(hp + 'p')):
        lines = p.find(hp + 'linesegarray')
        if lines is None or not len(lines):
            continue
        if last is None or int(lines[0].get('vertpos')) < last or index == start:
            starts.append((index, re.sub(r'\s+', '', ''.join(p.itertext()))))
        last = int(lines[-1].get('vertpos'))
    return [text for index, text in starts if index >= start]


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


def empty_blocks(folder, part_map):
    """Block parts that came out holding nothing (no text, table or picture): the source range was not saved."""
    import zipfile
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    found = []
    for name, part in manifest['parts'].items():
        if part['kind'] != 'block':
            continue
        with zipfile.ZipFile(folder / part['file']) as package:
            section = package.read('Contents/section0.xml').decode('utf-8')
        if not re.search(r'<hp:t>[^<]*\S|<hp:tbl |<hp:pic ', section):
            found.append(f'빈 블록: {name} (원본 문단 {part_map["parts"][name]["range"]})')
    return found


def cover_problems(pdf, cover):
    """The cover's title must be on the first page in one piece, with nothing above it but other cover values (a
    header the source carried, or a label holding the title, show here)."""
    import pymupdf
    with pymupdf.open(pdf) as document:
        lines = [re.sub(r'\s+', '', line) for line in document[0].get_text(sort=True).splitlines()]
    lines = [line for line in lines if line]
    text = ''.join(lines)
    title = re.sub(r'\s+', '', cover.get('title', ''))
    if not title:
        return []
    if len(title) >= 16 and re.search(r'(.{8,}).*\1', title):  # read from a header that repeats the title, say
        return [f'표지 제목으로 읽은 글에 같은 구절이 두 번 있음: {cover["title"][:40]}']
    at = text.find(title)
    if at < 0:
        return ['표지 제목이 첫 쪽에 한 덩어리로 나오지 않음(제목 자리가 다른 칸에 들어갔을 수 있음)']
    if text.count(title) > 1:
        return ['표지 제목이 첫 쪽에 두 번 나옴(원본의 머리말 같은 것이 따라왔을 수 있음)']
    starts = [sum(map(len, lines[:i])) for i in range(len(lines) + 1)]
    spread = sum(1 for i in range(len(lines)) if starts[i] < at + len(title) and starts[i + 1] > at)
    if spread > 3:  # a title wraps to two or three lines; more means it went into a narrow cell
        return [f'표지 제목이 {spread}줄로 쪼개짐(좁은 칸에 들어갔을 수 있음)']
    before = text[:at]
    for value in sorted((re.sub(r'\s+', '', str(v)) for k, v in cover.items() if k != 'title'), key=len, reverse=True):
        before = before.replace(value, '', 1)
    return [f'표지 제목 위에 다른 글자: {before[:30]}'] if len(before) > 3 else []


def variants(outline, part_map):
    """Other-length outlines, one Hangul run each: more (lines, rows and every text twice as long) and fewer."""
    def repeats(node):
        return node['t'] == 'table' and 'rows' in node and part_map['parts'][node['part']]['table'].get('repeat', True)

    def more(o):
        long(o)
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
    for name, change in (('more', more), ('fewer', fewer)):
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
    parser.add_argument('--start', help='register from the first paragraph holding this text (an attachment)')
    args = parser.parse_args()
    source, work = Path(args.source).resolve(strict=True), Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    report, exclude = dict(source=str(source), id=args.id, demoted=[]), []
    for attempt in range(1, args.retries + 2):
        part_map, outline, summary = propose(source, args.id, exclude, args.start)
        catalog, ok, (failed, message) = build(work, attempt, part_map, source, work / 'source.pdf')
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
    # check 1: self reproduction against the source's own pages (source.pdf came from the build)
    repro = assemble(catalog, args.id, outline, work, 'repro')
    check1 = dict(status=repro['status'], pages=repro['pages'], blocks=repro['blocks'])
    if repro['status'] == 'PASS_NATIVE':
        expected = source_page_starts(source, part_map['parts']['cover']['range'][0])
        found = page_starts(work / 'repro.pdf')
        # Lines may move between pages (letter spacing an author squeezed by hand does not carry over); only large
        # misalignments fail: another page count, an empty page, or chapter numbers that differ from the source's.
        numbers = summary.get('chapterNumbers', [])
        problems = []
        if abs(len(found) - len(expected)) > max(1, round(len(expected) * 0.1)):
            squeezed = summary.get('squeezedLines', 0)
            problems.append(f'쪽 수가 크게 다름: 원본 {len(expected)}, 재현 {len(found)}'
                            + (f' (원본이 자간을 줄여 한 줄에 맞춘 줄 {squeezed}개가 부품 모양으로 들어가 줄바꿈이 늘었을 수 있음)' if squeezed else ''))
        if '' in found:
            problems.append(f'빈 쪽: {[i + 1 for i, f in enumerate(found) if not f]}')
        if numbers and numbers != [str(n) for n in range(1, len(numbers) + 1)]:
            problems.append(f'장 번호가 원본과 다름: 원본 {numbers}, 조립은 1부터 차례로')
        # page counts alone pass a reproduction that lost a block or drew the cover wrong
        problems += empty_blocks(catalog / args.id, part_map) + cover_problems(work / 'repro.pdf', outline['cover'])
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
                              pdfs=[str(work / f'{n}.pdf') for n in ('source', 'repro', 'v-more', 'v-fewer')])
    write(work / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'demoted', 'check2')} | {'check1': {k: v for k, v in check1.items() if k != 'blocks'}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
