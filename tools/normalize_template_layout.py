"""Apply the common layout rules to a prepared template (build tool; not shipped to users).

derive  template.hwpx -> rules.json   one format per level/symbol role, from the template's majority
apply   in.hwpx out.hwpx rules.json   rewrite those roles: items LEFT aligned, one left/hanging/line
                                      spacing/leading-space count per role. Spacing before/after,
                                      borders and every other paragraph setting stay per paragraph.
Hanging values are calibrated by measuring a Hangul PDF with wrap_alignment.py and passing
rules.json back with corrected "hanging" values. Text, runs and fill bindings are untouched
except the spaces before an item symbol.

Template-wide keys, written by hand into rules.json:
  _fontSubstitutes  {"legacy face": "face"}: character formats name that face instead (same
                    language list). Hangul draws Hancom legacy (HFT) faces with a different font
                    on each PC and version, so the symbol width and the calibrated hanging move.
  _wordBreak        {"breakNonLatinWord": "BREAK_WORD", ...}: set on every paragraph format.
                    BREAK_WORD is Hangul's word (어절) wrap; KEEP_WORD splits Korean words.
  _tables[].trimEmptyParagraphs  drop empty paragraphs after a cell's text, so vertically
                    centred cells of one row line up and rows keep only the height they need.
  _tables[].dropFullWidthSpaces  remove full-width space controls left inside placeholders.
  _tables[].useTableMargin  cells drop their own margins and use the table's inner margin.
  _tables[].minimumRowHeightsMm  compact minimum heights; Hangul expands rows for longer content.
  _tables[].verticalAlignment  common cell vertical alignment for that table.
  _tables[].columns {"col": {"align", "hanging", "charPr"}}: one format for that column's body
                    cells (rows from firstBodyRow, default 1).
"""
from __future__ import annotations

import collections
import copy
import json
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/hancom-desktop/skills/hwpx/scripts'))
import layout_rules as rules  # noqa: E402

FIELDS = ('align', 'left', 'intent', 'lineSpacing', 'lead')


def _load(path):
    with zipfile.ZipFile(path) as package:
        infos = package.infolist()
        data = {info.filename: package.read(info) for info in infos}
    return infos, data


def _roles(header, section):
    formats, heights = rules.paragraph_formats(header), rules.char_heights(header)
    out = collections.defaultdict(list)
    for paragraph, text, runs in rules.body_paragraphs(section):
        kind = rules.classify(text)
        if kind is None or not runs:
            continue
        role_kind, symbol, level, lead = kind
        size = heights.get(runs[0].get('charPrIDRef'))
        out[f'{role_kind}|{level}|{symbol}|{size}'].append((paragraph, formats.get(paragraph.get('paraPrIDRef'), {}), lead, runs[0]))
    return out


def derive(path):
    _, data = _load(path)
    header, section = etree.fromstring(data['Contents/header.xml']), etree.fromstring(data['Contents/section0.xml'])
    styles = rules.char_styles(header)
    result = {}
    for role, members in _roles(header, section).items():
        if len(members) < 2 and not role.startswith('item|'):
            continue  # a lone heading has nothing to agree with; a lone item still gets LEFT alignment
        pick = lambda key: collections.Counter(fmt.get(key) for _, fmt, _, _ in members).most_common(1)[0][0]
        symbol_style = collections.Counter(styles[run.get('charPrIDRef')] for *_, run in members).most_common(1)[0][0]
        result[role] = {'align': 'LEFT' if role.startswith('item|') else pick('align'), 'left': pick('left'),
                        'hanging': pick('intent'), 'lineSpacing': pick('lineSpacing'),
                        'lead': collections.Counter(lead for _, _, lead, _ in members).most_common(1)[0][0],
                        'symbolCharPr': next(run.get('charPrIDRef') for *_, run in members if styles[run.get('charPrIDRef')] == symbol_style),
                        'count': len(members)}
    # Item text: one character format per size; regular weight wins, bold stays for inline emphasis.
    heights, candidates = rules.char_heights(header), collections.defaultdict(collections.Counter)
    for role, members in _roles(header, section).items():
        if role.startswith('item|'):
            for paragraph, *_ in members:
                ids = {run.get('charPrIDRef') for run in _content(paragraph)}
                if len({styles[i] for i in ids}) == 1:
                    candidates[heights[next(iter(ids))]][next(iter(ids))] += 1
    for size, counts in candidates.items():
        regular = {i: n for i, n in counts.items() if not styles[i][2]} or dict(counts)
        best_style = collections.Counter({styles[i]: 0 for i in regular})
        for i, n in regular.items():
            best_style[styles[i]] += n
        style = best_style.most_common(1)[0][0]
        result[f'_itemText|{size}'] = {'charPr': next(i for i in regular if styles[i] == style)}
    # A symbol drawn in the text font (◦, -) takes the item text format, so items that keep the symbol
    # in its own run and items that share one run with the text end up identical. Symbol fonts (❍) stay.
    for role, values in result.items():
        text_rule = result.get(f"_itemText|{role.rsplit('|', 1)[1]}") if role.startswith('item|') else None
        if text_rule and styles[values['symbolCharPr']][0] == styles[text_rule['charPr']][0]:
            values['symbolCharPr'] = text_rule['charPr']
    return result


