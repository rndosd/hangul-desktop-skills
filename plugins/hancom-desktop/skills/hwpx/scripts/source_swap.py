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

PAIR_KEYS = {'find', 'replace', 'delete', 'style', 'all', 'flatten', 'line'}
PICTURE_FORMATS = {'.png': 'png', '.jpg': 'jpg', '.jpeg': 'jpg', '.bmp': 'bmp', '.gif': 'gif'}
# Leading indentation and list mark of a line, kept when a whole line is rewritten.
MARKER = re.compile(r'^[ 　]*(?:[□■○●ㅇ◦▸▶▷·•◇◆※＊*\-]+[ 　]*)?')
REASON_HINTS = {
    'unsupported_run_control_or_mixed_text':
        '줄 안에 탭 같은 조판 부호가 있어 글자 단위로 바꿀 수 없습니다(전각 공백은 바꿀 수 있음). '
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


def _picture_table(path, agent=None):
    """Body pictures in document order: number, agent path, place, size in mm."""
    from hwpx import HwpxDocument
    with HwpxDocument.open(path) as doc:
        refs = doc.media.picture_references()
    own = agent is None
    if own:
        from hwpx_automation.office.agent import HwpxAgentDocument
        agent = HwpxAgentDocument.open(path)
    try:
        nodes = agent.query('picture', limit=100).to_dict()['nodes']
    finally:
        if own:
            agent.close()
    rows = []
    for number, ref in enumerate(refs, 1):
        node_path = nodes[number-1]['path'] if len(nodes) == len(refs) else None
        cell = re.search(r'row\[(\d+)\]/cell\[(\d+)\]', node_path or '')
        place = f'표 칸 {cell.group(1)}행{cell.group(2)}열' if cell else ('본문' if node_path else '위치 미확인')
        rows.append({'picture': number, 'path': node_path, 'place': place,
                     'widthMm': round(ref.width * 25.4 / 7200) if ref.width else None,
                     'heightMm': round(ref.height * 25.4 / 7200) if ref.height else None,
                     'width': ref.width, 'height': ref.height})
    return rows


def _image_size(data):
    try:
        import pymupdf
    except ImportError:  # older PyMuPDF
        import fitz as pymupdf
    pix = pymupdf.Pixmap(data)
    return pix.width, pix.height


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
            'pictureList': [f"[그림{r['picture']}] {r['place']} · {r['widthMm']}×{r['heightMm']}mm"
                            for r in _picture_table(source)],
            'nextStep': 'Write pairs: [{"find":"옛 문구","replace":"새 문구"}, {"find":"지울 줄 전체","delete":true}] then swap.'}


def _check_pairs(pairs):
    if not isinstance(pairs, list) or not pairs or len(pairs) > se.MAX_EDITS:
        raise ValueError('pairs must be a list of 1..100 objects')
    for pair in pairs:
        if isinstance(pair, dict) and 'picture' in pair:
            if set(pair) - {'picture', 'replace', 'delete'} or type(pair['picture']) is not int or pair['picture'] < 1:
                raise ValueError('picture pairs: {"picture": N (from --list), "replace": "image file"} or {"picture": N, "delete": true}')
            if pair.get('delete') is True:
                if 'replace' in pair:
                    raise ValueError('picture delete takes no replace')
            else:
                image = Path(str(pair.get('replace', '')))
                if image.suffix.lower() not in PICTURE_FORMATS or not image.is_file():
                    raise ValueError('picture replace needs an existing png/jpg/bmp/gif file: ' + str(image))
            continue
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
        if pair.get('line') and (pair.get('all') or pair.get('delete')):
            raise ValueError('line pairs rewrite one line; they take no all/delete')
        if (pair.get('delete') or pair.get('flatten')) and '"' in pair['find']:
            raise ValueError('delete/flatten find cannot contain a double quote; use a distinctive part without it')


def _keep_marker(old, new):
    """Keep the old line's indentation and list mark unless the new text brings its own."""
    lead = MARKER.match(old).group()
    if not lead or new.startswith(lead):
        return new
    body = new.lstrip(' 　')
    mark = lead.strip(' 　')
    indent = lead[:len(lead) - len(lead.lstrip(' 　'))]
    if mark and body.startswith(mark):
        return indent + body
    return lead + body


