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

A source without chapters (□ titles lead, as in a one-page report) gets no chapter parts; an outline's chapters are
then drawn as □ titles.

Usage: propose_assembly_map.py SOURCE.hwpx OUT_DIR --id ID [--exclude ROLE ...] [--start TEXT]
  --start TEXT    register from the first paragraph holding TEXT (an attachment after a press release)
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


def row_pictures(row):
    return (e for c in row for e in c.iter() if e.tag.split('}')[1] in ('pic', 'ole', 'container', 'rect'))


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
    columns = sum(span(c)[1] for c in rows[0]) if rows else 0
    if columns < 2 or len(rows[0]) < 2:
        return dict(kind='block', why='한 칸짜리 상자·띠 표')  # a title band or a box, not a table of rows
    def looks(cell):
        return {(q.get('paraPrIDRef'), *(r.get('charPrIDRef') for r in q.findall(HP + 'run')[:1])) for q in cell.iter(HP + 'p')
                if ''.join(t.text or '' for t in q.iter(HP + 't')).strip()}
    # a table part fills every cell in one look per column: cells mixing looks (smaller notes, squeezed lines) would grow
    uniform = all(len(set().union(*(looks(row[c]) for row in units if c < len(row)))) <= 1 for c in range(len(units[0]))) if units else False
    if (all(l == layout[0] for l in layout) and all(s == (1, 1) for l in layout for s in l)
            and heads == 1 and len(rows[0]) == len(units[0])):  # column headers over the unit's cells
        shape = dict(kind='repeat', headerRows=heads, unitRows=1, footerRows=footer,
                     footerLabels=sorted({t for t in texts[-1] if t.replace(' ', '') in [x.replace(' ', '') for x in TOTALS]}) if footer else [])
        if not uniform:
            # One highlighted row or a squeezed note mixes the looks of a column; the part keeps the row whose looks
            # are the most common ones (and holds no picture) and draws every outline row in it.
            common = [Counter(frozenset(looks(row[c])) for row in units).most_common(1)[0][0] for c in range(len(units[0]))]
            score = [(sum(frozenset(looks(row[c])) == common[c] for c in range(len(row))), not any(True for _ in row_pictures(row)))
                     for row in units]
            shape['unitRow'] = max(range(len(units)), key=lambda k: (score[k], -k))
        return shape
    first = [row[0] for row in body if row and row[0].find(HP + 'cellAddr').get('colAddr') == '0']
    if (len(first) == len(body) and all(span(c)[0] == 1 for c in first)
            and all(0 < len(flat_text(c)) <= 12 for c in first) and len({flat_text(c) for c in first}) == len(first)
            and all(len(looks(c)) <= 1 for row in body for c in row[1:])):  # each value cell in one look
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
    if 'container' in tags and not text.strip():
        # a chapter title written in a grouped box with a shadow (Ⅰ. 시험 개요), as ministry plans draw them
        lines = [''.join(t.text or '' for t in q.iter(HP + 't')).strip() for d in p.iter(HP + 'drawText') for q in d.iter(HP + 'p')]
        lines = [line for line in lines if line]
        if len(lines) == 1 and re.match(PATTERNS[0][1], lines[0]):
            return dict(role='chapter', text=lines[0], box=True)
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
    page_end, last = len(paragraphs), None  # the cover is one page: stop where the saved line positions start over
    for i, p in enumerate(paragraphs):
        lines = p.find(HP + 'linesegarray')
        if lines is None or not len(lines):
            continue
        if last is not None and (int(lines[0].get('vertpos')) < last or p.get('pageBreak') == '1'):
            page_end = i
            break
        last = int(lines[-1].get('vertpos'))
    paragraphs = paragraphs[:page_end]
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


