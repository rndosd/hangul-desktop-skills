"""Build an assembly template from one source HWPX (build tool; also the "register my form" helper).

Input is a part map (tools/assembly-maps/<id>.json): part name -> source paragraph range, kind,
heading level or table columns. Installed Hangul block-saves every range (assembly_native.ps1);
this tool then rewrites each saved part so that no source wording ships:
  fonts        every legacy (HFT) face a character format names becomes TrueType 바탕
  text parts   the text after the leading spaces and symbol becomes one plain run holding the
               part's placeholder, in the character format of the first body character
  item parts   left aligned, plus a "-deep" variant that adds deepIndentHwp to the left margin
               (the source indents items under a level-3 heading by that much). Hangul renders a
               wrapping text in each and the hanging indent is set so wrapped lines start under
               the first body character
  table parts  the header row stays; data rows lose their text and get the first data row's
               height and cell margins, so rows grow only with their new content; the holding
               paragraph gets at least 100% line spacing so the next line clears a grown table
  chapter box  kept with the next paragraph, like headings. Hangul renders calibration strings
               in the box; the measured character advances let the renderer size it to each title
and writes manifest.json (schema hwpx.assembly-template.v1) with file hashes.
Requires Windows, Hangul and the reviewed security module of the installed skill.

Usage: build_assembly_template.py MAP SOURCE.hwpx WORK_DIR [--out DIR]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import statistics
import subprocess
import zipfile
from pathlib import Path

from lxml import etree

from normalize_template_layout import substitute_fonts

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'plugins/hancom-desktop/skills/hwpx/assets/document-templates/assembly'
HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
HC = '{http://www.hancom.co.kr/hwpml/2011/core}'
PREFIX = {'cover': r'\s*', 'chapter_first': r'\s*', 'chapter': r'\s*', 'heading': r'\s*',
          'item': r'\s*◦\s*', 'dash': r'\s*-\s*', 'dot': r'\s*‧\s*', 'note': r'\s*※\s*'}
ITEM_KINDS = ('item', 'dash', 'dot', 'note')
# Short strings stay on one line; every string ends in 가 so its last character has a successor.
CALIBRATION = ['가가0123456789가', '.,·‧()-~/:%「」ㆍ가', 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ가', 'ABCDEFGHIJKLM가',
               'NOPQRSTUVWXYZ가', 'abcdefghijklm가', 'nopqrstuvwxyz가', "&+=[]'\"!?가 가"]
CALIBRATION_BOX_HWP = 46000
WRAP_TEXT = '가나다라마바사 아자차카타 ' * 10
SYMBOL = {'item': '◦', 'dash': '-', 'dot': '‧', 'note': '※'}
TRUETYPE_FACE = '바탕'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def native(plan, work, name):
    plan_path = work / f'{name}.json'
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    argv = ['powershell', '-NoProfile', '-STA', '-File', str(ROOT / 'tools/assembly_native.ps1'), '-PlanPath', str(plan_path)]
    done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8-sig', errors='replace')
    (work / f'{name}.result.json').write_text(done.stdout + done.stderr, encoding='utf-8')
    need(done.returncode == 0, f'Hangul step {name} failed: {done.stdout[-600:]} {done.stderr[-600:]}')


def text_of(element):
    return ''.join(t.text or '' for t in element.iter(HP + 't'))


def set_placeholder(paragraph, pattern, placeholder):
    """Keep the leading prefix runs; the body becomes one run holding the placeholder."""
    pieces = [(run, t) for run in paragraph.findall(HP + 'run') for t in run.findall(HP + 't')]
    full = ''.join(''.join(t.itertext()) for _, t in pieces)
    start = re.match(pattern, full).end()
    need(full[start:].strip(), f'no body text after the prefix: {full!r}')
    offset, placed = 0, False
    for run, t in pieces:
        text = ''.join(t.itertext())
        if placed:
            run.remove(t)
            if len(run) == 0:
                run.getparent().remove(run)
        elif offset + len(text) > start:
            need(len(t) == 0, f'inline control inside the prefix run: {full!r}')
            t.text = text[:start - offset] + placeholder
            if start == offset and start:
                # Hangul inserts replacement text in the format of the character before the
                # selection, so the last prefix character moves into the placeholder's run.
                before = next(piece for piece in reversed(pieces[:pieces.index((run, t))]) if piece[1].text)[1]
                before.text, t.text = before.text[:-1], before.text[-1] + t.text
            placed = True
        offset += len(text)
    for lines in paragraph.findall(HP + 'linesegarray'):
        paragraph.remove(lines)
    return full


def shape_of(header, section, paragraph):
    """The paragraph format of a part paragraph; the block-save trailer paragraph must not share it."""
    pid = paragraph.get('paraPrIDRef')
    need(section.findall(HP + 'p')[-1].get('paraPrIDRef') != pid or section.findall(HP + 'p')[-1] is paragraph, f'paragraph format {pid} is shared with the trailer')
    return header.find(f'.//{HH}paraPr[@id="{pid}"]')


def margin(header, section, paragraph, name, value=None):
    """Read or set one paragraph margin (left, intent) of a paragraph format used only by this paragraph."""
    pid = paragraph.get('paraPrIDRef')
    need(sum(p.get('paraPrIDRef') == pid for p in section.iter(HP + 'p')) == 1, f'paragraph format {pid} is shared')
    shape = shape_of(header, section, paragraph)
    if value is None:
        return int(shape.find(f'.//{HP}case/{HH}margin/{HC}{name}').get('value'))
    for branch, scale in (('case', 1), ('default', 2)):  # the compatibility branch stores doubled values
        shape.find(f'.//{HP}{branch}/{HH}margin/{HC}{name}').set('value', str(value * scale))


def normalize_table(section, spec):
    table = next(section.iter(HP + 'tbl'))
    rows = table.findall(HP + 'tr')
    need(len(rows[0].findall(HP + 'tc')) == spec['cols'], 'table column count differs from the part map')
    first = rows[1].findall(HP + 'tc')
    height = int(first[0].find(HP + 'cellSz').get('height'))
    header = [text_of(cell) for cell in rows[0].findall(HP + 'tc')]
    for row in rows[1:]:
        for column, cell in enumerate(row.findall(HP + 'tc')):
            model = first[column]
            cell.set('hasMargin', model.get('hasMargin'))
            cell.replace(cell.find(HP + 'cellMargin'), copy.deepcopy(model.find(HP + 'cellMargin')))
            cell.find(HP + 'cellSz').set('height', str(height))
            sub = cell.find(HP + 'subList')
            sub.set('vertAlign', model.find(HP + 'subList').get('vertAlign'))
            paragraphs = sub.findall(HP + 'p')
            for extra in paragraphs[1:]:
                sub.remove(extra)
            keep = paragraphs[0]
            runs = keep.findall(HP + 'run')
            for child in list(keep):
                if child is not runs[0]:
                    keep.remove(child)
            for child in list(runs[0]):
                runs[0].remove(child)
    table.find(HP + 'sz').set('height', str(int(rows[0].find(HP + 'tc/' + HP + 'cellSz').get('height')) + height * (len(rows) - 1)))
    table.set('rowCnt', str(len(rows)))
    return dict(dataRows=len(rows) - 1, cols=spec['cols'], header=header, rowHeightHwp=height,
                **({'firstColumnPrefix': spec['firstColumnPrefix']} if spec.get('firstColumnPrefix') else {}))


def blank_png():
    import pymupdf
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), 0)
    pixmap.clear_with(255)
    return pixmap.tobytes('png')


def write_part(raw, target, section, header, preview=None):
    with zipfile.ZipFile(raw) as package:
        infos = package.infolist()
        data = {info.filename: package.read(info) for info in infos}
    data['Contents/section0.xml'] = etree.tostring(section, xml_declaration=True, encoding='UTF-8', standalone=True)
    data['Contents/header.xml'] = etree.tostring(header, xml_declaration=True, encoding='UTF-8', standalone=True)
    hpf = data['Contents/content.hpf'].decode('utf-8')
    hpf = re.sub(r'<opf:title[^>]*?(?:/>|>.*?</opf:title>)', '<opf:title/>', hpf, flags=re.S)
    hpf = re.sub(r'(<opf:meta name="(?:creator|lastsaveby)" content="text">)[^<]*', r'\1', hpf)
    data['Contents/content.hpf'] = hpf.encode('utf-8')
    if preview is not None:
        data['Preview/PrvText.txt'] = preview.encode('utf-8')
    data['Preview/PrvImage.png'] = blank_png()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, 'w') as out:
        for info in infos:
            out.writestr(info, data[info.filename])


def load(raw):
    with zipfile.ZipFile(raw) as package:
        return etree.fromstring(package.read('Contents/section0.xml')), etree.fromstring(package.read('Contents/header.xml'))


def body_paragraphs(section):
    return [p for p in section.findall(HP + 'p') if text_of(p).strip()]


def use_truetype_faces(header, section):
    """Every Hancom legacy (HFT) face a character format names becomes TrueType 바탕: Hangul draws HFT
    faces with a different font on each PC and version, which moves symbol widths and hanging indents."""
    legacy = set()
    for fontface in header.iter(HH + 'fontface'):
        fonts = fontface.findall(HH + 'font')
        legacy |= {f.get('face') for f in fonts if f.get('type') == 'HFT'
                   and any(ref.get(fontface.get('lang').lower()) == f.get('id') for ref in header.iter(HH + 'fontRef'))}
        if not any(f.get('face') == TRUETYPE_FACE and f.get('type') == 'TTF' for f in fonts):
            font = etree.SubElement(fontface, HH + 'font', id=str(max(int(f.get('id')) for f in fonts) + 1), face=TRUETYPE_FACE, type='TTF', isEmbedded='0')
            etree.SubElement(font, HH + 'typeInfo', familyType='FCAT_GOTHIC', weight='6', proportion='0', contrast='0',
                             strokeVariation='1', armStyle='1', letterform='1', midline='1', xHeight='1')
            fontface.set('fontCnt', str(len(fonts) + 1))
    substitute_fonts(header, dict.fromkeys(legacy, TRUETYPE_FACE))
    for paragraph in section.iter(HP + 'p'):  # saved line breaks were laid out with the old faces
        for lines in paragraph.findall(HP + 'linesegarray'):
            paragraph.remove(lines)


def prepare(name, spec, raw, out_dir, deep_indent):
    section, header = load(raw)
    use_truetype_faces(header, section)
    kind, entry, previews, variants = spec['kind'], {'kind': spec['kind']}, [], []
    if kind == 'cover':
        top = section.findall(HP + 'p')
        entry['placeholder'] = {}
        for field, place in spec['fields'].items():
            if 'copyOf' in place:
                need(not text_of(top[place['paragraph']]).strip(), f'cover paragraph {place["paragraph"]} is not empty')
                clone = copy.deepcopy(top[place['copyOf']])
                set_placeholder(clone, PREFIX[kind], place['placeholder'])
                section.replace(top[place['paragraph']], clone)
            else:
                set_placeholder(top[place['paragraph']], PREFIX[kind], place['placeholder'])
            entry['placeholder'][field] = place['placeholder']
            previews.append(place['placeholder'])
    elif kind in ('chapter_first', 'chapter'):
        box = next(section.iter(HP + 'container'))
        title = next(p for p in box.iter(HP + 'p') if text_of(p).strip())
        original = set_placeholder(title, PREFIX[kind], spec['placeholder']).strip()
        need(original == spec['expect'], f'{name}: box title {original!r} differs from the map')
        page = next(section.iter(HP + 'pagePr'))
        page_margin = page.find(HP + 'margin')
        entry.update(placeholder=spec['placeholder'], numbering='roman',
                     box={'sourceTitle': original, 'sourceWidthHwp': int(box.find(HP + 'sz').get('width')),
                          # Resizing the group scales its framed rectangle and shadow offset together.
                          'frameRatio': round(int(next(r for r in box.iter(HP + 'rect') if r.find(HP + 'drawText') is not None).find(HP + 'curSz').get('width'))
                                              / int(box.find(HP + 'sz').get('width')), 5),
                          'maxWidthHwp': int(page.get('width')) - int(page_margin.get('left')) - int(page_margin.get('right'))})
        previews.append(spec['placeholder'])
        for paragraph in section.findall(HP + 'p')[:-1]:  # the box stays on the page of its first heading
            shape_of(header, section, paragraph).find(HH + 'breakSetting').set('keepWithNext', '1')
    elif kind == 'heading' or kind in ITEM_KINDS:
        paragraphs = body_paragraphs(section)
        need(len(paragraphs) == 1, f'{name}: one text paragraph expected, found {len(paragraphs)}')
        set_placeholder(paragraphs[0], PREFIX[kind], spec['placeholder'])
        if spec.get('symbol'):
            prefix = next(t for t in paragraphs[0].iter(HP + 't') if t.text and SYMBOL[kind] in t.text)
            prefix.text = prefix.text.replace(SYMBOL[kind], spec['symbol'], 1)
            entry['symbol'] = spec['symbol']
        entry['placeholder'] = spec['placeholder']
        previews.append(spec['placeholder'])
        shape = shape_of(header, section, paragraphs[0])
        if kind == 'heading':
            entry.update(level=spec['level'], numbering={1: 'decimal', 2: 'hangul', 3: 'paren'}[spec['level']])
            shape.find(HH + 'breakSetting').set('keepWithNext', '1')
        else:
            shape.find(HH + 'align').set('horizontal', 'LEFT')  # justified lines widen the space after the symbol
            margin(header, section, paragraphs[0], 'left', spec['baseLeftHwp'])
            entry['depth'] = 0
            deep_section, deep_header = copy.deepcopy(section), copy.deepcopy(header)
            margin(deep_header, deep_section, body_paragraphs(deep_section)[0], 'left', spec['baseLeftHwp'] + deep_indent)
            variants.append((f'{name}-deep', dict(entry, depth=1), deep_section, deep_header))
    elif kind == 'spacer':
        need(not body_paragraphs(section), 'spacer part must be empty')
    elif kind == 'table':
        entry['table'] = normalize_table(section, spec['table'])
        holder = next(p for p in section.findall(HP + 'p') if p.find(f'.//{HP}tbl') is not None)
        for spacing in shape_of(header, section, holder).iter(HH + 'lineSpacing'):
            if spacing.get('type') == 'PERCENT' and int(spacing.get('value')) < 100:
                spacing.set('value', '100')  # below 100% the next line overlaps a table that grew
        previews.extend(entry['table']['header'])
    else:
        raise ValueError(f'unknown kind {kind}')
    written = []
    for part_name, part_entry, part_section, part_header in [(name, entry, section, header), *variants]:
        target = out_dir / 'parts' / f'{part_name}.hwpx'
        write_part(raw, target, part_section, part_header, '\n'.join(previews))
        written.append((part_name, dict(part_entry, file=f'parts/{part_name}.hwpx', sha256=sha(target))))
    return written


def leftover_wording(path, allowed):
    """Text of a prepared part (body, preview text, title metadata) that is neither a placeholder,
    an allowed header nor symbols/spaces."""
    section, _ = load(path)
    with zipfile.ZipFile(path) as package:
        hpf = package.read('Contents/content.hpf').decode('utf-8')
        preview = package.read('Preview/PrvText.txt').decode('utf-8')
    text = ''.join(t.text or '' for t in section.iter(HP + 't')) + preview + ''.join(re.findall(r'<opf:title[^>]*>(.*?)</opf:title>', hpf, re.S))
    for value in sorted(allowed, key=len, reverse=True):
        text = text.replace(value, '')
    return re.sub(r'[\s◦○\-‧※·]', '', text)


def measure_advances(pdf, expected):
    """Pen distance from each visible calibration character to the next; keys keep any spaces between."""
    import pymupdf
    with pymupdf.open(pdf) as document:
        chars = [c for block in document[0].get_text('rawdict')['blocks'] for line in block.get('lines', [])
                 for span in line['spans'] for c in span['chars'] if not c['c'].isspace()]
    need(''.join(c['c'] for c in chars) == expected.replace(' ', ''), f'calibration text differs in {pdf}')
    need(len({round(c['origin'][1], 1) for c in chars}) == 1, f'calibration text wrapped in {pdf}')
    visible = [i for i, c in enumerate(expected) if c != ' ']
    return [(expected[i:j], b['origin'][0] - a['origin'][0]) for i, j, a, b in zip(visible, visible[1:], chars, chars[1:])]


def wrap_offset(pdf, symbol):
    """Body start minus wrapped-line start (pt) of the first item; zero means the wrap sits under the body."""
    import pymupdf
    rows = {}
    with pymupdf.open(pdf) as document:
        for block in document[0].get_text('rawdict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    for c in span['chars']:
                        if not c['c'].isspace():
                            rows.setdefault(round(c['origin'][1]), []).append(c)
    lines = [sorted(rows[y], key=lambda c: c['bbox'][0]) for y in sorted(rows)]
    first = next(i for i, line in enumerate(lines) if line[0]['c'] == symbol)
    need(first + 1 < len(lines), f'calibration text did not wrap in {pdf}')
    return lines[first][1]['bbox'][0] - lines[first + 1][0]['bbox'][0]


def calibrate_hanging(parts, out_dir, work):
    """Set each item part's hanging indent so wrapped lines start under the first body character."""
    items = {name: entry for name, entry in parts.items() if entry['kind'] in ITEM_KINDS and entry['depth'] == 0}
    for attempt in range(2):
        renders = [dict(part=str(out_dir / entry['file']), find=entry['placeholder'], text=WRAP_TEXT,
                        pdf=str(work / f'hanging-{attempt}-{name}.pdf')) for name, entry in items.items()]
        native(dict(renders=renders), work, f'hanging-{attempt}')
        offsets = {name: wrap_offset(work / f'hanging-{attempt}-{name}.pdf', entry.get('symbol', SYMBOL[entry['kind']])) for name, entry in items.items()}
        if attempt:
            return {name: round(offset * 25.4 / 72, 2) for name, offset in offsets.items()}
        for name, offset in offsets.items():
            for variant in (name, f'{name}-deep'):
                path = out_dir / parts[variant]['file']
                section, header = load(path)
                paragraph = body_paragraphs(section)[0]
                margin(header, section, paragraph, 'intent', margin(header, section, paragraph, 'intent') - round(offset * 100))
                write_part(path, path, section, header)
                parts[variant]['sha256'] = sha(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('map'); parser.add_argument('source'); parser.add_argument('work'); parser.add_argument('--out')
    args = parser.parse_args()
    part_map = json.loads(Path(args.map).read_text(encoding='utf-8'))
    need(part_map.get('schema') == 'hwpx.assembly-part-map.v1', 'unsupported part map schema')
    source = Path(args.source).resolve(strict=True)
    need(sha(source) == part_map['source']['sha256'], 'source file differs from the part map hash')
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    out_dir = Path(args.out).resolve() if args.out else TEMPLATES / part_map['id']
    need(not (out_dir / 'manifest.json').exists() or args.out, f'{out_dir} exists; pass --out to rebuild elsewhere')
    raw_dir = work / 'raw'
    raw_dir.mkdir()
    blocks = [dict(name=name, start=spec['range'][0], end=spec['range'][1], path=str(raw_dir / f'{name}.hwpx'),
                   **({'check': spec['check']} if 'check' in spec else {})) for name, spec in part_map['parts'].items()]
    native(dict(source=str(source), blocks=blocks, renders=[]), work, 'save-blocks')

    parts = {}
    for name, spec in part_map['parts'].items():
        parts.update(prepare(name, spec, raw_dir / f'{name}.hwpx', out_dir, part_map['deepIndentHwp']))
    for name, entry in parts.items():
        placeholders = entry.get('placeholder', {})
        allowed = list(placeholders.values()) if isinstance(placeholders, dict) else [placeholders]
        left = leftover_wording(out_dir / entry['file'], allowed + entry.get('table', {}).get('header', []))
        need(not left, f'{name}: source wording left in the prepared part: {left[:60]!r}')

    residual = calibrate_hanging(parts, out_dir, work)
    need(all(abs(value) <= 0.3 for value in residual.values()), f'hanging calibration did not converge: {residual}')
    renders = [dict(part=str(out_dir / entry['file']), find=entry['placeholder'], text=text, boxWidth=CALIBRATION_BOX_HWP,
                    pdf=str(work / f'calibrate-{name}-{index}.pdf'))
               for name, entry in parts.items() if 'box' in entry for index, text in enumerate(CALIBRATION)]
    native(dict(renders=renders), work, 'calibrate')
    for name, entry in parts.items():
        if 'box' not in entry:
            continue
        samples = {}
        for index, text in enumerate(CALIBRATION):
            for char, advance in measure_advances(work / f'calibrate-{name}-{index}.pdf', text):
                samples.setdefault(char, []).append(advance)
        advances = {char: round(statistics.median(values), 2) for char, values in sorted(samples.items()) if len(char) == 1}
        advances[' '] = round(statistics.median(samples['가 ']) - advances['가'], 2)
        need(all(char in advances or '가' <= char <= '힣' for char in entry['box']['sourceTitle']), f'{name}: calibration misses a source title character')
        entry['box'].update(advancePt=advances, fallbackAdvancePt=advances['가'])

    manifest = {'schema': 'hwpx.assembly-template.v1', 'id': part_map['id'], 'label': part_map['label'],
                'source': part_map['source'],
                'rules': {'spacerBeforeLaterChapters': True, 'bodyStartsNewSection': True,
                          'pageNumbers': {'position': 'BottomCenter', 'format': 'Digit', 'sideChar': '-'},
                          'deepItemsUnderHeadingLevel': 3, 'deepIndentHwp': part_map['deepIndentHwp']},
                'parts': parts}
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'BUILT', 'manifest': str(out_dir / 'manifest.json'), 'parts': sorted(parts),
                      'wrapResidualMm': residual}, ensure_ascii=False))


if __name__ == '__main__':
    main()
