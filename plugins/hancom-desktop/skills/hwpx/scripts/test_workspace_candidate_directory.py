from pathlib import Path
import unittest,sys,uuid
from workspace_candidate_directory import workspace_candidate_directory

class WorkspaceCandidateDirectory(unittest.TestCase):
    def setUp(self):
        self.parent=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
    def test_write_cleanup_and_parent_preserved(self):
        with workspace_candidate_directory(prefix='guard-',dir=self.parent) as folder:
            path=Path(folder);(path/'candidate.hwpx').write_bytes(b'owned synthetic candidate')
            self.assertTrue(path.is_dir());self.assertEqual(path.parent,self.parent)
        self.assertFalse(path.exists());self.assertTrue(self.parent.exists())
    def test_exception_cleanup(self):
        with self.assertRaisesRegex(RuntimeError,'synthetic failure'):
            with workspace_candidate_directory(prefix='guard-',dir=self.parent) as folder:
                path=Path(folder);(path/'candidate.hwpx').write_bytes(b'partial');raise RuntimeError('synthetic failure')
        self.assertFalse(path.exists())
    def test_distinct_overlapping_folders(self):
        with workspace_candidate_directory(prefix='guard-',dir=self.parent) as x:
            with workspace_candidate_directory(prefix='guard-',dir=self.parent) as y:
                self.assertNotEqual(x,y);self.assertTrue(Path(x).is_dir());self.assertTrue(Path(y).is_dir())
            self.assertTrue(Path(x).is_dir())
    def test_reject_path_in_prefix(self):
        for prefix in ['../escape','..\\escape','C:drive','']:
            with self.assertRaises(ValueError):
                with workspace_candidate_directory(prefix=prefix,dir=self.parent):pass
    def test_unknown_file_not_deleted(self):
        unknown=None;folder=None
        try:
            with self.assertRaises(OSError):
                with workspace_candidate_directory(prefix='guard-',dir=self.parent) as folder:
                    unknown=Path(folder)/'keep.txt';unknown.write_text('unexpected data')
            self.assertEqual(unknown.read_text(),'unexpected data')
        finally:
            if unknown and unknown.exists():unknown.unlink()
            if folder and Path(folder).is_dir():Path(folder).rmdir()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceCandidateDirectory))
    sys.exit(0 if result.wasSuccessful() else 1)
