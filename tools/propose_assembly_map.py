"""Propose a part map and a self-reproduction outline for one source HWPX (registration step 1).

Every top paragraph of the first section gets a role of the common outline vocabulary or none:
  chapter      a one-row number+title table (Ⅰ | 추진 근거) or a "Ⅰ. 제목" line
  heading1-3   "1. ", "가. ", "1) " lines; task, point, subhead, item, dash, dot, note, arrow, lead, box by their symbol
  table        a repeating table (one header, uniform rows, optional total row), a fixed table with named rows
               (labelColumn) or a step flow (arrow cells); any other table is a block
  block        everything else that is not empty (pictures, drawn titles, boxes of body text, irregular tables,
               automatic numbering, paragraphs with footnotes or unknown symbols), kept as the source has it
For each vocabulary role the most common look (paragraph and character format) gives one part; consecutive
block paragraphs give one block part each. The outline repeats the source in that vocabulary, with its page
breaks, so assembling it should give the source back (registration acceptance check 1).

Usage: propose_assembly_map.py SOURCE.hwpx OUT_DIR --id ID [--exclude ROLE ...]
  --exclude ROLE  draw that role (or pN, the paragraph N) as blocks: a part that failed to build
Writes OUT_DIR/map.json and OUT_DIR/outline.json and prints a summary.
"""
import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
ROMAN = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ'
PATTERNS = [  # (role, regex on the text after leading spaces), as the outline vocabulary names them
    ('chapter', rf'^[{ROMAN}]\.?\s'), ('heading1', r'^\d{1,2}\.\s'), ('heading2', r'^[가-하]\.\s'), ('heading3', r'^\d{1,2}\)\s'),
    ('task', '^[\U000F02B1-\U000F02C4]'), ('point', r'^[①-⑳]'), ('subhead', r'^[□■▣◻]'), ('item', r'^[○◦ㅇ∘●◯]'),
    ('dash', r'^[-–―]\s'), ('dot', r'^[·‧∙ㆍ•]'), ('note', r'^[※＊*]'), ('arrow', r'^[⇒→➡▶►]'), ('lead', '^[❍❑]'), ('box', r'^[◈◆◇]'),
]
TEXT_ROLES = ('subhead', 'item', 'dash', 'dot', 'note', 'arrow', 'lead', 'box', 'task', 'point')
DEFAULT_SYMBOL = {'item': '◦', 'dash': '-', 'dot': '‧', 'note': '※', 'arrow': '⇒'}
NUMBERED_PREFIX = {'heading1': r'^\d{1,2}\.\s*', 'heading2': r'^[가-하]\.\s*', 'heading3': r'^\d{1,2}\)\s*', 'chapter': rf'^[{ROMAN}]\.?\s*',
                   'task': '^[\U000F02B1-\U000F02C4]\\s*', 'point': r'^[①-⑳]\s*'}
ARROWS = ('➜', '⇨', '→', '▶', '➡', '⇒')
TOTALS = ('계', '합계', '총계', '소계', '합 계', '총 계')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def own_text(p):
    return ''.join(t.text or '' for run in p.findall(HP + 'run') for t in run.findall(HP + 't'))


def cells_of(table):
    return [tr.findall(HP + 'tc') for tr in table.findall(HP + 'tr')]


def span(cell):
    s = cell.find(HP + 'cellSpan')
    return int(s.get('rowSpan')), int(s.get('colSpan'))


def cell_value(cell):
    """One paragraph as a string, several as a list, none as ''."""
    texts = [clean(''.join(t.text or '' for t in p.iter(HP + 't'))) for p in cell.iter(HP + 'p')]
    texts = [t for t in texts if t]
    return texts[0] if len(texts) == 1 else texts or ''


def flat_text(cell):
    value = cell_value(cell)
    return ' '.join(value) if isinstance(value, list) else value


def own_tables(p):
    return [t for t in p.iter(HP + 'tbl') if t.getparent().getparent() is p]


