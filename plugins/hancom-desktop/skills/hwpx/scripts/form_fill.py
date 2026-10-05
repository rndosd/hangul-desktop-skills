# SPDX-License-Identifier: Apache-2.0
"""Exact-label filling of existing HWPX cell paragraphs; local CLI 0.3.1.

No row/paragraph creation, native field flattening, XML writing or COM calls.
Every requested field is resolved before any candidate is published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from safe_edit import (apply_run_updates, digest, local, paragraph_view, public_target,
                       sections, single_line, source_path, valid_table_geometry, write_new_json)

REQUEST = 'hwpx.form-fill-request.v1'
INSPECTION = 'hwpx.form-fill-targets.v1'
PLAN = 'hwpx.form-fill-plan.v1'
POLICY = 'preserve-existing-run-capacities-extra-in-last-nonempty;blank-to-first-run'
MAX_PARAGRAPHS = 100


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def positive(value):
    return type(value) is int and value > 0


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {'schema', 'fields'} or request.get('schema') != REQUEST:
        raise ValueError('unsupported request schema or unknown request keys')
    fields = request['fields']
    if not isinstance(fields, list) or not 1 <= len(fields) <= 100:
        raise ValueError('request must contain 1..100 fields')
    ids = set()
    slots = 0
    required = {'id', 'label', 'direction', 'expected_occurrences', 'paragraphs', 'values'}
    allowed = required | {'table', 'section', 'allow_replace', 'target_row_offset', 'target_column_offset'}
    for field in fields:
        if not isinstance(field, dict) or not required <= set(field) or not set(field) <= allowed:
            raise ValueError('missing or unknown field keys')
        name = single_line(field['id'], search=True)
        if name in ids:
            raise ValueError('duplicate request field id')
        ids.add(name)
        single_line(field['label'], search=True)
        if field['direction'] not in ('right', 'below'):
            raise ValueError('direction must be right or below')
        for key,direction in (('target_row_offset','right'),('target_column_offset','below')):
            if key in field and (field['direction'] != direction or type(field[key]) is not int or field[key] < 0):
                raise ValueError(key+' requires '+direction+' and a nonnegative integer')
        count = field['expected_occurrences']
        if not positive(count) or count > 100:
            raise ValueError('expected_occurrences must be 1..100')
        for key in ('table', 'section'):
            if key in field and not positive(field[key]):
                raise ValueError(key + ' must be a positive 1-based integer')
        if 'allow_replace' in field and type(field['allow_replace']) is not bool:
            raise ValueError('allow_replace must be boolean')
        numbers = field['paragraphs']
        if (not isinstance(numbers, list) or not numbers or
                not all(positive(n) for n in numbers) or numbers != sorted(set(numbers))):
            raise ValueError('paragraphs must be sorted unique positive 1-based numbers')
        values = field['values']
        if not isinstance(values, list) or len(values) != count:
            raise ValueError('values must match expected_occurrences exactly')
        for occurrence in values:
            if not isinstance(occurrence, list) or len(occurrence) != len(numbers):
                raise ValueError('each occurrence must supply every selected paragraph')
            for value in occurrence:
                single_line(value)
        slots += count * len(numbers)
    if slots > MAX_PARAGRAPHS:
        raise ValueError('request exceeds 100 selected paragraph slots')
    return request


def collect_cells(source):
    result = []
    table_number = 0
    for section_number, (part, root) in enumerate(sections(source), 1):
        ordinals = {}
        for node in root.iter():
            if local(node) == 'tbl':
                table_number += 1
                ordinals[node] = table_number

        def walk(node, ancestors, location):
            if local(node) == 'tc':
                tables = [n for n in ancestors if local(n) == 'tbl']
                if not tables:
                    raise ValueError('cell has no table owner')
                table = tables[-1]
                address = next((n for n in node if local(n) == 'cellAddr'), None)
                span = next((n for n in node if local(n) == 'cellSpan'), None)
                try:
                    row, col = int(address.get('rowAddr'))+1, int(address.get('colAddr'))+1
                    height, width = int(span.get('rowSpan')), int(span.get('colSpan'))
                except (AttributeError, TypeError, ValueError):
                    raise ValueError('invalid cell address or span')
                paragraphs = []
                lists = [(i, n) for i, n in enumerate(node) if local(n) == 'subList']
                for list_index, sublist in lists:
                    for index, paragraph in enumerate(sublist):
                        if local(paragraph) != 'p':
                            continue
                        text, runs, scope, reason = paragraph_view(paragraph, ancestors+[node, sublist], ordinals, allow_empty_runs=True)
                        paragraphs.append({'part': part, 'paragraph_path': location+[list_index,index],
                                           'text': text, 'supported': reason is None, 'reason': reason,
                                           'scope': dict(scope, section=section_number), '_runs': runs})
                reason = None
                if len(tables) != 1 or any(local(n) == 'tbl' for n in node.iter()):
                    reason = 'nested_cell_write_unvalidated'
                elif not valid_table_geometry(table):
                    reason = 'ambiguous_or_invalid_table_geometry'
                elif len(lists) != 1 or not paragraphs:
                    reason = 'unsupported_cell_paragraph_container'
                result.append({'part': part, 'cell_path': location, 'table': ordinals[table],
                               'section': section_number, 'row': row, 'column': col,
                               'row_span': height, 'column_span': width,
                               'text': '\n'.join(p['text'] for p in paragraphs), 'reason': reason,
                               '_paragraphs': paragraphs})
            for index, child in enumerate(node):
                walk(child, ancestors+[node], location+[index])
        walk(root, [], [])
    return result


def cell_key(cell):
    return cell['part'], tuple(cell['cell_path'])


def neighbor(label, cells, direction, *, target_row_offset=None, target_column_offset=None):
    if label['reason']:
        raise ValueError(label['reason'])
    if any(not p['supported'] for p in label['_paragraphs']):
        raise ValueError('unsupported_label_controls')
    r, c = label['row'], label['column']
    if direction == 'right':
        face = [(row, c+label['column_span']) for row in range(r, r+label['row_span'])]
        if target_row_offset is not None:
            if target_row_offset >= label['row_span']:
                raise ValueError('target_row_offset outside label span')
            face = [face[target_row_offset]]
    else:
        face = [(r+label['row_span'], col) for col in range(c, c+label['column_span'])]
        if target_column_offset is not None:
            if target_column_offset >= label['column_span']:
                raise ValueError('target_column_offset outside label span')
            face = [face[target_column_offset]]
    neighbors = []
    for row, column in face:
        owners = [n for n in cells if n['table'] == label['table'] and n['part'] == label['part']
                  and n['row'] <= row < n['row']+n['row_span']
                  and n['column'] <= column < n['column']+n['column_span']]
        if len(owners) != 1:
            raise ValueError('neighbor_missing_or_ambiguous')
        neighbors.append(owners[0])
    if len({cell_key(n) for n in neighbors}) != 1:
        raise ValueError('label_boundary_has_multiple_target_cells')
    target = neighbors[0]
    if target['reason']:
        raise ValueError(target['reason'])
    return target


def inspect_form(source, request):
    validate_request(request)
    source = source_path(source)
    before = digest(source)
    request_sha = fingerprint(request)
    cells = collect_cells(source)
    matches = []
    protected_labels = set()
    for field in request['fields']:
        labels = sorted([c for c in cells if c['text'] == field['label']
                         and ('table' not in field or c['table'] == field['table'])
                         and ('section' not in field or c['section'] == field['section'])],
                        key=lambda c: (c['section'], c['table'], c['row'], c['column']))
        matches.append(labels)
        protected_labels.update(cell_key(c) for c in labels)
    fields = []
    occupied = set()
    for field, labels in zip(request['fields'], matches):
        errors = []
        targets = []
        if len(labels) != field['expected_occurrences']:
            errors.append('label_occurrence_count_mismatch: expected '+str(field['expected_occurrences'])+', found '+str(len(labels)))
        else:
            for occurrence, label in enumerate(labels):
                try:
                    target = neighbor(label, cells, field['direction'],
                                      target_row_offset=field.get('target_row_offset'),
                                      target_column_offset=field.get('target_column_offset'))
                    if cell_key(target) in protected_labels:
                        raise ValueError('target_is_another_requested_label')
                    selected = []
                    for index, number in enumerate(field['paragraphs']):
                        if number > len(target['_paragraphs']):
                            raise ValueError('selected_paragraph_missing; no implicit creation')
                        paragraph = target['_paragraphs'][number-1]
                        if not paragraph['supported'] or not paragraph['_runs']:
                            raise ValueError(paragraph['reason'] or 'empty_paragraph_without_existing_plain_run')
                        if paragraph['text'] != '' and not field.get('allow_replace', False):
                            raise ValueError('nonempty_target_requires_explicit_allow_replace')
                        key = (paragraph['part'], tuple(paragraph['paragraph_path']))
                        if key in occupied:
                            raise ValueError('overlapping_target_paragraphs')
                        occupied.add(key)
                        item = public_target(paragraph)
                        item['value'] = field['values'][occurrence][index]
                        item['paragraph'] = number
                        selected.append(item)
                    token = fingerprint([before, request_sha, field['id'], occurrence, cell_key(label), cell_key(target)])
                    targets.append({'target_id': token, 'occurrence': occurrence+1,
                                    'label_cell': public_target(label), 'target_cell': public_target(target),
                                    'paragraphs': selected})
                except ValueError as exc:
                    errors.append('occurrence '+str(occurrence+1)+': '+str(exc))
        fields.append({'id': field['id'], 'label': field['label'], 'matched_labels': len(labels),
                       'status': 'BLOCKED' if errors else 'RESOLVED', 'errors': errors, 'targets': targets})
    if digest(source) != before:
        raise ValueError('source changed during inspection')
    return {'schema': INSPECTION, 'source_sha256': before, 'request_sha256': request_sha,
            'request': request, 'status': 'BLOCKED' if any(f['errors'] for f in fields) else 'REQUIRES_EXPLICIT_PLAN',
            'fields': fields, 'native_render': 'not_checked'}


def make_form_plan(inspection):
    if (inspection.get('schema') != INSPECTION or inspection.get('status') != 'REQUIRES_EXPLICIT_PLAN'
            or any(f['errors'] for f in inspection['fields'])):
        raise ValueError('all requested fields must resolve; partial plans are forbidden')
    return {'schema': PLAN, 'source_sha256': inspection['source_sha256'],
            'request_sha256': inspection['request_sha256'], 'request': inspection['request'],
            'style_policy': POLICY, 'fields': inspection['fields']}


def compile_form(source, plan):
    if not isinstance(plan, dict) or plan.get('schema') != PLAN or plan.get('style_policy') != POLICY:
        raise ValueError('unsupported form plan schema or style policy')
    if digest(source) != plan.get('source_sha256'):
        raise ValueError('stale source hash')
    inspection = inspect_form(source, plan.get('request'))
    rebuilt = make_form_plan(inspection)
    if canonical(rebuilt) != canonical(plan):
        raise ValueError('form plan binding mismatch; inspect and plan again')
    paragraphs = {(p['part'], tuple(p['paragraph_path'])): p
                  for c in collect_cells(source) for p in c['_paragraphs']}
    updates = []
    changed = set()
    completion = []
    for field in plan['fields']:
        for target in field['targets']:
            for selected in target['paragraphs']:
                key = (selected['part'], tuple(selected['paragraph_path']))
                paragraph = paragraphs[key]
                value = selected['value']
                original = paragraph['text']
                completion.append({'field_id': field['id'], 'occurrence': target['occurrence'],
                                   'target_id': target['target_id'], 'scope': selected['scope'],
                                   'paragraph': selected['paragraph'], 'before': original, 'after': value,
                                   'length_delta': len(value)-len(original)})
                if value == original:
                    continue
                runs = paragraph['_runs']
                active = [r for r in runs if r['text']] or runs[:1]
                remaining = value
                for index, run in enumerate(active):
                    new = remaining if index == len(active)-1 else remaining[:len(run['text'])]
                    remaining = remaining[len(new):]
                    if new != run['text']:
                        updates.append({'part': paragraph['part'], 'paragraph_path': tuple(paragraph['paragraph_path']),
                                        'run_path': tuple(run['path']), 'before': run['text'], 'after': new,
                                        'char_pr': run['char_pr'], **({'create_plain_text': True} if run.get('create_plain_text') else {})})
                changed.add(key)
    if not updates:
        raise ValueError('request produces no changes')
    return updates, changed, completion


def apply_form(source, output, plan, *, dry_run=False):
    source = source_path(source)
    updates, changed, completion = compile_form(source, plan)
    result = apply_run_updates(source, output, updates, changed,
                               source_sha=plan['source_sha256'], dry_run=dry_run)
    result.update(schema='hwpx.form-fill-receipt.v1', plan_sha256=fingerprint(plan),
                  request_sha256=plan['request_sha256'], style_policy=POLICY,
                  requested_fields=len(plan['fields']), resolved_occurrences=sum(len(f['targets']) for f in plan['fields']),
                  requested_paragraphs=len(completion), field_results=completion,
                  all_requested_fields_resolved=True, completion='filled_candidate_native_pending')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('inspect');read.add_argument('source');read.add_argument('--request',required=True);read.add_argument('--output',required=True)
    plan = commands.add_parser('plan');plan.add_argument('--inspection',required=True);plan.add_argument('--output',required=True)
    apply = commands.add_parser('apply');apply.add_argument('source');apply.add_argument('output');apply.add_argument('--plan',required=True);apply.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:
        if args.command=='inspect':
            request=json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
            result=inspect_form(args.source,request);write_new_json(args.output,result)
        elif args.command=='plan':
            inspection=json.loads(Path(args.inspection).read_text(encoding='utf-8-sig'))
            result=make_form_plan(inspection);write_new_json(args.output,result)
        else:
            plan=json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
            result=apply_form(args.source,args.output,plan,dry_run=args.dry_run)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if result.get('status')=='BLOCKED' else 0
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc),'native_render':'not_checked'},ensure_ascii=False))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