def _expand_lines(source, pairs, before):
    """Turn line pairs, and flatten pairs on editable lines, into whole-line base edits.

    A line is found by any unique part of it; the new text replaces the whole
    line in its body style, so labels and marks keep their own style where the
    words match. flatten stays only for lines the text engine cannot edit.
    """
    wanted = [(i, p) for i, p in enumerate(pairs) if p.get('line') or p.get('flatten')]
    if not wanted:
        return pairs, 0
    by_find = se.candidates_many(source, [p['find'] for _, p in wanted], before)
    out, converted = list(pairs), 0
    for i, pair in wanted:
        found = by_find[se.single_line(pair['find'], search=True)]
        lines = {}
        for target in found:
            lines.setdefault((target['part'], tuple(target['paragraph_path'])), target)
        target = next(iter(lines.values())) if len(lines) == 1 else None
        if target is None or not target['supported']:
            if pair.get('line'):
                reason = 'not_found' if not lines else 'ambiguous' if target is None else target['reason']
                out[i] = dict(pair, _error=reason, _targets=found)
            continue
        full = target['_paragraph_text']
        rest = {k: v for k, v in pair.items() if k not in ('line', 'flatten', 'find', 'replace')}
        out[i] = dict(rest, find=full, replace=_keep_marker(full, pair['replace']))
        converted += bool(pair.get('flatten'))
    return out, converted


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


HEADING = re.compile(r'^[ 　]*(?:□|■|◆|◇|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.|\d{1,2}\.|[가-하]\.)[ 　]*\S')


def _body_rows(path):
    """Top-level body paragraphs per section: (own text, is a plain blank spacer)."""
    sections = []
    for _, root in se.sections(io.BytesIO(Path(path).read_bytes())):
        rows = []
        for p in (n for n in root if se.local(n) == 'p'):
            runs = [r for r in p if se.local(r) == 'run']
            text = ''.join(''.join(t.itertext()) for r in runs for t in r if se.local(t) == 't')
            blank = (not text.strip() and p.get('pageBreak') != '1' and p.get('columnBreak') != '1'
                     and all(se.local(c) in ('run', 'linesegarray') for c in p)
                     and all(se.local(t) == 't' and not len(t) for r in runs for t in r))
            rows.append((text, blank))
        sections.append(rows)
    return sections


def _is_heading(text):
    line = text.strip()
    return bool(HEADING.match(text)) and len(line) <= 40 and ':' not in line and not line.endswith(('다.', '다'))


def _body_layout(rows_by_section, paths_by_section, deleted_paths):
    """Spacer blanks to remove with deleted lines, and heading lines to keep with the next.

    Source documents space their lines with blank paragraphs, so a deleted
    line between two blanks leaves a double gap: the later blank goes too.
    Their headings are rarely set to keep with the next paragraph (authors
    placed page breaks by hand), so a rewritten, shorter or longer text can
    leave a heading alone at a page end: headings and the blanks under them
    are set to keep with the next paragraph.
    """
    spacers, keep = [], []
    for rows, paths in zip(rows_by_section, paths_by_section):
        if len(paths) != len(rows):
            continue  # agent view and XML disagree: leave this section alone
        index = {path: i for i, path in enumerate(paths, 1)}
        removed = {index[p] for p in deleted_paths if p in index}
        for i in sorted(set(removed)):
            prev, nxt = i - 1, i + 1
            while prev in removed:
                prev -= 1
            while nxt in removed:
                nxt += 1
            if 1 <= prev and nxt <= len(rows) and rows[prev-1][1] and rows[nxt-1][1]:
                removed.add(nxt)
                spacers.append(paths[nxt-1])
        for i, (text, blank) in enumerate(rows, 1):
            if i in removed or blank or not _is_heading(text):
                continue
            j, under = i + 1, []
            while j <= len(rows) and (j in removed or rows[j-1][1]):
                if j not in removed:
                    under.append(j)
                j += 1
            if j > len(rows) or _is_heading(rows[j-1][0]):
                continue
            keep += [paths[k-1] for k in [i] + under]
    return spacers, keep


