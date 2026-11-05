"""A PDF name reused after a finished run is cleared; an interrupted run still stops."""
import json
import tempfile
import unittest
from pathlib import Path

import run_native_job as job


class RerunProgressTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pdf = Path(temp.name)/'result.pdf'
        self.progress = Path(str(self.pdf)+'.progress.jsonl')

    def log(self, *rows):
        self.progress.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')

    def test_no_progress_is_left_alone(self):
        self.assertIsNone(job.clear_stale_progress(self.pdf))

    def test_finished_run_is_moved_aside_not_deleted(self):
        self.log({'stage': 'open', 'normalQuit': False}, {'stage': 'quit', 'normalQuit': True})
        kept = Path(job.clear_stale_progress(self.pdf))
        self.assertFalse(self.progress.exists())
        self.assertTrue(kept.exists())
        self.assertIn('normalQuit', kept.read_text(encoding='utf-8'))

    def test_interrupted_run_stops_with_reason(self):
        self.log({'stage': 'hwpx-save-start', 'normalQuit': False}, '{"truncated":')
        with self.assertRaisesRegex(ValueError, 'did not record a normal finish'):
            job.clear_stale_progress(self.pdf)
        self.assertTrue(self.progress.exists())

    def test_cancel_marker_stops(self):
        Path(str(self.progress)+'.cancel').write_text('x', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'interrupted earlier run'):
            job.clear_stale_progress(self.pdf)


if __name__ == '__main__':
    unittest.main()
