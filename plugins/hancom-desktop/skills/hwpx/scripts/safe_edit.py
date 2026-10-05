# SPDX-License-Identifier: Apache-2.0
"""Selected, run-preserving text edits on an immutable HWPX source.

Local CLI implementation 0.3.1. Uses python-hwpx 6.3.0 public run API;
XML is read for selection and preservation evidence, never written directly.
Native Hancom opening/rendering remains a separate required verification step.
"""
from __future__ import annotations
from workspace_candidate_directory import workspace_candidate_directory

import argparse
import hashlib
import json
import os
import posixpath
import tempfile
import zipfile
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

from lxml import etree as ET

SCHEMA = 'hwpx.selected-text-edit.v1'
POLICY = 'preserve-matched-run-lengths-extra-in-last-run'
IMPLEMENTATION_VERSION = '0.3.1'
MAX_EDITS = 100


def local(node):
    return node.tag.rsplit('}', 1)[-1] if isinstance(node.tag, str) else '#non-element'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(data):
    parser = ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = ET.fromstring(data, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('unsupported XML DTD')
    return root


def source_path(path):
    result = Path(path).resolve(strict=True)
    if result.suffix.lower() != '.hwpx':
        raise ValueError('source must be HWPX; legacy HWP is not directly edited')
    return result


def single_line(value, *, search=False):
    if not isinstance(value, str) or (search and not value):
        raise ValueError('text must be a string; find must be nonempty')
    if any(c in value for c in '\r\n\t'):
        raise ValueError('newlines and tabs require a separate structural edit')
    for c in value:
        n = ord(c)
        if n < 32 or 0xD800 <= n <= 0xDFFF or n in (0xFFFE, 0xFFFF):
            raise ValueError('invalid XML text character')
    return value


def sections(path):
    """Resolve package spine order; preserve all other package members."""
    result = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP members')
        content = parse(z.read('Contents/content.hpf'))
        items = {n.get('id'): n.get('href') for n in content.iter() if local(n) == 'item'}
        for node in content.iter():
            if local(node) != 'itemref':
                continue
            href = items.get(node.get('idref'))
            if not href:
                raise ValueError('unresolved spine reference')
            member = posixpath.normpath(href if href.startswith('Contents/') else posixpath.join('Contents', href))
            if not member.startswith('Contents/'):
                raise ValueError('unsafe spine path')
            tree = parse(z.read(member))
            if local(tree) == 'sec':
                result.append((member, tree))
    if not result or len({name for name, _ in result}) != len(result):
        raise ValueError('missing or duplicate section spine entries')
    return result


def paragraph_view(node, ancestry, table_ordinals, *, allow_empty_runs=False):
    runs = []
    text = ''
    reason = None
    for index, child in enumerate(node):
        if local(child).lower() == 'linesegarray':
            continue
        if local(child) != 'run':
            reason = 'unsupported_paragraph_child'
            continue
        children = list(child)
        # Hancom saves genuinely empty cells as a styled, childless run.
        # Only the form path opts in; body selection and controls stay unchanged.
        if (allow_empty_runs and not children and child.text in (None, '')
                and child.get('charPrIDRef') is not None):
            runs.append({'path': [index, 0], 'text': '',
                         'char_pr': child.get('charPrIDRef'), 'start': len(text),
                         'create_plain_text': True})
            continue
        ts = [(i, n) for i, n in enumerate(children) if local(n) == 't']
        # Real Hancom titles often start with a separate, text-free run carrying
        # section/column metadata. Keep that leading run untouched; never treat
        # fields, stories or controls inside a text run as editable plain text.
        first_body = (len(ancestry) == 1 and local(ancestry[0]) == 'sec'
                      and next((p for p in ancestry[0] if local(p) == 'p'), None) is node)
        metadata_only = (children and not ts and first_body and not runs
                         and all(local(n) == 'secPr' or
                                 (local(n) == 'ctrl' and len(n) and all(local(c) == 'colPr' for c in n))
                                 for n in children)
                         and not any(local(n) in ('p','t','tbl','pic','fieldBegin','fieldEnd')
                                     for c in children for n in c.iter()))
        if metadata_only:
            continue
        if len(ts) != 1 or len(children) != 1 or len(ts[0][1]):
            reason = 'unsupported_run_control_or_mixed_text'
        for text_index, t in ts:
            value = ''.join(t.itertext())
            runs.append({'path': [index, text_index], 'text': value,
                         'char_pr': child.get('charPrIDRef'), 'start': len(text)})
            text += value
    if any(c in text for c in '\r\n\t'):
        reason = 'unsupported_existing_line_or_tab_structure'
    tables = [n for n in ancestry if local(n) == 'tbl']
    cells = [n for n in ancestry if local(n) == 'tc']
    scope = {'kind': 'body'}
    if cells:
        cell = cells[-1]
        table = tables[-1]
        scope = {'kind': 'cell', 'table': table_ordinals[table], 'table_id': table.get('id')}
        address = next((n for n in cell if local(n) == 'cellAddr'), None)
        span = next((n for n in cell if local(n) == 'cellSpan'), None)
        try:
            scope.update(row=int(address.get('rowAddr')) + 1, column=int(address.get('colAddr')) + 1,
                         row_span=int(span.get('rowSpan')), column_span=int(span.get('colSpan')))
            if min(scope[k] for k in ('row', 'column', 'row_span', 'column_span')) < 1:
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            reason = 'unsupported_cell_address_or_span'
        if len(tables) != 1 or any(local(n) == 'tbl' for n in cell.iter()):
            reason = 'nested_cell_write_unvalidated'
        elif not valid_table_geometry(table):
            reason = 'ambiguous_or_invalid_table_geometry'
        if len(ancestry) < 2 or local(ancestry[-1]) != 'subList' or local(ancestry[-2]) != 'tc':
            reason = 'unsupported_cell_story'
        else:
            scope['paragraph'] = [n for n in ancestry[-1] if local(n) == 'p'].index(node) + 1
    elif len(ancestry) != 1 or local(ancestry[0]) != 'sec':
        reason = 'unsupported_story'
    else:
        scope['paragraph'] = [n for n in ancestry[0] if local(n) == 'p'].index(node) + 1
    return text, runs, scope, reason


def valid_table_geometry(table):
    """Read merged ownership; never change or guess a cell's coordinates."""
    try:
        rows, columns = int(table.get('rowCnt')), int(table.get('colCnt'))
        if min(rows, columns) < 1:
            return False
        occupied = set()
        for tr in table:
            if local(tr) != 'tr':
                continue
            for cell in tr:
                if local(cell) != 'tc':
                    continue
                addr = next(n for n in cell if local(n) == 'cellAddr')
                span = next(n for n in cell if local(n) == 'cellSpan')
                row, col = int(addr.get('rowAddr')), int(addr.get('colAddr'))
                height, width = int(span.get('rowSpan')), int(span.get('colSpan'))
                if min(row, col) < 0 or min(height, width) < 1 or row+height > rows or col+width > columns:
                    return False
                for r in range(row, row+height):
                    for c in range(col, col+width):
                        if (r, c) in occupied:
                            return False
                        occupied.add((r, c))
        return len(occupied) == rows*columns
    except (StopIteration, ValueError, TypeError):
        return False


def candidates(path, find, source_sha):
    single_line(find, search=True)
    result = []
    table_number = 0
    for section_number, (member, root) in enumerate(sections(path), 1):
        table_ordinals = {}
        for node in root.iter():
            if local(node) == 'tbl':
                table_number += 1
                table_ordinals[node] = table_number

        def walk(node, ancestry, location):
            if local(node) == 'p':
                text, runs, scope, reason = paragraph_view(node, ancestry, table_ordinals)
                start = text.find(find)
                while start >= 0:
                    binding = [source_sha, member, location, start, find]
                    token = hashlib.sha256(json.dumps(binding, ensure_ascii=False).encode('utf-8')).hexdigest()
                    result.append({'target_id': token, 'part': member, 'section': section_number,
                                   'paragraph_path': location, 'start': start, 'end': start + len(find),
                                   'scope': scope, 'supported': reason is None, 'reason': reason,
                                   'context': text[max(0, start-30):start+len(find)+30],
                                   '_runs': runs, '_paragraph_text': text})
                    start = text.find(find, start + 1)
            for i, child in enumerate(node):
                walk(child, ancestry + [node], location + [i])
        walk(root, [], [])
    return result


def public_target(item):
    return {k: v for k, v in item.items() if not k.startswith('_')}


def inspect_targets(source, find, *, table=None, row=None, column=None, limit=200):
    source = source_path(source)
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('limit must be 1..1000')
    coordinates = (table, row, column)
    if any(x is not None for x in coordinates) and not all(isinstance(x, int) and x > 0 for x in coordinates):
        raise ValueError('table, row and column must all be positive 1-based coordinates')
    before = digest(source)
    targets = candidates(source, find, before)
    if table is not None:
        targets = [t for t in targets if t['scope']['kind'] == 'cell'
                   and t['scope']['table'] == table and all(k in t['scope'] for k in ('row', 'column', 'row_span', 'column_span'))
                   and t['scope']['row'] <= row < t['scope']['row'] + t['scope']['row_span']
                   and t['scope']['column'] <= column < t['scope']['column'] + t['scope']['column_span']]
        # Ambiguous/overlapping cell geometry must never silently select an owner.
        owners = {(t['scope']['row'], t['scope']['column']) for t in targets}
        if len(owners) > 1:
            raise ValueError('ambiguous cell ownership')
    if digest(source) != before:
        raise ValueError('source changed during inspection')
    return {'schema': 'hwpx.text-targets.v1', 'source_sha256': before, 'find': find,
            'total': len(targets), 'truncated': len(targets) > limit,
            'targets': [public_target(t) for t in targets[:limit]], 'native_render': 'not_checked'}


def make_plan(inspection, target_ids, replacement):
    single_line(replacement)
    if inspection.get('schema') != 'hwpx.text-targets.v1' or not target_ids or len(target_ids) != len(set(target_ids)):
        raise ValueError('invalid inspection or duplicate/empty selection')
    targets = {t['target_id']: t for t in inspection['targets']}
    for token in target_ids:
        if token not in targets or not targets[token]['supported']:
            raise ValueError('selection is missing or unsupported')
    if inspection['find'] == replacement:
        raise ValueError('replacement must change the selected text')
    return {'schema': SCHEMA, 'source_sha256': inspection['source_sha256'], 'style_policy': POLICY,
            'edits': [{'target_id': token, 'find': inspection['find'], 'replace': replacement} for token in target_ids]}


def compile_edits(source, plan, source_sha):
    if not isinstance(plan, dict) or plan.get('schema') != SCHEMA or plan.get('style_policy') != POLICY:
        raise ValueError('unsupported plan schema or style policy')
    if plan.get('source_sha256') != source_sha:
        raise ValueError('stale source hash')
    edits = plan.get('edits')
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise ValueError('plan must contain 1..100 explicit edits')
    by_find = {}
    selected = []
    spans = defaultdict(list)
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError('invalid edit')
        find, replacement = single_line(edit.get('find'), search=True), single_line(edit.get('replace'))
        if find == replacement:
            raise ValueError('replacement must change the selected text')
        if find not in by_find:
            by_find[find] = {t['target_id']: t for t in candidates(source, find, source_sha)}
        target = by_find[find].get(edit.get('target_id'))
        if target is None or not target['supported']:
            raise ValueError('target is missing or unsupported: ' + str(target['reason'] if target else 'unknown_target'))
        key = (target['part'], tuple(target['paragraph_path']))
        interval = (target['start'], target['end'])
        if any(interval[0] < b and a < interval[1] for a, b in spans[key]):
            raise ValueError('overlapping or duplicate selected edits')
        spans[key].append(interval)
        selected.append((target, replacement))
    run_patches = defaultdict(list)
    run_originals = {}
    changed_paragraphs = set()
    for target, replacement in selected:
        pieces = []
        for run in target['_runs']:
            a, b = max(target['start'], run['start']), min(target['end'], run['start'] + len(run['text']))
            if a < b:
                pieces.append((run, a-run['start'], b-run['start']))
        remaining = replacement
        for i, (run, a, b) in enumerate(pieces):
            addition = remaining if i == len(pieces)-1 else remaining[:b-a]
            remaining = remaining[len(addition):]
            key = (target['part'], tuple(target['paragraph_path']), tuple(run['path']))
            run_originals[key] = run
            run_patches[key].append((a, b, addition))
        changed_paragraphs.add((target['part'], tuple(target['paragraph_path'])))
    updates = []
    for key, patches in run_patches.items():
        original = run_originals[key]['text']
        new = original
        for a, b, addition in sorted(patches, reverse=True):
            new = new[:a] + addition + new[b:]
        if new != original:
            updates.append({'part': key[0], 'paragraph_path': key[1], 'run_path': key[2],
                            'before': original, 'after': new, 'char_pr': run_originals[key]['char_pr']})
    return selected, updates, changed_paragraphs


def snapshot(path, overrides=None, changed_paragraphs=None, *, attribute_overrides=None, xml_roots=None, added_plain_text=None):
    """Whole-package comparison; only selected paragraph caches may differ."""
    overrides = overrides or {}
    changed_paragraphs = changed_paragraphs or set()
    attribute_overrides = attribute_overrides or {}
    xml_roots = xml_roots or {}
    added_plain_text = added_plain_text or {}
    parts = {}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP members')
        for member in names:
            if member.startswith('Preview/'):
                continue
            data = z.read(member)
            if not member.endswith(('.xml', '.hpf')):
                parts[member] = hashlib.sha256(data).hexdigest()
                continue
            root = xml_roots.get(member)
            if root is None:
                root = parse(data)

            def tree(node, location, parent_location):
                if local(node).lower() == 'linesegarray' and (member, parent_location) in changed_paragraphs:
                    return None
                tag = (node.tag if isinstance(node.tag, str) else
                       '#comment' if isinstance(node, ET._Comment) else
                       ('#processing-instruction', node.target))
                children = tuple(v for i, c in enumerate(node) for v in [tree(c, location+(i,), location)] if v is not None)
                key = (member, location)
                if key in added_plain_text:
                    if (node.tag != '{http://www.hancom.co.kr/hwpml/2011/paragraph}run'
                            or len(node) or node.text not in (None, '')):
                        raise ValueError('plain text creation requires a truly childless run')
                    # Read-only expected tree: never modify or serialize source XML.
                    children = (('{http://www.hancom.co.kr/hwpml/2011/paragraph}t',
                                 (), added_plain_text[key], '', ()),)
                value = overrides.get((member, location), node.text or '')
                attributes = dict(node.attrib)
                attributes.update(attribute_overrides.get((member, location), {}))
                return tag, tuple(sorted(attributes.items())), value, node.tail or '', children
            preceding, following = [], []
            sibling = root.getprevious()
            while sibling is not None:
                preceding.append(tree(sibling, (), ()))
                sibling = sibling.getprevious()
            sibling = root.getnext()
            while sibling is not None:
                following.append(tree(sibling, (), ()))
                sibling = sibling.getnext()
            parts[member] = (tuple(reversed(preceding)), tree(root, (), ()), tuple(following))
    return parts


def apply_run_updates(source, output, updates, changed, *, source_sha, dry_run=False):
    """Shared immutable-source publication for already bound, plain-run updates."""
    from hwpx import HwpxDocument
    from hwpx.oxml import HwpxOxmlParagraph
    from hwpx.tools.package_validator import validate_editor_open_safety

    source = source_path(source)
    output = Path(output).absolute()
    if source == output.resolve() or output.exists() or output.is_symlink():
        raise ValueError('output must be a new path distinct from source')
    if output.suffix.lower() != '.hwpx' or not output.parent.is_dir():
        raise ValueError('new HWPX output requires an existing parent directory')
    installed = version('python-hwpx')
    if installed != '6.3.0':
        raise ValueError('unvalidated python-hwpx version: ' + installed)
    before = source_sha
    if digest(source) != before:
        raise ValueError('source changed during preparation; no output published')
    if not validate_editor_open_safety(source).ok:
        raise ValueError('source open-safety validation failed')
    overrides = {(u['part'], u['paragraph_path']+u['run_path']): u['after']
                 for u in updates if not u.get('create_plain_text')}
    additions = {(u['part'], u['paragraph_path']+(u['run_path'][0],)): u['after']
                 for u in updates if u.get('create_plain_text')}
    expected = snapshot(source, overrides, changed, added_plain_text=additions)
    with workspace_candidate_directory(prefix='hwpx-selected-', dir=output.parent) as tmp:
        candidate = Path(tmp)/'candidate.hwpx'
        doc = HwpxDocument.open(source)
        try:
            sections_by_name = {s.part_name: s for s in doc.sections}
            for update in updates:
                section = sections_by_name[update['part']]
                node = section.element
                for index in update['paragraph_path']:
                    node = node[index]
                paragraph = HwpxOxmlParagraph(node, section)
                run = next((r for r in paragraph.runs if r.element is node[update['run_path'][0]]), None)
                if run is None or run.text != update['before'] or run.char_pr_id_ref != update['char_pr']:
                    raise ValueError('public API target binding mismatch')
                if update.get('create_plain_text'):
                    if (update['before'] != '' or len(run.element)
                            or run.element.text not in (None, '')
                            or tuple(update['run_path']) != (update['run_path'][0], 0)):
                        raise ValueError('childless run binding mismatch')
                    run.text = update['after']
                elif update['before'] == '':
                    # Existing run with exactly one plain t, no controls.
                    run.text = update['after']
                elif run.replace_text(update['before'], update['after'], count=1) != 1:
                    raise ValueError('public API replacement count mismatch')
            doc.save_to_path(candidate)
        finally:
            doc.close()
        reopened = HwpxDocument.open(candidate)
        reopened.close()
        if not validate_editor_open_safety(candidate).ok:
            raise ValueError('candidate open-safety validation failed')
        if snapshot(candidate, changed_paragraphs=changed) != expected:
            raise ValueError('non-target preservation mismatch; no output published')
        if digest(source) != before:
            raise ValueError('source changed during operation; no output published')
        output_hash = digest(candidate)
        if not dry_run:
            # Same-directory atomic publication, no overwrite and no partial output.
            # Unsupported filesystems fail closed rather than copy over a destination.
            os.link(candidate, output)
    return {'implementation_version': IMPLEMENTATION_VERSION,
            'status': 'PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',
            'source_sha256': before, 'output_sha256': output_hash, 'published': not dry_run,
            'python_hwpx': installed, 'changed_runs': len(updates), 'run_diff': updates,
            'preservation_scope': 'all XML structure/attributes/text/tails and non-Preview binary members',
            'excluded': ['Preview/*', 'selected paragraphs lineSegArray caches only'],
            'native_verification_required': True, 'completion': 'edited_candidate_native_pending',
            'native_open': 'not_checked', 'native_render': 'not_checked', 'visual_review': 'not_performed'}


def apply_plan(source, output, plan, *, dry_run=False):
    source = source_path(source)
    before = digest(source)
    selected, updates, changed = compile_edits(source, plan, before)
    result = apply_run_updates(source, output, updates, changed, source_sha=before, dry_run=dry_run)
    result.update(schema='hwpx.selected-text-edit-receipt.v1', selected_edits=len(selected),
                  plan_sha256=hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(),
                  style_policy=POLICY,
                  layout_risk=[{'target_id': t['target_id'], 'scope': t['scope'],
                                'length_delta': len(replacement)-(t['end']-t['start'])}
                               for t, replacement in selected])
    return result


def write_new_json(path, payload):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('inspect')
    read.add_argument('source')
    read.add_argument('--find', required=True)
    for name in ('table', 'row', 'column', 'limit'):
        read.add_argument('--'+name, type=int, default=200 if name == 'limit' else None)
    read.add_argument('--output', required=True)
    plan_cmd = commands.add_parser('plan')
    plan_cmd.add_argument('--inspection', required=True)
    plan_cmd.add_argument('--target', action='append', required=True)
    plan_cmd.add_argument('--replace', required=True)
    plan_cmd.add_argument('--output', required=True)
    apply_cmd = commands.add_parser('apply')
    apply_cmd.add_argument('source')
    apply_cmd.add_argument('output')
    apply_cmd.add_argument('--plan', required=True)
    apply_cmd.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            result = inspect_targets(args.source, args.find, table=args.table, row=args.row, column=args.column, limit=args.limit)
            write_new_json(args.output, result)
        elif args.command == 'plan':
            inspection = json.loads(Path(args.inspection).read_text(encoding='utf-8-sig'))
            result = make_plan(inspection, args.target, args.replace)
            write_new_json(args.output, result)
        else:
            plan = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
            result = apply_plan(args.source, args.output, plan, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc), 'native_render': 'not_checked'}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