def _order_key(body_order):
    """Document-order key: the body paragraph holding the node, then positions inside it."""
    def key(path):
        owner = max((p for p in body_order if path == p or path.startswith(p + '/')), key=len, default=None)
        rest = path[len(owner):] if owner else path
        return (body_order.get(owner, (0, 0)), tuple(int(n) for n in re.findall(r'\[(\d+)\]', rest)))
    return key


def _paragraph_nodes(agent, find):
    """Lines containing find; when several, the one whose whole text is find."""
    nodes = agent.query(f'paragraph:contains("{find}")', limit=50).to_dict()['nodes']
    if len(nodes) > 1:
        exact = [n for n in nodes if n['summary'].get('text', '').strip() == find.strip()]
        nodes = exact or nodes
    return nodes


def swap(source, output, pairs, batch_runner):
    source = se.source_path(source)
    output = Path(output).absolute()
    if output.exists() or output.suffix.lower() != '.hwpx' or not output.parent.is_dir() or output == source:
        raise ValueError('new .hwpx output path required (existing parent, not the source)')
    _check_pairs(pairs)
    before = se.digest(source)
    pictures_in = [(i, p) for i, p in enumerate(pairs) if 'picture' in p]
    pairs = [p if 'picture' not in p else {'_picture': True} for p in pairs]
    pairs, flatten_as_line = _expand_lines(source, pairs, before)
    unresolved, changes = [], []
    edits = [(i, p) for i, p in enumerate(pairs) if not p.get('_picture') and not p.get('delete') and not p.get('flatten')]
    later = [(i, p) for i, p in enumerate(pairs) if not p.get('_picture') and (p.get('delete') or p.get('flatten'))]
    picture_swaps = [(i, p) for i, p in pictures_in if not p.get('delete')]
    picture_drops = [(i, p) for i, p in pictures_in if p.get('delete')]
    picture_notes, pictures_replaced, pictures_deleted = [], 0, 0
    stage = source
    applied = 0
    follow_up = []
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='hwpx-swap-', dir=output.parent) as temp:
        if edits:
            by_find = se.candidates_many(source, [p['find'] for _, p in edits], before)
            inspection, seen = [], {}
            for i, pair in edits:
                if '_error' in pair:
                    unresolved.append(_entry(i, pair, pair['_error'], pair['_targets']))
                    continue
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
                target = Path(temp)/'stage-text.hwpx'
                receipt = se.apply_plan(source, target, plan)
                applied = receipt['selected_edits']
                follow_up = receipt['layout_follow_up']
                stage = target
        if picture_swaps:
            # Public media API: the picture keeps its box (size, place, crop);
            # only the image it shows changes.
            from hwpx import HwpxDocument
            from hwpx.tools.package_validator import validate_editor_open_safety
            table = {r['picture']: r for r in _picture_table(stage)}
            target = Path(temp)/'stage-picture.hwpx'
            with HwpxDocument.open(stage) as doc:
                for i, pair in picture_swaps:
                    row = table.get(pair['picture'])
                    if row is None:
                        unresolved.append({'pair': i, 'find': f"그림{pair['picture']}", 'reason': 'not_found',
                                           'hint': f'그림은 1~{len(table)}번까지 있습니다(swap --list의 pictureList).'})
                        continue
                    image = Path(pair['replace'])
                    data = image.read_bytes()
                    doc.media.replace_picture(data, PICTURE_FORMATS[image.suffix.lower()],
                                              picture_index=pair['picture'] - 1)
                    pictures_replaced += 1
                    try:
                        w, h = _image_size(data)
                        box, new = row['width'] / row['height'], w / h
                        if abs(new / box - 1) > 0.1:
                            picture_notes.append(f"그림{pair['picture']}: 칸 비율 {box:.2f}, 새 그림 비율 {new:.2f} - 늘어나 보일 수 있으니 같은 비율의 그림을 쓰거나 한글에서 크기를 맞추세요.")
                    except Exception:
                        picture_notes.append(f"그림{pair['picture']}: 새 그림 크기를 읽지 못해 비율을 확인하지 못했습니다.")
                if pictures_replaced:
                    doc.save_to_path(target)
            if pictures_replaced:
                if not validate_editor_open_safety(target).ok:
                    raise ValueError('picture replacement failed open-safety validation; no output published')
                stage = target
        commands, deleted, rewritten, touched_cells = [], 0, 0, set()
        spacers_removed = headings_kept = 0
        body_order = {}
        deleted_lines = []
        if stage != source or later or picture_drops:
            from hwpx_automation.office.agent import HwpxAgentDocument
            with HwpxAgentDocument.open(stage) as agent:
                revision = agent.revision
                for i, pair in later:
                    nodes = _paragraph_nodes(agent, pair['find'])
                    if not nodes or (len(nodes) > 1 and not pair.get('all')):
                        reason = 'not_found' if not nodes else 'ambiguous'
                        entry = {'pair': i, 'find': pair['find'][:60], 'reason': reason}
                        entry['hint'] = ('여러 줄에 있습니다. 더 긴 문구 또는 "all": true.' if nodes else
                                         '그 글이 든 줄이 없습니다. swap --list의 글자를 그대로 복사하세요.')
                        unresolved.append(entry)
                        continue
                    for node in nodes:
                        if pair.get('delete'):
                            commands.append({'commandId': f'delete{i}-{len(commands)}', 'op': 'remove', 'path': node['path']})
                            deleted += 1
                            deleted_lines.append(node['summary'].get('text', '')[:60])
                            if '/cell[' in node['path']:
                                touched_cells.add(node['path'].rsplit('/paragraph[', 1)[0])
                        else:
                            commands.append({'commandId': f'flatten{i}-{len(commands)}', 'op': 'set', 'path': node['path'],
                                             'properties': {'text': _keep_marker(node['summary'].get('text', ''), pair['replace'])}})
                            rewritten += 1
                if picture_drops:
                    table = {r['picture']: r for r in _picture_table(stage, agent)}
                    for i, pair in picture_drops:
                        row = table.get(pair['picture'])
                        if row is None or not row['path']:
                            unresolved.append({'pair': i, 'find': f"그림{pair['picture']}", 'reason': 'not_found',
                                               'hint': f'그림은 1~{len(table)}번까지 있습니다(swap --list의 pictureList).'})
                            continue
                        commands.append({'commandId': f'picture{i}', 'op': 'remove', 'path': row['path']})
                        pictures_deleted += 1
                rows = _body_rows(stage)
                views = [agent.get(f'/section[{k}]', depth=1, child_limit=200).to_dict() for k in range(1, len(rows) + 1)]
                paths = [[c['path'] for c in v['children']] if not v['coverage']['truncatedChildren'] else []
                         for v in views]
                body_order = {c['path']: (k, i) for k, v in enumerate(views, 1)
                              for i, c in enumerate(v['children'], 1)}
                keep_now = {c['path']: c['summary'].get('keepWithNext') for v in views for c in v['children']}
                spacers, keep = _body_layout(rows, paths, [c['path'] for c in commands if c['op'] == 'remove'])
                for path in spacers:
                    commands.append({'commandId': f'spacer{len(commands)}', 'op': 'remove', 'path': path})
                    spacers_removed += 1
                for path in keep:
                    if not keep_now.get(path):
                        commands.append({'commandId': f'keep{len(commands)}', 'op': 'set', 'path': path,
                                         'properties': {'keepWithNext': True}})
                        headings_kept += 1
            if commands:
                # Later nodes first, so positional paths of earlier ones stay valid.
                commands.sort(key=lambda c: _order_key(body_order)(c['path']), reverse=True)
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
            'replaced': applied, 'deleted': deleted, 'deletedLines': deleted_lines, 'flattened': rewritten,
            'flattenRequestsKeptStyle': flatten_as_line,
            'spacersRemoved': spacers_removed, 'keptWithNext': headings_kept,
            'picturesReplaced': pictures_replaced, 'picturesDeleted': pictures_deleted, 'pictureNotes': picture_notes,
            'unresolved': unresolved, 'layoutFollowUp': follow_up,
            'pictures': pictures,
            'nextStep': ('Fix unresolved pairs and run swap again on the output; ' if unresolved else '')
                        + 'then open in Hangul (PDF) and check every page. Pictures not replaced or deleted keep the source logos and marks - tell the user.',
            'native': 'NOT_CHECKED'}
