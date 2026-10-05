import tempfile
import unittest
from pathlib import Path
from hwpx import HwpxDocument
from diagnose_edit import diagnose


class RouteTests(unittest.TestCase):
    def test_nested_write_blocked_for_all_text_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'sample.hwpx'
            doc = HwpxDocument.new()
            doc.add_paragraph('BODY_UNIQUE')
            host = doc.add_table(1, 1).cell(0, 0)
            host.set_text('HOST_UNIQUE')
            host.add_table(1, 1).cell(0, 0).set_text('INNER_UNIQUE')
            doc.save_to_path(p)
            doc.close()
            for operation in ('replace_text', 'set_cell_text'):
                for find in ('HOST_UNIQUE', 'INNER_UNIQUE'):
                    self.assertEqual(diagnose(p, operation, find)['decision'], 'BLOCK')
            d = diagnose(p, 'replace_text', 'BODY_UNIQUE')
            self.assertEqual(d['route'], 'safe_replace.py')
            self.assertEqual(d['structure']['nested_tables'], 1)
            self.assertEqual(d['structure']['max_table_depth'], 2)
            self.assertEqual(diagnose(p, 'replace_text', 'ABSENT')['decision'], 'BLOCK')
            self.assertEqual(diagnose(p, 'paragraph_alignment', 'INNER_UNIQUE')['decision'], 'REQUIRES_NATIVE_TARGET_CHECK')

    def test_too_many_tables_not_native_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'sample.hwpx'
            doc = HwpxDocument.new()
            for i in range(3):
                doc.add_table(1, 1).cell(0, 0).set_text('CELL_'+str(i))
            doc.save_to_path(p)
            doc.close()
            self.assertEqual(diagnose(p, 'paragraph_alignment', 'CELL_0')['decision'], 'BLOCK')


if __name__ == '__main__':
    unittest.main()
