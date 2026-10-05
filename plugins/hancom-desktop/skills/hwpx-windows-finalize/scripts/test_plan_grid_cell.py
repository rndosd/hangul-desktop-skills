import tempfile
from pathlib import Path
import unittest
from xml.etree import ElementTree as E
from zipfile import ZipFile
import plan_grid_cell as p
import hancom_completion_gate as g


def table():
    return E.fromstring('<tbl id="7" rowCnt="2" colCnt="3"><tr>'
      '<tc><subList><p><t>A</t></p></subList><cellAddr rowAddr="0" colAddr="0"/><cellSpan rowSpan="2" colSpan="1"/></tc>'
      '<tc><subList><p><t>B</t></p></subList><cellAddr rowAddr="0" colAddr="1"/><cellSpan rowSpan="1" colSpan="2"/></tc>'
      '</tr><tr><tc><subList><p><t>C</t></p></subList><cellAddr rowAddr="1" colAddr="1"/><cellSpan rowSpan="1" colSpan="1"/></tc>'
      '<tc><subList><p><t>D</t></p></subList><cellAddr rowAddr="1" colAddr="2"/><cellSpan rowSpan="1" colSpan="1"/></tc></tr></tbl>')


class GridPlanTest(unittest.TestCase):
    def test_merged_ownership_and_row_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.hwpx'
            with ZipFile(path,'w') as z:
                z.writestr('Contents/content.hpf','<package><manifest><item id="s" href="Contents/section0.xml"/></manifest><spine><itemref idref="s"/></spine></package>')
                z.writestr('Contents/section0.xml','<sec>'+E.tostring(table(),encoding='unicode')+'</sec>')
            merged=p.plan(path,1,1,3)
            self.assertEqual(merged['ownerCell']['column'],2)
            self.assertEqual(merged['actions'],['TableRightCell'])
            down=p.plan(path,1,2,2)
            self.assertEqual(down['actions'],['TableRightCell','TableLowerCell'])
            self.assertEqual([c['text'] for c in down['route']],['A','B','C'])
            self.assertEqual(p.plan(path,1,2,1)['actions'],[])
            with self.assertRaises(g.GateError):p.plan(path,1,3,1)

    def test_overlap_gap_and_out_of_bounds_block(self):
        for kind in ('overlap','gap','outside'):
            t=table();span=t.find('tr/tc/cellSpan')
            if kind=='overlap':span.set('colSpan','2')
            elif kind=='gap':span.set('rowSpan','1')
            else:span.set('rowSpan','3')
            with self.assertRaises(g.GateError):p.grid(t)

    def test_empty_space_and_object_are_distinct(self):
        t=table();first=t.find('tr/tc/subList/p/t')
        first.text=None
        cells,_=p.grid(t)
        self.assertTrue(cells[0]['emptyFirstParagraph'])
        first.text='   '
        cells,_=p.grid(t)
        self.assertFalse(cells[0]['emptyFirstParagraph'])
        self.assertEqual(cells[0]['text'],'')
        first.text=None
        E.SubElement(t.find('tr/tc/subList/p'),'pic')
        cells,_=p.grid(t)
        self.assertFalse(cells[0]['plainFirstParagraph'])
        self.assertFalse(cells[0]['emptyFirstParagraph'])

    def test_route_can_cross_empty_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.hwpx';t=table()
            t.findall('tr/tc')[1].find('subList/p/t').text=None
            with ZipFile(path,'w') as z:
                z.writestr('Contents/content.hpf','<package><manifest><item id="s" href="Contents/section0.xml"/></manifest><spine><itemref idref="s"/></spine></package>')
                z.writestr('Contents/section0.xml','<sec>'+E.tostring(t,encoding='unicode')+'</sec>')
            route=p.plan(path,1,2,2)['route']
            self.assertEqual([x['text'] for x in route],['A','','C'])
            self.assertTrue(route[1]['emptyFirstParagraph'])
