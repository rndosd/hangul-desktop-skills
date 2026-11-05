# SPDX-License-Identifier: Apache-2.0
"""Swap the content of a user's source document while keeping its design.

`listing` prints every non-empty paragraph (body and table cells) once, with
whether its text can be edited. `swap` takes plain pairs, picks the targets
itself and runs the existing guarded engines: selected-text edits for
replacements, the public agent batch for paragraph deletions and opt-in
flattening rewrites. Nothing here writes XML directly.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import safe_edit as se

PAIR_KEYS = {'find', 'replace', 'delete', 'style', 'all', 'flatten'}
REASON_HINTS = {
    'unsupported_run_control_or_mixed_text':
        '줄 안에 전각 공백·탭 같은 제어 글자가 있어 글자 단위로 바꿀 수 없습니다. '
        '"flatten": true로 줄 전체를 다시 쓰면 되지만 그 줄의 글자 서식이 첫 서식 하나로 합쳐집니다.',
    'nested_cell_write_unvalidated': '표 안의 표(상자)라 이 경로로는 바꿀 수 없습니다. "flatten": true로 줄 전체를 다시 쓰세요.',
}


def _walk_paragraphs(source):
    data = Path(source).read_bytes()
    table_number = 0
    for section_number, (member, root) in enumerate(se.sections(io.BytesIO(data)), 1):
        table_ordinals = {}
        for node in root.iter():
            if se.local(node) == 'tbl':
                table_number += 1
                table_ordinals[node] = table_number

        def walk(node, ancestry, location):
            if se.local(node) == 'p':
                text, runs, scope, reason = se.paragraph_view(node, ancestry, table_ordinals)
                yield text, runs, scope, reason, (member, tuple(location))
            for i, child in enumerate(node):
                yield from walk(child, ancestry + [node], location + [i])
        yield from walk(root, [], [])


def _label(scope):
    if scope.get('kind') == 'cell':
        return f"표{scope.get('table')} {scope.get('row')}행{scope.get('column')}열"
    return '본문'


def _pictures(source):
    import zipfile
    with zipfile.ZipFile(source) as package:
        return sum(package.read(n).decode('utf-8', 'replace').count('<hp:pic ')
                   for n in package.namelist() if n.startswith('Contents/section'))


def listing(source):
    source = se.source_path(source)
    lines, editable = [], 0
    for text, runs, scope, reason, _ in _walk_paragraphs(source):
        if not text.strip():
            continue
        styles = len({r['char_pr'] for r in runs if r['text'].strip()})
        mark = '' if reason is None else f'  ✗{reason}'
        editable += reason is None
        lines.append(f"[{_label(scope)}] {text}{'  (서식 ' + str(styles) + '종)' if styles > 1 else ''}{mark}")
    return {'status': 'LISTED', 'source': str(source), 'sourceSha256': se.digest(source),
            'paragraphs': len(lines), 'editable': editable, 'pictures': _pictures(source),
            'lines': lines,
            'nextStep': 'Write pairs: [{"find":"옛 문구","replace":"새 문구"}, {"find":"지울 줄 전체","delete":true}] then swap.'}


def _check_pairs(pairs):
    if not isinstance(pairs, list) or not pairs or len(pairs) > se.MAX_EDITS:
        raise ValueError('pairs must be a list of 1..100 objects')
    for pair in pairs:
        if not isinstance(pair, dict) or 'find' not in pair or set(pair) - PAIR_KEYS:
            raise ValueError('each pair needs find and replace or delete:true; other keys: style, all, flatten')
        se.single_line(pair['find'], search=True)
        if pair.get('delete') is True:
            if 'replace' in pair or pair.get('flatten'):
                raise ValueError('delete pairs take no replace/flatten')
        else:
            if not isinstance(pair.get('replace'), str):
                raise ValueError('replace text required (or delete:true): ' + pair['find'][:40])
            se.single_line(pair['replace'])
        if pair.get('style', 'base') not in se.EDIT_STYLES:
            raise ValueError('style must be base or keep')
        if (pair.get('delete') or pair.get('flatten')) and '"' in pair['find']:
            raise ValueError('delete/flatten find cannot contain a double quote; use a distinctive part without it')


def _choose(pair, targets):
    """Pick targets for one pair, or explain why not."""
    if not targets:
        return None, 'not_found'
    if len(targets) > 1 and not pair.get('all'):
        exact = [t for t in targets if t['_paragraph_text'].strip() == pair['find'].strip()]
        if len(exact) != 1:
            return None, 'ambiguous'
        targets = exact
    bad = [t for t in targets if not t['supported']]
    if bad:
        return None, bad[0]['reason']
    return targets, None


def _entry(index, pair, reason, targets):
    entry = {'pair': index, 'find': pair['find'][:60], 'reason': reason}
    if reason in REASON_HINTS:
        entry['hint'] = REASON_HINTS[reason]
    elif reason == 'ambiguous':
        entry['hint'] = '여러 곳에 있습니다. 더 긴 문구로 찾거나 모두 바꾸려면 "all": true.'
        entry['where'] = [f"[{_label(t['scope'])}] {t['context']}" for t in targets[:4]]
    elif reason == 'inside_text_changed_by_earlier_pair':
        entry['hint'] = '앞의 다른 짝이 이미 이 글자를 포함한 줄을 바꿉니다(중복 짝이면 빼세요).'
    elif reason == 'not_found':
        entry['hint'] = '문구가 없습니다. swap --list의 글자를 그대로 복사하세요(여러 줄에 걸친 문구는 줄마다 따로).'
    return entry


def _path_key(path):
    return tuple(int(n) for n in re.findall(r'\[(\d+)\]', path))


def _paragraph_nodes(agent, find, *, exact):
    result = agent.query(f'paragraph:contains("{find}")', limit=50).to_dict()
    nodes = result['nodes']
    if exact:
        nodes = [n for n in nodes if n['summary'].get('text', '').strip() == find.strip()]
    return nodes


def swap(source, output, pairs, batch_runner):
    source = se.source_path(source)
    output = Path(output).absolute()
    if output.exists() or output.suffix.lower() != '.hwpx' or not output.parent.is_dir() or output == source:
        raise ValueError('new .hwpx output path required (existing parent, not the source)')
    _check_pairs(pairs)
    before = se.digest(source)
    unresolved, changes = [], []
    edits = [(i, p) for i, p in enumerate(pairs) if not p.get('delete') and not p.get('flatten')]
    later = [(i, p) for i, p in enumerate(pairs) if p.get('delete') or p.get('flatten')]
    stage = source
    applied = 0
    follow_up = []
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='hwpx-swap-', dir=output.parent) as temp:
        if edits:
            by_find = se.candidates_many(source, [p['find'] for _, p in edits], before)
            inspection, seen = [], {}
            for i, pair in edits:
                found = by_find[se.single_line(pair['find'], search=True)]

                def overlaps(t):
                    key = (t['part'], tuple(t['paragraph_path']))
                    return any(t['start'] < b and a < t['end'] for a, b in seen.get(key, ()))
                free = [t for t in found if not overlaps(t)]
                if found and not free:
                    unresolved.append(_entry(i, pair, 'inside_text_changed_by_earlier_pair', found))
                    continue
                fresh, reason = _choose(pair, free)
                if reason:
                    unresolved.append(_entry(i, pair, reason, free))
                    continue
                for t in fresh:
                    seen.setdefault((t['part'], tuple(t['paragraph_path'])), []).append((t['start'], t['end']))
                inspection.append({'schema': 'hwpx.text-targets.v1', 'source_sha256': before, 'find': pair['find'],
                                   'total': len(fresh), 'truncated': False,
                                   'targets': [se.public_target(t) for t in fresh]})
                changes.append({'query': len(inspection)-1, 'targets': [t['target_id'] for t in fresh],
                                'replace': pair['replace'], 'style': pair.get('style', 'base')})
            if changes:
                plan = se.combine_plans(inspection, changes)
                target = output if not later else Path(temp)/'stage-text.hwpx'
                receipt = se.apply_plan(source, target, plan)
                applied = receipt['selected_edits']
                follow_up = receipt['layout_follow_up']
                stage = target
        commands, deleted, rewritten, touched_cells = [], 0, 0, set()
        if later:
            from hwpx_automation.office.agent import HwpxAgentDocument
            with HwpxAgentDocument.open(stage) as agent:
                revision = agent.revision
                for i, pair in later:
                    nodes = _paragraph_nodes(agent, pair['find'], exact=bool(pair.get('delete')))
                    if not nodes or (len(nodes) > 1 and not pair.get('all')):
                        reason = 'not_found' if not nodes else 'ambiguous'
                        entry = {'pair': i, 'find': pair['find'][:60], 'reason': reason}
                        entry['hint'] = ('지울 줄은 줄 전체 글자와 같아야 합니다.' if pair.get('delete') and not nodes else
                                         '여러 줄에 있습니다. 더 긴 문구 또는 "all": true.' if nodes else
                                         'flatten은 줄 안의 고유한 일부 글자로 찾습니다.')
                        unresolved.append(entry)
                        continue
                    for node in nodes:
                        if pair.get('delete'):
                            commands.append({'commandId': f'delete{i}-{len(commands)}', 'op': 'remove', 'path': node['path']})
                            deleted += 1
                            if '/cell[' in node['path']:
                                touched_cells.add(node['path'].rsplit('/paragraph[', 1)[0])
                        else:
                            commands.append({'commandId': f'flatten{i}-{len(commands)}', 'op': 'set', 'path': node['path'],
                                             'properties': {'text': pair['replace']}})
                            rewritten += 1
            if commands:
                commands.sort(key=lambda c: _path_key(c['path']), reverse=True)
                request = {'schemaVersion': 'hwpx.agent-batch/v1', 'input': {'filename': str(stage)},
                           'output': {'filename': str(output), 'overwrite': False}, 'commands': commands,
                           'expectedRevision': revision, 'idempotencyKey': 'swap-' + se.digest(stage)[:16],
                           'dryRun': False, 'quality': 'transparent',
                           'verificationRequirements': ['package', 'reopen', 'openSafety', 'semanticDiff', 'bytePreservation']}
                result = batch_runner(request)
                if not result.get('ok'):
                    return {'status': 'BLOCKED', 'reason': 'deletion/flatten batch failed', 'batch': result,
                            'documentPublished': False}
            elif stage != source:
                Path(stage).replace(output)
        if se.digest(source) != before:
            raise ValueError('source changed during swap')
        published = output.exists()
    if touched_cells:
        follow_up.append({'reason': 'cell_paragraphs_deleted', 'cells': sorted(touched_cells),
                          'next_action': 'Row heights stay as before; check the page image and shrink the row with layout if it looks empty.'})
    pictures = _pictures(output) if published else None
    return {'status': ('PASS_STRUCTURE' if not unresolved else 'PARTIAL') if published else 'NOTHING_APPLIED',
            'output': str(output) if published else None, 'documentPublished': published,
            'replaced': applied, 'deleted': deleted, 'flattened': rewritten,
            'unresolved': unresolved, 'layoutFollowUp': follow_up,
            'pictures': pictures,
            'nextStep': ('Fix unresolved pairs and run swap again on the output; ' if unresolved else '')
                        + 'then open in Hangul (PDF) and check every page. Pictures (logos, marks) are unchanged — tell the user.',
            'native': 'NOT_CHECKED'}
