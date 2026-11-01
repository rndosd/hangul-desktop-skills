"""Layout bench: fill each template with short/medium/long content, export via Hangul, measure.

Usage: run_layout.py SKILLS_DIR VALUES_DIR OUT_DIR
SKILLS_DIR is the installed skills root (the pair hwpx / hwpx-windows-finalize) to test.
Writes OUT_DIR/results.json and one contact sheet per document. Needs Windows Hangul.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'plugins/hancom-desktop/skills/hwpx-windows-finalize/scripts'))
import page_layout as page_metrics  # noqa: E402  (the shipped measurement, used here as the bench's ruler)


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {'status': 'UNPARSED', 'stdout': result.stdout[-600:], 'stderr': result.stderr[-600:]}


def sheet(pdf, target):
    with pymupdf.open(pdf) as src:
        cols = min(src.page_count, 4)
        rows = -(-src.page_count // cols)
        w, h = src[0].rect.width, src[0].rect.height
        out = pymupdf.open()
        page = out.new_page(width=w * cols, height=h * rows)
        for i in range(src.page_count):
            r = pymupdf.Rect((i % cols) * w, (i // cols) * h, (i % cols + 1) * w, (i // cols + 1) * h)
            page.show_pdf_page(r, src, i)
            page.draw_rect(r, color=(0.6, 0.6, 0.6), width=2)
        page.get_pixmap(dpi=min(110, int(1800 / (w * cols / 72)))).save(target)


def main(skills, values, out):
    skills, values, out = Path(skills), Path(values), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    launcher = skills / 'hwpx/scripts/Invoke-HangulTask.ps1'
    native = skills / 'hwpx-windows-finalize/scripts'
    results = []
    for value_file in sorted(values.glob('plan-*.json')):
        name = value_file.stem
        template = '-'.join(name.split('-')[:2])
        hwpx, pdf = out / f'{name}.hwpx', out / f'{name}.pdf'
        record = {'document': name, 'template': template, 'size': name.split('-')[2]}
        fill = run(['powershell.exe', '-NoProfile', '-File', str(launcher), 'fill', '--template', template,
                    '--values', str(value_file), '--output', str(hwpx), '--full-output'])
        record['fill'] = fill.get('status')
        record['layoutRules'] = (fill.get('layoutRules') or {}).get('status')
        if not hwpx.is_file():
            results.append(record)
            continue
        job = run([sys.executable, '-X', 'utf8', '-B', str(native / 'run_native_job.py'), str(hwpx), '--mode', 'OpenOnly',
                   '--pdf', str(pdf), '--run', str(out / f'run-{name}'), '--context', 'ordinary-shell'])
        record['native'] = job.get('status')
        time.sleep(2)  # let Hangul exit before the next job
        if pdf.is_file():
            sys.path.insert(0, str(native))
            from wrap_alignment import measure as wrap
            metrics = page_metrics.measure(pdf)
            wrap_report = wrap(pdf)
            record.update(pages=metrics['pages'], fill_ratio=metrics['fill'], findings=metrics['findings'], counts=metrics['counts'],
                          wrap={k: wrap_report[k] for k in ('status', 'wrappedItems', 'misaligned')})
            sheet(pdf, out / f'{name}.png')
        results.append(record)
        print(json.dumps({k: record.get(k) for k in ('document', 'fill', 'layoutRules', 'native', 'pages', 'counts', 'wrap')}, ensure_ascii=False), flush=True)
    (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main(*sys.argv[1:4])
