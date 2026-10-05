import tempfile
from pathlib import Path
import unittest
from zipfile import ZipFile
import trace_border_fill_usage as t
import hancom_completion_gate as g


class BorderUseTest(unittest.TestCase):
    def test_renumber_swap_missing_and_changed_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.hwpx', Path(tmp)/'b.hwpx'
            def make(path, ids=('1','2'), swap=False, width='1', missing=False, duplicate=False):
                x,y = ids
                definitions = f'<borderFill id="{x}" width="{width}"><img binaryItemIDRef="a"/></borderFill><borderFill id="{y}"><img binaryItemIDRef="b"/></borderFill>'
                if duplicate: definitions += f'<borderFill id="{x}"/>'
                with ZipFile(path,'w') as z:
                    z.writestr('Contents/content.hpf', '<package><manifest><item id="s" href="Contents/section0.xml"/><item id="a" href="BinData/a"/><item id="b" href="BinData/b"/></manifest><spine><itemref idref="s"/></spine></package>')
                    z.writestr('Contents/header.xml', '<head>'+definitions+f'<charPr id="9" borderFillIDRef="{x}"/><paraPr id="7"><border borderFillIDRef="{y}"/></paraPr></head>')
                    first = 'missing' if missing else (y if swap else x)
                    z.writestr('Contents/section0.xml',f'<section><tbl><tc borderFillIDRef="{first}"/><tc borderFillIDRef="{x if swap else y}"/></tbl><p paraPrIDRef="7"><run charPrIDRef="9"/></p></section>')
                    z.writestr('BinData/a',b'A');z.writestr('BinData/b',b'B')
            make(a)
            make(b,ids=('51','20'))
            self.assertEqual(t.compare(a,b)['status'],'scoped_equal')
            make(b,swap=True)
            self.assertEqual(t.compare(a,b)['changedConsumers'],2)
            make(b,width='99')
            self.assertEqual(t.compare(a,b)['changedConsumers'],2)
            make(b,missing=True)
            with self.assertRaises(g.GateError): t.compare(a,b)
            make(b,duplicate=True)
            with self.assertRaises(g.GateError): t.compare(a,b)


if __name__ == '__main__':
    unittest.main(verbosity=2)
