"""Assemble one-source template parts in outline order (hwpx.assembly-outline.v1).

Python side: template manifest loading, outline validation, numbering, chapter box widths, table
instances and the resolved native plan (hwpx.native-assemble.v1) that Hancom.Assembly.ps1 executes
step by step. Every check here runs before Hangul starts.

A table part is header rows plus one unit of rows that repeats (a unit may span rows, with cells
merged inside it). Each outline table becomes its own copy of the part with the unit repeated and
every cell's text written into the file; Hangul lays the rows out when it inserts that copy.
"""
import copy
import hashlib
import json
import re
import zipfile
from pathlib import Path

from lxml import etree

TEMPLATE_SCHEMA = 'hwpx.assembly-template.v1'
OUTLINE_SCHEMA = 'hwpx.assembly-outline.v1'
PLAN_SCHEMA = 'hwpx.native-assemble.v1'
ROMAN = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ'
HANGUL = '가나다라마바사아자차카타파하'
ITEM_KINDS = ('item', 'dash', 'dot', 'note', 'arrow', 'lead')
# One placeholder, no numbering: the outline node {"t": kind, "text": ...} fills it.
TEXT_KINDS = (*ITEM_KINDS, 'box', 'subhead')
PART_KINDS = ('cover', 'chapter_first', 'chapter', 'heading', 'task', 'point', 'table', 'spacer', 'summary', 'summary_chapter', *TEXT_KINDS)
# The symbol each text part already draws; the same symbol typed at the start of the text is dropped.
KIND_SYMBOLS = {'item': '◦○∘•', 'dash': '-–', 'dot': '‧·ㆍ', 'note': '※', 'arrow': '⇒→', 'subhead': '□', 'box': '◈', 'lead': '❍'}
BOXED_DIGITS = 20  # Hancom private-use squared digits U+F02B1.., and circled ①..⑳
# The common outline vocabulary. A template draws the roles it has parts for; a role it lacks is drawn by
# the first available role down this chain (a template may override it in rules.fallbacks), and the
# result lists every such substitution.
ROLE_LABELS = {'chapter': '장', 'heading1': '1. 제목', 'heading2': '가. 제목', 'heading3': '1) 제목', 'task': '네모 번호 과제',
               'subhead': '□ 소제목', 'lead': '❍ 머리 문단', 'item': '○ 항목', 'dash': '- 항목', 'dot': '‧ 항목', 'note': '※ 참고',
               'arrow': '⇒ 결과', 'point': '① 원 번호 줄', 'box': '◈ 강조 상자'}
FALLBACKS = {'heading1': ['task', 'subhead'], 'heading2': ['heading1'], 'heading3': ['heading2'], 'task': ['heading1', 'subhead'],
             'subhead': ['task', 'heading1'], 'lead': ['item'], 'dash': ['item'], 'dot': ['dash'], 'note': ['dash'], 'arrow': ['dash'],
             'point': ['item'], 'box': ['lead']}
TABLE_ROLES = {'schedule': '업무·일정 목록', 'grid': '구분·내용 표', 'steps': '가로 단계 흐름', 'targets': '대상별 현황', 'indicators': '과제별 성과지표'}
COVER_FIELDS = ('title', 'subtitle', 'date', 'organization', 'department')
# A cover value without a place on this template's cover is added to another field, never dropped.
COVER_CARRY = {'subtitle': ('title', ' - '), 'date': ('organization', ' · '), 'department': ('organization', ' · ')}
STEP_OPS = ('text', 'section', 'insert', 'pageNumbers', 'boxWidth', 'pageBreak')
MAX_NODES, MAX_ROWS, MAX_TEXT, MAX_CELL_PARAGRAPHS = 400, 100, 2000, 20
HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'


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
    required = ('cover', 'chapter_first', 'chapter', *(('spacer',) if manifest['rules'].get('spacerBeforeLaterChapters') else ()))
    for kind in required:
        need(sum(p['kind'] == kind for p in parts.values()) == 1, f'조립 양식에 {kind} 부품이 하나 있어야 합니다.')
    return manifest


def places(value):
    """A cover field names one placeholder or a list of them (the same value in several places)."""
    return value if isinstance(value, list) else [value]


