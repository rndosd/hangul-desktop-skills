"""Table bench: content and structure edits on real public tables, then Hangul output.

Each scenario runs the skill's own command (common entry or its table helper), then checks
  - outcome: PASS (edit applied), BLOCKED (refused) or ERROR, against the expected outcome
  - target table: the requested change happened (expected grid predicate)
  - everything else: every other table's cells and all body paragraphs are unchanged
  - for refused edits: no output file was written
and exports successful outputs through Hangul for page metrics (table splits, short tails).

Usage: run_tables.py SKILLS_DIR FIXTURE_DIR OUT_DIR
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'plugins/hancom-desktop/skills/hwpx-windows-finalize/scripts'))
import page_layout as page_metrics  # noqa: E402  (the shipped measurement, used here as the bench's ruler)

L = lambda e: etree.QName(e).localname
LONG = ' 이 칸에는 운영 방법과 확인 기준을 함께 적어 내용이 여러 줄로 늘어날 때 행 높이와 쪽 나눔이 자연스러운지 확인한다.'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tables(path):
    """Document-order tables (nested included, like the helpers) -> {index: {(row, col): text}}; plus body text."""
    with zipfile.ZipFile(path) as z:
        sections = sorted(n for n in z.namelist() if n.startswith('Contents/section') and n.endswith('.xml'))
        roots = [etree.fromstring(z.read(n)) for n in sections]
    grids, body = {}, []
    index = 0
    for root in roots:
        for node in root.iter():
            if L(node) == 'tbl':
                index += 1
                grid = {}
                for cell in node.iter():
                    if L(cell) != 'tc' or next((a for a in cell.iterancestors() if L(a) == 'tbl'), None) is not node:
                        continue
                    addr = next((c for c in cell if L(c) == 'cellAddr'), None)
                    text = ''.join(t.text or '' for t in cell.iter() if L(t) == 't')
                    grid[(int(addr.get('rowAddr')) + 1, int(addr.get('colAddr')) + 1)] = text
                grids[index] = grid
            elif L(node) == 'p' and not any(L(a) == 'tbl' for a in node.iterancestors()):
                body.append(''.join(t.text or '' for t in node.iter() if L(t) == 't' and not any(L(a) == 'tbl' for a in t.iterancestors())))
    return grids, body


class Bench:
    def __init__(self, skills, fixtures, out):
        self.launcher = Path(skills) / 'hwpx/scripts/Invoke-HangulTask.ps1'
        self.native = Path(skills) / 'hwpx-windows-finalize/scripts'
        self.fx, self.out = Path(fixtures), Path(out)
        self.out.mkdir(parents=True, exist_ok=False)

    def cli(self, *args):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(self.launcher), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        text = result.stdout.strip()
        try:
            return json.loads(text[text.find('{'):]) if '{' in text else {'status': 'NO_OUTPUT', 'stderr': result.stderr[-300:]}
        except ValueError:
            return {'status': 'UNPARSED', 'stdout': text[-300:], 'stderr': result.stderr[-300:]}

    def helper(self, script, source, output, request, table=None, inspect=True):
        """inspect (for hashes) then apply a table helper with a request built from the inspection."""
        info = {}
        if inspect:
            ins = self.out / f'{output.stem}-inspect.json'
            refused = self.cli('tool', script, 'inspect', source, '--table', table, '--output', ins)
            if not ins.is_file():
                return dict(refused, stage='inspect')  # the helper refused the table before any edit
            text = ins.read_text(encoding='utf-8').strip()
            if not text:
                return dict(refused, stage='inspect')
            info = json.loads(text)
        body = request(info) if callable(request) else request
        body.setdefault('source_sha256', info.get('source_sha256', sha(source)))
        req = self.out / f'{output.stem}-request.json'
        req.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
        args = ['tool', script, 'apply', source, output, '--request', req] if script != 'safe_table_columns.py' else ['tool', script, source, output, '--request', req]
        return self.cli(*args)

    def export(self, hwpx):
        pdf = hwpx.with_suffix('.pdf')
        subprocess.run([sys.executable, '-X', 'utf8', '-B', str(self.native / 'run_native_job.py'), str(hwpx), '--mode', 'OpenOnly',
                        '--pdf', str(pdf), '--run', str(self.out / f'run-{hwpx.stem}'), '--context', 'ordinary-shell'], capture_output=True)
        time.sleep(2)
        return pdf if pdf.is_file() else None


def text_edit(bench, source, output, edits, table=None):
    """Common entry: inspect -> text-plan -> text for exact phrases; edits = [(find, replace)], optionally inside one table."""
    queries = bench.out / f'{output.stem}-q.json'
    queries.write_text(json.dumps([{'find': f} for f, _ in edits], ensure_ascii=False), encoding='utf-8')
    targets = bench.out / f'{output.stem}-targets.json'
    bench.cli('inspect', source, '--queries', queries, '--output', targets)
    if not targets.is_file():
        return {'status': 'BLOCKED', 'reason': 'inspect produced no targets'}
    found = json.loads(targets.read_text(encoding='utf-8'))
    changes = []
    for i, (entry, (find, new)) in enumerate(zip(found, edits)):
        listed = entry.get('targets') or entry.get('candidates') or []
        # Prefer the match whose whole context is the phrase (the cell itself), not a longer cell containing it.
        if table is not None:
            listed = [c for c in listed if (c.get('scope') or {}).get('table') == table]
        listed = sorted(listed, key=lambda c: c.get('context') != find)
        ids = [c['target_id'] for c in listed if c.get('supported')]
        if not ids:
            reasons = entry.get('unsupportedReasons') or {}
            return {'status': 'BLOCKED', 'reason': f'no supported target for query {i}: {reasons}'}
        changes.append({'query': i, 'targets': ids[:1], 'replace': new})
    changes_file = bench.out / f'{output.stem}-changes.json'
    changes_file.write_text(json.dumps(changes, ensure_ascii=False), encoding='utf-8')
    plan = bench.out / f'{output.stem}-plan.json'
    planned = bench.cli('text-plan', '--inspection', targets, '--changes', changes_file, '--output', plan)
    if planned.get('status') != 'PLANNED':
        return planned
    return bench.cli('text', source, output, '--plan', plan)


def only_target_changed(before, after, table, predicate):
    (bg, bb), (ag, ab) = before, after
    problems = []
    if bb != ab:
        problems.append('body paragraphs changed')
    for index in set(bg) | set(ag):
        if index != table and bg.get(index) != ag.get(index):
            problems.append(f'table {index} changed')
    ok, detail = predicate(bg.get(table, {}), ag.get(table, {}))
    if not ok:
        problems.append(detail)
    return problems


def rows(grid):
    return max((r for r, _ in grid), default=0)


def changed_cells(b, a):
    return {k for k in set(b) | set(a) if b.get(k) != a.get(k)}


def scenarios(fx):
    """(id, title, fixture, table, kind, run(bench, src, out) -> result, expected outcome, predicate(before, after))."""
    B, CS, A, C, MR = 'B.hwpx', 'CS.hwpx', 'A.hwpx', 'C.hwpx', 'MR.hwpx'
    s = []
    add = lambda *x: s.append(x)
    add('S01', '셀 문구 1개 수정', B, 3, 'content', lambda b, src, out: text_edit(b, src, out, [('사천여고', '사천여자고')]),
        'PASS', lambda bf, af: (changed_cells(bf, af) == {(2, 3)} and af[(2, 3)] == '사천여자고', 'only cell (2,3) should change'))
    add('S02', '셀 문구 3개 동시 수정', B, 3, 'content',
        lambda b, src, out: text_edit(b, src, out, [('범어고', '범어고등'), ('보광고', '보광고등'), ('태봉고', '태봉고등')]),
        'PASS', lambda bf, af: (len(changed_cells(bf, af)) == 3, '3 cells should change'))
    add('S03', '병합·서식 섞인 셀 문구 수정', A, 7, 'content', None, 'PASS', lambda bf, af: (len(changed_cells(bf, af)) == 1, '1 cell should change'))
    add('S04', '중첩 표 안 셀 문구 수정(미검증 범위)', C, 10, 'limit', None, 'BLOCKED', None)
    add('S05', '긴 내용으로 행 높이 증가', CS, 7, 'content', None, 'PASS', lambda bf, af: (len(changed_cells(bf, af)) == 1, '1 cell should change'))
    add('S06', '셀 크기 고정 표 행 삭제+추가(막아야 함)', B, 3, 'limit', None, 'BLOCKED', None)
    add('S06b', '행 삭제+추가(공통 table, 크기 조절 가능한 표)', CS, 4, 'structure', None, 'PASS', lambda bf, af: (rows(af) == rows(bf), 'row count should stay'))
    add('S07', '표 끝에 행 추가', CS, 4, 'structure', None, 'PASS', lambda bf, af: (rows(af) == rows(bf) + 1, 'one more row'))
    add('S08', '중간 행 삭제', CS, 4, 'structure', None, 'PASS', lambda bf, af: (rows(af) == rows(bf) - 1, 'one fewer row'))
    add('S09', '열 너비 재분배(resize)', CS, 4, 'structure', None, 'PASS', lambda bf, af: (bf == af, 'text unchanged'))
    add('S10', '내용 있는 두 칸 병합(내용 버림 방지)', CS, 4, 'limit', None, 'BLOCKED', None)
    add('S10b', '두 칸 내용을 모두 남기며 병합', MR, 1, 'structure', None, 'PASS',
        lambda bf, af: (len(af) == len(bf) - 1 and all(t in ''.join(af.values()) for t in bf.values()), 'one fewer cell, no text lost'))
    add('S11', '내용을 합친 병합 해제(되돌릴 칸을 알 수 없어 막아야 함)', MR, 1, 'limit', None, 'BLOCKED', None)
    add('S12', '여러 열 정렬 변경', CS, 7, 'format', None, 'PASS', lambda bf, af: (bf == af, 'text unchanged'))
    add('S13', '셀 세로 정렬·안 여백', CS, 7, 'format', None, 'PASS', lambda bf, af: (bf == af, 'text unchanged'))
    add('S14', '셀 크기 고정 표 열 너비(막아야 함)', B, 3, 'limit', None, 'BLOCKED', None)
    add('S15', '셀 크기 고정 표 합계 행 강조·정렬', B, 3, 'format', None, 'PASS', lambda bf, af: (bf == af, 'text unchanged'))
    add('S16', '서식 섞인 표 행 복제', MR, 1, 'structure', None, 'PASS', lambda bf, af: (rows(af) == rows(bf) + 1, 'one more row'))
    add('S17', '병합 표 행 삭제', CS, 6, 'limit', None, 'BLOCKED', None)
    add('S18', '중첩 표 행 삭제', C, 10, 'limit', None, 'BLOCKED', None)
    add('S19', '병합 많은 표에 셀 병합', C, 6, 'limit', None, 'BLOCKED', None)
    add('S20', '긴 표: 행 8개 추가로 쪽 넘김', CS, 7, 'structure', None, 'PASS', lambda bf, af: (rows(af) == rows(bf) + 8, 'eight more rows'))
    return s


def run_named(bench, sid, src, out, grids):
    """Scenario bodies that need the fixture's actual text or a helper request."""
    g = grids
    if sid == 'S03':
        cell = next(v for k, v in sorted(g[7].items()) if len(v) > 12)
        word = cell.split()[1] if len(cell.split()) > 2 else cell[:6]
        return text_edit(bench, src, out, [(word, word + '(수정)')])
    if sid == 'S04':
        return text_edit(bench, src, out, [('◦지역인재전형 확대', '◦지역인재전형 확대(수정)')], table=10)
    if sid == 'S05':
        cell = g[7][(3, 4)] if (3, 4) in g[7] else next(v for v in g[7].values() if len(v) > 8)
        return text_edit(bench, src, out, [(cell, cell + LONG)])
    if sid == 'S06':
        header = [g[3][(1, c)] for c in range(1, 7)]
        request = {'schema': 'hangul.task.v1', 'operation': 'table', 'headers': header, 'reason': '완료된 조합 삭제와 신규 조합 추가 시험',
                   'operations': [{'op': 'delete', 'key': {'순': '3'}},
                                  {'op': 'insert_after', 'key': {'순': '5'}, 'cells': ['5-1', '중', '새학교중', '새학교중 사회적협동조합', '2026.03.02.', '공립'], 'heightHwpunit': 1800}]}
        req = bench.out / f'{out.stem}-request.json'
        req.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        return bench.cli('table', src, out, '--request', req)
    if sid == 'S06b':
        cols = max(c for _, c in g[4])
        header = [g[4][(1, c)] for c in range(1, cols + 1)]
        n = rows(g[4])
        key_col = next(c for c in range(1, cols + 1) if len({g[4].get((r, c)) for r in range(2, n + 1)}) == n - 1 and all(g[4].get((r, c)) for r in range(2, n + 1)))
        request = {'schema': 'hangul.task.v1', 'operation': 'table', 'headers': header, 'reason': '완료 단계 삭제와 새 단계 추가 시험',
                   'operations': [{'op': 'delete', 'key': {header[key_col - 1]: g[4][(3, key_col)]}},
                                  {'op': 'insert_after', 'key': {header[key_col - 1]: g[4][(5, key_col)]}, 'cells': ['신규 단계'] + [f'새 내용 {c}' for c in range(2, cols + 1)], 'heightHwpunit': 1800}]}
        req = bench.out / f'{out.stem}-request.json'
        req.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        return bench.cli('table', src, out, '--request', req)
    if sid in ('S07', 'S08', 'S09'):
        last = rows(g[4]) - 1
        def build(info):
            base = {'schema': 'hwpx.safe-table-layout.v1', 'table': 4}
            if sid == 'S07':
                return dict(base, operation='insert_after', row=last, values=[f'추가 {i}' for i in range(len(info['rows'][0]))])
            if sid == 'S08':
                return dict(base, operation='delete_row', row=2)
            widths = info['widths_mm']
            moved = [w + (2 if i == 0 else -2 if i == len(widths) - 1 else 0) for i, w in enumerate(widths)]
            return dict(base, operation='resize', widths_mm=moved)
        return bench.helper('safe_table_layout.py', src, out, build, 4)
    if sid == 'S10':
        return bench.helper('safe_cell_layout.py', src, out, {'schema': 'hwpx.safe-cell-layout.v1', 'table': 4, 'operation': 'merge', 'range': [3, 1, 3, 2]}, 4)
    if sid == 'S11':
        merged = bench.out / 'S10b.hwpx'
        if not merged.is_file():
            return {'status': 'SKIPPED', 'reason': 'S10b produced no output'}
        return bench.helper('safe_cell_layout.py', merged, out, {'schema': 'hwpx.safe-cell-layout.v1', 'table': 1, 'operation': 'unmerge', 'range': [2, 2, 2, 3]}, 1)
    if sid == 'S12':
        n = rows(g[7])
        return bench.helper('safe_cell_layout.py', src, out, {'schema': 'hwpx.safe-cell-layout.v1', 'table': 7, 'operation': 'align_many',
                                                               'alignments': [{'range': [2, 1, n, 1], 'alignment': 'CENTER'}, {'range': [2, 2, n, 4], 'alignment': 'LEFT'}]}, 7)
    if sid == 'S13':
        return bench.helper('safe_cell_spacing.py', src, out, {'schema': 'hwpx.safe-cell-spacing.v1', 'table': 7,
                                                               'edits': [{'row': 2, 'column': 1, 'vertical_align': 'CENTER'}, {'row': 3, 'column': 2, 'margins_mm': {'left': 2, 'right': 2}}]}, 7)
    if sid == 'S14':
        def build(info):
            widths = [round(w, 1) for w in info['widths_mm']]
            widths[3] += 4
            widths[5] -= 4
            return {'schema': 'hwpx.table-columns.v1', 'table': 3, 'widths_mm': widths}
        info_out = bench.out / f'{out.stem}-cols-inspect.json'
        bench.cli('tool', 'safe_table_layout.py', 'inspect', src, '--table', 3, '--output', info_out)
        info = json.loads(info_out.read_text(encoding='utf-8'))
        return bench.helper('safe_table_columns.py', src, out, build(info), 3, inspect=False)
    if sid == 'S15':
        last = rows(g[3])
        return bench.helper('safe_summary_style.py', src, out, {'schema': 'hwpx.summary-cell-format.v1', 'table': 3,
                                                                'edits': [{'row': last, 'column': 1, 'expected_texts': [g[3][(last, 1)]], 'bold': True, 'alignment': 'CENTER'},
                                                                          {'row': last, 'column': 5, 'expected_texts': [g[3][(last, 5)]], 'alignment': 'RIGHT'}]}, 3)
    if sid == 'S16':
        def build(info):
            # rows[r][cell][paragraph][run]; data row 1 is rows[1] (the header row is protected).
            cells = [[[f'추가-{c}' if j == 0 else '' for j, _ in enumerate(p)] for p in cell] for c, cell in enumerate(info['rows'][1], 1)]
            return {'schema': 'hwpx.rich-table.v1', 'table': 1, 'table_sha256': info.get('table_sha256'), 'row': 2,
                    'operation': 'clone_after', 'cells': cells, 'editable_reason': '같은 서식의 행을 하나 더 추가하는 시험'}
        return bench.helper('safe_rich_table.py', src, out, build, 1)
    if sid == 'S10b':
        return bench.helper('safe_rich_table.py', src, out, lambda info: {
            'schema': 'hwpx.rich-table.v1', 'table': 1, 'table_sha256': info.get('table_sha256'), 'row': 2,
            'operation': 'merge_horizontal', 'columns': [2, 3], 'editable_reason': '두 칸 내용을 모두 남기며 병합하는 시험'}, 1)
    if sid == 'S17':
        return bench.helper('safe_table_layout.py', src, out, {'schema': 'hwpx.safe-table-layout.v1', 'table': 6, 'operation': 'delete_row', 'row': 2}, 6)
    if sid == 'S18':
        return bench.helper('safe_table_layout.py', src, out, {'schema': 'hwpx.safe-table-layout.v1', 'table': 10, 'operation': 'delete_row', 'row': 2}, 10)
    if sid == 'S19':
        return bench.helper('safe_cell_layout.py', src, out, {'schema': 'hwpx.safe-cell-layout.v1', 'table': 6, 'operation': 'merge', 'range': [2, 2, 2, 3]}, 6)
    if sid == 'S20':
        current, result = src, {}
        for i in range(8):
            step = bench.out / f'S20-step{i}.hwpx'
            n = rows(tables(current)[0][7]) - 1
            result = bench.helper('safe_table_layout.py', current, step, lambda info, n=n, i=i: {
                'schema': 'hwpx.safe-table-layout.v1', 'table': 7, 'operation': 'insert_after', 'row': n,
                'values': [f'추가 영역 {i + 1}'] + [f'추가 항목 {i + 1}-{c}' for c in range(2, len(info['rows'][0]) + 1)]}, 7)
            if not step.is_file():
                return result
            current = step
        shutil.copyfile(current, out)
        return dict(result, steps=8)
    raise KeyError(sid)


