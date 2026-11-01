"""Measure page-layout problems in a Hangul-exported PDF (review hints; see hwpx/references/layout-rules.md).

Findings (each with page and example):
  LAST_PAGE_SPARSE  last page holds only a few text lines
  PAGE_GAP          a body page (not the first) leaves a large empty area at the bottom
                    while the next page has content
  TABLE_SPLIT_THIN  a table split across pages leaves 1 data row on one side
  SHORT_TAIL        a wrapped line ends with a fragment of 1-2 characters
  BOLD_MIX          list items of the same symbol differ in weight (whole item bold vs regular)
  HEADING_WRAP      a numbered heading (①, □) wraps back to the left of its text
Thresholds are bench settings, not rules for every document.

Usage: page_layout.py document.pdf [--json]
"""
from __future__ import annotations

import collections
import contextlib
import io
import json
import re
import statistics
import sys

import pymupdf

PT = 25.4 / 72
FOOTER = re.compile(r'^[-–]\s*\d+\s*[-–]$')
ITEM = set('◦○❍-⇒·•m')
HEADING = set('□❑') | {chr(c) for c in range(0x2460, 0x2474)} | {chr(c) for c in range(0xF000, 0xF100)}
LAST_PAGE_MAX_LINES = 3
GAP_RATIO = 0.40
SHORT_TAIL_CHARS = 2


def _stroked(page):
    """Hangul draws bold as the same text filled and then stroked; collect the stroked areas."""
    return [pymupdf.Rect(s['bbox']) for s in page.get_texttrace() if s['type'] == 1]


def _lines(page):
    out = []
    stroked = _stroked(page)
    for block_no, block in enumerate(page.get_text('rawdict')['blocks']):
        for line in block.get('lines', []):
            chars = [c for s in line['spans'] for c in s['chars']]
            visible = [c for c in chars if not c['c'].isspace()]
            if not visible:
                continue
            text = ''.join(c['c'] for c in chars).strip()
            bold = sum(1 for c in visible if any(r.contains(pymupdf.Rect(c['bbox']).tl + (pymupdf.Rect(c['bbox']).br - pymupdf.Rect(c['bbox']).tl) * 0.5) for r in stroked))
            out.append({'block': block_no, 'top': line['bbox'][1], 'bottom': line['bbox'][3], 'x': visible[0]['bbox'][0],
                        'center': (visible[0]['bbox'][0] + visible[-1]['bbox'][2]) / 2,
                        'x2': visible[1]['bbox'][0] if len(visible) > 1 else None, 'text': text, 'size': max(s['size'] for s in line['spans']),
                        'bold': bold / max(1, len(visible)), 'visible': len(visible)})
    return sorted(out, key=lambda l: (round(l['top'], 1), l['x']))


