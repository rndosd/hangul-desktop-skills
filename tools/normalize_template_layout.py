"""Apply the common layout rules to a prepared template (build tool; not shipped to users).

derive  template.hwpx -> rules.json   one format per level/symbol role, from the template's majority
apply   in.hwpx out.hwpx rules.json   rewrite those roles: items LEFT aligned, one left/hanging/line
                                      spacing/leading-space count per role. Spacing before/after,
                                      borders and every other paragraph setting stay per paragraph.
Hanging values are calibrated by measuring a Hangul PDF with wrap_alignment.py and passing
rules.json back with corrected "hanging" values. Text, runs and fill bindings are untouched
except the spaces before an item symbol.
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


def _set(paraPr, values):
    for node in paraPr.iter():
        name = rules._local(node)
        if name == 'align':
            node.set('horizontal', values['align'])
        elif name == 'lineSpacing':
            node.set('value', str(values['lineSpacing']))
        elif name in ('left', 'intent'):
            value = values['left'] if name == 'left' else values['hanging']
            in_default = any(rules._local(a) == 'default' for a in node.iterancestors())
            node.set('value', str(value * 2 if in_default else value))  # legacy default branch uses 2x units


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