def chapter_cells(table):
    """(number, title) of a one-row number+title table, or None."""
    rows = cells_of(table)
    if len(rows) != 1 or len(rows[0]) > 4:
        return None
    texts = [flat_text(c) for c in rows[0]]
    number = next((t for t in texts if re.fullmatch(rf'([{ROMAN}]|\d{{1,2}})\.?', t)), None)
    titles = [t for t in texts if t and t != number]
    return (number, max(titles, key=len)) if number and titles and len(''.join(titles)) < 40 else None


def table_shape(table):
    """How a table can be drawn: repeat (header, units, optional total row), labels (fixed, named rows), steps or block."""
    rows = cells_of(table)
    texts = [[flat_text(c) for c in row] for row in rows]
    if any(t in ARROWS for row in texts for t in row):
        return dict(kind='steps', headerRows=0, unitRows=len(rows), fixedTexts=sorted({t for row in texts for t in row if t in ARROWS}))
    heads = max(span(c)[0] for c in rows[0]) if rows else 1
    if len(rows) < heads + 1:
        return dict(kind='block', why='표에 본문 줄이 없음')
    body = rows[heads:]
    footer = 1 if len(body) > 1 and any(t.replace(' ', '') in [x.replace(' ', '') for x in TOTALS] for t in texts[-1]) else 0
    units = body[:len(body) - footer]
    layout = [tuple(span(c) for c in row) for row in units]
    if all(l == layout[0] for l in layout) and all(s == (1, 1) for l in layout for s in l):
        return dict(kind='repeat', headerRows=heads, unitRows=1, footerRows=footer,
                    footerLabels=sorted({t for t in texts[-1] if t.replace(' ', '') in [x.replace(' ', '') for x in TOTALS]}) if footer else [])
    first = [row[0] for row in body if row and row[0].find(HP + 'cellAddr').get('colAddr') == '0']
    if (len(first) == len(body) and all(span(c)[0] == 1 for c in first)
            and all(0 < len(flat_text(c)) <= 12 for c in first) and len({flat_text(c) for c in first}) == len(first)):
        return dict(kind='labels', headerRows=heads, unitRows=len(body))
    return dict(kind='block', why='칸 합침이 불규칙한 표')


def role_of(p, numbered_shapes):
    """Vocabulary role of a top paragraph, with what the outline and the map need."""
    text = own_text(p)
    tags = {e.tag.split('}')[1] for e in p.iter()}
    tables = own_tables(p)
    if p.get('paraPrIDRef') in numbered_shapes:
        return dict(role='block', why='자동 번호·글머리표')
    if tables:
        chapter = chapter_cells(tables[0])
        if chapter and not text.strip():
            return dict(role='chapter', number=chapter[0], title=chapter[1], table=True)
        shape = table_shape(tables[0])
        if shape['kind'] == 'block' or text.strip():
            return dict(role='block', why=shape.get('why', '표와 글이 한 문단'))
        return dict(role='table', shape=shape, inline=tables[0].find(HP + 'pos').get('treatAsChar') == '1')
    if 'pic' in tags or 'ole' in tags:
        return dict(role='block', why='그림')
    drawn_text = ''.join(t.text or '' for d in p.iter(HP + 'drawText') for t in d.iter(HP + 't')).strip()
    if ('container' in tags or 'rect' in tags) and (drawn_text or not text.strip()):
        return dict(role='block', why='글상자·도형')
    if 'footNote' in tags or 'endNote' in tags:
        return dict(role='block', why='각주')
    if not text.strip():
        return dict(role='block', why='글상자·도형 안 글') if ''.join(t.text or '' for t in p.iter(HP + 't')).strip() else dict(role='empty')
    # what is left with drawings is a line led by a small drawn square (one rectangle or a group of them)
    body = text.strip()
    for role, pattern in PATTERNS:
        if re.match(pattern, body):
            return dict(role=role, text=body)
    if 'rect' in tags or 'container' in tags:
        return dict(role='subhead', text=body, drawn=True)  # a small drawn square before the title
    return dict(role='block', why='공통 어휘가 아닌 문단')