def _content(paragraph):
    runs = [node for node in paragraph if rules._local(node) == 'run' and any(rules._local(t) == 't' and t.text for t in node.iter())]
    return rules.content_runs(runs)


def _empty(paragraph):
    """No text and nothing drawn (table, picture, shape, field or other control)."""
    return not any(rules._local(n) == 't' and n.text for n in paragraph.iter()) and not any(
        rules._local(n) in ('tbl', 'pic', 'ctrl', 'rect', 'line', 'ellipse', 'container', 'equation', 'ole', 'fieldBegin')
        for n in paragraph.iter())


def _set(paraPr, values):
    """Write the given values; keys a rule leaves out keep the paragraph's own setting."""
    for node in paraPr.iter():
        name = rules._local(node)
        if name == 'align' and 'align' in values:
            node.set('horizontal', values['align'])
        elif name == 'lineSpacing' and 'lineSpacing' in values:
            node.set('value', str(values['lineSpacing']))
        elif (name == 'left' and 'left' in values) or (name == 'intent' and 'hanging' in values):
            value = values['left'] if name == 'left' else values['hanging']
            in_default = any(rules._local(a) == 'default' for a in node.iterancestors())
            node.set('value', str(value * 2 if in_default else value))  # legacy default branch uses 2x units


def substitute_fonts(header, substitutes):
    """Character formats that name a face in substitutes name its replacement from the same language list."""
    faces = {node.get('lang').lower(): {font.get('id'): font.get('face') for font in node if rules._local(font) == 'font'}
             for node in header.iter() if rules._local(node) == 'fontface'}
    for ref in (n for n in header.iter() if rules._local(n) == 'fontRef'):
        for slot, font_id in ref.attrib.items():
            face = faces.get(slot, {}).get(font_id)
            if face in substitutes:
                replacement = next((i for i, f in faces[slot].items() if f == substitutes[face]), None)
                if replacement is None:
                    raise ValueError(f'{substitutes[face]} is not in the {slot} font list')
                ref.set(slot, replacement)


