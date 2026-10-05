import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from hwpx import HwpxDocument
from safe_replace import replace, snapshot


class PreservationTests(unittest.TestCase):
    def test_simple_mixed_nested(self):
        for kind in ('simple', 'mixed', 'nested'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                source, output = Path(tmp)/'in.hwpx', Path(tmp)/'out.hwpx'
                doc = HwpxDocument.new()
                if kind == 'simple':
                    doc.add_paragraph('TARGET_OLD')
                elif kind == 'mixed':
                    p = doc.add_paragraph('', include_run=False)
                    p.add_run('PREFIX', bold=True)
                    p.add_run('TARGET_OLD', italic=True)
                    p.add_run('SUFFIX', underline=True)
                else:
                    host = doc.add_table(1, 1).cell(0, 0)
                    host.set_text('TARGET_OLD')
                    inner = host.add_table(1, 2)
                    inner.set_cell_text(0, 0, 'INNER_KEEP')
                    inner.set_cell_text(0, 1, 'INNER_OTHER')
                doc.add_paragraph('KEEP')
                doc.save_to_path(source)
                doc.close()
                original = source.read_bytes()
                if kind == 'nested':
                    with self.assertRaisesRegex(ValueError, 'nested_text_write_unvalidated'):
                        replace(source, output, 'TARGET_OLD', 'TARGET_NEW')
                    self.assertFalse(output.exists())
                    self.assertEqual(original, source.read_bytes())
                    continue
                result = replace(source, output, 'TARGET_OLD', 'TARGET_NEW')
                self.assertEqual(result['status'], 'PASS_STRUCTURE')
                self.assertEqual(snapshot(source, 'TARGET_OLD', 'TARGET_NEW')[0], snapshot(output)[0])
                self.assertEqual(original, source.read_bytes())

    def test_wrong_ambiguous_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'in.hwpx', Path(tmp)/'out.hwpx'
            doc = HwpxDocument.new()
            doc.add_paragraph('DUP DUP')
            doc.save_to_path(source)
            doc.close()
            for old in ('MISSING', 'DUP'):
                with self.assertRaises(ValueError):
                    replace(source, output, old, 'NEW')
                self.assertFalse(output.exists())
            with self.assertRaises(ValueError):
                replace(source, source, 'DUP', 'NEW')

    def test_changed_non_target_is_not_published(self):
        from hwpx._document.ns.text import TextNamespace
        original_replace = TextNamespace.replace
        def destructive(instance, old, new, **kwargs):
            changed = original_replace(instance, old, new, **kwargs)
            original_replace(instance, 'KEEP', 'LOST')
            return changed
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'in.hwpx', Path(tmp)/'out.hwpx'
            doc = HwpxDocument.new()
            doc.add_paragraph('TARGET')
            doc.add_paragraph('KEEP')
            doc.save_to_path(source)
            doc.close()
            before = source.read_bytes()
            with patch.object(TextNamespace, 'replace', destructive):
                with self.assertRaisesRegex(ValueError, 'preservation mismatch'):
                    replace(source, output, 'TARGET', 'NEW')
            self.assertFalse(output.exists())
            self.assertEqual(before, source.read_bytes())


if __name__ == '__main__':
    unittest.main()