def look(p):
    """Paragraph format and the character format of the first letters (not of a leading symbol run): authors
    often condense one line's letter spacing to fit it, which is a look of its own."""
    runs = [r for r in p.findall(HP + 'run') if re.search('[가-힣A-Za-z0-9]', ''.join(t.text or '' for t in r.findall(HP + 't')))]
    return p.get('paraPrIDRef'), runs[0].get('charPrIDRef') if runs else None


def page_numbers(section):
    number = next(section.iter(HP + 'pageNum'), None)
    if number is None:
        return None
    position = ''.join(w.capitalize() for w in number.get('pos', 'BOTTOM_CENTER').split('_'))
    return dict(position=position, format=number.get('formatType', 'DIGIT').capitalize(), sideChar=number.get('sideChar', ''))


DATE = r'(19|20)\d\d\.\s?\d{1,2}\.(\s?\d{1,2}\.)?(\s?\(.\))?'
ORG = r'(교육청|교육지원청|학교|센터|위원회|과|팀|부|원)\)?$'


def pieces_of(p, heights):
    """(text, character height) of every run text of a paragraph, tables and boxes included."""
    return [(piece.strip(), heights.get(run.get('charPrIDRef'), 0)) for run in p.iter(HP + 'run') for t in run.findall(HP + 't')
            for piece in [t.text, *(c.tail for c in t)] if piece and piece.strip()]


def cover_end_of(paragraphs, heights):
    """Where the cover ends: after the title (the largest letters), at the first paragraph holding body text
    (a long line that is neither the title, an organization nor a date), such as an introduction box."""
    found = [(i, x, h) for i, p in enumerate(paragraphs) for x, h in pieces_of(p, heights) if re.search('[가-힣A-Za-z]', x)]
    if not found:
        return len(paragraphs)
    top_height = max(h for _, _, h in found)
    title_at = max(i for i, _, h in found if h >= top_height * 0.7)
    for i in range(title_at + 1, len(paragraphs)):
        if any(len(x) > 20 and h < top_height * 0.7 and not re.search(ORG, x) and not re.fullmatch(DATE, x)
               for x, h in pieces_of(paragraphs[i], heights)):
            return i
    return len(paragraphs)


def cover_spec(paragraphs, heights):
    """Placeholders for the cover's title (its largest letters, lines joined), organization and date; other
    words are dropped, ornaments kept."""
    # exact run texts (replace matches them inside their runs); repeated ones are replaced once, so they are skipped
    raw = [x for p in paragraphs for x in pieces_of(p, heights)]
    texts = [x for x, _ in raw]
    pieces = [(x, h) for x, h in dict.fromkeys(raw) if texts.count(x) == 1 or not re.search('[가-힣A-Za-z0-9]', x)]
    replace, fields, keep = {}, {}, []
    lettered = [h for x, h in pieces if re.search('[가-힣A-Za-z]', x)]
    need(lettered, '표지에서 제목을 찾지 못했습니다')
    big = [x for x, h in pieces if re.search('[가-힣A-Za-z]', x) and h >= max(lettered) * 0.7]
    titles = [x for x in big if not (re.search(ORG, x) and len(x) <= 20)] or big  # a large organization name is not the title
    dates = [x for x, _ in pieces if x not in titles and re.fullmatch(DATE, x)]
    orgs = [x for x, _ in pieces if x not in titles and x not in dates and re.search(ORG, x) and len(x) <= 40]
    for x, _ in pieces:
        if x in titles:
            replace[x] = '[제목]' if x == titles[0] else ''  # a title of several lines goes in as one
            fields['title'] = '[제목]'
        elif dates and x == dates[0]:
            replace[x], fields['date'] = '[날짜]', '[날짜]'
        elif orgs and x == orgs[0]:
            replace[x], fields['organization'] = '[기관]', '[기관]'
        elif re.search('[가-힣A-Za-z0-9]', x) and len(x) > 2:
            replace[x] = ''  # other source words do not ship
        else:
            keep.append(x)  # ornaments, such as a Wingdings letter
    value = {'title': clean(' '.join(titles)), **({'date': clean(dates[0])} if 'date' in fields else {}),
             **({'organization': clean(orgs[0])} if 'organization' in fields else {})}
    return dict(replace=replace, fields=fields, keep=sorted(set(keep))), value