def apply(source, target, role_rules):
    infos, data = _load(source)
    header, section = etree.fromstring(data['Contents/header.xml']), etree.fromstring(data['Contents/section0.xml'])
    container = next(n for n in header.iter() if rules._local(n) == 'paraProperties')
    by_id = {node.get('id'): node for node in container if rules._local(node) == 'paraPr'}
    users = collections.Counter(p.get('paraPrIDRef') for p in section.iter() if rules._local(p) == 'p')
    next_id = max(int(i) for i in by_id) + 1
    clones, changed = {}, 0
    styles = rules.char_styles(header)
    for role, members in _roles(header, section).items():
        values = role_rules.get(role)
        if not values:
            continue
        role_users = collections.Counter(p.get('paraPrIDRef') for p, _, _, _ in members)
        text_rule = role_rules.get(f"_itemText|{role.rsplit('|', 1)[1]}") if role.startswith('item|') else None
        for paragraph, fmt, lead, symbol_run in members:
            if styles[symbol_run.get('charPrIDRef')] != styles[values['symbolCharPr']]:
                symbol_run.set('charPrIDRef', values['symbolCharPr'])
            content = _content(paragraph)
            if text_rule and content and content[0] is not symbol_run and len({styles[r.get('charPrIDRef')] for r in content}) == 1:
                for run in content:
                    run.set('charPrIDRef', text_rule['charPr'])
            elif text_rule and content and content[0] is symbol_run and len(content) == 1:
                symbol_run.set('charPrIDRef', text_rule['charPr'])  # symbol and text share one run
            pid = paragraph.get('paraPrIDRef')
            if role_users[pid] == users[pid]:  # used only by this role: edit in place
                _set(by_id[pid], values)
            else:
                key = (role, pid)
                if key not in clones:
                    clone = copy.deepcopy(by_id[pid]); clone.set('id', str(next_id)); _set(clone, values)
                    container.append(clone); clones[key] = str(next_id); next_id += 1
                paragraph.set('paraPrIDRef', clones[key])
            if lead != values['lead']:
                first = next(t for t in paragraph.iter() if rules._local(t) == 't' and t.text and t.text.strip())
                first.text = ' ' * values['lead'] + first.text.lstrip(' 　')
            # Saved line breaks were laid out with the old indent; Hangul reuses them until the
            # paragraph is edited, so drop them and let Hangul lay the paragraph out again.
            for cached in [node for node in paragraph if rules._local(node) == 'linesegarray']:
                paragraph.remove(cached)
            changed += 1
    # Per-table settings: how the table splits at a page boundary and column widths (same total width).
    for spec in role_rules.get('_tables', []):
        table = next((t for t in section.iter() if rules._local(t) == 'tbl' and t.get('id') == spec['id']), None)
        if table is None:
            raise ValueError('table not found: ' + spec['id'])
        if 'pageBreak' in spec:
            table.set('pageBreak', spec['pageBreak'])
        if 'minimumRowHeightsMm' in spec:
            heights = [round(value * 7200 / 25.4) for value in spec['minimumRowHeightsMm']]
            if len(heights) != int(table.get('rowCnt')) or any(value <= 0 for value in heights):
                raise ValueError('minimumRowHeightsMm must match positive table row heights')
            for cell in (n for n in table.iter() if rules._local(n) == 'tc'):
                addr = next(n for n in cell if rules._local(n) == 'cellAddr')
                span = next(n for n in cell if rules._local(n) == 'cellSpan')
                start, count = int(addr.get('rowAddr')), int(span.get('rowSpan'))
                if start + count > len(heights):
                    raise ValueError('cell span exceeds table rows')
                next(n for n in cell if rules._local(n) == 'cellSz').set('height', str(sum(heights[start:start + count])))
            next(n for n in table if rules._local(n) == 'sz').set('height', str(sum(heights)))
            table.set('noAdjust', '0')
        if 'verticalAlignment' in spec:
            if spec['verticalAlignment'] not in ('TOP', 'CENTER', 'BOTTOM'):
                raise ValueError('invalid vertical alignment')
            for cell in (n for n in table.iter() if rules._local(n) == 'tc'):
                next(n for n in cell if rules._local(n) == 'subList').set('vertAlign', spec['verticalAlignment'])
        if 'minimumRowHeightsMm' in spec or 'verticalAlignment' in spec:
            for paragraph in (n for n in table.iter() if rules._local(n) == 'p'):
                for cached in [n for n in paragraph if rules._local(n) == 'linesegarray']:
                    paragraph.remove(cached)
        if 'widths' in spec:
            total = sum(int(next(c for c in tc if rules._local(c) == 'cellSz').get('width'))
                        for tc in next(tr for tr in table if rules._local(tr) == 'tr') if rules._local(tc) == 'tc')
            if sum(spec['widths']) != total:
                raise ValueError(f"widths must keep the table width {total}")
            for tr in (n for n in table if rules._local(n) == 'tr'):
                for tc in (n for n in tr if rules._local(n) == 'tc'):
                    addr = next(c for c in tc if rules._local(c) == 'cellAddr')
                    span = next((c for c in tc if rules._local(c) == 'cellSpan'), None)
                    first, count = int(addr.get('colAddr')), int(span.get('colSpan')) if span is not None else 1
                    next(c for c in tc if rules._local(c) == 'cellSz').set('width', str(sum(spec['widths'][first:first + count])))
            for row in (n for n in table if rules._local(n) == 'tr'):
                for paragraph in row.iter():
                    if rules._local(paragraph) == 'p':
                        for cached in [n for n in paragraph if rules._local(n) == 'linesegarray']:
                            paragraph.remove(cached)
        if spec.get('trimEmptyParagraphs'):
            for cell in (n for n in table.iter() if rules._local(n) == 'subList'):
                paragraphs = [n for n in cell if rules._local(n) == 'p']
                while len(paragraphs) > 1 and _empty(paragraphs[-1]):
                    cell.remove(paragraphs.pop())
        if spec.get('dropFullWidthSpaces'):
            # A full-width space inside a placeholder stays put when the slot is filled: "정　비 완료".
            for space in [n for n in table.iter() if rules._local(n) == 'fwSpace']:
                holder, before = space.getparent(), space.getprevious()
                if before is None:
                    holder.text = (holder.text or '') + (space.tail or '')
                else:
                    before.tail = (before.tail or '') + (space.tail or '')
                holder.remove(space)
        if spec.get('useTableMargin'):
            # Cells with their own tight margins put text against the borders; use the table's inner margin.
            inner = next(n for n in table if rules._local(n) == 'inMargin')
            for cell in (n for n in table.iter() if rules._local(n) == 'tc'):
                cell.set('hasMargin', '0')
                for margin in (n for n in cell if rules._local(n) == 'cellMargin'):
                    margin.attrib.update(inner.attrib)
                for paragraph in (n for n in cell.iter() if rules._local(n) == 'p'):
                    for cached in [n for n in paragraph if rules._local(n) == 'linesegarray']:
                        paragraph.remove(cached)
        for column, values in spec.get('columns', {}).items():
            # Body cells of one column share one paragraph and character format; the header row keeps its own.
            for cell in (n for n in table.iter() if rules._local(n) == 'tc'):
                addr = next(c for c in cell if rules._local(c) == 'cellAddr')
                if addr.get('colAddr') != column or int(addr.get('rowAddr')) < spec.get('firstBodyRow', 1):
                    continue
                for paragraph in (n for n in next(c for c in cell if rules._local(c) == 'subList') if rules._local(n) == 'p'):
                    if 'charPr' in values:
                        for run in (n for n in paragraph if rules._local(n) == 'run'):
                            run.set('charPrIDRef', values['charPr'])
                    key = ('column', spec['id'], column, paragraph.get('paraPrIDRef'))
                    if key not in clones:
                        clone = copy.deepcopy(by_id[paragraph.get('paraPrIDRef')]); clone.set('id', str(next_id)); _set(clone, values)
                        container.append(clone); clones[key] = str(next_id); next_id += 1
                    paragraph.set('paraPrIDRef', clones[key])
                    for cached in [n for n in paragraph if rules._local(n) == 'linesegarray']:
                        paragraph.remove(cached)
    substitutes = role_rules.get('_fontSubstitutes', {})
    substitute_fonts(header, substitutes)
    if role_rules.get('_wordBreak'):
        for setting in (n for n in container.iter() if rules._local(n) == 'breakSetting'):
            for name, value in role_rules['_wordBreak'].items():
                setting.set(name, value)
    if substitutes or role_rules.get('_wordBreak'):
        for paragraph in (n for n in section.iter() if rules._local(n) == 'p'):  # every line may wrap anew
            for cached in [n for n in paragraph if rules._local(n) == 'linesegarray']:
                paragraph.remove(cached)
    container.set('itemCnt', str(len([n for n in container if rules._local(n) == 'paraPr'])))
    data['Contents/header.xml'] = etree.tostring(header, xml_declaration=True, encoding='UTF-8', standalone=True)
    data['Contents/section0.xml'] = etree.tostring(section, xml_declaration=True, encoding='UTF-8', standalone=True)
    with zipfile.ZipFile(target, 'x') as out:
        for info in infos:  # same order and compression; mimetype stays first and stored
            out.writestr(info, data[info.filename])
    return {'paragraphs': changed, 'clonedFormats': len(clones)}


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'derive':
        Path(sys.argv[3]).write_text(json.dumps(derive(sys.argv[2]), ensure_ascii=False, indent=1), encoding='utf-8')
    elif command == 'apply':
        print(json.dumps(apply(sys.argv[2], sys.argv[3], json.loads(Path(sys.argv[4]).read_text(encoding='utf-8'))), ensure_ascii=False))
    else:
        raise SystemExit(__doc__)
