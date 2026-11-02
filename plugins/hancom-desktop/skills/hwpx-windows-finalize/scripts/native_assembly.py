"""Assemble one-source template parts in outline order (hwpx.assembly-outline.v1).

Pure Python: template manifest loading, outline validation, numbering, chapter box widths and the
resolved native plan (hwpx.native-assemble.v1) that Hancom.Assembly.ps1 executes step by step.
Every check here runs before Hangul starts.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

TEMPLATE_SCHEMA = 'hwpx.assembly-template.v1'
OUTLINE_SCHEMA = 'hwpx.assembly-outline.v1'
PLAN_SCHEMA = 'hwpx.native-assemble.v1'
ROMAN = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ'
HANGUL = '가나다라마바사아자차카타파하'
ITEM_KINDS = ('item', 'dash', 'dot', 'note')
PART_KINDS = ('cover', 'chapter_first', 'chapter', 'heading', 'table', 'spacer', *ITEM_KINDS)
STEP_OPS = ('text', 'section', 'insert', 'pageNumbers', 'boxWidth', 'table')
MAX_NODES, MAX_ROWS, MAX_TEXT = 400, 100, 2000
HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_template(catalog, template_id):
    need(isinstance(template_id, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]*', template_id or ''), '조립 양식 ID는 영문 소문자·숫자·하이픈입니다.')
    folder = Path(catalog) / template_id
    need((folder / 'manifest.json').is_file(), f'조립 양식이 없습니다: {template_id}')
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    need(manifest.get('schema') == TEMPLATE_SCHEMA and manifest.get('id') == template_id, '조립 양식 manifest schema/id 불일치')
    parts = manifest.get('parts')
    need(isinstance(parts, dict) and parts, '조립 양식에 parts가 없습니다.')
    for name, part in parts.items():
        need(part.get('kind') in PART_KINDS, f'알 수 없는 부품 종류: {name}')
        path = (folder / part['file']).resolve()
        need(path.parent.parent == folder.resolve() and path.is_file(), f'부품 파일이 없습니다: {name}')
        need(sha(path) == part['sha256'], f'부품 파일이 manifest와 다릅니다: {name}')
        part['path'] = str(path)
    for kind in ('cover', 'chapter_first', 'chapter', 'spacer'):
        need(sum(p['kind'] == kind for p in parts.values()) == 1, f'조립 양식에 {kind} 부품이 하나 있어야 합니다.')
    return manifest


def number(level, index):
    """Label of the index-th (1-based) sibling: level 0 Roman chapters, then 1. / 가. / 1)."""
    if level == 0:
        need(index <= len(ROMAN), f'장은 {len(ROMAN)}개까지입니다.')
        return f'{ROMAN[index - 1]}.'
    if level == 2:
        need(index <= len(HANGUL), f'2단계 제목은 한 묶음에 {len(HANGUL)}개까지입니다.')
        return f'{HANGUL[index - 1]}.'
    return f'{index}.' if level == 1 else f'{index})'


def box_width(box, title):
    """Chapter box width (HWPUNIT) that keeps the source box's padding around a new title.

    The framed rectangle is frameRatio of the group width, so the group grows by the text growth
    divided by that ratio."""
    advance = box['advancePt']
    def width(text):
        return sum(advance.get(c, advance['가'] if '가' <= c <= '힣' else box['fallbackAdvancePt']) for c in text)
    return round(box['sourceWidthHwp'] + 100 * (width(title) - width(box['sourceTitle'])) / box['frameRatio'])


def _text(value, where, placeholders, allow_empty=False):
    need(isinstance(value, str), f'{where}: 문자열이어야 합니다.')
    need(allow_empty or value.strip(), f'{where}: 빈 문구는 넣을 수 없습니다.')
    need(len(value) <= MAX_TEXT and not re.search(r'[\r\n\t]', value), f'{where}: 줄바꿈·탭 없이 {MAX_TEXT}자 이하여야 합니다.')
    need(not any(p in value for p in placeholders), f'{where}: 양식 자리표시 문구를 내용에 쓸 수 없습니다.')
    return value


def build_plan(manifest, outline):
    """Validate the outline against the template and resolve it into native steps."""
    parts = manifest['parts']
    by_kind = {}
    for name, part in parts.items():
        by_kind.setdefault((part['kind'], part.get('level'), part.get('depth', 0)), name)
    placeholders = set()
    for part in parts.values():
        value = part.get('placeholder')
        placeholders.update(value.values() if isinstance(value, dict) else [value] if value else [])
    need(isinstance(outline, dict) and outline.get('schema', OUTLINE_SCHEMA) == OUTLINE_SCHEMA, f'outline schema는 {OUTLINE_SCHEMA}입니다.')
    need(set(outline) <= {'schema', 'template', 'cover', 'nodes'}, '지원 키: schema, template, cover, nodes')
    need(outline.get('template', manifest['id']) == manifest['id'], 'outline의 template이 선택한 양식과 다릅니다.')
    cover, cover_part = outline.get('cover'), next(n for n, p in parts.items() if p['kind'] == 'cover')
    fields = parts[cover_part]['placeholder']
    need(isinstance(cover, dict) and set(cover) <= set(fields) and {'title', 'date'} <= set(cover), f'cover 지원 키: {", ".join(fields)} (title·date 필수)')
    steps = [dict(op='text', find=fields[key], text=_text(cover.get(key, ''), f'cover.{key}', placeholders, key not in ('title', 'date'))) for key in fields]
    nodes = outline.get('nodes')
    need(isinstance(nodes, list) and 1 <= len(nodes) <= MAX_NODES, f'nodes는 1~{MAX_NODES}개입니다.')
    need(isinstance(nodes[0], dict) and nodes[0].get('t') == 'chapter', '본문은 장(chapter)으로 시작해야 합니다.')
    counters, level = [0, 0, 0, 0], 0
    for position, node in enumerate(nodes, 1):
        where = f'nodes[{position}]'
        need(isinstance(node, dict) and 't' in node, f'{where}: t가 필요합니다.')
        kind = node['t']
        if kind == 'chapter':
            need(set(node) == {'t', 'text'}, f'{where}: chapter는 t, text만 받습니다.')
            counters, level = [counters[0] + 1, 0, 0, 0], 0
            name = by_kind[('chapter_first' if counters[0] == 1 else 'chapter', None, 0)]
            label = f'{number(0, counters[0])} {_text(node["text"], where, placeholders)}'
            box = parts[name]['box']
            width = box_width(box, label)
            need(width <= box['maxWidthHwp'], f'{where}: 장 제목이 길어 상자가 본문 폭을 넘습니다 '
                 f'(필요 {width / 283.465:.1f}mm, 최대 {box["maxWidthHwp"] / 283.465:.1f}mm). 제목을 줄이세요.')
            if counters[0] == 1:
                steps += [dict(op='section'), dict(op='insert', part=name, keepSection=1), dict(op='pageNumbers', **manifest['rules']['pageNumbers'])]
            else:
                spacer = by_kind[('spacer', None, 0)]
                steps.append(dict(op='insert', part=spacer, keepSection=0))
            steps += [*([] if counters[0] == 1 else [dict(op='insert', part=name, keepSection=0)]),
                      dict(op='text', find=parts[name]['placeholder'], text=label), dict(op='boxWidth', width=width)]
        elif kind == 'heading':
            need(set(node) == {'t', 'level', 'text'} and node['level'] in (1, 2, 3), f'{where}: heading은 level 1~3과 text가 필요합니다.')
            depth = node['level']
            need(depth == 1 or counters[depth - 1] > 0, f'{where}: {depth}단계 제목 앞에 {depth - 1}단계 제목이 필요합니다.')
            counters[depth] += 1
            counters[depth + 1:] = [0] * (3 - depth)
            level = depth
            name = by_kind.get(('heading', depth, 0))
            need(name, f'양식에 {depth}단계 제목 부품이 없습니다.')
            label = f'{number(depth, counters[depth])} {_text(node["text"], where, placeholders)}'
            steps += [dict(op='insert', part=name, keepSection=0), dict(op='text', find=parts[name]['placeholder'], text=label)]
        elif kind in ITEM_KINDS:
            need(set(node) == {'t', 'text'}, f'{where}: {kind}는 t, text만 받습니다.')
            deep = int(level >= manifest['rules']['deepItemsUnderHeadingLevel'])
            name = by_kind.get((kind, None, deep)) or by_kind.get((kind, None, 0))
            need(name, f'양식에 {kind} 부품이 없습니다.')
            steps += [dict(op='insert', part=name, keepSection=0),
                      dict(op='text', find=parts[name]['placeholder'], text=_text(node['text'], where, placeholders))]
        elif kind == 'table':
            need({'t', 'part', 'rows'} <= set(node) <= {'t', 'part', 'rows', 'header'}, f'{where}: table은 t, part, rows와 선택 header만 받습니다.')
            part = parts.get(node['part'])
            need(part is not None and part['kind'] == 'table', f'{where}: 표 부품 {node["part"]!r}이 양식에 없습니다.')
            spec, rows, header = part['table'], node['rows'], node.get('header')
            if header is not None:
                need(isinstance(header, list) and len(header) == spec['cols'], f'{where}: header 칸 수가 {spec["cols"]}이 아닙니다.')
                for c, cell in enumerate(header, 1):
                    _text(cell, f'{where}.header[{c}]', placeholders)
            need(isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS, f'{where}: rows는 1~{MAX_ROWS}행입니다.')
            for r, row in enumerate(rows, 1):
                need(isinstance(row, list) and len(row) == spec['cols'], f'{where}: {r}행의 칸 수가 {spec["cols"]}이 아닙니다.')
                for c, cell in enumerate(row, 1):
                    _text(cell, f'{where}.rows[{r}][{c}]', placeholders, allow_empty=True)
            name = node['part']
            steps += [dict(op='insert', part=name, keepSection=0),
                      dict(op='table', have=spec['dataRows'], cols=spec['cols'], prefix=spec.get('firstColumnPrefix', ''), header=header, rows=rows)]
        else:
            raise ValueError(f'{where}: 알 수 없는 t {kind!r} (chapter, heading, item, dash, dot, note, table)')
    used = {step['part'] for step in steps if step['op'] == 'insert'}
    return dict(schema=PLAN_SCHEMA, base=dict(path=parts[cover_part]['path'], sha256=parts[cover_part]['sha256']),
                parts={name: dict(path=parts[name]['path'], sha256=parts[name]['sha256']) for name in sorted(used)},
                steps=steps)


def validate_plan(plan, source=None):
    """Boundary check of a resolved plan before the native runner trusts it."""
    need(isinstance(plan, dict) and set(plan) == {'schema', 'base', 'parts', 'steps'} and plan['schema'] == PLAN_SCHEMA, 'assembly plan requires schema, base, parts and steps')
    refs = [plan['base'], *plan['parts'].values()]
    for ref in refs:
        need(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and Path(ref['path']).is_absolute(), 'explicit absolute part path and hash required')
        need(Path(ref['path']).suffix.lower() == '.hwpx' and sha(Path(ref['path']).resolve(strict=True)) == ref['sha256'].lower(), 'assembly input changed: ' + ref['path'])
    if source is not None:
        need(Path(source).resolve() == Path(plan['base']['path']).resolve(), 'assembly base must match source')
    need(isinstance(plan['steps'], list) and 1 <= len(plan['steps']) <= 4 * MAX_NODES, 'assembly steps out of range')
    for step in plan['steps']:
        need(isinstance(step, dict) and step.get('op') in STEP_OPS, 'unknown assembly step')
        need(step['op'] != 'insert' or step.get('part') in plan['parts'], 'assembly step names an unknown part')
    return dict(plan, base=dict(path=str(Path(plan['base']['path']).resolve()), sha256=plan['base']['sha256'].lower()))


def check_output(path, plan):
    """Read the saved HWPX: no placeholder may remain and every requested text must be present."""
    with zipfile.ZipFile(path) as package:
        sections = [name for name in package.namelist() if re.fullmatch(r'Contents/section\d+\.xml', name)]
        from xml.etree import ElementTree
        roots = [ElementTree.fromstring(package.read(name)) for name in sorted(sections)]
    text = ''.join(t.text or '' for root in roots for t in root.iter(HP + 't'))
    finds = {step['find'] for step in plan['steps'] if step['op'] == 'text'}
    wanted = [step['text'] for step in plan['steps'] if step['op'] == 'text' and step['text']]
    wanted += [cell for step in plan['steps'] if step['op'] == 'table' for row in [step.get('header') or [], *step['rows']] for cell in row if cell]
    tables = [int(t.get('rowCnt')) for root in roots for t in root.iter(HP + 'tbl')]
    expected = [len(step['rows']) + 1 for step in plan['steps'] if step['op'] == 'table']
    result = dict(placeholdersLeft=sorted(p for p in finds if p in text), missingTexts=[t for t in wanted if t not in text],
                  tableRows=dict(expected=expected, actual=tables[len(tables) - len(expected):] if expected else []))
    result['ok'] = not result['placeholdersLeft'] and not result['missingTexts'] and result['tableRows']['expected'] == result['tableRows']['actual']
    return result