def number(style, index, what):
    """Label of the index-th (1-based) sibling in a part's numbering style."""
    if style in ('roman', 'roman-bare'):
        need(index <= len(ROMAN), f'{what}은 {len(ROMAN)}개까지입니다.')
        return ROMAN[index - 1] + ('.' if style == 'roman' else '')
    if style == 'hangul':
        need(index <= len(HANGUL), f'{what}은 한 묶음에 {len(HANGUL)}개까지입니다.')
        return f'{HANGUL[index - 1]}.'
    if style in ('boxed', 'circled'):
        need(index <= BOXED_DIGITS, f'{what}은 한 묶음에 {BOXED_DIGITS}개까지입니다.')
        return chr((0xF02B1 if style == 'boxed' else 0x2460) + index - 1)
    return {'decimal': f'{index}.', 'digit': str(index), 'paren': f'{index})'}[style]


def numbered(part, label, text):
    """Text steps of a numbered title: number and title in their own runs, or one 'label text' string."""
    if part.get('numberPlaceholder'):
        return [dict(op='text', find=part['numberPlaceholder'], text=label), dict(op='text', find=part['placeholder'], text=text)]
    return [dict(op='text', find=part['placeholder'], text=f'{label} {text}')]


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


def _cell(value, where, placeholders):
    """A cell is one paragraph (string, may be empty) or several paragraphs (list of non-empty strings)."""
    if isinstance(value, list):
        need(1 <= len(value) <= MAX_CELL_PARAGRAPHS, f'{where}: 칸 안 문단은 1~{MAX_CELL_PARAGRAPHS}개입니다.')
        return [_text(v, f'{where}[{i}]', placeholders) for i, v in enumerate(value, 1)]
    return _text(value, where, placeholders, allow_empty=True)


def _cells(tr):
    return tr.findall(HP + 'tc')


def _unnumbered(header):
    """Map a paragraph shape id to a copy without automatic numbering (made once per id, added to header)."""
    shapes = header.find(HH + 'refList').find(HH + 'paraProperties')
    made = {}

    def plain(shape_id):
        if shape_id not in made:
            shape = next(s for s in shapes.findall(HH + 'paraPr') if s.get('id') == shape_id)
            heading = shape.find(HH + 'heading')
            if heading is None or heading.get('type') not in ('NUMBER', 'OUTLINE'):
                made[shape_id] = shape_id
            else:
                clone = copy.deepcopy(shape)
                clone.set('id', str(max(int(s.get('id')) for s in shapes.findall(HH + 'paraPr')) + 1))
                clone.find(HH + 'heading').attrib.update({'type': 'NONE', 'idRef': '0', 'level': '0'})
                shapes.append(clone)
                shapes.set('itemCnt', str(len(shapes.findall(HH + 'paraPr'))))
                made[shape_id] = clone.get('id')
                plain.made = True
        return made[shape_id]
    plain.made = False
    return plain


def _set_cell(cell, value, prefix='', plain=None):
    """Replace a cell's paragraphs with one copy of its first paragraph per text, in that paragraph's first run format.

    A numbered first paragraph (a step's "1.") numbers only the first text: later texts continue it unnumbered
    through plain (see _unnumbered). Bullets repeat on every text."""
    sub = cell.find(HP + 'subList')
    paragraphs = sub.findall(HP + 'p')
    for paragraph in paragraphs:
        sub.remove(paragraph)
    for index, text in enumerate(value if isinstance(value, list) else [value]):
        paragraph = copy.deepcopy(paragraphs[0])
        if index and plain:
            paragraph.set('paraPrIDRef', plain(paragraph.get('paraPrIDRef')))
        for child in list(paragraph):
            if child.tag != HP + 'run':
                paragraph.remove(child)  # saved line layout no longer fits
        runs = paragraph.findall(HP + 'run')
        for extra in runs[1:]:
            paragraph.remove(extra)
        for child in list(runs[0]):
            runs[0].remove(child)
        if text:
            etree.SubElement(runs[0], HP + 't').text = prefix + text
        sub.append(paragraph)


