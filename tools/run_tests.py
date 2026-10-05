"""Focused release tests: pure HWPX guards and per-PC configuration. No COM."""
from pathlib import Path
import subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'plugins/hancom-desktop/skills/hwpx'
commands=[
    [sys.executable,'-X','utf8','-B',str(ROOT/'tests/test_configuration_pair.py')],
    [sys.executable,'-X','utf8','-B',str(ROOT/'tests/test_portable_font.py')],
    [sys.executable,'-X','utf8','-B',str(SKILL/'tests/test_common_task_entry.py')],
    [sys.executable,'-X','utf8','-B',str(SKILL/'scripts/candidate_runtime.py'),str(SKILL/'scripts/test_safe_replace.py')],
]
for argv in commands:
    result=subprocess.run(argv,cwd=ROOT)
    if result.returncode:raise SystemExit(result.returncode)