def cover_spec(paragraphs, heights, labelled=False):
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
    # in an attachment's title band, a short word as large as the title beside it is a label box (붙임, 참고), not part
    # of the title; on a full cover such a word is a heading of the next page (차 례) and is dropped like other words
    labels = [x for x in titles if len(re.sub(r'\s', '', x)) <= 4] if labelled and any(len(re.sub(r'\s', '', x)) > 4 for x in titles) else []
    titles = [x for x in titles if x not in labels]
    dates = [x for x, _ in pieces if x not in titles and re.fullmatch(DATE, x)]
    orgs = [x for x, _ in pieces if x not in titles and x not in dates and re.search(ORG, x) and len(x) <= 40]
    for x, _ in pieces:
        if labels and x == labels[0]:
            replace[x], fields['subtitle'] = '[부제목]', '[부제목]'
        elif x in titles:
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
    value = {'title': clean(' '.join(titles)), **({'subtitle': clean(labels[0])} if labels else {}),
             **({'date': clean(dates[0])} if 'date' in fields else {}),
             **({'organization': clean(orgs[0])} if 'organization' in fields else {})}
    limits = {'subtitle': max(4, len(re.sub(r'\s', '', labels[0])))} if labels else {}
    return dict(replace=replace, fields=fields, keep=sorted(set(keep)), **({'fieldLimits': limits} if limits else {})), value


def start_of(top, text):
    """Index of the first top paragraph whose text (its tables included) holds text: an attachment (붙임) of a
    press release, say, registered without the pages before it."""
    flat = re.sub(r'\s+', '', text)
    found = [i for i, p in enumerate(top) if flat in re.sub(r'\s+', '', ''.join(t.text or '' for t in p.iter(HP + 't')))]
    need(found, f'--start 문구를 찾지 못했습니다: {text}')
    # the body may name the attachment first ("붙임: ... 계획"); its title box (a table) is where it starts
    return next((i for i in found if own_tables(top[i])), found[0])