def table_instance(part, header, units, target):
    """Write a copy of a table part with the outline's header cells and units; returns the row count."""
    spec = part['table']
    with zipfile.ZipFile(part['path']) as package:
        infos = package.infolist()
        data = {info.filename: package.read(info) for info in infos}
    section = etree.fromstring(data['Contents/section0.xml'])
    shapes = etree.fromstring(data['Contents/header.xml']) if 'Contents/header.xml' in data else None
    plain = _unnumbered(shapes) if shapes is not None else None
    table = next(section.iter(HP + 'tbl'))
    rows = table.findall(HP + 'tr')
    heads, unit = rows[:spec['headerRows']], rows[spec['headerRows']:]
    if header is not None:
        for cell, value in zip([c for tr in heads for c in _cells(tr)], header):
            _set_cell(cell, value, plain=plain)
    for tr in unit:
        table.remove(tr)
    prefix, fixed = spec.get('firstColumnPrefix', ''), spec.get('fixedCells', [])
    for index, values in enumerate(units):
        clones = [copy.deepcopy(tr) for tr in unit]
        cells = [c for tr in clones for c in _cells(tr)]
        for cell in cells:
            address = cell.find(HP + 'cellAddr')
            address.set('rowAddr', str(int(address.get('rowAddr')) + index * len(unit)))
        for cell, value in zip([c for i, c in enumerate(cells) if i not in fixed], values):  # fixed cells keep their text
            _set_cell(cell, value, prefix if cell.find(HP + 'cellAddr').get('colAddr') == '0' and value else '', plain)
        for tr in clones:
            table.append(tr)
    count = len(heads) + len(unit) * len(units)
    size = table.find(HP + 'sz')
    size.set('height', str(int(size.get('height')) * count // len(rows)))  # Hangul sets the real height on layout
    table.set('rowCnt', str(count))
    for holder in section.iter(HP + 'p'):
        if holder.find(f'.//{HP}tbl') is table:
            for lines in holder.findall(HP + 'linesegarray'):
                holder.remove(lines)
    data['Contents/section0.xml'] = etree.tostring(section, xml_declaration=True, encoding='UTF-8', standalone=True)
    if plain and plain.made:  # rewrite the header only when it gained a shape
        data['Contents/header.xml'] = etree.tostring(shapes, xml_declaration=True, encoding='UTF-8', standalone=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'x') as out:
        for info in infos:
            out.writestr(info, data[info.filename])
    return count


def text_width(text, em):
    """Rough advance (HWPUNIT) of a title: Hangul and other wide characters one em, the rest half."""
    return sum(em if ord(c) >= 0x1100 else em // 2 for c in text)


def _loosen(data, section):
    """Clear keep-with-next on the shapes of a part's own paragraphs; rewrites header.xml in data and
    returns True when a shape changed."""
    header = etree.fromstring(data['Contents/header.xml'])
    ids = {p.get('paraPrIDRef') for p in section.findall(HP + 'p')}
    settings = [s for shape in header.iter(HH + 'paraPr') if shape.get('id') in ids
                for s in shape.iter(HH + 'breakSetting') if s.get('keepWithNext') == '1']
    for setting in settings:
        setting.set('keepWithNext', '0')
    if settings:
        data['Contents/header.xml'] = etree.tostring(header, xml_declaration=True, encoding='UTF-8', standalone=True)
    return bool(settings)


def loose_instance(part, target):
    """Write a copy of a title part that does not keep with the next paragraph; False (nothing written)
    when the part does not keep with it anyway."""
    with zipfile.ZipFile(part['path']) as package:
        infos = package.infolist()
        data = {info.filename: package.read(info) for info in infos}
    if not _loosen(data, etree.fromstring(data['Contents/section0.xml'])):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'x') as out:
        for info in infos:
            out.writestr(info, data[info.filename])
    return True


def fitted_instance(part, values, target, loose=False):
    """Write a copy of a part whose title sits in a fixed-width table cell (a numbered tab): the
    placeholders become the texts and that cell grows by the title's extra width, within the body.
    A loose copy does not keep with the next paragraph."""
    fit = part['fit']
    with zipfile.ZipFile(part['path']) as package:
        infos = package.infolist()
        data = {info.filename: package.read(info) for info in infos}
    section = etree.fromstring(data['Contents/section0.xml'])
    if loose:
        _loosen(data, section)
    for t in section.iter(HP + 't'):
        for placeholder, value in values.items():
            if t.text:
                t.text = t.text.replace(placeholder, value)
            for child in t:
                if child.tail:
                    child.tail = child.tail.replace(placeholder, value)
    table = next(section.iter(HP + 'tbl'))
    cell = list(table.iter(HP + 'tc'))[fit['cell']].find(HP + 'cellSz')
    size = table.find(HP + 'sz')
    grow = text_width(values[fit['placeholder']], fit['emHwp']) - text_width(fit['sourceText'], fit['emHwp'])
    grow = max(0, min(grow, fit['maxWidthHwp'] - int(size.get('width'))))
    cell.set('width', str(int(cell.get('width')) + grow))
    size.set('width', str(int(size.get('width')) + grow))
    for paragraph in section.iter(HP + 'p'):
        for lines in paragraph.findall(HP + 'linesegarray'):
            paragraph.remove(lines)
    data['Contents/section0.xml'] = etree.tostring(section, xml_declaration=True, encoding='UTF-8', standalone=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'x') as out:
        for info in infos:
            out.writestr(info, data[info.filename])


def _role_key(kind, level=None):
    return f'heading{level}' if kind == 'heading' else kind


def _has_role(parts, role):
    kinds = {_role_key(p['kind'], p.get('level')) for p in parts.values()}
    return role in kinds or role == 'chapter' and 'chapter_first' in kinds


def resolve_role(parts, rules, role, seen=()):
    """The role that draws role on this template: itself, else the first available one down its fallback chain."""
    if _has_role(parts, role):
        return role
    for candidate in {**FALLBACKS, **rules.get('fallbacks', {})}.get(role, []):
        if candidate not in seen:
            found = resolve_role(parts, rules, candidate, (*seen, role))
            if found:
                return found
    return None


def table_parts(parts):
    return {name: part for name, part in parts.items() if part['kind'] == 'table'}


def resolve_table(parts, node, where):
    """The table part for an outline table: by part name, or by role and cell count with a same-size fallback."""
    tables = table_parts(parts)
    listing = ', '.join(f'{p["table"].get("role", "grid")}({n}, 칸 {p["table"]["unitCells"]})' for n, p in tables.items())
    if 'part' in node:
        need(node['part'] in tables, f'{where}: 표 부품 {node["part"]!r}이 양식에 없습니다. 이 양식의 표: {listing}')
        return node['part'], None
    rows = node.get('rows')
    width = len(rows[0]) if isinstance(rows, list) and rows and isinstance(rows[0], list) else None
    same_role = [n for n, p in tables.items() if p['table'].get('role', 'grid') == node['role']]
    pick = [n for n in same_role if tables[n]['table']['unitCells'] == width] or (same_role if len(same_role) == 1 else [])
    if pick:
        return pick[0], None
    sized = sorted((n for n, p in tables.items() if p['table']['unitCells'] == width and p['table']['repeat']),
                   key=lambda n: tables[n]['table'].get('role', 'grid') != 'grid')
    need(sized, f'{where}: 이 양식에 {node["role"]!r} 표나 칸 {width}개 반복 표가 없습니다. 이 양식의 표: {listing}')
    return sized[0], tables[sized[0]]['table'].get('role', 'grid')


def describe(manifest):
    """What an outline can use on this template: roles drawn as themselves or by a substitute, tables and cover fields."""
    parts, rules = manifest['parts'], manifest['rules']
    roles = {role: resolve_role(parts, rules, role) for role in ROLE_LABELS}
    fields = next(p for p in parts.values() if p['kind'] == 'cover')['placeholder']
    return dict(
        id=manifest['id'], label=manifest['label'],
        roles={role: ROLE_LABELS[role] for role, used in roles.items() if used == role},
        substitutes={role: used for role, used in roles.items() if used and used != role},
        unavailable=[role for role, used in roles.items() if not used],
        tables=[dict(part=name, role=p['table'].get('role', 'grid'), roleLabel=TABLE_ROLES.get(p['table'].get('role', 'grid')),
                     cells=p['table']['unitCells'], columns=p['table'].get('columns') or p['table']['header'], header=p['table']['header'],
                     repeat=p['table']['repeat']) for name, p in table_parts(parts).items()],
        cover=dict(fields=list(fields), required=[k for k in ('title', 'date') if k in fields],
                   carried={k: COVER_CARRY[k][0] for k in COVER_FIELDS if k not in fields and k in COVER_CARRY}),
        summary=any(p['kind'] == 'summary' for p in parts.values()),
        textBeforeFirstChapter=bool(rules.get('textBeforeFirstChapter')))


def build_plan(manifest, outline, tables_dir=None, notes=None):
    """Validate the outline against the template and resolve it into native steps.

    Table nodes are written as part copies into tables_dir (a new folder). Roles, table roles and cover
    fields the template lacks are drawn by substitutes; each substitution is appended to notes."""
    parts, rules = manifest['parts'], manifest['rules']
    notes = [] if notes is None else notes
    by_kind = {}
    for name, part in parts.items():
        by_kind.setdefault((part['kind'], part.get('level'), part.get('depth', 0), part.get('context')), name)
    placeholders = set()
    for part in parts.values():
        value = part.get('placeholder')
        placeholders.update([p for v in value.values() for p in places(v)] if isinstance(value, dict) else [value] if value else [])
        placeholders.update([part['numberPlaceholder']] if part.get('numberPlaceholder') else [])
    need(isinstance(outline, dict) and outline.get('schema', OUTLINE_SCHEMA) == OUTLINE_SCHEMA, f'outline schema는 {OUTLINE_SCHEMA}입니다.')
    need(set(outline) <= {'schema', 'template', 'cover', 'summary', 'nodes'}, '지원 키: schema, template, cover, summary, nodes')
    need(outline.get('template', manifest['id']) == manifest['id'], 'outline의 template이 선택한 양식과 다릅니다.')
    cover, cover_part = outline.get('cover'), next(n for n, p in parts.items() if p['kind'] == 'cover')
    fields = parts[cover_part]['placeholder']
    required = [key for key in ('title', 'date') if key in fields]
    need(isinstance(cover, dict) and set(cover) <= set(fields) | set(COVER_FIELDS) and set(required) <= set(cover),
         f'cover 지원 키: {", ".join(COVER_FIELDS)} (이 양식은 {"·".join(required)} 필수)')
    cover = dict(cover)
    for key in COVER_FIELDS:
        if key in cover and key not in fields:
            target, joint = COVER_CARRY[key]
            need(target in fields, f'cover.{key}: 이 양식 표지에 {key}·{target} 자리가 없습니다. 본문에 넣으세요.')
            value =_text(cover.pop(key), f'cover.{key}', placeholders, True)
            if value:
                cover[target] = joint.join(v for v in (cover.get(target, ''), value) if v)
                notes.append(dict(at=f'cover.{key}', role=key, used=target, note=f'이 양식 표지에 {key} 자리가 없어 {target}에 붙였습니다.'))
    steps = [dict(op='text', find=place, text=_text(cover.get(key, ''), f'cover.{key}', placeholders, key not in required))
             for key in fields for place in places(fields[key])]
    if rules.get('pageNumbers') and not rules.get('bodyStartsNewSection'):
        steps.append(dict(op='pageNumbers', **rules['pageNumbers']))  # one section: the cover part hides its own number
    instances = {}

    def inserted(name, loose=False):
        """Insert step of a part; a loose title is inserted from a copy that does not keep with the next paragraph."""
        copy_name, target = f'{name}@{len(instances) + 1}', Path(tables_dir or '.') / f'{name}-{len(instances) + 1}.hwpx'
        if not (loose and tables_dir is not None and loose_instance(parts[name], target)):  # no folder: a check-only plan
            return dict(op='insert', part=name, keepSection=0)
        instances[copy_name] = dict(path=str(target.resolve()), sha256=sha(target))
        return dict(op='insert', part=copy_name, keepSection=0)

    def titled(name, label, title, loose=False):
        """Insert steps of a numbered title; a title in a fixed-width cell gets its own fitted copy."""
        part = parts[name]
        if 'fit' not in part:
            return [inserted(name, loose), *numbered(part, label, title)]
        need(tables_dir is not None, 'fitted titles need a folder for part copies')
        copy_name, target = f'{name}@{len(instances) + 1}', Path(tables_dir) / f'{name}-{len(instances) + 1}.hwpx'
        fitted_instance(part, {part['numberPlaceholder']: label, part['placeholder']: title}, target, loose)
        instances[copy_name] = dict(path=str(target.resolve()), sha256=sha(target))
        return [dict(op='insert', part=copy_name, keepSection=0, expect=dict(texts=[label, title]))]

    def body(nodes, prefix, summary):
        """Steps of one node list; the summary list uses the summary chapter part and its own numbering."""
        need(isinstance(nodes, list) and 1 <= len(nodes) <= MAX_NODES, f'{prefix}는 1~{MAX_NODES}개입니다.')
        need(isinstance(nodes[0], dict) and (nodes[0].get('t') == 'chapter' or rules.get('textBeforeFirstChapter')),
             f'{prefix}는 장(chapter)으로 시작해야 합니다.')
        def find(kind, level=None, depth=0, after=None):
            """The part for a kind; on the summary page, or right after a node of kind after, a part made for it comes first."""
            return ((summary and by_kind.get((kind, level, depth, 'summary'))) or (after and by_kind.get((kind, level, depth, f'after-{after}')))
                    or by_kind.get((kind, level, depth, None)))

        def substitute(node, where):
            """The node redrawn with the role this template has for it (the same node when the role exists)."""
            kind = node['t']
            if kind not in ROLE_LABELS and kind != 'heading' or kind == 'heading' and node.get('level') not in (1, 2, 3):
                return node  # unknown kinds and malformed headings are rejected below
            role = _role_key(kind, node.get('level'))
            used = resolve_role(parts, rules, role)
            if used in (None, role):
                return node
            notes.append(dict(at=where, role=role, used=used, note=f'{ROLE_LABELS[role]} 부품이 없어 {ROLE_LABELS[used]}로 넣었습니다.'))
            moved = {k: v for k, v in node.items() if k not in ('t', 'level')}
            if role in KIND_SYMBOLS and isinstance(moved.get('text'), str):  # the symbol typed for the original role
                moved['text'] = re.sub(rf'^\s*[{re.escape(KIND_SYMBOLS[role])}]\s+', '', moved['text']) or moved['text']
            return dict(moved, t='heading', level=int(used[-1])) if used.startswith('heading') else dict(moved, t=used)

        drawn, breaks = [], []
        for position, node in enumerate(nodes, 1):
            where = f'{prefix}[{position}]'
            need(isinstance(node, dict) and isinstance(node.get('t'), str), f'{where}: t가 필요합니다.')
            node = dict(node)
            breaks.append(node.pop('pageBreakBefore', False))  # any node may start a new page
            need(breaks[-1] in (True, False), f'{where}: pageBreakBefore는 true/false입니다.')
            drawn.append(substitute(node, where))

        def rank(node):
            """Title rank (chapter highest), or None for body nodes."""
            kind = node['t']
            return 0 if kind == 'chapter' else node.get('level') if kind == 'heading' else 1.5 if kind in ('task', 'subhead') else None

        def bodyless(index):
            """A title with nothing under it (the next node is a title of its rank or higher, or none) is one line of a
            list such as □ lines or "1. 기간: ..." lines: kept with the next paragraph, a run of them moves as one block."""
            following = drawn[index + 1] if index + 1 < len(drawn) else None
            return following is None or rank(following) is not None and rank(following) <= rank(drawn[index])

        out, counters, tasks, points, level, previous = [], [0, 0, 0, 0], 0, 0, 0, None
        for position, node in enumerate(drawn, 1):
            where = f'{prefix}[{position}]'
            kind, after, previous = node['t'], previous, node['t']  # after: the kind drawn just before this node
            if breaks[position - 1] and kind != 'chapter':  # a chapter breaks after its spacer, below
                out.append(dict(op='pageBreak'))
            if kind == 'chapter':
                need(set(node) == {'t', 'text'}, f'{where}: chapter는 t, text만 받습니다.')
                counters, tasks, points, level = [counters[0] + 1, 0, 0, 0], 0, 0, 0
                first = counters[0] == 1
                name = find('summary_chapter') if summary else find('chapter_first' if first else 'chapter')
                part = parts[name]
                label = number(part['numbering'], counters[0], '장')
                title = _text(node['text'], where, placeholders)
                if first and not summary and rules.get('bodyStartsNewSection'):
                    out += [dict(op='section'), dict(op='insert', part=name, keepSection=1), dict(op='pageNumbers', **rules['pageNumbers']),
                            *numbered(part, label, title)]
                else:
                    if not first and not summary and rules.get('spacerBeforeLaterChapters'):
                        out.append(dict(op='insert', part=find('spacer'), keepSection=0))
                    if part.get('pageBreakBefore') or breaks[position - 1]:
                        out.append(dict(op='pageBreak'))
                    out += titled(name, label, title)
                if 'box' in part:
                    width = box_width(part['box'], f'{label} {title}')
                    need(width <= part['box']['maxWidthHwp'], f'{where}: 장 제목이 길어 상자가 본문 폭을 넘습니다 '
                         f'(필요 {width / 283.465:.1f}mm, 최대 {part["box"]["maxWidthHwp"] / 283.465:.1f}mm). 제목을 줄이세요.')
                    out.append(dict(op='boxWidth', width=width))
            elif kind == 'heading':
                need(set(node) == {'t', 'level', 'text'} and node['level'] in (1, 2, 3), f'{where}: heading은 level 1~3과 text가 필요합니다.')
                depth = node['level']
                need(depth == 1 or counters[depth - 1] > 0 or rules.get('headingLevelsMaySkip'),  # some sources put 가. right under a task
                     f'{where}: {depth}단계 제목 앞에 {depth - 1}단계 제목이 필요합니다.')
                counters[depth] += 1
                counters[depth + 1:] = [0] * (3 - depth)
                tasks, points, level = 0, 0, depth
                name = find('heading', depth)
                need(name, f'양식에 {depth}단계 제목 부품이 없습니다.')
                label, title = number(parts[name]['numbering'], counters[depth], f'{depth}단계 제목'), _text(node['text'], where, placeholders)
                out += titled(name, label, title, bodyless(position - 1))
            elif kind in ('task', 'point'):
                need(set(node) == {'t', 'text'}, f'{where}: {kind}는 t, text만 받습니다.')
                name = find(kind, after=after)
                need(name, f'양식에 {kind} 부품이 없습니다.')
                if kind == 'task':
                    tasks, points = tasks + 1, 0
                    counters[2:] = [0, 0]  # 가. and 1) titles under a task count from the task
                else:
                    points += 1
                out += [inserted(name, kind == 'task' and bodyless(position - 1)),
                        *numbered(parts[name], number(parts[name]['numbering'], tasks if kind == 'task' else points, '번호 항목'), _text(node['text'], where, placeholders))]
            elif kind in TEXT_KINDS:
                need(set(node) == {'t', 'text'}, f'{where}: {kind}는 t, text만 받습니다.')
                deep = int(level >= rules['deepItemsUnderHeadingLevel'])
                name = find(kind, None, deep, after) or find(kind, None, 0, after)
                need(name, f'양식에 {kind} 부품이 없습니다.')
                text = _text(node['text'], where, placeholders)
                text = re.sub(rf'^\s*[{re.escape(KIND_SYMBOLS[kind])}]\s+', '', text) or text
                out += [inserted(name, kind == 'subhead' and bodyless(position - 1)), dict(op='text', find=parts[name]['placeholder'], text=text)]
            elif kind == 'table':
                need({'t', 'rows'} <= set(node) <= {'t', 'role', 'part', 'rows', 'header'} and len({'role', 'part'} & set(node)) == 1,
                     f'{where}: table은 t, rows, role(또는 part) 하나와 선택 header만 받습니다.')
                table_name, used = resolve_table(parts, node, where)
                if used:
                    notes.append(dict(at=where, role=f'table:{node["role"]}', used=f'table:{used}',
                                      note=f'{node["role"]} 표가 없어 칸 수가 같은 {table_name} 표({used})로 넣었습니다.'))
                part = parts[table_name]
                spec, rows, header = part['table'], node['rows'], node.get('header')
                if header is not None:
                    need(isinstance(header, list) and len(header) == spec['headerCells'], f'{where}: header 칸 수가 {spec["headerCells"]}이 아닙니다.')
                    for c, cell in enumerate(header, 1):
                        _text(cell, f'{where}.header[{c}]', placeholders)
                most = MAX_ROWS if spec['repeat'] else 1
                need(isinstance(rows, list) and 1 <= len(rows) <= most, f'{where}: rows는 1~{most}묶음입니다.')
                for r, row in enumerate(rows, 1):
                    need(isinstance(row, list) and len(row) == spec['unitCells'], f'{where}: {r}행의 칸 수가 {spec["unitCells"]}이 아닙니다.')
                    rows[r - 1] = [_cell(cell, f'{where}.rows[{r}][{c}]', placeholders) for c, cell in enumerate(row, 1)]
                need(tables_dir is not None, 'table nodes need a folder for table copies')
                name = f'{table_name}@{len(instances) + 1}'
                target = Path(tables_dir) / f'{table_name}-{len(instances) + 1}.hwpx'
                count = table_instance(part, header, rows, target)
                instances[name] = dict(path=str(target.resolve()), sha256=sha(target))
                texts = [p for row in [header or [], *rows] for cell in row for p in (cell if isinstance(cell, list) else [cell]) if p]
                out.append(dict(op='insert', part=name, keepSection=0, expect=dict(tableRows=count, texts=texts)))
            else:
                raise ValueError(f'{where}: 알 수 없는 t {kind!r} (공통 역할: chapter, heading(level 1~3), {", ".join(r for r in ROLE_LABELS if r != "chapter" and not r.startswith("heading"))}, table)')
        return out

    summary = outline.get('summary')
    if summary is not None:
        name = by_kind.get(('summary', None, 0, None))
        need(name, '이 양식에는 요약(summary) 부품이 없습니다.')
        need(isinstance(summary, dict) and set(summary) == {'title', 'nodes'}, 'summary는 title과 nodes를 받습니다.')
        steps += [dict(op='insert', part=name, keepSection=0), dict(op='text', find=parts[name]['placeholder'], text=_text(summary['title'], 'summary.title', placeholders)),
                  *body(summary['nodes'], 'summary.nodes', True)]
    steps += body(outline.get('nodes'), 'nodes', False)
    used = {step['part'] for step in steps if step['op'] == 'insert'}
    files = {**parts, **instances}
    return dict(schema=PLAN_SCHEMA, base=dict(path=parts[cover_part]['path'], sha256=parts[cover_part]['sha256']),
                parts={name: dict(path=files[name]['path'], sha256=files[name]['sha256']) for name in sorted(used)},
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
    text = ''.join(''.join(t.itertext()) for root in roots for t in root.iter(HP + 't'))
    finds = {step['find'] for step in plan['steps'] if step['op'] == 'text'}
    wanted = [step['text'] for step in plan['steps'] if step['op'] == 'text' and step['text']]
    copies = [step['expect'] for step in plan['steps'] if 'expect' in step]
    wanted += [text for expect in copies for text in expect['texts']]
    # Outline tables appear in order among the design's own tables (bars, boxes), so match them as a subsequence.
    remaining = iter(int(t.get('rowCnt')) for root in roots for t in root.iter(HP + 'tbl'))
    expected = [expect['tableRows'] for expect in copies if 'tableRows' in expect]
    found = [rows for rows in expected if any(count == rows for count in remaining)]
    result = dict(placeholdersLeft=sorted(p for p in finds if p in text), missingTexts=[t for t in wanted if t not in text],
                  tableRows=dict(expected=expected, found=found))
    result['ok'] = not result['placeholdersLeft'] and not result['missingTexts'] and found == expected
    return result