def propose(source, template_id, exclude=()):
    with zipfile.ZipFile(source) as package:
        header = etree.fromstring(package.read('Contents/header.xml'))
        section = etree.fromstring(package.read('Contents/section0.xml'))
        sections = [n for n in package.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n)]
    numbered = {s.get('id') for s in header.iter(HH + 'paraPr') if s.find(HH + 'heading') is not None and s.find(HH + 'heading').get('type') != 'NONE'}
    top = section.findall(HP + 'p')
    roles = [role_of(p, numbered) for p in top]
    for index, info in enumerate(roles):
        if info['role'] in exclude or f'p{index}' in exclude:
            info.update(role='block', why=f'{info["role"]} 부품 빌드 실패로 블록')
    # the cover may hold tables (a title band); the body starts at the first chapter or vocabulary line
    first = next((i for i, r in enumerate(roles) if r['role'] not in ('empty', 'block', 'table') and i > 0), None)
    need(first is not None, '공통 어휘로 읽히는 문단이 없습니다')
    chapters = [i for i, r in enumerate(roles) if r['role'] == 'chapter']
    need(chapters, '장(Ⅰ 제목)이 없어 조립 양식으로 만들 수 없습니다. 빈칸 채우기로 등록하세요.')
    heights = {c.get('id'): int(c.get('height')) for c in header.iter(HH + 'charPr')}
    cover_end = cover_end_of(top[:first], heights)
    cover, cover_value = cover_spec(top[:cover_end], heights)
    parts, notes = {}, []
    parts['cover'] = dict(range=[0, cover_end], kind='cover', keepFaces=True, **cover)

    # the empty line most later chapters have above them becomes the spacer part (left out atop a new page)
    later = [i for i in chapters[1:] if top[i].get('pageBreak') != '1']
    spaced = [i - 1 for i in later if roles[i - 1]['role'] == 'empty' and not own_tables(top[i - 1])]
    spacer = bool(later) and len(spaced) * 2 > len(later)
    if spacer:
        parts['spacer'] = dict(range=[spaced[0], spaced[0] + 1], kind='spacer')

    def chapter_part(i, kind):
        info = roles[i]
        spec = dict(range=[i, i + 1], kind=kind, placeholder='[장 제목]', numberPlaceholder='[장 번호]')
        number = info['number'] if info.get('table') else re.match(NUMBERED_PREFIX['chapter'], info['text']).group(0).strip()
        title = info['title'] if info.get('table') else re.sub(NUMBERED_PREFIX['chapter'], '', info['text'])
        spec['replace'] = {number: '[장 번호]', title: '[장 제목]'}
        spec['numbering'] = ('roman' if number.endswith('.') else 'roman-bare') if number.strip('.') in ROMAN else 'digit'
        if info.get('table'):
            spec['fitTitleCell'] = True
        return spec

    parts['chapter_first'] = chapter_part(chapters[0], 'chapter_first')
    parts['chapter'] = chapter_part(chapters[1] if len(chapters) > 1 else chapters[0], 'chapter')
    # one part per vocabulary role, from its most common look
    for role in ('heading1', 'heading2', 'heading3', *TEXT_ROLES):
        found = [i for i, r in enumerate(roles) if r['role'] == role and i >= cover_end]
        if not found:
            continue
        common = Counter(look(top[i]) for i in found).most_common(1)[0][0]
        i = next(i for i in found if look(top[i]) == common)
        if role in TEXT_ROLES and role not in ('task', 'point') and not roles[i].get('drawn'):  # numbered symbols differ by number
            # a line of the role written with another symbol in another look (※ among small * notes) is a different
            # thing the vocabulary has no second part for: it stays as the source has it
            for j in found:
                if roles[j]['text'][0] != roles[i]['text'][0] and look(top[j]) != common:
                    roles[j] = dict(role='block', why=f'{role}의 다른 모양({roles[j]["text"][0]})')
            found = [j for j in found if roles[j]['role'] == role]
        others = sum(look(top[j]) != common for j in found)
        if others:
            notes.append(f'{role}: 모양 {len({look(top[j]) for j in found})}가지 중 가장 많은 것으로 부품을 만듦({others}줄은 그 모양으로 들어감)')
        spec = dict(range=[i, i + 1], placeholder='[항목]')
        if role.startswith('heading'):
            spec.update(kind='heading', level=int(role[-1]), placeholder=f'[{role[-1]}단계 제목]')
        elif role in ('task', 'point'):
            spec.update(kind=role, placeholder='[과제 제목]' if role == 'task' else '[점 내용]', numberPlaceholder='[번호]',
                        numbering='boxed' if role == 'task' else 'circled')
            symbol = re.match(NUMBERED_PREFIX[role], roles[i]['text']).group(0).strip()
            spec['replace'] = {symbol: '[번호]', re.sub(NUMBERED_PREFIX[role], '', roles[i]['text']): spec['placeholder']}
        else:
            spec.update(kind=role, placeholder='[소제목]' if role == 'subhead' else '[항목]')
            symbol = roles[i]['text'][0]
            if role in DEFAULT_SYMBOL and symbol != DEFAULT_SYMBOL[role]:
                spec.update(prefix=r'\s*' + re.escape(symbol) + r'\s*', symbol=symbol)
            if role != 'subhead':
                spec['baseLeftHwp'] = 0
        parts[role] = spec
    # tables and blocks: one part each, at their own place
    nodes, block_start, count = [], None, Counter()
    tables = {}

    def close_block(end):
        nonlocal block_start
        if block_start is None:
            return
        count['block'] += 1
        name = f'block{count["block"]}'
        spec = dict(range=[block_start, end], kind='block')
        if any(t.find(HP + 'pos').get('treatAsChar') != '1' for p in top[block_start:end] for t in own_tables(p)):
            spec['tableAsChar'] = True
        parts[name] = spec
        nodes.append(dict(t='block', part=name, **({'pageBreakBefore': True} if top[block_start].get('pageBreak') == '1' else {})))
        notes.append(f'{name}: 원본 그대로 블록 (문단 {block_start}~{end - 1}: {", ".join(sorted({roles[j]["why"] for j in range(block_start, end) if roles[j]["role"] == "block"}))})')
        block_start = None

    for i in range(cover_end, len(top)):
        info, p = roles[i], top[i]
        if info['role'] == 'block':
            if block_start is None:
                block_start = i
            continue
        if info['role'] == 'empty':
            continue
        close_block(i)
        node = None
        if info['role'] == 'chapter':
            node = dict(t='chapter', text=clean(info['title'] if info.get('table') else re.sub(NUMBERED_PREFIX['chapter'], '', info['text'])))
        elif info['role'].startswith('heading'):
            node = dict(t='heading', level=int(info['role'][-1]), text=clean(re.sub(NUMBERED_PREFIX[info['role']], '', info['text'])))
        elif info['role'] in ('task', 'point'):
            node = dict(t=info['role'], text=clean(re.sub(NUMBERED_PREFIX[info['role']], '', info['text'])))
        elif info['role'] in TEXT_ROLES:
            text = info['text'] if info.get('drawn') else re.sub(r'^\S\s*', '', info['text'])
            node = dict(t=info['role'], text=clean(text) or clean(info['text']))
        elif info['role'] == 'table':
            node = table_node(i, p, info, parts, tables)
        if node is None:
            continue
        if p.get('pageBreak') == '1':
            node['pageBreakBefore'] = True
        nodes.append(node)
    close_block(len(top))
    rules = dict(spacerBeforeLaterChapters=spacer, bodyStartsNewSection=False, deepItemsUnderHeadingLevel=9,
                 pageNumbers=page_numbers(section), headingLevelsMaySkip=True)
    if nodes and nodes[0]['t'] != 'chapter':
        rules['textBeforeFirstChapter'] = True
    if len(sections) > 1:
        notes.append(f'구역이 {len(sections)}개입니다. 첫 구역만 등록했습니다.')
    part_map = dict(schema='hwpx.assembly-part-map.v1', id=template_id, label=f'등록: {cover_value["title"]}',
                    source=dict(sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(), title=Path(source).name,
                                publisher='', license='사용자 등록', attribution='사용자가 등록한 문서에서 만든 조립 양식'),
                    rules=rules, deepIndentHwp=1000, parts=parts)
    outline = dict(schema='hwpx.assembly-outline.v1', template=template_id, cover=cover_value, nodes=nodes)
    summary = dict(parts=sorted(parts), blocks=sum(n['t'] == 'block' for n in nodes), nodes=len(nodes),
                   roles=dict(Counter(r['role'] for r in roles[cover_end:] if r['role'] != 'empty')), notes=notes)
    return part_map, outline, summary


