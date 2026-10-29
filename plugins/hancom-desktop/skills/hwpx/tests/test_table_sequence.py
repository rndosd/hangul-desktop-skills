from pathlib import Path
from unittest.mock import patch
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from candidate_runtime import activate
activate()
import hangul_task as task
import safe_mixed_table_structure as guarded
import semantic_table_binding as binding
from hwpx import HwpxDocument

HEADERS=['단계','실행 업무','담당','완료 목표']
SOURCE=ROOT/'assets/complex-structure/source.hwpx'


def request():
    return dict(schema=task.SCHEMA,operation='table',headers=HEADERS,
                reason='연속 행 편집에서 새 항목의 전체 문구와 기존 표 서식을 보존한다.',
                operations=[
                    dict(op='insert_after',key={'실행 업무':'새 사업장 통신·전원 점검'},cells=['확인','새 단계 1: 전체 내용','담당 A','1차'],heightHwpunit=2400),
                    dict(op='insert_after',key={'실행 업무':'새 단계 1: 전체 내용'},cells=['확인','새 단계 2: 후속 내용','담당 B','2차'],heightHwpunit=2800),
                    dict(op='delete',key={'실행 업무':'새 단계 1: 전체 내용'})])


class TableSequenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path(__file__).parent/('.table-sequence-'+uuid.uuid4().hex)
        self.folder.mkdir()
        self.output=self.folder/'output.hwpx'
        self.source=self.folder/'fixture.hwpx'

    def tearDown(self):
        self.output.unlink(missing_ok=True)
        self.source.unlink(missing_ok=True)
        self.folder.rmdir()

    def blocked(self,source,plan):
        before=source.read_bytes()
        with patch.object(guarded,'apply_table_ops',wraps=guarded.apply_table_ops) as engine:
            with self.assertRaises(ValueError):task.table(source,self.output,plan)
            self.assertEqual(engine.call_count,0)
        self.assertFalse(self.output.exists())
        self.assertEqual(source.read_bytes(),before)

    def fixture(self,change):
        with HwpxDocument.open(SOURCE) as document:
            table=next(t for t in document.tables.all if t.element.get('id')=='944839944')
            change(table)
            table.mark_dirty()
            document.save_to_path(self.source)
        return self.source

    def test_insert_new_key_insert_delete_in_one_save(self):
        plan=request()
        before=SOURCE.read_bytes()
        result=task.table(SOURCE,self.output,plan)
        self.assertEqual(result['execution'],{'rowPatchCalls':1,'documentSaveCalls':1,'operations':3})
        self.assertEqual(binding.bind(self.output,HEADERS,{'실행 업무':'새 단계 2: 후속 내용'})['values'],plan['operations'][1]['cells'])
        with self.assertRaises(ValueError):binding.bind(self.output,HEADERS,{'실행 업무':'새 단계 1: 전체 내용'})
        self.assertEqual(SOURCE.read_bytes(),before)

    def test_other_rows_vertical_merge_is_preserved(self):
        source=self.fixture(lambda t:t.merge_cells(2,0,3,0))
        result=task.table(source,self.output,request())
        self.assertTrue(result['checks']['originalCellsTextRunsSpansSizesBordersExact'])
        merged=[c for c in binding.bind(self.output,HEADERS)['owners'] if c['span']['rowSpan']=='2']
        self.assertEqual(len(merged),1)

    def test_crossing_vertical_merge_is_rejected(self):
        source=self.fixture(lambda t:t.merge_cells(5,0,6,0))
        self.blocked(source,request())

    def test_protected_target_cell_is_rejected(self):
        source=self.fixture(lambda t:t.cell(5,1).element.set('protect','1'))
        self.blocked(source,request())

    def test_ambiguous_key_is_rejected(self):
        plan=request();plan['operations'][0]['key']={'담당':'시설지원반'}
        self.blocked(SOURCE,plan)

    def test_partial_key_is_rejected(self):
        plan=request();plan['operations'][0]['key']={'실행 업무':'통신·전원 점검'}
        self.blocked(SOURCE,plan)

    def test_late_missing_key_publishes_nothing(self):
        plan=request();plan['operations'].append(dict(op='delete',key={'실행 업무':'없는 항목'}))
        self.blocked(SOURCE,plan)

    def test_incomplete_cell_map_is_rejected(self):
        plan=request();plan['operations'][0]['cells'].pop()
        self.blocked(SOURCE,plan)

    def test_dry_run_leaves_no_file(self):
        result=task.table(SOURCE,self.output,request(),True)
        self.assertTrue(result['dryRun'])
        self.assertFalse(result['documentPublished'])
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
