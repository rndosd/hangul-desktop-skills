"""Common layout rules for list items and numbered headings (structural part).

Rules (references/layout-rules.md):
  R2  list items are LEFT aligned, so justification cannot stretch the space after a symbol
  R3  paragraphs of the same level and symbol share one format (align, left, hanging,
      line spacing, leading spaces, and the symbol run's size, font, character spacing and
      bold). Spacing before/after may differ by
      position, such as the first heading on a page, so it is not compared.
  R5  item symbols follow the level order: circle (1) -> '-' or '⇒' (2) -> '·' (3)
  R6  item text uses one character format per document and size (font, spacing, weight);
      items that bold only some words are inline emphasis and are not compared
  R7  the run that draws an item's or heading's symbol and leading spaces uses no Hancom legacy
      (HFT) font: Hangul replaces those differently by PC and version, which changes the symbol
      width and so breaks the hanging indent
R1 (wrapped lines start under the first body character) and R4 (deeper levels start
further right) need real line positions; hwpx-windows-finalize/scripts/wrap_alignment.py
measures them in the Hangul PDF.

Usage: layout_rules.py document.hwpx  -> JSON report; findings are warnings, not blocks.
"""
from __future__ import annotations

import collections
import json
import sys
import zipfile

from lxml import etree

CIRCLES = set('◦○❍')
LEVEL = {**{c: 1 for c in CIRCLES}, '-': 2, '–': 2, '⇒': 2, '‧': 3, '·': 3, 'ㆍ': 3}
# Hancom private-use circled numbers (U+F02B1..) and ①-⑳ used as numbered sub-headings.
CIRCLED = {chr(c) for c in range(0xF02B1, 0xF02C5)} | {chr(c) for c in range(0x2460, 0x2474)}
ROMAN = tuple('ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ')
# Font slots that draw symbols, spaces and numbers at the start of an item or heading.
PREFIX_SLOTS = ('hangul', 'latin', 'symbol', 'other')
# Symbol-font (Wingdings) code points shown by the glyph they draw.
SHOWN = {'': '❍', '': '•'}


def _local(node):
    return etree.QName(node).localname


def paragraph_formats(header):
    """paraPr id -> format values; the HwpUnitChar case is what current Hangul reads."""
    formats = {}
    for node in header.iter():
        if _local(node) != 'paraPr':
            continue
        values = {'id': node.get('id')}
        for child in node.iter():
            name = _local(child)
            if name == 'align':
                values['align'] = child.get('horizontal')
            elif name in ('intent', 'left', 'prev', 'next') and name not in values:
                values[name] = int(child.get('value'))
            elif name == 'lineSpacing' and 'lineSpacing' not in values:
                values['lineSpacing'] = int(child.get('value'))
        formats[values['id']] = values
    return formats


def char_heights(header):
    return {node.get('id'): int(node.get('height')) for node in header.iter() if _local(node) == 'charPr'}


def char_styles(header):
    """charPr id -> (Hangul font, character spacing, bold) for the run that carries an item's symbol."""
    styles = {}
    for node in header.iter():
        if _local(node) != 'charPr':
            continue
        parts = {_local(child): child for child in node}
        styles[node.get('id')] = (parts['fontRef'].get('hangul') if 'fontRef' in parts else None,
                                  int(parts['spacing'].get('hangul', 0)) if 'spacing' in parts else 0,
                                  'bold' in parts)
    return styles


def legacy_fonts(header):
    """charPr id -> Hancom legacy (HFT) faces in its prefix slots, for the charPrs that have any."""
    faces = {}
    for node in header.iter():
        if _local(node) == 'fontface':
            faces[(node.get('lang') or '').lower()] = {font.get('id'): font.get('face') for font in node
                                                       if _local(font) == 'font' and font.get('type') == 'HFT'}
    legacy = {}
    for node in header.iter():
        if _local(node) != 'charPr':
            continue
        ref = next((child for child in node if _local(child) == 'fontRef'), None)
        names = sorted({faces.get(slot, {}).get(ref.get(slot)) for slot in PREFIX_SLOTS} - {None}) if ref is not None else []
        if names:
            legacy[node.get('id')] = names
    return legacy


def classify(text):
    """(kind, symbol, level, leading spaces) for a paragraph's visible start, or None."""
    stripped = text.lstrip(' 　')
    if not stripped:
        return None
    lead = len(text) - len(stripped)
    first = stripped[0]
    if first in LEVEL and stripped[1:2].isspace():
        return 'item', SHOWN.get(first, first), LEVEL[first], lead
    if first in CIRCLED:
        return 'heading', '①', 0, lead
    if stripped.startswith(ROMAN) and stripped[1:2] == '.':
        return 'heading', 'Ⅰ.', 0, lead
    return None


def content_runs(runs):
    """Runs holding an item's text: a first run that holds only the symbol, and runs of only spaces, are left out."""
    text = lambda run: ''.join(t.text or '' for t in run.iter() if _local(t) == 't')
    rest = runs[1:] if len(runs) > 1 and len(text(runs[0]).strip()) <= 1 else runs
    return [run for run in rest if text(run).strip()] or rest


def body_paragraphs(section):
    """Paragraphs outside tables, in document order, with visible text and first run."""
    for paragraph in section.iter():
        if _local(paragraph) != 'p' or any(_local(a) == 'tc' for a in paragraph.iterancestors()):
            continue
        text = ''.join(node.text or '' for node in paragraph.iter() if _local(node) == 't')
        if text.strip():
            runs = [node for node in paragraph if _local(node) == 'run' and any(_local(t) == 't' and t.text for t in node.iter())]
            yield paragraph, text, runs


