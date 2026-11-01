"""safe_rich_table: row clone and content-keeping merge on the bundled mixed-runs fixture (no COM)."""
from pathlib import Path
import json, subprocess, sys, tempfile, unittest, zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/hancom-desktop/skills/hwpx/scripts'
FIXTURE = ROOT / 'plugins/hancom-desktop/skills/hwpx/assets/mixed-runs/source.hwpx'


def run(*args):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(SCRIPTS / 'candidate_runtime.py'), str(SCRIPTS / 'safe_rich_table.py'), *map(str, args)],
                            capture_output=True, text=True, encoding='utf-8')
    return result


def table_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read('Contents/section0.xml').decode('utf-8')
    return xml


class RichTableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        inspection = self.tmp / 'inspect.json'
        self.assertEqual(run('inspect', FIXTURE, '--table', 1, '--output', inspection).returncode, 0)
        self.info = json.loads(inspection.read_text(encoding='utf-8'))

    def apply(self, request):
        request = dict(request, schema='hwpx.rich-table.v1', source_sha256=self.info['source_sha256'], table=1,
                       table_sha256=self.info['table_sha256'], editable_reason='회귀 시험용 표 편집')
        path = self.tmp / 'request.json'
        path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        out = self.tmp / f"{request['operation']}.hwpx"
        result = run('apply', FIXTURE, out, '--request', path)
        return result, out

    def test_clone_after_adds_one_row(self):
        cells = [[[f'추가-{c}' if j == 0 else '' for j, _ in enumerate(p)] for p in cell] for c, cell in enumerate(self.info['rows'][1], 1)]
        result, out = self.apply({'operation': 'clone_after', 'row': 2, 'cells': cells})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('추가-1', table_text(out))
        self.assertIn('rowCnt="4"', table_text(out))

    def test_merge_horizontal_keeps_both_texts(self):
        right = self.info['rows'][1][2][0][0]
        result, out = self.apply({'operation': 'merge_horizontal', 'row': 2, 'columns': [2, 3]})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(right, table_text(out))


if __name__ == '__main__':
    unittest.main(verbosity=2)