def table_node(i, p, info, parts, tables):
    """The outline node of a table; the first table of each shape and size gives the part."""
    table = own_tables(p)[0]
    rows = cells_of(table)
    shape = info['shape']
    key = (shape['kind'], shape['headerRows'], tuple(len(r) for r in rows[shape['headerRows']:shape['headerRows'] + 1]),
           shape.get('footerRows', 0), len(rows) if shape['kind'] != 'repeat' else 0)
    name = tables.get(key)
    if name is None:
        name = f'table{len(tables) + 1}'
        tables[key] = name
        spec = dict(headerRows=shape['headerRows'], unitRows=shape['unitRows'], role='grid')
        if shape['kind'] == 'repeat' and shape.get('footerRows'):
            spec.update(footerRows=1, footerLabels=shape['footerLabels'])
        if shape['kind'] == 'labels':
            spec.update(repeat=False, labelColumn=0)
        if shape['kind'] == 'steps':
            spec.update(repeat=False, fixedTexts=shape['fixedTexts'], role='steps')
        parts[name] = dict(range=[i, i + 1], kind='table', table=spec, **({} if info['inline'] else {'tableAsChar': True}))
    heads = shape['headerRows']
    header = [cell_value(c) for row in rows[:heads] for c in row]
    node = dict(t='table', part=name)
    if header:
        node['header'] = [' '.join(h) if isinstance(h, list) else h for h in header]
    if shape['kind'] == 'repeat':
        body = rows[heads:len(rows) - shape.get('footerRows', 0)]
        node['rows'] = [[cell_value(c) for c in row] for row in body]
        if shape.get('footerRows'):
            node['footer'] = [cell_value(c) for c in rows[-1] if flat_text(c) not in shape['footerLabels']]
    elif shape['kind'] == 'labels':
        node['values'] = {flat_text(row[0]): [cell_value(c) for c in row[1:]] for row in rows[heads:]}
    else:
        node['rows'] = [[cell_value(c) for row in rows for c in row if flat_text(c) not in shape['fixedTexts']]]
    if any(isinstance(h, str) and not h for h in node.get('header', [])):
        node.pop('header')  # an empty header cell (a diagonal one) keeps the part's own
    return node


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source')
    parser.add_argument('out')
    parser.add_argument('--id', required=True)
    parser.add_argument('--exclude', action='append', default=[])
    args = parser.parse_args()
    part_map, outline, summary = propose(Path(args.source).resolve(strict=True), args.id, args.exclude)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'map.json').write_text(json.dumps(part_map, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'outline.json').write_text(json.dumps(outline, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