def check(path):
    with zipfile.ZipFile(path) as package:
        header = etree.fromstring(package.read('Contents/header.xml'))
        sections = sorted(n for n in package.namelist() if n.startswith('Contents/section') and n.endswith('.xml'))
        trees = [etree.fromstring(package.read(name)) for name in sections]
    formats, heights, styles = paragraph_formats(header), char_heights(header), char_styles(header)
    legacy = legacy_fonts(header)
    legacy_prefixes = collections.defaultdict(list)  # (symbol, faces) -> examples
    roles = collections.defaultdict(list)
    item_text = collections.defaultdict(list)  # size -> [(text format, example)] for items without inline emphasis
    findings = []
    previous_level = 0
    for tree in trees:
        for paragraph, text, runs in body_paragraphs(tree):
            kind = classify(text)
            if kind is None:
                previous_level = 0
                continue
            role_kind, symbol, level, lead = kind
            fmt = formats.get(paragraph.get('paraPrIDRef'), {})
            size = heights.get(runs[0].get('charPrIDRef')) if runs else None
            symbol_run = styles.get(runs[0].get('charPrIDRef'), (None, 0, False)) if runs else (None, 0, False)
            signature = (fmt.get('align'), fmt.get('left'), fmt.get('intent'), fmt.get('lineSpacing'), lead, size, *symbol_run)
            roles[(role_kind, level, symbol, size)].append((signature, text.strip()[:40]))
            if runs and runs[0].get('charPrIDRef') in legacy:
                legacy_prefixes[(symbol, tuple(legacy[runs[0].get('charPrIDRef')]))].append(text.strip()[:40])
            if role_kind == 'item':
                text_formats = {(styles.get(run.get('charPrIDRef')), heights.get(run.get('charPrIDRef'))) for run in content_runs(runs)}
                if len(text_formats) == 1:
                    item_text[size].append((text_formats.pop(), text.strip()[:40]))
                if fmt.get('align') not in ('LEFT', None):
                    findings.append({'rule': 'R2', 'symbol': symbol, 'level': level,
                                     'message': f"목록 항목이 {fmt.get('align')} 정렬입니다. 기호 뒤 간격이 늘어나지 않도록 왼쪽 정렬을 씁니다.",
                                     'example': text.strip()[:40]})
                if level > previous_level + 1:
                    findings.append({'rule': 'R5', 'symbol': symbol, 'level': level,
                                     'message': f"{level}단계 항목('{symbol}')이 바로 위 {level - 1}단계 항목 없이 나옵니다.",
                                     'example': text.strip()[:40]})
                previous_level = level
            else:
                # A circled number heads its own level-1 items, and may carry a '⇒' detail line.
                previous_level = 1 if symbol == '①' else 0
    for (role_kind, level, symbol, size), items in roles.items():
        variants = collections.Counter(signature for signature, _ in items)
        if len(variants) > 1:
            findings.append({
                'rule': 'R3', 'symbol': symbol, 'level': level,
                'message': f"같은 단계의 '{symbol}' {'항목' if role_kind == 'item' else '제목'} {len(items)}개가 서식 {len(variants)}가지를 씁니다.",
                'variants': [{'count': count, 'align': s[0], 'left': s[1], 'hanging': s[2], 'lineSpacing': s[3],
                              'leadingSpaces': s[4], 'size': s[5], 'font': s[6], 'charSpacing': s[7], 'bold': s[8],
                              'example': next(t for sig, t in items if sig == s)}
                             for s, count in variants.most_common()]})
    for size, entries in item_text.items():
        variants = collections.Counter(text_format for text_format, _ in entries)
        if len(variants) > 1:
            findings.append({
                'rule': 'R6', 'symbol': '*', 'level': None,
                'message': f"목록 항목 본문 {len(entries)}개가 글자 서식 {len(variants)}가지(글꼴·자간·굵기)를 씁니다. 강조는 일부 단어에만 씁니다.",
                'variants': [{'count': count, 'font': s[0][0] if s[0] else None, 'charSpacing': s[0][1] if s[0] else None,
                              'bold': s[0][2] if s[0] else None, 'size': s[1],
                              'example': next(t for f, t in entries if f == s)} for s, count in variants.most_common()]})
    for (symbol, faces), examples in legacy_prefixes.items():
        findings.append({'rule': 'R7', 'symbol': symbol, 'level': None, 'count': len(examples), 'fonts': list(faces), 'example': examples[0],
                         'message': f"'{symbol}' 문단 {len(examples)}개의 기호·앞 공백을 한컴 옛 글꼴({', '.join(faces)})로 그립니다. "
                                    "PC·한글 판마다 다른 글꼴로 바뀌어 기호 폭과 내어쓰기 위치가 달라지므로 PC마다 같은 TrueType 글꼴을 씁니다."})
    r2 = [f for f in findings if f['rule'] == 'R2']
    if r2:  # one line per symbol is enough to act on
        seen, kept = set(), []
        for finding in r2:
            if finding['symbol'] not in seen:
                seen.add(finding['symbol'])
                kept.append(dict(finding, count=sum(f['symbol'] == finding['symbol'] for f in r2)))
        findings = [f for f in findings if f['rule'] != 'R2'] + kept
    checked = sum(len(items) for items in roles.values())
    return {'schema': 'hangul.layout-rules.v1', 'status': 'WARN' if findings else 'PASS', 'checkedParagraphs': checked,
            'scope': 'body paragraphs outside tables; R1/R4 need wrap_alignment on the Hangul PDF',
            'warnings': [f"[{f['rule']}] {f['message']} 예: {f.get('example') or f['variants'][0]['example']}" for f in findings],
            'findings': findings}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')  # a Korean Windows console (cp949) cannot print symbols such as ‧
    print(json.dumps(check(sys.argv[1]), ensure_ascii=False, indent=2))
