"""fill: long plans split into ordered batches without separating a command from one that uses its result."""
from pathlib import Path
import sys, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/hancom-desktop/skills/hwpx/scripts'))
from fill_template import _dependency_safe_chunks as chunks


def cmd(n, ref=None):
    c = {'commandId': f'fill-{n}', 'op': 'set', 'path': f'/p[{n}]'}
    if ref is not None:
        c['target'] = f'$fill-{ref}.path'
    return c


class FillBatchTest(unittest.TestCase):
    def test_plain_commands_split_by_limit(self):
        self.assertEqual(chunks([cmd(i) for i in range(1, 251)], 100), [(0, 100), (100, 200), (200, 250)])

    def test_reference_keeps_pair_together(self):
        commands = [cmd(i) for i in range(1, 100)] + [cmd(100), cmd(101, ref=100)] + [cmd(i) for i in range(102, 120)]
        result = chunks(commands, 100)
        start = next(s for s, e in result if s <= 99 < e)
        self.assertTrue(start <= 99 and next(e for s, e in result if s <= 99 < e) > 100)
        self.assertTrue(all(e - s <= 100 for s, e in result))

    def test_unsplittable_returns_none(self):
        commands = [cmd(1)] + [cmd(i, ref=1) for i in range(2, 12)]
        self.assertIsNone(chunks(commands, 5))


if __name__ == '__main__':
    unittest.main(verbosity=2)
