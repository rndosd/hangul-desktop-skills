"""Register the fixed regression documents (README.md, part 2) one by one and print one table.

Usage: run_registrations.py SOURCE_DIR WORK_DIR
SOURCE_DIR holds the files named in README.md; a missing file is listed as skipped. WORK_DIR must be new.
Requires Windows, Hangul and the installed skill's environment, like the register command itself.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[2] / 'plugins/hancom-desktop/skills/hwpx/scripts/Invoke-HangulTask.ps1'
DOCUMENTS = [  # (file, template id, start text)
    ('gne-space.hwpx', 'gne-space', None),
    ('gg-exchange.hwpx', 'gg-exchange', None),
    ('labor-survey.hwpx', 'labor-survey', '실태조사 주요 결과'),
    ('youth-forum.hwpx', 'youth-forum', '포럼 개최 계획'),
    ('export-visit.hwpx', 'export-visit', '현장방문 개요'),
    ('csat-plan.hwpx', 'csat-plan', None),
]


def main():
    sources, work = Path(sys.argv[1]), Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, template_id, start in DOCUMENTS:
        if not (sources / name).is_file():
            rows.append(dict(file=name, status='SKIPPED'))
            continue
        began = time.time()
        argv = ['powershell', '-NoProfile', '-File', str(LAUNCHER), 'register', str(sources / name), '--id', template_id,
                '--work', str(work / template_id), *(['--start', start] if start else [])]
        done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8-sig', errors='replace')
        try:
            result = json.loads(done.stdout)
        except json.JSONDecodeError:
            result = dict(status='FAIL_RUN', reason=(done.stdout + done.stderr)[-300:])
        rows.append(dict(file=name, status=result.get('status'), minutes=round((time.time() - began) / 60, 1),
                         problems=result.get('problems') or ([result['reason']] if result.get('reason') else []),
                         tables=len(result.get('canUse', {}).get('tables', [])), blocks=result.get('sourceWording', {}).get('blocks')))
    (work / 'summary.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    for row in rows:
        print(f"{row['file']:<20} {row['status']:<12} {row.get('minutes', ''):>5}분  표 {row.get('tables', '-')}  블록 {row.get('blocks', '-')}  "
              + '; '.join(row.get('problems', [])))
    return 0 if all(r['status'] in ('REGISTERED', 'SKIPPED') for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
