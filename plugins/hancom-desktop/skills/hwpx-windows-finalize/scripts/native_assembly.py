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
ITEM_KINDS = ('item', 'dash', 'dot', 'note', 'arrow')
# One placeholder, no numbering: the outline node {"t": kind, "text": ...} fills it.
TEXT_KINDS = (*ITEM_KINDS, 'box', 'subhead')
PART_KINDS = ('cover', 'chapter_first', 'chapter', 'heading', 'task', 'point', 'table', 'spacer', 'summary', 'summary_chapter', *TEXT_KINDS)
# The symbol each text part already draws; the same symbol typed at the start of the text is dropped.
KIND_SYMBOLS = {'item': '◦○∘•', 'dash': '-–', 'dot': '‧·ㆍ', 'note': '※', 'arrow': '⇒→', 'subhead': '□', 'box': '◈'}
BOXED_DIGITS = 20  # Hancom private-use squared digits U+F02B1.., and circled ①..⑳
STEP_OPS = ('text', 'section', 'insert', 'pageNumbers', 'boxWidth', 'pageBreak')
MAX_NODES, MAX_ROWS, MAX_TEXT, MAX_CELL_PARAGRAPHS = 400, 100, 2000, 20
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
    required = ('cover', 'chapter_first', 'chapter', *(('spacer',) if manifest['rules'].get('spacerBeforeLaterChapters') else ()))
    for kind in required:
        need(sum(p['kind'] == kind for p in parts.values()) == 1, f'조립 양식에 {kind} 부품이 하나 있어야 합니다.')
    return manifest


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


def _set_cell(cell, value, prefix=''):
    """Replace a cell's paragraphs with one copy of its first paragraph per text, in that paragraph's first run format."""
    sub = cell.find(HP + 'subList')
    paragraphs = sub.findall(HP + 'p')
    for paragraph in paragraphs:
        sub.remove(paragraph)
    for text in value if isinstance(value, list) else [value]:
        paragraph = copy.deepcopy(paragraphs[0])
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
    table = next(section.iter(HP + 'tbl'))
    rows = table.findall(HP + 'tr')
    heads, unit = rows[:spec['headerRows']], rows[spec['headerRows']:]
    if header is not None:
        for cell, value in zip([c for tr in heads for c in _cells(tr)], header):
            _set_cell(cell, value)
    for tr in unit:
        table.remove(tr)
    prefix = spec.get('firstColumnPrefix', '')
    for index, values in enumerate(units):
        clones = [copy.deepcopy(tr) for tr in unit]
        for cell, value in zip([c for tr in clones for c in _cells(tr)], values):
            address = cell.find(HP + 'cellAddr')
            address.set('rowAddr', str(int(address.get('rowAddr')) + index * len(unit)))
            _set_cell(cell, value, prefix if address.get('colAddr') == '0' and value else '')
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
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'x') as out:
        for info in infos:
            out.writestr(info, data[info.filename])
    return count


