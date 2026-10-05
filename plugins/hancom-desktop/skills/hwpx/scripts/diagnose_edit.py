"""Read-only HWPX preflight and route guard. Does not call MCP or edit XML."""
import argparse
import hashlib
import json
import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def local(tag):
    return tag.rsplit('}', 1)[-1]


def sections(package):
    root = ET.fromstring(package.read('Contents/content.hpf'))
    items = {n.get('id'): n.get('href') for n in root.iter() if local(n.tag) == 'item'}
    names = []
    for node in root.iter():
        if local(node.tag) != 'itemref':
            continue
        href = items.get(node.get('idref'))
        if not href:
            raise ValueError('unresolved spine reference')
        name = posixpath.normpath(href if href.startswith('Contents/') else posixpath.join('Contents', href))
        if name.startswith('../') or name.startswith('/'):
            raise ValueError('unsafe spine path')
        if name.endswith('.xml'):
            tree = ET.fromstring(package.read(name))
            if local(tree.tag) == 'sec':
                names.append((name, tree))
    if not names:
        raise ValueError('no section in content.hpf spine')
    return names


def diagnose(path, operation='inspect', find=None, *, request=None):
    path = Path(path)
    if operation == 'fill_form':
        from form_fill import inspect_form
        inspection = inspect_form(path, request)
        allowed = inspection['status'] == 'REQUIRES_EXPLICIT_PLAN'
        return dict(schema='hwpx.preflight.v1', source=str(path.resolve()),
                    sha256=inspection['source_sha256'], operation=operation,
                    decision='REQUIRES_EXPLICIT_PLAN' if allowed else 'BLOCK',
                    route='form_fill.py' if allowed else None,
                    reason='all_requested_fields_reviewed_plan_required' if allowed else 'unresolved_form_request',
                    form_targets=inspection)
    counts = dict(sections=0, tables=0, nested_tables=0, paragraphs=0,
                  mixed_run_paragraphs=0, pictures=0, explicit_linebreaks=0, max_table_depth=0)
    targets = []
    longest = 0
    with zipfile.ZipFile(path) as package:
        for name, root in sections(package):
            counts['sections'] += 1
            def walk(node, ancestry, node_path):
                nonlocal longest
                kind = local(node.tag)
                depth = sum(local(a.tag) == 'tbl' for a in ancestry)
                if kind == 'tbl':
                    counts['tables'] += 1
                    counts['nested_tables'] += int(depth > 0)
                    counts['max_table_depth'] = max(counts['max_table_depth'], depth + 1)
                if kind == 'p':
                    counts['paragraphs'] += 1
                    refs = {n.get('charPrIDRef') for n in node if local(n.tag) == 'run'}
                    counts['mixed_run_paragraphs'] += int(len(refs) > 1)
                if kind == 'pic':
                    counts['pictures'] += 1
                if kind == 'lineBreak':
                    counts['explicit_linebreaks'] += 1
                if kind == 't':
                    value = node.text or ''
                    longest = max(longest, len(value))
                    if find and find in value:
                        cells = [a for a in ancestry if local(a.tag) == 'tc']
                        nested_context = any(any(local(n.tag) == 'tbl' for n in cell.iter()) for cell in cells)
                        targets.append(dict(part=name, path=node_path, count=value.count(find),
                                            nested_context=nested_context, table_depth=depth))
                for i, child in enumerate(node):
                    walk(child, ancestry + [node], node_path + '/' + str(i))
            walk(root, [], name)
    result = dict(schema='hwpx.preflight.v1', source=str(path.resolve()),
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest(), structure=counts,
                  longest_text_node_characters=longest, targets=targets, operation=operation,
                  route='read_only', decision='ALLOW')
    if operation == 'selected_text':
        from safe_edit import inspect_targets
        listing = inspect_targets(path, find)
        supported = sum(t['supported'] for t in listing['targets'])
        result.update(selected_text_targets=listing,
                      decision='REQUIRES_EXPLICIT_PLAN' if supported else 'BLOCK',
                      route='safe_edit.py' if supported else None,
                      reason='reviewed_hash_bound_target_plan_required' if supported else 'no_supported_selected_text_target')
        return result
    if operation != 'inspect':
        if sum(t['count'] for t in targets) != 1:
            result.update(decision='BLOCK', route=None, reason='unique_text_target_required')
        elif operation in ('replace_text', 'set_cell_text') and targets[0]['nested_context']:
            result.update(decision='BLOCK', route=None, reason='nested_text_write_unvalidated')
        elif operation == 'replace_text':
            if targets[0]['table_depth']:
                result.update(decision='BLOCK', route=None, reason='local_table_text_route_unvalidated')
            else:
                result['route'] = 'safe_replace.py'
        elif operation == 'paragraph_alignment':
            if counts['tables'] not in (1, 2) or not targets[0]['table_depth']:
                result.update(decision='BLOCK', route=None, reason='native_cell_scope_unsupported')
            else:
                result.update(route='Invoke-HancomCell.ps1', decision='REQUIRES_NATIVE_TARGET_CHECK',
                              reason='first_cell_first_paragraph_exact_text_parent_and_alignment_0_or_2_only')
        else:
            result.update(route='MCP', decision='REQUIRES_CONTRACT_CHECK',
                          reason='candidate_only_dry_run_and_non_target_preservation_required')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--operation', choices=['inspect','replace_text','selected_text','fill_form','set_cell_text','paragraph_alignment'], default='inspect')
    parser.add_argument('--find')
    parser.add_argument('--request', help='form-fill request JSON for fill_form only')
    args = parser.parse_args()
    try:
        request = json.loads(Path(args.request).read_text(encoding='utf-8-sig')) if args.request else None
        result = diagnose(args.source, args.operation, args.find, request=request)
    except Exception as error:
        result = dict(decision='BLOCK', reason=str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2 if result['decision'] == 'BLOCK' else 0)
