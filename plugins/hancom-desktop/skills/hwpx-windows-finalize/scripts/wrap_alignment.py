"""Measure list-item line positions in a Hangul-exported PDF (common layout rules R1, R4).

R1  a wrapped line starts under the first body character of the item's first line
R4  deeper item levels start further right than their parent level
The structural rules (alignment, one format per level, symbol order) are checked on the
HWPX by hwpx/scripts/layout_rules.py. Findings are warnings for review, not a verdict on
the page; an item that never wraps cannot be checked for R1.

Usage: wrap_alignment.py document.pdf  -> JSON report
"""
from __future__ import annotations

import json
import statistics
import sys

PT_TO_MM = 25.4 / 72
TOLERANCE_MM = 0.6
LEVEL = {'◦': 1, '○': 1, '❍': 1, '•': 1, '-': 2, '–': 2, '⇒': 2, '‧': 3, '·': 3}
# Symbol fonts export ❍ as the letter it is mapped to in Wingdings.
SYMBOL_FONT_LETTERS = {'m': '❍', '': '❍', '': '•'}


def _lines(page):
    out = []
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            chars = [c for span in line['spans'] for c in span['chars']]
            visible = [c for c in chars if not c['c'].isspace()]
            if visible:
                size = max(span['size'] for span in line['spans'])
                out.append({'top': line['bbox'][1], 'bottom': line['bbox'][3], 'chars': chars,
                            'visible': visible, 'size': size, 'text': ''.join(c['c'] for c in chars).strip()})
    return sorted(out, key=lambda line: (round(line['top'], 1), line['visible'][0]['bbox'][0]))


def _marker(line):
    """The item symbol a line starts with, or None."""
    visible, text = line['visible'], line['text']
    first = visible[0]['c']
    symbol = SYMBOL_FONT_LETTERS.get(first, first)
    if symbol not in LEVEL or len(visible) < 2:
        return None
    rest = text[1:]
    if not rest[:1].isspace() and first not in '◦○❍•⇒·‧':
        return None
    if first == 'm' and not ('가' <= rest.strip()[:1] <= '힣'):
        return None  # an ordinary word starting with "m", not the Wingdings ❍
    return symbol


def measure(pdf_path):
    import pymupdf
    items, levels = [], {}
    with pymupdf.open(pdf_path) as document:
        for number, page in enumerate(document, 1):
            lines = _lines(page)
            index = 0
            while index < len(lines):
                line = lines[index]
                symbol = _marker(line)
                if symbol is None:
                    index += 1
                    continue
                marker_x = line['visible'][0]['bbox'][0]
                body_x = line['visible'][1]['bbox'][0]
                levels.setdefault(LEVEL[symbol], []).append(marker_x)
                wraps, previous, follow = [], line, index + 1
                while follow < len(lines):
                    candidate = lines[follow]
                    height = previous['bottom'] - previous['top']
                    if (candidate['top'] - previous['bottom'] > 0.9 * height or candidate['top'] < previous['bottom'] - 1
                            or abs(candidate['size'] - line['size']) > 0.6 or _marker(candidate)
                            or candidate['visible'][0]['bbox'][0] < marker_x - 0.5 / PT_TO_MM):
                        break
                    wraps.append(candidate['visible'][0]['bbox'][0])
                    previous, follow = candidate, follow + 1
                item = {'page': number, 'symbol': symbol, 'level': LEVEL[symbol], 'text': line['text'][:40],
                        'markerMm': round(marker_x * PT_TO_MM, 1), 'bodyMm': round(body_x * PT_TO_MM, 1)}
                if wraps:
                    offset = (wraps[0] - body_x) * PT_TO_MM
                    item.update(lines=1 + len(wraps), wrapMm=round(wraps[0] * PT_TO_MM, 1),
                                offsetMm=round(offset, 1), aligned=abs(offset) <= TOLERANCE_MM)
                items.append(item)
                index = follow
    wrapped = [item for item in items if 'aligned' in item]
    misaligned = [item for item in wrapped if not item['aligned']]
    warnings = [f"[R1] {item['page']}쪽 '{item['symbol']}' 항목의 둘째 줄이 본문 첫 글자보다 {item['offsetMm']:+.1f}mm 어긋남: {item['text']}"
                for item in misaligned]
    medians = {level: statistics.median(xs) for level, xs in levels.items()}
    order = sorted(medians)
    for upper, lower in zip(order, order[1:]):
        if medians[lower] <= medians[upper] + 0.5 / PT_TO_MM:
            warnings.append(f"[R4] {lower}단계 항목이 {upper}단계 항목보다 오른쪽에서 시작하지 않습니다 "
                            f"({medians[lower] * PT_TO_MM:.1f}mm ≤ {medians[upper] * PT_TO_MM:.1f}mm).")
    status = 'WARN' if warnings else ('PASS' if wrapped else 'NOT_CHECKED')
    return {'schema': 'hangul.wrap-alignment.v1', 'status': status, 'items': len(items), 'wrappedItems': len(wrapped),
            'misaligned': len(misaligned), 'toleranceMm': TOLERANCE_MM,
            'levelStartMm': {str(level): round(x * PT_TO_MM, 1) for level, x in sorted(medians.items())},
            'warnings': warnings, 'details': misaligned,
            'note': 'Only items that wrap can be checked for R1; NOT_CHECKED means none wrapped, not a pass.'}


if __name__ == '__main__':
    print(json.dumps(measure(sys.argv[1]), ensure_ascii=False, indent=2))