def text_width(text, em):
    """Rough advance (HWPUNIT) of a title: Hangul and other wide characters one em, the rest half."""
    return sum(em if ord(c) >= 0x1100 else em // 2 for c in text)


def fitted_instance(part, values, target):
    """Write a copy of a part whose title sits in a fixed-width table cell (a numbered tab): the
    placeholders become the texts and that cell grows by the title's extra width, within the body."""
    fit = part['fit']
    with zipfile.ZipFile(part['path']) as package:
        infos = package.infolist()
        data = {info.filename: package.read(info) for info in infos}
    section = etree.fromstring(data['Contents/section0.xml'])
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


def build_plan(manifest, outline, tables_dir=None):
    """Validate the outline against the template and resolve it into native steps.

    Table nodes are written as part copies into tables_dir (a new folder)."""
    parts, rules = manifest['parts'], manifest['rules']
    by_kind = {}
    for name, part in parts.items():
        by_kind.setdefault((part['kind'], part.get('level'), part.get('depth', 0), part.get('context')), name)
    placeholders = set()
    for part in parts.values():
        value = part.get('placeholder')
        placeholders.update(value.values() if isinstance(value, dict) else [value] if value else [])
        placeholders.update([part['numberPlaceholder']] if part.get('numberPlaceholder') else [])
    need(isinstance(outline, dict) and outline.get('schema', OUTLINE_SCHEMA) == OUTLINE_SCHEMA, f'outline schema는 {OUTLINE_SCHEMA}입니다.')
    need(set(outline) <= {'schema', 'template', 'cover', 'summary', 'nodes'}, '지원 키: schema, template, cover, summary, nodes')
    need(outline.get('template', manifest['id']) == manifest['id'], 'outline의 template이 선택한 양식과 다릅니다.')
    cover, cover_part = outline.get('cover'), next(n for n, p in parts.items() if p['kind'] == 'cover')
    fields = parts[cover_part]['placeholder']
    need(isinstance(cover, dict) and set(cover) <= set(fields) and {'title', 'date'} <= set(cover), f'cover 지원 키: {", ".join(fields)} (title·date 필수)')
    steps = [dict(op='text', find=fields[key], text=_text(cover.get(key, ''), f'cover.{key}', placeholders, key not in ('title', 'date'))) for key in fields]
    if rules.get('pageNumbers') and not rules.get('bodyStartsNewSection'):
        steps.append(dict(op='pageNumbers', **rules['pageNumbers']))  # one section: the cover part hides its own number
    instances = {}

    def body(nodes, prefix, summary):
        """Steps of one node list; the summary list uses the summary chapter part and its own numbering."""
        need(isinstance(nodes, list) and 1 <= len(nodes) <= MAX_NODES, f'{prefix}는 1~{MAX_NODES}개입니다.')
        need(isinstance(nodes[0], dict) and nodes[0].get('t') == 'chapter', f'{prefix}는 장(chapter)으로 시작해야 합니다.')
        def find(kind, level=None, depth=0):
            """The part for a kind; on the summary page a part made for it comes first."""
            return (summary and by_kind.get((kind, level, depth, 'summary'))) or by_kind.get((kind, level, depth, None))

        out, counters, tasks, points, level = [], [0, 0, 0, 0], 0, 0, 0
        for position, node in enumerate(nodes, 1):
            where = f'{prefix}[{position}]'
            need(isinstance(node, dict) and 't' in node, f'{where}: t가 필요합니다.')
            kind = node['t']
            if kind == 'chapter':
                need(set(node) == {'t', 'text'}, f'{where}: chapter는 t, text만 받습니다.')
                counters, tasks, points, level = [counters[0] + 1, 0, 0, 0], 0, 0, 0
                first = counters[0] == 1
                name = find('summary_chapter') if summary else find('chapter_first' if first else 'chapter')
                part = parts[name]
                label = number(part['numbering'], counters[0], '장')
                title = _text(node['text'], where, placeholders)
                if first and not summary and rules.get('bodyStartsNewSection'):
                    out += [dict(op='section'), dict(op='insert', part=name, keepSection=1), dict(op='pageNumbers', **rules['pageNumbers'])]
                else:
                    if not first and not summary and rules.get('spacerBeforeLaterChapters'):
                        out.append(dict(op='insert', part=find('spacer'), keepSection=0))
                    if part.get('pageBreakBefore'):
                        out.append(dict(op='pageBreak'))
                    out.append(dict(op='insert', part=name, keepSection=0))
                out += numbered(part, label, title)
                if 'box' in part:
                    width = box_width(part['box'], f'{label} {title}')
                    need(width <= part['box']['maxWidthHwp'], f'{where}: 장 제목이 길어 상자가 본문 폭을 넘습니다 '
                         f'(필요 {width / 283.465:.1f}mm, 최대 {part["box"]["maxWidthHwp"] / 283.465:.1f}mm). 제목을 줄이세요.')
                    out.append(dict(op='boxWidth', width=width))
            elif kind == 'heading':
                need(set(node) == {'t', 'level', 'text'} and node['level'] in (1, 2, 3), f'{where}: heading은 level 1~3과 text가 필요합니다.')
                depth = node['level']
                need(depth == 1 or counters[depth - 1] > 0, f'{where}: {depth}단계 제목 앞에 {depth - 1}단계 제목이 필요합니다.')
                counters[depth] += 1
                counters[depth + 1:] = [0] * (3 - depth)
                tasks, points, level = 0, 0, depth
                name = find('heading', depth)
                need(name, f'양식에 {depth}단계 제목 부품이 없습니다.')
                label, title = number(parts[name]['numbering'], counters[depth], f'{depth}단계 제목'), _text(node['text'], where, placeholders)
                if 'fit' in parts[name]:
                    need(tables_dir is not None, 'fitted titles need a folder for part copies')
                    copy_name, target = f'{name}@{len(instances) + 1}', Path(tables_dir) / f'{name}-{len(instances) + 1}.hwpx'
                    fitted_instance(parts[name], {parts[name]['numberPlaceholder']: label, parts[name]['placeholder']: title}, target)
                    instances[copy_name] = dict(path=str(target.resolve()), sha256=sha(target))
                    out.append(dict(op='insert', part=copy_name, keepSection=0, expect=dict(texts=[label, title])))
                else:
                    out += [dict(op='insert', part=name, keepSection=0), *numbered(parts[name], label, title)]
            elif kind in ('task', 'point'):
                need(set(node) == {'t', 'text'}, f'{where}: {kind}는 t, text만 받습니다.')
                name = find(kind)
                need(name, f'양식에 {kind} 부품이 없습니다.')
                if kind == 'task':
                    tasks, points = tasks + 1, 0
                else:
                    points += 1
                out += [dict(op='insert', part=name, keepSection=0),
                        *numbered(parts[name], number(parts[name]['numbering'], tasks if kind == 'task' else points, '번호 항목'), _text(node['text'], where, placeholders))]
            elif kind in TEXT_KINDS:
                need(set(node) == {'t', 'text'}, f'{where}: {kind}는 t, text만 받습니다.')
                deep = int(level >= rules['deepItemsUnderHeadingLevel'])
                name = find(kind, None, deep) or find(kind)
                need(name, f'양식에 {kind} 부품이 없습니다.')
                text = _text(node['text'], where, placeholders)
                text = re.sub(rf'^\s*[{re.escape(KIND_SYMBOLS[kind])}]\s+', '', text) or text
                out += [dict(op='insert', part=name, keepSection=0), dict(op='text', find=parts[name]['placeholder'], text=text)]
            elif kind == 'table':
                need({'t', 'part', 'rows'} <= set(node) <= {'t', 'part', 'rows', 'header'}, f'{where}: table은 t, part, rows와 선택 header만 받습니다.')
                part = parts.get(node['part'])
                need(part is not None and part['kind'] == 'table', f'{where}: 표 부품 {node["part"]!r}이 양식에 없습니다.')
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
                name = f'{node["part"]}@{len(instances) + 1}'
                target = Path(tables_dir) / f'{node["part"]}-{len(instances) + 1}.hwpx'
                count = table_instance(part, header, rows, target)
                instances[name] = dict(path=str(target.resolve()), sha256=sha(target))
                texts = [p for row in [header or [], *rows] for cell in row for p in (cell if isinstance(cell, list) else [cell]) if p]
                out.append(dict(op='insert', part=name, keepSection=0, expect=dict(tableRows=count, texts=texts)))
            else:
                known = sorted({p['kind'] for p in parts.values()} & {'heading', 'task', 'point', 'table', *TEXT_KINDS})
                raise ValueError(f'{where}: 알 수 없는 t {kind!r} (chapter, {", ".join(known)})')
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
