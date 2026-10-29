"""Behavior checks for structure-based selection; no COM or source opening."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from select_document_block import BlockLibrary, SelectionError

class ContentRouting(unittest.TestCase):
    def setUp(self):
        self.folder = Path(os.environ['HWPX_TEST_WORKSPACE']) / ('content-' + uuid.uuid4().hex)
        self.folder.mkdir()
        self.catalog = self.folder / 'blocks.json'
        self.cards = []
        self.add('body', {}, {'steps': ('paragraphs', ['text']), 'principles': ('paragraphs', ['text'])})
        self.add('schedule', {}, {'sessions': ('rows', ['time', 'activity', 'owner', 'minutes'])})
        self.add('budget', {'title': '제목'}, {'items': ('rows', ['item', 'quantity', 'amount'])})
        self.add('minutes', {'agenda': '안건', 'decisions': '결정', 'follow_up': '후속'}, {})
        self.save()

    def add(self, identity, fields, repeats):
        def ref(name): return {'path': name, 'sha256': '0' * 64}
        manifest = {'schema': 'hangul.fill.v1', 'blockId': identity, 'sourceDocumentSha256': '0' * 64,
                    'slots': {name: {'label': label} for name, label in fields.items()},
                    'repeats': {name: {'path': '/section[1]/' + ('row[1]' if shape == 'rows' else 'paragraph[1]'),
                                       'fields': {field: {} for field in members}}
                                for name, (shape, members) in repeats.items()}}
        raw = json.dumps(manifest, ensure_ascii=False).encode()
        (self.folder / (identity + '.json')).write_bytes(raw)
        card = {'id': identity, 'label': identity, 'purposes': ['planning'], 'keywords': ['일정'],
                'structure': {'pages': 1, 'summary': 'same topic for all cards'},
                'state': 'reviewed', 'content_state': 'neutral_form',
                'origin': {'file': ref('not-opened.hwpx'), 'selection': 'test', 'attribution': 'test', 'reuse_conditions': []},
                'document': ref(identity + '.hwpx'), 'pdf': ref(identity + '.pdf'), 'preview': ref(identity + '.png'),
                'verification': {'evidence': ref('not-opened.json'), 'tested_edits': [], 'limits': []},
                'fill': {'path': identity + '.json', 'sha256': hashlib.sha256(raw).hexdigest()}}
        self.cards.append(card)

    def save(self):
        self.catalog.write_text(json.dumps({'schema': 'hwpx.block-library.v1', 'blocks': self.cards}), encoding='utf-8')

    def match(self, value): return BlockLibrary(self.catalog).match_content(value)

    def test_schedule_facts_remain_rows_and_use_row_binding(self):
        records = [{'time': '첫째 날', 'activity': '책 선택', 'owner': '담임'}]
        selected = self.match({'layout': 'rows', 'records': records})['selected']
        self.assertEqual(selected['template'], 'schedule')
        self.assertEqual(selected['values'], {'sessions': records})
        self.assertEqual(selected['unfilledFields'], ['minutes'])

    def test_budget_is_not_selected_by_shared_topic_keywords(self):
        result = self.match({'layout': 'rows', 'records': [{'item': '종이', 'quantity': '2', 'amount': '미정'}]})
        self.assertEqual(result['selected']['template'], 'budget')

    def test_named_form_retains_all_supplied_values(self):
        values = {'agenda': '수업 협의', 'decisions': '자료 공유', 'follow_up': '담당 미정'}
        self.assertEqual(self.match({'layout': 'form', 'values': values})['selected']['values'], values)

    def test_explanation_can_still_use_one_body_template(self):
        result = self.match({'layout': 'paragraphs', 'template': 'body', 'repeat': 'steps',
                             'records': [{'text': '짧은 운영 설명'}]})
        self.assertEqual(result['selected']['template'], 'body')

    def test_ambiguous_paragraph_binding_requires_a_choice(self):
        result = self.match({'layout': 'paragraphs', 'records': [{'text': '설명'}]})
        self.assertIsNone(result['selected'])
        self.assertEqual(result['bestCount'], 2)

    def test_rows_cannot_fall_back_to_plain_paragraphs(self):
        self.assertEqual(self.match({'layout': 'rows', 'records': [{'text': '내용'}]})['candidateCount'], 0)

    def test_unrepresented_fact_is_not_discarded(self):
        result = self.match({'layout': 'rows', 'records': [{'time': '월요일', 'activity': '읽기', 'support_needs': '지원'}]})
        self.assertEqual(result['candidateCount'], 0)

    def test_equally_compatible_forms_do_not_choose_first(self):
        self.add('other-schedule', {}, {'events': ('rows', ['time', 'activity', 'owner', 'minutes'])})
        self.save()
        self.assertIsNone(self.match({'layout': 'rows', 'records': [{'time': '월', 'activity': '읽기'}]})['selected'])

    def test_compact_fit_is_listed_first_but_does_not_replace_semantic_choice(self):
        self.add('compact', {}, {'events': ('rows', ['time', 'activity'])})
        self.save()
        result = self.match({'layout': 'rows', 'records': [{'time': '월', 'activity': '읽기'}]})
        self.assertIsNone(result['selected'])
        self.assertEqual(result['candidates'][0]['template'], 'compact')

    def test_common_title_does_not_guess_a_document_purpose(self):
        self.add('toc', {'title': '목차 제목'}, {})
        self.save()
        result = self.match({'layout': 'form', 'values': {'title': '새 문서'}})
        self.assertIsNone(result['selected'])

    def test_changed_binding_never_silently_routes(self):
        (self.folder / 'schedule.json').write_text('{}')
        result = self.match({'layout': 'rows', 'records': [{'time': '월', 'activity': '읽기'}]})
        self.assertIsNone(result['selected'])
        self.assertEqual(result['unavailableBindings'][0]['reason'], 'FILL_HASH_MISMATCH')

    def test_invalid_records_are_rejected_before_editing(self):
        for record in ({'time': 10}, {'time': '월\n화'}, {}, {'time': ['월']}):
            with self.subTest(record=record), self.assertRaises(SelectionError):
                self.match({'layout': 'rows', 'records': [record]})
        for content in ({'layout':[]}, {'layout':'rows','records':[{'time':'월'}],'template':[]},
                        {'layout':'rows','records':[{'time':'월'}],'repeat':{}}):
            with self.subTest(content=content), self.assertRaises(SelectionError):
                self.match(content)

    def test_summary_exposes_actual_shapes_without_opening_documents(self):
        cards = {card['id']: card for card in BlockLibrary(self.catalog).list(summary=True)['blocks']}
        self.assertEqual(cards['body']['inputModel']['repeats']['steps']['layout'], 'paragraphs')
        self.assertEqual(cards['schedule']['inputModel']['repeats']['sessions']['layout'], 'rows')

    def test_common_fill_refuses_no_match_without_publishing(self):
        content = self.folder / 'input.json'
        content.write_text(json.dumps({'layout': 'rows', 'records': [{'unsupported': 'value'}]}))
        output = self.folder / 'not-published.hwpx'
        run = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(ROOT / 'scripts/hangul_task.py'), 'fill',
                              '--content', str(content), '--catalog', str(self.catalog), '--output', str(output)],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 2, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['reason'], 'CONTENT_NO_MATCH')
        self.assertFalse(output.exists())

if __name__ == '__main__': unittest.main()
