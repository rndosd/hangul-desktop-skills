import tempfile
from pathlib import Path
import unittest
from zipfile import ZipFile
import diagnose_binary_references as d
import hancom_completion_gate as g


class AssetDiagnosisTest(unittest.TestCase):
    def test_classification_and_unchanged_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.hwpx', Path(tmp)/'b.hwpx'
            def make(path, prefix='', asset='A', width='10', rename=False):
                identity = 'renamed' if rename else 'asset'
                with ZipFile(path, 'w') as z:
                    z.writestr('Contents/content.hpf', f'<package><manifest><item id="s" href="Contents/section0.xml"/><item id="{identity}" href="BinData/{identity}.bin"/></manifest><spine><itemref idref="s"/></spine></package>')
                    z.writestr('Contents/section0.xml', f'<section>{prefix}<pic width="{width}"><img binaryItemIDRef="{identity}"/></pic></section>')
                    z.writestr(f'BinData/{identity}.bin', asset.encode())
            make(a)
            for kwargs, expected in [({}, 'identical_owner_subtree_and_path'),
                                     ({'rename': True}, 'identical_owner_subtree_and_path'),
                                     ({'prefix': '<run/>'}, 'identical_owner_subtree_at_different_xml_path'),
                                     ({'width': '20'}, 'owner_subtree_changed'),
                                     ({'asset': 'B'}, 'payload_changed_at_owner_ordinal')]:
                make(b, **kwargs)
                result = d.diagnose(a, b)
                self.assertEqual(result['summary'], {expected: 1})
                self.assertEqual(result['status'], 'diagnostic_only')
            make(b, prefix='<run/>')
            self.assertFalse(g.compare(a, b)['invariants']['binaryReferences'])

    def test_unknown_owner_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'a.hwpx'
            with ZipFile(p, 'w') as z:
                z.writestr('Contents/content.hpf', '<package><manifest><item id="s" href="Contents/section0.xml"/></manifest><spine><itemref idref="s"/></spine></package>')
                z.writestr('Contents/section0.xml', '<section binaryItemIDRef=""/>')
            self.assertEqual(d.diagnose(p, p)['summary'], {'unresolved_owner_or_reference_count': 1})

    def test_multiple_references_and_missing_owner_stay_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.hwpx', Path(tmp)/'b.hwpx'
            def make(path, content):
                with ZipFile(path, 'w') as z:
                    z.writestr('Contents/content.hpf', '<package><manifest><item id="s" href="Contents/section0.xml"/></manifest><spine><itemref idref="s"/></spine></package>')
                    z.writestr('Contents/section0.xml', '<section>'+content+'</section>')
            make(a, '<pic><img binaryItemIDRef=""/><img binaryItemIDRef=""/></pic>')
            make(b, '<pic><img binaryItemIDRef=""/><img binaryItemIDRef=""/></pic>')
            self.assertEqual(d.diagnose(a, b)['summary'], {'unresolved_owner_or_reference_count': 1})
            make(b, '')
            self.assertEqual(d.diagnose(a, b)['summary'], {'unresolved_owner_or_reference_count': 1})


if __name__ == '__main__':
    unittest.main(verbosity=2)