def measure(pdf):
    findings, pages = [], []
    with pymupdf.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            lines = _lines(page)
            footer = [l for l in lines if FOOTER.match(l['text'])]
            body = [l for l in lines if l not in footer]
            drawings = [d['rect'] for d in page.get_drawings() if d['rect'].height < page.rect.height * 0.95]
            bottoms = [l['bottom'] for l in body] + [r.y1 for r in drawings if r.y1 < (footer[0]['top'] if footer else page.rect.height)]
            tops = [l['top'] for l in body] + [r.y0 for r in drawings]
            tables = []
            try:
                with contextlib.redirect_stdout(io.StringIO()):  # PyMuPDF prints a package tip to stdout here
                    found = page.find_tables().tables
                for table in found:
                    tables.append({'top': table.bbox[1], 'bottom': table.bbox[3], 'rows': table.row_count,
                                   'cols': table.col_count, 'x0': table.bbox[0], 'x1': table.bbox[2]})
            except Exception:
                pass
            pages.append({'page': number, 'lines': body, 'top': min(tops) if tops else None, 'bottom': max(bottoms) if bottoms else None,
                          'limit': (footer[0]['top'] if footer else page.rect.height - 15 / PT), 'tables': tables})
    body_top = statistics.median([p['top'] for p in pages if p['top'] is not None] or [0])
    for p in pages:
        p['fill'] = None if p['bottom'] is None else round((p['bottom'] - body_top) / max(1, p['limit'] - body_top), 2)
    last = pages[-1]
    if len(pages) > 1 and len(last['lines']) <= LAST_PAGE_MAX_LINES:
        findings.append({'code': 'LAST_PAGE_SPARSE', 'page': last['page'], 'detail': f"{len(last['lines'])} lines",
                         'example': last['lines'][0]['text'][:30] if last['lines'] else ''})
    for p, nxt in zip(pages[1:-1], pages[2:]):
        if p['fill'] is not None and p['fill'] < 1 - GAP_RATIO and nxt['lines']:
            findings.append({'code': 'PAGE_GAP', 'page': p['page'], 'detail': f"page used to {p['fill']:.0%}", 'example': p['lines'][-1]['text'][:30]})
    for p, nxt in zip(pages, pages[1:]):
        if p['tables'] and nxt['tables']:
            end, start = p['tables'][-1], nxt['tables'][0]
            # Same table continuing: same columns and horizontal extent; a heading bar on the next page is not a continuation.
            same = end['cols'] == start['cols'] and abs(end['x0'] - start['x0']) < 3 / PT and abs(end['x1'] - start['x1']) < 3 / PT
            if same and p['limit'] - end['bottom'] < 25 / PT and start['top'] - body_top < 25 / PT and min(end['rows'], start['rows']) <= 2:
                findings.append({'code': 'TABLE_SPLIT_THIN', 'page': p['page'], 'detail': f"rows {end['rows']} | {start['rows']} on next page"})
    for p in pages:
        by_block = collections.defaultdict(list)
        for line in p['lines']:
            by_block[line['block']].append(line)
        for block in by_block.values():
            for previous, line in zip(block, block[1:]):
                # A wrapped line restarts at (or left of) the previous line's start; neighbouring table cells do not.
                if (line['visible'] <= SHORT_TAIL_CHARS and abs(line['size'] - previous['size']) < 0.6
                        and 0 <= line['top'] - previous['bottom'] < previous['bottom'] - previous['top']
                        and (line['x'] <= previous['x'] + 2 / PT or abs(line['center'] - previous['center']) < 3 / PT)
                        and line['text'][:1] not in ITEM | HEADING | {'⇨', '→'}):
                    findings.append({'code': 'SHORT_TAIL', 'page': p['page'], 'detail': f"'{line['text']}' after '{previous['text'][-12:]}'"})
    items = collections.defaultdict(list)
    for p in pages:
        for line in p['lines']:
            if line['text'][:1] in ITEM and line['text'][1:2].isspace() and line['visible'] > 4:
                items[(line['text'][0], round(line['size']))].append((p['page'], line))
    for (symbol, size), entries in items.items():
        heavy = [e for e in entries if e[1]['bold'] > 0.8]
        light = [e for e in entries if e[1]['bold'] < 0.2]
        if heavy and light:
            odd = heavy if len(heavy) < len(light) else light
            findings.append({'code': 'BOLD_MIX', 'page': odd[0][0], 'detail': f"'{symbol}' items: {len(heavy)} bold, {len(light)} regular",
                             'example': odd[0][1]['text'][:30]})
    for p in pages:
        lines = p['lines']
        for line, nxt in zip(lines, lines[1:]):
            if line['text'][:1] in HEADING and line['x2'] is not None and abs(nxt['size'] - line['size']) < 0.6 \
                    and nxt['text'][:1] not in ITEM | HEADING \
                    and 0 <= nxt['top'] - line['bottom'] < 0.9 * (line['bottom'] - line['top']) and nxt['x'] < line['x2'] - 0.6 / PT:
                findings.append({'code': 'HEADING_WRAP', 'page': p['page'], 'detail': f"wrap at {(nxt['x'] - line['x2']) * PT:+.1f}mm",
                                 'example': line['text'][:30]})
    counts = collections.Counter(f['code'] for f in findings)
    label = {'LAST_PAGE_SPARSE': '마지막 쪽에 몇 줄만 남음', 'PAGE_GAP': '쪽 아래가 크게 비어 있음', 'TABLE_SPLIT_THIN': '표가 쪽 경계에서 1행만 남고 나뉨',
             'SHORT_TAIL': '한두 글자만 다음 줄로 넘어감', 'BOLD_MIX': '같은 기호 항목의 굵기가 섞임', 'HEADING_WRAP': '번호 제목 둘째 줄이 본문 첫 글자보다 왼쪽'}
    warnings = [f"[{f['code']}] {f['page']}쪽 {label[f['code']]}: {f['detail']} {f.get('example', '')}".strip() for f in findings]
    return {'schema': 'hangul.page-layout.v1', 'status': 'WARN' if findings else 'PASS', 'pdf': str(pdf), 'pages': len(pages),
            'fill': [p['fill'] for p in pages], 'counts': dict(counts), 'findings': findings, 'warnings': warnings}


if __name__ == '__main__':
    report = measure(sys.argv[1])
    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"{report['pages']} pages fill={report['fill']} {report['counts']}")
        for f in report['findings']:
            print(f"  p{f['page']} {f['code']:16} {f['detail']} {f.get('example', '')}")
