"""Blank-document composition. Agent designs content; this CLI enforces the contract.

No template selection, network calls, COM calls, or existing-document mutation.
Runtime: python-hwpx 6.3.0, python-hwpx-automation 7.0.3.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from workspace_candidate_directory import workspace_candidate_directory
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from font_space_indent import indent_mm,space_metric
import fresh_header_serialization as fresh_header

from hwpx import HwpxDocument
from hwpx_automation.office.authoring import validate_document_plan, inspect_document_authoring_quality

NS = {'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
      'hh': 'http://www.hancom.co.kr/hwpml/2011/head',
      'hc': 'http://www.hancom.co.kr/hwpml/2011/core'}
DEFAULTS = dict(paper='A4', orientation='portrait', font='맑은 고딕',
                body_pt=11, title_pt=20, heading_pts=[15, 13, 12],
                line_spacing=160, margins_mm=dict(left=20, right=20, top=20, bottom=20),
                title_align='center', body_align='left', table_header_fill='#EAEAEA',
                character_ratio=100, letter_spacing=0, body_spacing_pt=dict(before=0,after=5),
                table_layout=None, table_line_spacing=None, table_paragraph_after_pt=2,
                table_header_align=None, table_keep_with_next=None,
                table_outer_spacing_pt=dict(before=6,after=6),
                heading_numbering=None, indent_policy='font_spaces', heading_layout=[
                    dict(indent_left_mm=0, first_line_indent_mm=0, spacing_before_pt=14, spacing_after_pt=6),
                    dict(indent_left_mm=0, first_line_indent_mm=0, spacing_before_pt=6, spacing_after_pt=4),
                    dict(indent_left_mm=0, first_line_indent_mm=0, spacing_before_pt=6, spacing_after_pt=4)])


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def intake(brief):
    """Return questions, never invent missing facts or document intent."""
    questions = []
    for key, question in [('purpose', '문서로 전달하거나 결정하려는 목적은 무엇인가요?'),
                          ('audience', '누가 읽고 어떤 행동을 해야 하나요?'),
                          ('kind', '원하는 문서 종류는 무엇인가요?')]:
        if not brief.get(key):
            questions.append(dict(key=key, question=question, blocking=True))
    if not brief.get('facts') and not brief.get('allow_draft'):
        questions.append(dict(key='facts', question='반드시 들어갈 내용이나 근거를 알려 주세요. 미정 표시가 있는 초안도 괜찮나요?', blocking=True))
    for item in brief.get('unknowns', []):
        questions.append(dict(key=item['key'], question=item['question'],
                              blocking=bool(item.get('critical', False) and not brief.get('allow_draft'))))
    return dict(can_design=not any(q['blocking'] for q in questions), questions=questions,
                defaults=DEFAULTS, note='날짜·금액·인명·장소는 기본값이 없습니다. 미정은 [확인 필요: 항목]으로 표시합니다.')


def formatting(brief, design):
    fmt = deepcopy(DEFAULTS)
    fmt['margins_mm'] = dict(DEFAULTS['margins_mm'])
    for src in [design.get('format', {}), brief.get('format', {})]:
        extra = set(src) - set(DEFAULTS)
        if extra:
            raise ValueError(f'지원하지 않는 서식: {sorted(extra)}. 무시하지 말고 지원 경로를 확인하세요.')
        for key, value in src.items():
            if key == 'margins_mm':
                if set(value) - set(fmt[key]):
                    raise ValueError('여백 키는 left/right/top/bottom만 지원합니다.')
                fmt[key].update(value)
            else:
                fmt[key] = value
    if isinstance(brief.get('summary_data'),dict) and brief['summary_data'].get('presentation','auto')!='text':
        summary_defaults=dict(table_header_align='center',table_line_spacing=140,
            table_layout=dict(cell_margins_mm=dict(left=1.5,right=1.5,top=1,bottom=1),vertical_align='CENTER',line_wrap='BREAK',page_break='CELL',repeat_header=True))
        for key,value in summary_defaults.items():
            if key not in design.get('format',{}) and key not in brief.get('format',{}):fmt[key]=value
    if fmt['indent_policy'] not in ('font_spaces','explicit'):
        raise ValueError('indent_policy는 font_spaces/explicit입니다.')
    if fmt['paper'] != 'A4' or fmt['orientation'] not in ('portrait', 'landscape'):
        raise ValueError('첫 구현은 A4 세로/가로만 지원합니다. 다른 용지는 조용히 대체하지 않습니다.')
    for key in ['body_pt', 'title_pt', 'line_spacing']:
        if not isinstance(fmt[key], (float, int)) or not math.isfinite(fmt[key]) or fmt[key] <= 0:
            raise ValueError(f'잘못된 서식 값: {key}')
    if len(fmt['heading_pts']) != 3 or any(not isinstance(x, (float, int)) or not math.isfinite(x) or x <= 0 for x in fmt['heading_pts']):
        raise ValueError('heading_pts는 양수 3개가 필요합니다.')
    if not isinstance(fmt['font'], str) or not fmt['font'].strip():
        raise ValueError('font가 필요합니다.')
    if fmt['title_align'] not in ('left', 'center', 'right', 'justify') or fmt['body_align'] not in ('left', 'center', 'right', 'justify'):
        raise ValueError('지원하지 않는 정렬입니다.')
    if any(isinstance(x,bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or x < 0 for x in fmt['margins_mm'].values()):
        raise ValueError('잘못된 여백입니다.')
    if fmt['table_header_align'] not in (None,'left','center','right') or fmt['table_keep_with_next'] is not None and type(fmt['table_keep_with_next']) is not bool:
        raise ValueError('표 제목 행 정렬 또는 표 뒤 문단 유지 설정이 잘못되었습니다.')
    if fmt['table_line_spacing'] is not None and (isinstance(fmt['table_line_spacing'],bool) or not isinstance(fmt['table_line_spacing'],(int,float)) or not math.isfinite(fmt['table_line_spacing']) or not 100 <= fmt['table_line_spacing'] <= 250):
        raise ValueError('표 줄 간격은 100~250% 또는 null입니다.')
    if isinstance(fmt['table_paragraph_after_pt'],bool) or not isinstance(fmt['table_paragraph_after_pt'],(int,float)) or not math.isfinite(fmt['table_paragraph_after_pt']) or not 0 <= fmt['table_paragraph_after_pt'] <= 12:
        raise ValueError('표 셀 문단 뒤 간격은 0~12pt입니다.')
    if type(fmt['character_ratio']) is not int or not 50 <= fmt['character_ratio'] <= 200 or type(fmt['letter_spacing']) is not int or not -20 <= fmt['letter_spacing'] <= 50:
        raise ValueError('장평은 50~200%, 자간은 -20~50% 정수로 지정하세요.')
    space=fmt['body_spacing_pt']
    if set(space) != {'before','after'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 72 for v in space.values()):
        raise ValueError('본문 앞뒤 간격은 before/after 0~72pt입니다.')
    outer=fmt['table_outer_spacing_pt']
    if not isinstance(outer,dict) or set(outer)!={'before','after'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=36 for v in outer.values()):
        raise ValueError('표 바깥 앞뒤 간격은 before/after 0~36pt입니다.')
    table_layout=fmt['table_layout']
    if table_layout is not None:
        if not {'cell_margins_mm','vertical_align','line_wrap','page_break','repeat_header'} <= set(table_layout) or set(table_layout)-{'cell_margins_mm','vertical_align','line_wrap','page_break','repeat_header','treat_as_char'}:
            raise ValueError('table_layout: 셀 여백·세로 정렬·줄바꿈·쪽 나눔·제목 반복만 지원합니다.')
        padding=table_layout['cell_margins_mm']
        if set(padding) != {'left','right','top','bottom'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 10 for v in padding.values()):
            raise ValueError('셀 여백은 네 방향에 0~10mm를 지정하세요.')
        if table_layout['vertical_align'] not in ('TOP','CENTER','BOTTOM') or table_layout['line_wrap']!='BREAK' or table_layout['page_break'] not in ('CELL','TABLE') or type(table_layout['repeat_header']) is not bool:
            raise ValueError('세로 정렬 TOP/CENTER/BOTTOM, 줄바꿈 BREAK, 표 쪽 나눔 CELL/TABLE을 사용하세요.')
        if type(table_layout.get('treat_as_char',True)) is not bool:
            raise ValueError('treat_as_char must be boolean')
    layouts = fmt['heading_layout']
    if not isinstance(layouts, list) or len(layouts) != 3:
        raise ValueError('heading_layout에는 수준별 문단 서식 3개가 필요합니다.')
    for layout in layouts:
        if set(layout) != set(DEFAULTS['heading_layout'][0]):
            raise ValueError('heading_layout: 들여쓰기·첫 줄·앞뒤 간격만 지원합니다.')
        if any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in layout.values()):
            raise ValueError('heading_layout 값은 유한한 수여야 합니다.')
        if not 0 <= layout['indent_left_mm'] <= 40 or not -layout['indent_left_mm'] <= layout['first_line_indent_mm'] <= 40:
            raise ValueError('제목 들여쓰기는 0~40mm, 내어쓰기는 왼쪽 여백 안에 있어야 합니다.')
        if any(not 0 <= layout[k] <= 72 for k in ('spacing_before_pt','spacing_after_pt')):
            raise ValueError('제목 앞뒤 간격은 0~72pt여야 합니다.')
    # User geometry has priority. Agent-authored positions use nominal space
    # metrics by default, so an arbitrary 6mm choice does not override policy.
    if fmt['indent_policy']=='font_spaces' and 'heading_layout' not in brief.get('format',{}):
        fmt['heading_layout']=deepcopy(fmt['heading_layout'])
        for i,layout in enumerate(fmt['heading_layout']):
            layout['indent_left_mm']=indent_mm(fmt['font'],fmt['heading_pts'][i],i,True,fmt['character_ratio'],fmt['letter_spacing'])
            layout['first_line_indent_mm']=0
    numbering = fmt['heading_numbering']
    if numbering is not None:
        if not isinstance(numbering,list) or len(numbering) != 3:
            raise ValueError('heading_numbering은 null 또는 수준별 번호 정의 3개입니다.')
        for level, spec in enumerate(numbering,1):
            if set(spec) != {'format','text','start'} or spec['format'] not in ('DIGIT','HANGUL_SYLLABLE','LATIN_SMALL'):
                raise ValueError('지원 번호 모양은 DIGIT/HANGUL_SYLLABLE/LATIN_SMALL입니다.')
            if spec['text'] not in (f'^{level}.',f'^{level})',f'(^{level})') or type(spec['start']) is not int or not 1 <= spec['start'] <= 99:
                raise ValueError('번호 텍스트는 해당 수준 참조와 마침표/괄호, 시작값은 1~99만 지원합니다.')
    w, h = (210, 297) if fmt['orientation'] == 'portrait' else (297, 210)
    if w - fmt['margins_mm']['left'] - fmt['margins_mm']['right'] < 50 or h - fmt['margins_mm']['top'] - fmt['margins_mm']['bottom'] < 50:
        raise ValueError('본문 영역이 너무 작습니다.')
    return fmt


def block_texts(block):
    if block['type'] in ('heading', 'paragraph'):
        return [block['text']]
    if block['type'] == 'bullets':
        return list(block['items'])
    if block['type'] == 'table':
        return ([block['caption']] if block.get('caption') else []) + [c['label'] for c in block['columns']] + [str(row[c['key']]) for row in block['rows'] for c in block['columns']]
    return []


def item_indent(brief,design,block,fmt):
    """One/two nominal spaces for level2/3; explicit user geometry wins."""
    spec=block['list']
    if 'indent_left_mm' in spec:
        if fmt['indent_policy']=='font_spaces' and 'indent_policy' not in brief.get('format',{}):
            raise ValueError('항목 수동 들여쓰기는 사용자 지정 indent_policy:explicit 또는 사용자 format.indent_policy 지정이 필요합니다. 기본은 level별 공백 폭입니다.')
        return spec['indent_left_mm']
    if fmt['indent_policy']=='explicit':raise ValueError('explicit 정책에서는 모든 번호/글머리표 항목의 indent_left_mm를 명시하세요.')
    return indent_mm(fmt['font'],fmt['body_pt'],spec['level']-1,block['type']=='table' or block.get('emphasis',False),fmt['character_ratio'],fmt['letter_spacing'])


def summary_spec(brief):
    """Explicit intake semantics; never infer a table from arbitrary digits."""
    summary=brief.get('summary_data')
    if not summary:return None
    if not isinstance(summary,dict) or set(summary)-{'caption','metrics','presentation','text_reason'}:
        raise ValueError('summary_data: caption/metrics/presentation/text_reason만 지원합니다.')
    metrics=summary.get('metrics',[])
    if not isinstance(metrics,list) or len(metrics)<2:raise ValueError('요약 표는 비교할 제공 수치 2개 이상에 사용하세요.')
    if summary.get('presentation','auto') not in ('auto','table','text'):raise ValueError('summary presentation: auto/table/text')
    if summary.get('presentation')=='text' and not summary.get('text_reason','').strip():raise ValueError('요약을 문장으로 제시할 때는 사용자 요청 또는 문서 목적에 따른 이유가 필요합니다.')
    facts=brief.get('facts',{})
    import re
    seen=set()
    for metric in metrics:
        if not isinstance(metric,dict) or set(metric)-{'label','value','unit','evidence','note'} or not {'label','value','unit','evidence'}<=set(metric):raise ValueError('metric: label/value/unit/evidence와 선택 note를 사용하세요.')
        if not all(isinstance(metric[k],str) and metric[k].strip() for k in ('label','value')) or not isinstance(metric['unit'],str):raise ValueError('metric label/value/unit은 문자열입니다.')
        if 'note' in metric and not isinstance(metric['note'],str):raise ValueError('metric note는 문자열입니다.')
        if metric['label'] in seen:raise ValueError('요약 항목 이름 중복')
        seen.add(metric['label'])
        refs=metric['evidence']
        if not isinstance(refs,list) or not refs or any(ref not in facts for ref in refs):raise ValueError('요약 항목은 제공 사실의 evidence를 요구합니다.')
        source='\n'.join(facts[ref]['text'] for ref in refs)
        if '[확인 필요:' not in metric['value']:
            values=set(re.findall(r'\d+(?:[.,:/-]\d+)*',metric['value']))
            source_values=set(re.findall(r'\d+(?:[.,:/-]\d+)*',source))
            if not values or not values<=source_values or metric['label'] not in source or metric['unit'] and metric['unit'] not in source:
                raise ValueError('요약 표 값·항목·단위가 해당 제공 사실에서 확인되지 않습니다.')
    return summary


def prepare_design(brief,design):
    """Materialize default summary table before validation, never edit output."""
    result=deepcopy(design);summary=summary_spec(brief)
    if not summary or summary.get('presentation')=='text':return result
    blocks=result['plan']['blocks']
    existing=[b for b in blocks if b.get('summary_group')=='provided_metrics']
    if existing:return result  # preserve the agent's purpose-specific table
    with_note=any(m.get('note') for m in summary['metrics'])
    columns=[dict(key='label',label='항목',widthWeight=2,align='left'),dict(key='value',label='값',widthWeight=1,align='right')]
    if with_note:columns.append(dict(key='note',label='확인 사항',widthWeight=3,align='left'))
    rows=[]
    for m in summary['metrics']:
        row=dict(label=m['label'],value=m['value']+m['unit'])
        if with_note:row['note']=m.get('note','')
        rows.append(row)
    block=dict(id='provided-summary-table',type='table',summary_group='provided_metrics',caption=summary.get('caption','제공 수치 요약'),columns=columns,rows=rows,evidence=list(dict.fromkeys(ref for m in summary['metrics'] for ref in m['evidence'])),reason='제공된 집계 수치를 동일한 열에서 대조한다. 확인되지 않은 값을 추가하거나 합계·미응답을 추정하지 않는다.')
    if block['id'] in {b['id'] for b in blocks}:raise ValueError('요약 표 id 충돌')
    after=result.get('summary_after')
    if after is not None:
        matches=[i for i,b in enumerate(blocks) if b['id']==after]
        if not matches:raise ValueError('summary_after 대상 블록이 없습니다.')
        pos=matches[0]+1
    else:pos=next((i+1 for i,b in enumerate(blocks) if b['type']=='heading'),0)
    blocks.insert(pos,block)
    result.setdefault('preparation',{})['summary_table']=dict(block_id=block['id'],inserted_after=after,rows=len(rows),source='brief.summary_data')
    return result


def validate(brief, design):
    issues = []
    def fail(code, detail):
        issues.append(dict(code=code, detail=detail))
    if not intake(brief)['can_design']:
        fail('MISSING_CRITICAL_INPUT', intake(brief)['questions'])
    if design.get('schema') != 'hwpx.new_document.v1':
        fail('SCHEMA', 'schema must be hwpx.new_document.v1')
    plan = design.get('plan', {})
    result = validate_document_plan(plan).to_dict()
    if not result['ok']:
        fail('PLAN_INVALID', result)
    elif result.get('issues'):
        fail('PLAN_WARNINGS', result['issues'])
    if set(plan) - {'schemaVersion', 'title', 'subtitle', 'blocks'}:
        fail('UNSUPPORTED_PLAN_FIELD', 'metadata/style/generator profiles are not silently forwarded')
    facts = brief.get('facts', {})
    blocks = plan.get('blocks', [])
    ids = [b.get('id') for b in blocks]
    if not all(ids) or len(ids) != len(set(ids)):
        fail('BLOCK_IDS', 'Every block needs a unique id')
    supported = {'heading', 'paragraph', 'bullets', 'table', 'page_break'}
    allowed = {'heading': {'id','type','text','level','evidence','reason'},
               'paragraph': {'id','type','text','evidence','reason','emphasis','list'},
               'bullets': {'id','type','items','ordered','evidence','reason'},
               'table': {'id','type','caption','columns','rows','evidence','reason','list','row_heights_mm','summary_group'},
               'page_break': {'id','type','reason','evidence'}}
    last_level = 0
    item_parent_level=1
    list_groups={}
    visible = [plan.get('title', ''), plan.get('subtitle', '')]
    for i, block in enumerate(blocks):
        typ = block.get('type')
        if typ not in supported:
            fail('UNSUPPORTED_BLOCK', typ)
            continue
        if set(block) - allowed[typ]:
            fail('UNSUPPORTED_BLOCK_FIELD', block['id'])
        if typ == 'heading':
            level = block.get('level', 1)
            if level > last_level + 1:
                fail('HEADING_SKIP', block['id'])
            last_level = level
            item_parent_level=level
        if typ == 'paragraph' and 'emphasis' in block and type(block['emphasis']) is not bool:
            fail('INVALID_EMPHASIS',block['id'])
        if 'list' in block:
            spec=block['list']
            if not isinstance(spec,dict) or not {'kind','level','group'}<=set(spec) or set(spec)-{'kind','level','group','indent_left_mm'}:
                fail('INVALID_LIST_SPEC',block['id'])
            elif spec['kind'] not in ('number','bullet') or type(spec['level']) is not int or spec['level'] not in (2,3) or not isinstance(spec['group'],str) or not spec['group'].strip() or ('indent_left_mm' in spec and (isinstance(spec['indent_left_mm'],bool) or not isinstance(spec['indent_left_mm'],(int,float)) or not math.isfinite(spec['indent_left_mm']) or not 0 <= spec['indent_left_mm'] <= 40)):
                fail('INVALID_LIST_SPEC',block['id'])
            else:
                previous=list_groups.setdefault(spec['group'],spec['kind'])
                if previous!=spec['kind']:fail('LIST_GROUP_KIND_CONFLICT',spec['group'])
                if spec['level']>item_parent_level+1:fail('LIST_LEVEL_SKIP',block['id'])
                item_parent_level=spec['level']
        if typ == 'page_break' and (i == 0 or i == len(blocks)-1 or blocks[i-1]['type'] == 'page_break' or not block.get('reason')):
            fail('UNJUSTIFIED_PAGE_BREAK', block['id'])
        if typ == 'table':
            if not block.get('reason'):
                fail('TABLE_REASON_REQUIRED', block['id'])
            for col in block['columns']:
                if set(col) - {'key','label','widthWeight','align'} or col.get('widthWeight',1) <= 0 or col.get('align','left') not in ('left','center','right'):
                    fail('INVALID_COLUMN', block['id'])
            heights=block.get('row_heights_mm')
            if heights is not None and (not isinstance(heights,list) or len(heights)!=len(block['rows'])+1 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 5<=v<=60 for v in heights)):
                fail('INVALID_ROW_HEIGHTS',block['id'])
        for ref in block.get('evidence', []):
            if ref not in facts:
                fail('UNKNOWN_EVIDENCE', ref)
        visible.extend(block_texts(block))
    text = '\n'.join(visible)
    coverage = design.get('coverage', {})
    for requirement in brief.get('requirements', []):
        refs = coverage.get(requirement['id'], [])
        if not refs or any(ref not in ids for ref in refs):
            fail('REQUIREMENT_NOT_COVERED', requirement['id'])
        linked_text = '\n'.join(t for b in blocks if b.get('id') in refs for t in block_texts(b))
        linked_text+='\n'+'\n'.join(' '.join(str(row[c['key']]) for c in b['columns']) for b in blocks if b['type']=='table' and b.get('id') in refs for row in b['rows'])
        for literal in requirement.get('must_include', []):
            if literal not in linked_text:
                fail('REQUIRED_CONTENT_MISSING', literal)
    # Required facts may span label/value cells in one row, never unrelated rows.
    fact_text=text+'\n'+'\n'.join(' '.join(str(row[c['key']]) for c in b['columns']) for b in blocks if b['type']=='table' for row in b['rows'])
    for fact_id, fact in facts.items():
        if fact.get('required', True) and fact['text'] not in fact_text:
            fail('REQUIRED_FACT_MISSING', fact_id)
    try:
        summary=summary_spec(brief)
        if summary and summary.get('presentation')!='text':
            summary_tables=[b for b in blocks if b['type']=='table' and b.get('summary_group')=='provided_metrics']
            if len(summary_tables)!=1:fail('SUMMARY_TABLE_REQUIRED','prepare를 실행하거나 provided_metrics 요약 표를 설계하세요.')
            else:
                if len(summary_tables[0]['rows'])!=len(summary['metrics']):fail('SUMMARY_EXTRA_OR_MISSING_ROWS','요약 표에는 선언된 제공 항목만 사용하세요.')
                for metric in summary['metrics']:
                    expected=[metric['label'],metric['value']+metric['unit']]
                    matches=[row for row in summary_tables[0]['rows'] if all(t in [str(v) for v in row.values()] for t in expected) and (not metric.get('note') or any(metric['note'] in str(v) for v in row.values()))]
                    if len(matches)!=1:fail('SUMMARY_METRIC_NOT_PRESERVED',metric['label'])
    except (ValueError,TypeError,KeyError) as exc:fail('SUMMARY_SPEC_INVALID',str(exc))
    # All quantitative tokens must come verbatim from supplied facts, or be
    # explicitly labelled draft placeholders. This is a guard, not truth verification.
    import re
    sourced_text = '\n'.join(f['text'] for f in facts.values())
    sourced_numbers = set(re.findall(r'\d+(?:[.,:/-]\d+)*', sourced_text))
    for b in [dict(id='title',type='paragraph',text=plan.get('title','')),
              dict(id='subtitle',type='paragraph',text=plan.get('subtitle',''))] + blocks:
        for fragment in block_texts(b):
            unmarked = re.sub(r'\[확인 필요:[^\]]*\]', '', fragment)
            for token in re.findall(r'\d+(?:[.,:/-]\d+)*', unmarked):
                if token not in sourced_numbers:
                    fail('UNSOURCED_NUMBER', dict(block=b['id'], token=token))
    # Explicit factual claims are audited separately from suggestions and headings.
    for claim in design.get('claims', []):
        value, refs = claim.get('text', ''), claim.get('evidence', [])
        if not value or value not in text or not refs or any(ref not in facts for ref in refs):
            fail('CLAIM_UNSUPPORTED', claim)
        elif not any(value in facts[ref]['text'] for ref in refs):
            fail('CLAIM_NOT_VERBATIM', claim)
    for unknown in brief.get('unknowns', []):
        marker = '[확인 필요: ' + unknown['key'] + ']'
        if marker not in text:
            fail('UNKNOWN_NOT_MARKED', unknown['key'])
        # An end-of-document note cannot qualify an unsupported scope in
        # another paragraph. Authors declare affected blocks after source review.
        targets = unknown.get('block_ids')
        if targets is not None:
            if (not isinstance(targets, list) or not targets or
                    any(not isinstance(ref, str) or ref not in ids for ref in targets) or
                    len(targets) != len(set(targets))):
                fail('UNKNOWN_BLOCK_REFS_INVALID', unknown['key'])
            else:
                for ref in targets:
                    linked = next(b for b in blocks if b['id'] == ref)
                    if marker not in '\n'.join(block_texts(linked)):
                        fail('UNKNOWN_NOT_MARKED_AT_USE', dict(key=unknown['key'], block=ref))
    try:
        fmt = formatting(brief, design)
        for block in blocks:
            if block.get('list'):item_indent(brief,design,block,fmt)
        if not fmt['heading_numbering'] and any(isinstance(b.get('list'),dict) and b['list'].get('kind')=='number' for b in blocks):
            fail('LIST_NUMBERING_REQUIRED','number list uses the explicitly selected heading_numbering sequence')
        if fmt['table_layout']:
            width=(297 if fmt['orientation']=='landscape' else 210)-fmt['margins_mm']['left']-fmt['margins_mm']['right']
            pad=fmt['table_layout']['cell_margins_mm']
            for block in blocks:
                if block['type']!='table':continue
                weights=[c.get('widthWeight',1) for c in block['columns']]
                if min(width*w/sum(weights) for w in weights) <= pad['left']+pad['right']+5:
                    fail('TABLE_TEXT_AREA_TOO_SMALL',block['id'])
    except (ValueError, TypeError, KeyError) as exc:
        fail('FORMAT_INVALID', str(exc))
        fmt = None
    return dict(ok=not issues, mandatory_failures=issues, resolved_format=fmt,
                semantic_review=design.get('review', {}),
                warning='근거 연결과 숫자 검사는 사실성 전체를 증명하지 않습니다. 생성 전 모든 주장과 목적별 항목을 사람이 아닌 작성 에이전트도 원문과 대조해야 합니다.')


def canonicalize_fresh_character(doc, identity):
    """Only call for styles freshly created by these new-document authors."""
    header = doc.parts.headers[0]
    character_order = ['fontRef','ratio','spacing','relSz','offset','italic','bold',
                       'underline','strikeout','outline','shadow','emboss','engrave',
                       'supscript','subscript']
    matches = [n for n in header.element.findall('.//{'+NS['hh']+'}charPr') if n.get('id') == identity]
    if len(matches) != 1:
        raise ValueError('New character property identity is not unique')
    node = matches[0]
    names = [n.tag.rsplit('}',1)[-1] for n in node]
    if len(names) != len(set(names)) or any(n not in character_order for n in names):
        raise ValueError('Unsupported new character property children')
    if 'strikeout' not in names:
        node.append(node.makeelement('{'+NS['hh']+'}strikeout',dict(shape='NONE',color='#000000')))
    node[:] = sorted(list(node),key=lambda n:character_order.index(n.tag.rsplit('}',1)[-1]))
    header.mark_dirty()
    return identity


def compose(brief, design):
    check = validate(brief, design)
    if not check['ok']:
        raise ValueError(json.dumps(check['mandatory_failures'], ensure_ascii=False))
    fmt = check['resolved_format']
    doc = HwpxDocument.new()
    fresh_header.register_new(doc)
    doc.page.setup(paper_size='A4', orientation=fmt['orientation'], margins_mm=fmt['margins_mm'])
    # python-hwpx 6.3.0 emits PORTRAIT, which this Hangul version treats as
    # rotated paper despite portrait dimensions. Use the native token observed
    # in Hancom-saved files; dimensions above carry the requested orientation.
    # Public section API, applied only to this newly created document.
    for section in doc.sections:
        section.properties.set_page_size(orientation='WIDELY')
    doc.styles.ensure_font(fmt['font'])
    # Fresh-document-only public model adapter. Existing document editors do
    # not call this path. Seed definitions remain untouched; newly constructed
    # character properties use the observed native/official child order.
    header = doc.parts.headers[0]
    seed_char_ids = {n.get('id') for n in header.element.findall('.//{'+NS['hh']+'}charPr')}
    def new_run(**kwargs):
        identity = doc.styles.ensure_run(**kwargs)
        if identity in seed_char_ids:
            return identity
        return canonicalize_fresh_character(doc, identity)
    run_geometry=dict(ratio=fmt['character_ratio'],letter_spacing=fmt['letter_spacing'])
    # Reuse one numbering definition across headings; creating a list for every
    # paragraph would assign independent list IDs and lose sequence continuity.
    number_refs = doc.styles.ensure_numbering(kind='number', levels=fmt['heading_numbering']) if fmt['heading_numbering'] else None
    list_refs={}
    def item_format(block):
        spec=block.get('list')
        if not spec:return {}
        group=spec['group']
        if group not in list_refs:
            levels=fmt['heading_numbering'] if spec['kind']=='number' else [dict(char='·')]*3
            list_refs[group]=doc.styles.ensure_numbering(kind=spec['kind'],levels=levels)
        return dict(number_ref=list_refs[group][spec['level']-1],layout=dict(indent_left_mm=item_indent(brief,design,block,fmt),first_line_indent_mm=0))
    # The core's empty-document seed is a valid section carrier; leave it intact.
    def para(text, size=None, bold=False, align=None, before=0, after=5, keep=False, page=False, level=None, layout=None, number_ref=None, line=None):
        run = new_run(size=size or fmt['body_pt'], font=fmt['font'], bold=bold,**run_geometry)
        p = doc.add_paragraph(text, char_pr_id_ref=run, inherit_style=False)
        if number_ref is not None:
            p.para_pr_id_ref = number_ref
        doc.styles.apply_paragraph_format(paragraph_index=len(doc.paragraphs)-1,
             alignment=align or fmt['body_align'], line_spacing_percent=line or fmt['line_spacing'],
             spacing_before_pt=before, spacing_after_pt=after, keep_with_next=keep,
             indent_left_mm=(layout or {}).get('indent_left_mm',0),
             first_line_indent_mm=(layout or {}).get('first_line_indent_mm',0),
             page_break_before=page, outline_level=level)
        return p
    plan = design['plan']
    para(plan['title'], size=fmt['title_pt'], bold=True, align=fmt['title_align'], after=12, keep=True)
    if plan.get('subtitle'):
        para(plan['subtitle'], after=10, keep=True)
    pending_break = False
    for block in plan['blocks']:
        typ = block['type']
        if typ == 'page_break':
            pending_break = True
            continue
        if typ == 'heading':
            lv = block['level']
            layout=fmt['heading_layout'][lv-1]
            para(block['text'], size=fmt['heading_pts'][lv-1], bold=True,
                 before=layout['spacing_before_pt'], after=layout['spacing_after_pt'],
                 keep=True, page=pending_break, level=None if number_refs else lv-1,
                 layout=layout, number_ref=number_refs[lv-1] if number_refs else None)
        elif typ == 'paragraph':
            para(block['text'], bold=block.get('emphasis',False),before=fmt['body_spacing_pt']['before'],after=fmt['body_spacing_pt']['after'],page=pending_break,**item_format(block))
        elif typ == 'bullets':
            # A standalone list is native too; literal number prefixes do not
            # renumber when the user adds/removes items in Hangul.
            levels = [dict(format='DIGIT',text='^1.',start=1)] if block.get('ordered') else [dict(char='•')]
            refs = doc.styles.ensure_numbering(kind='number' if block.get('ordered') else 'bullet', levels=levels)
            for i, item in enumerate(block['items']):
                para(item, after=3, page=pending_break and i == 0, number_ref=refs[0])
        elif typ == 'table':
            caption = para(block.get('caption', ''), bold=True, after=4, keep=True, page=pending_break,**item_format(block))
            cols = block['columns']
            width_mm = (297 if fmt['orientation']=='landscape' else 210) - fmt['margins_mm']['left'] - fmt['margins_mm']['right']
            table = doc.add_table(rows=len(block['rows'])+1, cols=len(cols),
                                  width=round(width_mm*7200/25.4), height=sum(round(v*7200/25.4) for v in block['row_heights_mm']) if block.get('row_heights_mm') else (len(block['rows'])+1)*1800,
                                  char_pr_id_ref=new_run(font=fmt['font'], size=fmt['body_pt'],**run_geometry),
                                  para_pr_id_ref=caption.para_pr_id_ref)
            table.set_column_widths([col.get('widthWeight',1) for col in cols])
            # New-table external spacing, independent of cell internal padding.
            outer=table.element.find('{'+NS['hp']+'}outMargin')
            if outer is None:raise ValueError('new table outMargin missing')
            outer.set('top',str(round(fmt['table_outer_spacing_pt']['before']*100)))
            outer.set('bottom',str(round(fmt['table_outer_spacing_pt']['after']*100)))
            if fmt['table_layout']:
                # Bounded formatting of a newly created table only. Public cell
                # elements expose these OWPML attributes; no existing form edits.
                table.element.set('pageBreak',fmt['table_layout']['page_break'])
                table.element.set('repeatHeader','1' if fmt['table_layout']['repeat_header'] else '0')
                pos=table.element.find('{'+NS['hp']+'}pos')
                if pos is None:raise ValueError('new table pos missing')
                pos.set('treatAsChar','1' if fmt['table_layout'].get('treat_as_char',True) else '0')
            cell_styles={}
            def cell_style(align):
                if align not in cell_styles:
                    cell_styles[align]=para('',align=align,after=fmt['table_paragraph_after_pt'],line=fmt['table_line_spacing'])
                return cell_styles[align]
            # Caption keeps with the table; the table does not inherit the
            # caption's keep-with-next and pull its following paragraph along.
            host=para('',after=0,keep=bool(fmt['table_keep_with_next']))
            table.paragraph.para_pr_id_ref=host.para_pr_id_ref
            # Native Hangul adds an empty text atom after a newly authored table.
            # Prepare it through the public run setter so strict text preservation
            # is stable on the first SaveAs; never rewrite an existing table run.
            table.paragraph.runs[-1].text=''
            table.mark_dirty()
            rows = [[col['label'] for col in cols]] + [[str(row[col['key']]) for col in cols] for row in block['rows']]
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    cell = table.cell(r,c)
                    if block.get('row_heights_mm'):
                        cell.set_size(height=round(block['row_heights_mm'][r]*7200/25.4))
                    cell.set_text(value)  # brand-new empty cells only
                    if fmt['table_layout']:
                        tl=fmt['table_layout']
                        cell.element.set('hasMargin','1')
                        cell.element.set('header','1' if r==0 and tl['repeat_header'] else '0')
                        margin=cell.element.find('{'+NS['hp']+'}cellMargin')
                        if margin is None:raise ValueError('새 셀의 cellMargin이 없습니다.')
                        for side,value_mm in tl['cell_margins_mm'].items():margin.set(side,str(round(value_mm*7200/25.4)))
                        sublist=cell.element.find('{'+NS['hp']+'}subList')
                        sublist.set('vertAlign',tl['vertical_align']);sublist.set('lineWrap',tl['line_wrap'])
                    for p in cell.paragraphs:
                        align=(fmt['table_header_align'] or fmt['body_align']) if r==0 else cols[c].get('align',fmt['body_align'])
                        p.para_pr_id_ref = cell_style(align).para_pr_id_ref
                        for run in p.runs:
                            run.char_pr_id_ref = new_run(font=fmt['font'], size=fmt['body_pt'], bold=r==0,**run_geometry)
                    if r == 0:
                        table.set_cell_shading(r,c,fmt['table_header_fill'])
            host.remove()
            for style in cell_styles.values():style.remove()
            table.mark_dirty()
        pending_break = False
    check["fresh_header_preparation"] = fresh_header.prepare(doc)
    return doc, check


def audit_output(path, brief, design):
    """Independent XML readback checks content multiplicity/order and table cells."""
    quality = inspect_document_authoring_quality(path)
    failures = []
    with zipfile.ZipFile(path) as z:
        header = ET.fromstring(z.read('Contents/header.xml'))
        section = ET.fromstring(z.read('Contents/section0.xml'))
        all_text = [x.text or '' for x in section.findall('.//hp:t',NS)]
        expected = [design['plan']['title']]
        if design['plan'].get('subtitle'):
            expected.append(design['plan']['subtitle'])
        for block in design['plan']['blocks']:
            if block['type']=='bullets':
                expected.extend(block['items'])
            else:
                expected.extend(block_texts(block))
        expected = [s for s in expected if s]
        actual = [s for s in all_text if s]
        if actual != expected:
            failures.append(dict(code='CONTENT_SEQUENCE_MISMATCH',expected=expected,actual=actual))
            # Content lookups below assume exact multiplicity/order. A changed
            # paragraph must produce a failure receipt, not StopIteration.
            return dict(status='FAIL',mandatory_failures=failures,quality=quality,
                        render_status='NOT_CHECKED',native_reopen='NOT_CHECKED',
                        content_count=len(actual),table_count=len(section.findall('.//hp:tbl',NS)),
                        sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
        if any(n.get('type')=='PERCENT' and n.get('unit')!='HWPUNIT' for n in header.findall('.//hh:lineSpacing',NS)):
            failures.append(dict(code='FRESH_LINE_SPACING_UNIT_MISMATCH'))
        char_ids = {e.get('id') for e in header.findall('.//hh:charPr',NS)}
        para_ids = {e.get('id') for e in header.findall('.//hh:paraPr',NS)}
        style_ids = {e.get('id') for e in header.findall('.//hh:style',NS)}
        for elem in section.iter():
            for attr, ids in [('charPrIDRef',char_ids),('paraPrIDRef',para_ids),('styleIDRef',style_ids)]:
                if attr in elem.attrib and elem.get(attr) not in ids:
                    failures.append(dict(code='DANGLING_STYLE',ref=elem.get(attr),attribute=attr))
        expected_tables = [b for b in design['plan']['blocks'] if b['type']=='table']
        tables = section.findall('.//hp:tbl',NS)
        cell_alignments={}
        if len(tables) != len(expected_tables):
            failures.append(dict(code='TABLE_COUNT'))
        for table, block in zip(tables,expected_tables):
            rows = table.findall('hp:tr',NS)
            expected_rows = [[c['label'] for c in block['columns']]] + [[str(r[c['key']]) for c in block['columns']] for r in block['rows']]
            actual_rows = [[''.join(c.itertext()) for c in row.findall('hp:tc/hp:subList',NS)] for row in rows]
            if actual_rows != expected_rows:
                failures.append(dict(code='TABLE_CELL_MISMATCH'))
            if block.get('row_heights_mm'):
                target_heights=[round(v*7200/25.4) for v in block['row_heights_mm']]
                size=table.find('hp:sz',NS)
                if size is None or int(size.get('height','-1'))!=sum(target_heights):failures.append(dict(code='FORM_TABLE_HEIGHT_MISMATCH',block=block['id']))
                for r,row in enumerate(rows):
                    for cell in row.findall('hp:tc',NS):
                        size=cell.find('hp:cellSz',NS)
                        if size is None or int(size.get('height','-1'))!=target_heights[r]:failures.append(dict(code='FORM_ROW_HEIGHT_MISMATCH',block=block['id'],row=r))
            for row in rows:
                for cell in row.findall('hp:tc',NS):
                    span = cell.find('hp:cellSpan',NS)
                    if span is not None and (span.get('rowSpan')!='1' or span.get('colSpan')!='1'):
                        failures.append(dict(code='UNREQUESTED_MERGE'))
            fmt=formatting(brief,design)
            for r,row in enumerate(rows):
                for c,cell in enumerate(row.findall('hp:tc',NS)):
                    align=(fmt['table_header_align'] or fmt['body_align']) if r==0 else block['columns'][c].get('align',fmt['body_align'])
                    for p in cell.findall('hp:subList/hp:p',NS):cell_alignments[p]=align.upper()
        # Check resolved user settings against persisted shape definitions.
        fmt = formatting(brief,design)
        page = section.find('.//hp:pagePr',NS)
        if page is None or page.get('landscape') != 'WIDELY':
            failures.append(dict(code='NATIVE_PAGE_ORIENTATION_TOKEN_INVALID'))
        margin = page.find('hp:margin',NS) if page is not None else None
        expected_w, expected_h = (297,210) if fmt['orientation']=='landscape' else (210,297)
        if page is None or abs(int(page.get('width','-1'))-round(expected_w*7200/25.4))>1 or abs(int(page.get('height','-1'))-round(expected_h*7200/25.4))>1:
            failures.append(dict(code='PAGE_SIZE_MISMATCH'))
        for key, val in fmt['margins_mm'].items():
            if margin is None or abs(int(margin.get(key,'-1'))-round(val*7200/25.4))>1:
                failures.append(dict(code='MARGIN_MISMATCH',side=key))
        top_paras = section.findall('hp:p',NS)
        para_by_id = {e.get('id'):e for e in header.findall('.//hh:paraPr',NS)}
        char_by_id = {e.get('id'):e for e in header.findall('.//hh:charPr',NS)}
        font_groups = {g.get('lang'):{f.get('id'):f.get('face') for f in g.findall('hh:font',NS)} for g in header.findall('.//hh:fontface',NS)}
        for p in section.findall('.//hp:p',NS):
            if not ''.join(p.itertext()): continue
            shape = para_by_id.get(p.get('paraPrIDRef'))
            if shape is None: continue
            line = shape.findall('.//hh:lineSpacing',NS)
            wanted_line=(fmt['table_line_spacing'] or fmt['line_spacing']) if p in cell_alignments else fmt['line_spacing']
            if not line or any(e.get('value') != str(wanted_line) for e in line):
                failures.append(dict(code='LINE_SPACING_MISMATCH'))
            for run in p.findall('hp:run',NS):
                if not run.findall('hp:t',NS): continue
                char = char_by_id.get(run.get('charPrIDRef'))
                if char is None: continue
                font_ref = char.find('hh:fontRef',NS)
                if font_ref is None or any(font_groups.get(lang,{}).get(font_ref.get(attr)) != fmt['font'] for lang,attr in [('HANGUL','hangul'),('LATIN','latin')]):
                    failures.append(dict(code='FONT_MISMATCH'))
                for node_name,key in [('ratio','character_ratio'),('spacing','letter_spacing')]:
                    geom=char.find('hh:'+node_name,NS)
                    if geom is None or any(geom.get(lang)!=str(fmt[key]) for lang in ('hangul','latin','hanja','japanese','other','symbol','user')):
                        failures.append(dict(code='CHARACTER_GEOMETRY_MISMATCH',field=key))
        expected_width=round((expected_w-fmt['margins_mm']['left']-fmt['margins_mm']['right'])*7200/25.4)
        for table in tables:
            outer=table.find('hp:outMargin',NS)
            if outer is None or any(outer.get(side)!=str(round(fmt['table_outer_spacing_pt'][key]*100)) for side,key in [('top','before'),('bottom','after')]):
                failures.append(dict(code='TABLE_OUTER_SPACING_MISMATCH'))
            if abs(int(table.find('hp:sz',NS).get('width'))-expected_width)>1:
                failures.append(dict(code='TABLE_WIDTH_MISMATCH'))
            if fmt['table_layout']:
                tl=fmt['table_layout']
                if table.get('pageBreak')!=tl['page_break'] or table.get('repeatHeader')!=('1' if tl['repeat_header'] else '0'):
                    failures.append(dict(code='TABLE_FLOW_MISMATCH'))
                pos=table.find('hp:pos',NS)
                if pos is None or pos.get('treatAsChar')!=('1' if tl.get('treat_as_char',True) else '0'):
                    failures.append(dict(code='TABLE_ANCHOR_MISMATCH'))
                for r,row in enumerate(table.findall('hp:tr',NS)):
                    for cell in row.findall('hp:tc',NS):
                        margin=cell.find('hp:cellMargin',NS);sub=cell.find('hp:subList',NS)
                        if cell.get('hasMargin')!='1' or margin is None or any(abs(int(margin.get(side,'999999'))-round(mm*7200/25.4))>1 for side,mm in tl['cell_margins_mm'].items()):
                            failures.append(dict(code='CELL_MARGIN_MISMATCH'))
                        if sub is None or sub.get('vertAlign')!=tl['vertical_align'] or sub.get('lineWrap')!=tl['line_wrap'] or cell.get('header')!=('1' if r==0 and tl['repeat_header'] else '0'):
                            failures.append(dict(code='CELL_FLOW_MISMATCH'))
        breaks = [p for p in top_paras if para_by_id.get(p.get('paraPrIDRef')) is not None and para_by_id[p.get('paraPrIDRef')].find('hh:breakSetting',NS) is not None and para_by_id[p.get('paraPrIDRef')].find('hh:breakSetting',NS).get('pageBreakBefore')=='1']
        expected_break_texts=[]
        pending=False
        for block in design['plan']['blocks']:
            if block['type']=='page_break': pending=True
            elif pending:
                texts=block_texts(block)
                text=texts[0] if texts else ''
                expected_break_texts.append(text)
                pending=False
        if [''.join(p.itertext()) for p in breaks] != expected_break_texts:
            failures.append(dict(code='PAGE_BREAK_MISMATCH'))
        ordinary=[p for p in top_paras if p.find('.//hp:tbl',NS) is None and ''.join(p.itertext())]
        cursor=1+bool(design['plan'].get('subtitle'))
        for block in design['plan']['blocks']:
            if block['type'] == 'page_break': continue
            if block['type'] != 'bullets':
                cursor+=int(bool(block.get('caption'))) if block['type']=='table' else 1
                continue
            members=[]
            for offset,item in enumerate(block['items']):
                target=ordinary[cursor+offset]
                heading=para_by_id[target.get('paraPrIDRef')].find('hh:heading',NS)
                expected_type='NUMBER' if block.get('ordered') else 'BULLET'
                if heading is None or heading.get('type')!=expected_type:
                    failures.append(dict(code='NATIVE_LIST_MISSING',block=block['id']))
                else:members.append((heading.get('idRef'),heading.get('level')))
            if len(set(members))>1:failures.append(dict(code='LIST_SEQUENCE_SPLIT',block=block['id']))
            cursor+=len(block['items'])
        title_para = next(p for p in top_paras if ''.join(p.itertext())==design['plan']['title'])
        title_run = title_para.find('hp:run',NS)
        if int(char_by_id[title_run.get('charPrIDRef')].get('height')) != round(fmt['title_pt']*100):
            failures.append(dict(code='TITLE_SIZE_MISMATCH'))
        title_alignment=para_by_id[title_para.get('paraPrIDRef')].find('hh:align',NS)
        if title_alignment is None or title_alignment.get('horizontal') != fmt['title_align'].upper():
            failures.append(dict(code='TITLE_ALIGNMENT_MISMATCH'))
        heading_texts={b['text'] for b in design['plan']['blocks'] if b['type']=='heading'}
        for p in section.findall('.//hp:p',NS):
            text=''.join(p.itertext())
            if not text or text==design['plan']['title'] or text in heading_texts: continue
            shape=para_by_id.get(p.get('paraPrIDRef'))
            if shape is not None and shape.find('hh:align',NS).get('horizontal')!=cell_alignments.get(p,fmt['body_align'].upper()):
                failures.append(dict(code='BODY_ALIGNMENT_MISMATCH'))
            for run in p.findall('hp:run',NS):
                if not run.findall('hp:t',NS): continue
                char=char_by_id.get(run.get('charPrIDRef'))
                if char is not None and int(char.get('height'))!=round(fmt['body_pt']*100):
                    failures.append(dict(code='BODY_SIZE_MISMATCH'))
            if p in cell_alignments:
                values=shape.findall('.//hh:margin/hc:next',NS)
                if not fresh_header.margin_matches(shape,'next',round(fmt['table_paragraph_after_pt']*100)):
                    failures.append(dict(code='CELL_PARAGRAPH_SPACING_MISMATCH'))
        if fmt['table_keep_with_next'] is not None:
            for p in top_paras:
                if p.find('.//hp:tbl',NS) is None:continue
                setting=para_by_id[p.get('paraPrIDRef')].find('hh:breakSetting',NS)
                if setting is None or setting.get('keepWithNext')!=('1' if fmt['table_keep_with_next'] else '0'):
                    failures.append(dict(code='TABLE_HOST_FLOW_MISMATCH'))
        heading_number_ids=set()
        persisted_groups={}
        for b in design['plan']['blocks']:
            if not b.get('list'):continue
            spec=b['list'];text=b['text'] if b['type']=='paragraph' else b.get('caption','')
            p=next(p for p in top_paras if ''.join(p.itertext())==text)
            shape=para_by_id[p.get('paraPrIDRef')];head=shape.find('hh:heading',NS)
            wanted='NUMBER' if spec['kind']=='number' else 'BULLET'
            if head is None or head.get('type')!=wanted or head.get('level')!=str(spec['level']-1):
                failures.append(dict(code='LIST_HEADING_MISMATCH',block=b['id']));continue
            ref=head.get('idRef');old_ref=persisted_groups.setdefault(spec['group'],ref)
            if ref!=old_ref:failures.append(dict(code='LIST_SEQUENCE_SPLIT',block=b['id']))
            definition=header.find(f".//hh:numbering[@id='{ref}']",NS) if spec['kind']=='number' else header.find(f".//hh:bullet[@id='{ref}']",NS)
            node=definition.find(f"hh:paraHead[@level='{spec['level']}']",NS) if definition is not None and spec['kind']=='number' else definition.find('hh:paraHead',NS) if definition is not None else None
            selected=fmt['heading_numbering'][spec['level']-1] if spec['kind']=='number' else None
            if node is None or node.get('autoIndent')!='1' or (selected and (node.get('numFormat')!=selected['format'] or node.text!=selected['text'] or node.get('start')!=str(selected['start']))) or (spec['kind']=='bullet' and definition.get('char')!='·'):
                failures.append(dict(code='LIST_DEFINITION_MISMATCH',block=b['id']))
            for tag,expected_value in [('left',round(item_indent(brief,design,b,fmt)*7200/25.4)),('intent',0)]:
                vals=shape.findall('.//hh:margin/hc:'+tag,NS)
                if not fresh_header.margin_matches(shape,tag,expected_value,tolerance=0):failures.append(dict(code='LIST_POSITION_MISMATCH',block=b['id']))
        numbered_groups={b['list']['group'] for b in design['plan']['blocks'] if b.get('list',{}).get('kind')=='number'}
        if len({persisted_groups.get(group) for group in numbered_groups})!=len(numbered_groups):
            failures.append(dict(code='LIST_GROUPS_NOT_RESET'))
        for b in design['plan']['blocks']:
            if b['type']=='paragraph':
                p=next(p for p in top_paras if ''.join(p.itertext())==b['text'])
                shape=para_by_id[p.get('paraPrIDRef')]
                for run in p.findall('hp:run',NS):
                    if run.find('hp:t',NS) is None:continue
                    char=char_by_id.get(run.get('charPrIDRef'))
                    if char is None or (char.find('hh:bold',NS) is not None)!=b.get('emphasis',False):
                        failures.append(dict(code='PARAGRAPH_EMPHASIS_MISMATCH',block=b['id']))
                for tag,key in [('prev','before'),('next','after')]:
                    values=shape.findall(f'.//hh:margin/hc:{tag}',NS)
                    if not fresh_header.margin_matches(shape,tag,round(fmt['body_spacing_pt'][key]*100)):
                        failures.append(dict(code='BODY_SPACING_MISMATCH',block=b['id']))
        for b in design['plan']['blocks']:
            if b['type']=='heading':
                p = next(p for p in top_paras if ''.join(p.itertext())==b['text'])
                shape = para_by_id[p.get('paraPrIDRef')]
                setting = shape.find('hh:breakSetting',NS)
                if setting is None or setting.get('keepWithNext')!='1':
                    failures.append(dict(code='HEADING_KEEP_MISSING',block=b['id']))
                run = p.find('hp:run',NS)
                if int(char_by_id[run.get('charPrIDRef')].get('height')) != round(fmt['heading_pts'][b['level']-1]*100):
                    failures.append(dict(code='HEADING_SIZE_MISMATCH',block=b['id']))
                layout=fmt['heading_layout'][b['level']-1]
                for name,key,unit in [('left','indent_left_mm',7200/25.4),('intent','first_line_indent_mm',7200/25.4),('prev','spacing_before_pt',100),('next','spacing_after_pt',100)]:
                    values=shape.findall(f'.//hh:margin/hc:{name}',NS)
                    if not fresh_header.margin_matches(shape,name,round(layout[key]*unit)):
                        failures.append(dict(code='HEADING_LAYOUT_MISMATCH',block=b['id'],field=key))
                if fmt['heading_numbering']:
                    head=shape.find('hh:heading',NS)
                    definition=header.find(f".//hh:numbering[@id='{head.get('idRef')}']",NS) if head is not None else None
                    spec=fmt['heading_numbering'][b['level']-1]
                    node=definition.find(f"hh:paraHead[@level='{b['level']}']",NS) if definition is not None else None
                    if head is None or head.get('type')!='NUMBER' or head.get('level')!=str(b['level']-1) or node is None or node.get('autoIndent')!='1' or node.get('numFormat')!=spec['format'] or node.text!=spec['text'] or node.get('start')!=str(spec['start']):
                        failures.append(dict(code='HEADING_NUMBERING_MISMATCH',block=b['id']))
                    if head is not None:heading_number_ids.add(head.get('idRef'))
        if fmt['heading_numbering'] and len(heading_number_ids)!=1:
            failures.append(dict(code='HEADING_NUMBERING_SEQUENCE_SPLIT'))
        if heading_number_ids & {persisted_groups.get(group) for group in numbered_groups}:
            failures.append(dict(code='LIST_USES_HEADING_SEQUENCE'))
    v = quality['validation']
    if not v['validate_package']['ok'] or not v['validate_document']['ok'] or not v['reopened']:
        failures.append(dict(code='FILE_INVALID',validation=v))
    return dict(status='PASS_STRUCTURE' if not failures else 'FAIL',mandatory_failures=failures,
                quality=quality, render_status='NOT_CHECKED',native_reopen='NOT_CHECKED',
                content_count=len(actual),table_count=len(tables),page_break_count=len(breaks),
                persisted_format_checked=fmt,
                sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def create(brief, design, output):
    output = Path(output).resolve()
    if output.suffix.lower() != '.hwpx':
        raise ValueError('출력 확장자는 .hwpx여야 합니다.')
    receipt = output.with_suffix('.receipt.json')
    if output.exists() or receipt.exists():
        raise FileExistsError('기존 출력 또는 영수증을 덮어쓰지 않습니다.')
    output.parent.mkdir(parents=True,exist_ok=True)
    doc, validation = compose(brief,design)
    try:
        with workspace_candidate_directory(dir=output.parent,prefix='newdoc-') as tmp:
            candidate=Path(tmp)/'candidate.hwpx'
            doc.save_to_path(candidate)
            audit=audit_output(candidate,brief,design)
            if audit['mandatory_failures']:
                raise ValueError(json.dumps(audit['mandatory_failures'],ensure_ascii=False))
            # Exclusive creation protects against races with other runs.
            with output.open('xb') as stream:
                stream.write(candidate.read_bytes())
    finally:
        doc.close()
    dump(receipt,dict(validation=validation,output=str(output),audit=audit))
    return audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['intake','prepare','validate','create','audit'])
    parser.add_argument('--brief',type=Path,required=True)
    parser.add_argument('--design',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--prepared-design',type=Path)
    args=parser.parse_args()
    brief=json.loads(args.brief.read_text(encoding='utf-8-sig'))
    design=json.loads(args.design.read_text(encoding='utf-8-sig')) if args.design else None
    try:
        if args.command=='intake': result=intake(brief)
        elif args.command=='prepare':
            if not args.prepared_design:raise ValueError('prepare에는 --prepared-design 경로가 필요합니다.')
            prepared=prepare_design(brief,design)
            with args.prepared_design.open('x',encoding='utf8') as stream:
                stream.write(json.dumps(prepared,ensure_ascii=False,indent=2))
            result=dict(ok=True,prepared_design=str(args.prepared_design),preparation=prepared.get('preparation',{}))
        elif args.command=='validate': result=validate(brief,design)
        elif args.command=='audit': result=audit_output(args.output,brief,design)
        else: result=create(brief,design,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result.get('ok',result.get('can_design',result.get('status')=='PASS_STRUCTURE')) else 2
    except (ValueError,TypeError,KeyError,OSError,zipfile.BadZipFile,ET.ParseError) as exc:
        print(json.dumps(dict(status='BLOCKED',error=str(exc)),ensure_ascii=False))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