def main(skills, fixtures, out):
    bench = Bench(skills, fixtures, out)
    report = []
    # Measure each untouched fixture once, so page findings are attributed only when an edit adds them.
    original = {}
    for fixture in sorted({x[2] for x in scenarios(bench.fx)}):
        copy = bench.out / f'original-{Path(fixture).stem}.hwpx'
        shutil.copyfile(bench.fx / fixture, copy)
        pdf = bench.export(copy)
        original[fixture] = page_metrics.measure(pdf)['counts'] if pdf else {}
    for sid, title, fixture, table, kind, body, expected, predicate in scenarios(bench.fx):
        src = bench.fx / fixture
        before = tables(src)
        output = bench.out / f'{sid}.hwpx'
        try:
            result = body(bench, src, output) if body else run_named(bench, sid, src, output, before[0])
        except Exception as exc:  # a bench bug must not hide other scenarios
            result = {'status': 'ERROR', 'reason': f'{type(exc).__name__}: {exc}'}
        produced = output.is_file()
        outcome = 'PASS' if produced else ('BLOCKED' if result.get('status') in ('BLOCKED', 'STALE') or 'reason' in result else 'ERROR')
        record = {'id': sid, 'title': title, 'fixture': fixture, 'table': table, 'kind': kind, 'expected': expected, 'outcome': outcome,
                  'status': result.get('status'), 'reason': str(result.get('reason') or result.get('error') or '')[:200]}
        if produced and predicate:
            record['problems'] = only_target_changed(before, tables(output), table, predicate)
        if not produced and expected == 'BLOCKED':
            record['problems'] = [] if sha(src) == sha(bench.fx / fixture) else ['source changed']
        if produced:
            pdf = bench.export(output)
            if pdf:
                metrics = page_metrics.measure(pdf)
                added = {code: n - original[fixture].get(code, 0) for code, n in metrics['counts'].items() if n > original[fixture].get(code, 0)}
                record.update(pages=metrics['pages'], counts=added,
                              findings=[f for f in metrics['findings'] if f['code'] in added][:6])
        record['verdict'] = 'OK' if outcome == expected and not record.get('problems') else 'ISSUE'
        report.append(record)
        print(json.dumps({k: record.get(k) for k in ('id', 'title', 'expected', 'outcome', 'verdict', 'reason', 'problems', 'counts')}, ensure_ascii=False), flush=True)
    (bench.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main(*sys.argv[1:4])