def propose(source, template_id, exclude=(), start_text=None):
    with zipfile.ZipFile(source) as package:
        header = etree.fromstring(package.read('Contents/header.xml'))
        names = sorted((n for n in package.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n)), key=lambda n: int(re.search(r'\d+', n).group()))
        sections = [etree.fromstring(package.read(n)) for n in names]
    numbered = {s.get('id') for s in header.iter(HH + 'paraPr') if s.find(HH + 'heading') is not None and s.find(HH + 'heading').get('type') != 'NONE'}
    # Hangul numbers top paragraphs on through all sections (a cover section, then the body), as block saving counts them
    top, bounds = [], []
    for section in sections:
        bounds.append(len(top))
        top += section.findall(HP + 'p')
    start = start_of(top, start_text) if start_text else 0
    roles = [role_of(p, numbered) if i >= start else dict(role='empty') for i, p in enumerate(top)]
    for index, info in enumerate(roles):
        if info['role'] in exclude or f'p{index}' in exclude:
            info.update(role='block', why=f'{info["role"]} 부품 빌드 실패로 블록')
    # number tabs (1 | 타시·도 전출) under Roman-numbered chapters are first-level titles drawn as tabs
    tabs = [i for i, r in enumerate(roles) if r['role'] == 'chapter' and r.get('table') and r['number'].strip('.').isdigit()]
    if tabs and any(r['role'] == 'chapter' and r.get('number', r.get('text', ' '))[0] in ROMAN for r in roles):
        for i in tabs:
            roles[i] = dict(roles[i], role='heading1', text=roles[i]['title'])
    chapters = [i for i, r in enumerate(roles) if r['role'] == 'chapter']  # none: □ titles lead (a one-page report)
    need(chapters or any(r['role'] in ('subhead', 'heading1', 'task') for r in roles),
         '장(Ⅰ)도 □·1.·① 제목도 없어 조립 양식으로 만들 수 없습니다. 빈칸 채우기로 등록하세요.')
    # a body that starts in a later section: what comes before it there (a contents list, a summary) stays as the source has it
    body_section = max((k for k, b in enumerate(bounds) if chapters and b <= chapters[0]), default=0)
    if body_section:
        for j in range(start, bounds[body_section]):
            if roles[j]['role'] not in ('empty', 'block'):
                roles[j] = dict(role='block', why='본문 앞 구역(차례 등)')
    # the cover may hold tables (a title band); the body starts at the first chapter or vocabulary line
    first = next((i for i, r in enumerate(roles) if r['role'] not in ('empty', 'block', 'table') and i > start), None)
    need(first is not None, '공통 어휘로 읽히는 문단이 없습니다')
    heights = {c.get('id'): int(c.get('height')) for c in header.iter(HH + 'charPr')}
    # lines whose letters the author squeezed (negative spacing) to fit them: parts draw one look, so these may wrap
    condensed = {c.get('id') for c in header.iter(HH + 'charPr') if int(c.find(HH + 'spacing').get('hangul')) < 0}
    squeezed = sum(1 for i, r in enumerate(roles) if r['role'] not in ('empty', 'block', 'table', 'chapter') and look(top[i])[1] in condensed)
    cover_end = start + cover_end_of(top[start:first], heights)
    cover, cover_value = cover_spec(top[start:cover_end], heights, labelled=bool(start))
    parts, notes = {}, []

    def chapter_number(i):
        info = roles[i]
        mark = (info['number'] if info.get('table') else re.match(NUMBERED_PREFIX['chapter'], info['text']).group(0)).strip(' .')
        return str(ROMAN.index(mark) + 1) if mark in ROMAN else mark

    # Chapter numbers that start again at 1 mean a summary page before the body (요약): it stays as the source has it
    restart = next((k for k in range(1, len(chapters)) if chapter_number(chapters[k]) == '1'), None)
    if restart is not None:
        for j in range(cover_end, chapters[restart]):
            if roles[j]['role'] != 'empty':
                roles[j] = dict(role='block', why='본문 앞 요약쪽')
        chapters = chapters[restart:]
    parts['cover'] = dict(range=[start, cover_end], kind='cover', keepFaces=True, **cover,
                          # an attachment carries the main document's header, footer and logos: not its own
                          **({'dropPictures': True, 'dropHeaderFooter': True} if start else {}))

    # the empty line most later chapters have above them becomes the spacer part (left out atop a new page)
    later = [i for i in chapters[1:] if top[i].get('pageBreak') != '1']
    spaced = [i - 1 for i in later if roles[i - 1]['role'] == 'empty' and not own_tables(top[i - 1])]
    spacer = bool(later) and len(spaced) * 2 > len(later)
    if spacer:
        parts['spacer'] = dict(range=[spaced[0], spaced[0] + 1], kind='spacer')

    def chapter_part(i, kind):
        info = roles[i]
        if info.get('box'):  # the build fits the box to each title and numbers it Ⅰ. Ⅱ.
            return dict(range=[i, i + 1], kind=kind, placeholder='[장 제목]', expect=info['text'])
        spec = dict(range=[i, i + 1], kind=kind, placeholder='[장 제목]', numberPlaceholder='[장 번호]')
        number = info['number'] if info.get('table') else re.match(NUMBERED_PREFIX['chapter'], info['text']).group(0).strip()
        title = info['title'] if info.get('table') else re.sub(NUMBERED_PREFIX['chapter'], '', info['text'])
        spec['replace'] = {number: '[장 번호]', title: '[장 제목]'}
        spec['numbering'] = ('roman' if number.endswith('.') else 'roman-bare') if number.strip('.') in ROMAN else 'digit'
        if info.get('table'):
            spec['fitTitleCell'] = True
        return spec

    if chapters:
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
        if role.startswith('heading') and roles[i].get('table'):
            tab = next((j for j in found if roles[j].get('table')), i)  # a number tab: number and title in its cells
            spec.update(range=[tab, tab + 1], kind='heading', level=1, placeholder='[1단계 제목]', numberPlaceholder='[번호]',
                        numbering='digit', fitTitleCell=True, replace={roles[tab]['number']: '[번호]', roles[tab]['title']: '[1단계 제목]'})
        elif role.startswith('heading'):
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
        spec = dict(range=[block_start, end], kind='block', keepFaces=True)  # as the source has it, fonts too
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
            text = info['text'] if info.get('table') else re.sub(NUMBERED_PREFIX[info['role']], '', info['text'])
            node = dict(t='heading', level=int(info['role'][-1]), text=clean(text))
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
    numbers = page_numbers(sections[body_section])
    rules = dict(spacerBeforeLaterChapters=spacer, bodyStartsNewSection=bool(body_section and numbers), deepItemsUnderHeadingLevel=9,
                 pageNumbers=numbers, headingLevelsMaySkip=True)
    if body_section and not numbers:  # no own page numbers to start: the body still begins on a page of its own
        parts['chapter_first']['pageBreakBefore'] = True
    if nodes and nodes[0]['t'] != 'chapter':
        rules['textBeforeFirstChapter'] = True
    if body_section:
        notes.append(f'본문이 {body_section + 1}번째 구역에서 시작합니다. 앞 구역의 표지 뒤 내용은 원본 그대로 블록입니다.')
    part_map = dict(schema='hwpx.assembly-part-map.v1', id=template_id, label=f'등록: {cover_value["title"]}',
                    source=dict(sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(), title=Path(source).name,
                                publisher='', license='사용자 등록', attribution='사용자가 등록한 문서에서 만든 조립 양식'),
                    rules=rules, deepIndentHwp=1000, parts=parts)
    outline = dict(schema='hwpx.assembly-outline.v1', template=template_id, cover=cover_value, nodes=nodes)
    summary = dict(parts=sorted(parts), blocks=sum(n['t'] == 'block' for n in nodes), nodes=len(nodes),
                   chapterNumbers=[chapter_number(i) for i in chapters], squeezedLines=squeezed,
                   roles=dict(Counter(r['role'] for r in roles[cover_end:] if r['role'] != 'empty')), notes=notes)
    return part_map, outline, summary


