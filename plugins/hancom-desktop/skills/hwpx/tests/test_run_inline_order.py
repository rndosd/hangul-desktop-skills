"""Whole-run edits must keep text on the original side of inline objects."""
from pathlib import Path
import sys, unittest
from types import SimpleNamespace
from xml.etree import ElementTree as E
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from candidate_runtime import activate
activate()
from hwpx.oxml.run import HwpxOxmlRun
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'

def make(items):
    node=E.Element(P+'run')
    for tag,text in items:E.SubElement(node,P+tag).text=text
    return HwpxOxmlRun(node,SimpleNamespace(element=E.Element(P+'p'),section=SimpleNamespace(mark_dirty=lambda:None)))

class InlineOrder(unittest.TestCase):
    def test_label_stays_after_shape(self):
        for label in ('  목표','  더 길어진 운영 방법'):
            run=make([('t',' '),('rect',None),('t',' 근거')])
            shape=E.tostring(run.element[1])
            run.text=label
            self.assertEqual(run.text,label)
            self.assertEqual(run.element[0].text,' ')
            self.assertEqual(run.element[2].text,label[1:])
            self.assertEqual(E.tostring(run.element[1]),shape)

    def test_label_stays_before_shape(self):
        run=make([('t','목표 '),('rect',None)])
        run.text='운영 방법 '
        self.assertEqual(run.element[0].text,'운영 방법 ')
        self.assertEqual(run.element[1].tag,P+'rect')

    def test_ambiguous_assignment_is_nonmutating(self):
        run=make([('t','앞'),('rect',None),('t','뒤')]);before=E.tostring(run.element)
        with self.assertRaisesRegex(ValueError,'scoped replace_text'):run.text='대체'
        self.assertEqual(E.tostring(run.element),before)

    def test_unchanged_ambiguous_run_is_noop(self):
        run=make([('t','앞'),('rect',None),('t','뒤')]);before=E.tostring(run.element)
        run.text='앞뒤'
        self.assertEqual(E.tostring(run.element),before)

    def test_nested_text_control_is_nonmutating(self):
        run=make([('t','앞')]);E.SubElement(run.element[0],P+'tab')
        before=E.tostring(run.element)
        with self.assertRaisesRegex(ValueError,'scoped replace_text'):run.text='대체'
        self.assertEqual(E.tostring(run.element),before)

    def test_plain_split_text_remains_supported(self):
        run=make([('t','old'),('t',' text')]);run.text='new text'
        self.assertEqual(run.text,'new text')

if __name__=='__main__':unittest.main()