SCHEDULE_HEADS = ('일정', '기간', '시기', '일시', '날짜', '추진 일정')


def table_roles(rows, shape):
    """What an outline calls a repeating table: schedule when a header names dates, grid otherwise, with the
    header texts as column names, and the item symbol most unit cells of one column start with as its prefix."""
    heads = shape['headerRows']
    header = [flat_text(c) for c in rows[heads - 1]] if heads else []
    names = [re.sub(r'\s+', '', h) for h in header]
    found = dict(role='schedule' if any(any(k.replace(' ', '') in n for k in SCHEDULE_HEADS) for n in names) else 'grid')
    if header and all(header):
        found['columns'] = [re.sub(r'(?<=\S) (?=\S( |$))', '', h) for h in header]  # 기 간 -> 기간
    body = rows[heads:len(rows) - shape.get('footerRows', 0)]
    for column in range(len(body[0]) if body else 0):
        starts = Counter(m.group(0) for row in body if column < len(row) for m in [re.match(r'^[○◦ㅇ∘●◯]', flat_text(row[column]))] if m)
        if starts and starts.most_common(1)[0][1] * 2 > len(body):
            found.update(firstColumnPrefix=starts.most_common(1)[0][0] + ' ', **({'prefixColumn': column} if column else {}))
            break
    return found


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
        spec = dict(headerRows=shape['headerRows'], unitRows=shape['unitRows'], role='grid', keepWrap=True)  # the source's own wrap
        if shape['kind'] == 'repeat' and shape.get('footerRows'):
            spec.update(footerRows=1, footerLabels=shape['footerLabels'])
        if shape['kind'] == 'repeat':
            spec.update(table_roles(rows, shape))
        if shape.get('unitRow'):
            spec['unitRow'] = shape['unitRow']
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
        spec = parts[name]['table']
        if spec.get('firstColumnPrefix'):  # the part draws the symbol; the outline holds the text after it
            column = spec.get('prefixColumn', 0)
            for row in node['rows']:
                if isinstance(row[column], str):
                    row[column] = re.sub(rf'^\s*{re.escape(spec["firstColumnPrefix"].strip())}\s*', '', row[column])
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
    parser.add_argument('--start')
    args = parser.parse_args()
    part_map, outline, summary = propose(Path(args.source).resolve(strict=True), args.id, args.exclude, args.start)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'map.json').write_text(json.dumps(part_map, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'outline.json').write_text(json.dumps(outline, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
