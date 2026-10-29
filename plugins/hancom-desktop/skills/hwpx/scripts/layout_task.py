"""Compile role-scoped table adaptation into the existing public atomic batch.

Coordinates are 1-based logical addresses, including merged owners. No XML is
written here. The public batch owns mutation, preservation, and publication.
"""
from pathlib import Path
import hashlib
import math
from candidate_runtime import activate

SCHEMA = 'hangul.layout.v1'
ROLE_PROPERTIES = {
    'run': ('fontName', 'fontSizePt', 'color', 'bold', 'italic'),
    'paragraph': ('alignment', 'resetIndent', 'lineSpacingPercent'),
    'cell': ('verticalAlignment', 'paddingMm'),
}


def role_properties(spec):
    allowed = {name for names in ROLE_PROPERTIES.values() for name in names}
    require(isinstance(spec, dict) and not set(spec) - allowed, 'unsupported role property')
    return {kind: {name: spec[name] for name in names if name in spec}
            for kind, names in ROLE_PROPERTIES.items()}

def require(value, message):
    if not value:
        raise ValueError(message)

def _keys(value, allowed, required=()):
    require(isinstance(value, dict) and set(required) <= set(value)
            and not set(value) - set(allowed), 'layout request keys: ' + ', '.join(allowed))

def _plain_empty(paragraph):
    # Controls, fields, bookmarks and forced breaks are not disposable space.
    allowed = {'p', 'run', 't', 'linesegarray', 'lineseg'}
    return (not paragraph.text.strip()
            and not any(paragraph.element.get(k, '0') != '0' for k in ('pageBreak', 'columnBreak'))
            and all(str(e.tag).rsplit('}', 1)[-1] in allowed for e in paragraph.element.iter()))

def compile_layout(source, output, request):
    activate()
    from hwpx_automation.office.agent.document import HwpxAgentDocument
    _keys(request, ('schema', 'expectedRevision', 'groups', 'rowHeights'), ('schema', 'expectedRevision', 'groups'))
    require(request['schema'] == SCHEMA, 'layout schema must be ' + SCHEMA)
    require(isinstance(request['groups'], list), 'groups must be an array')
    require(isinstance(request.get('rowHeights', []), list), 'rowHeights must be an array')
    with HwpxAgentDocument.open(source) as view:
        require(view.revision == request['expectedRevision'], 'stale layout revision')
        records = view.records
        by_path = {r.path: r for r in records}
        children = {}
        for rec in records:
            children.setdefault(rec.parent_path, []).append(rec)
        tables = [r for r in records if r.kind == 'table']
        pending, removals, roles = {}, {}, []

        def table(number):
            require(type(number) is int and 1 <= number <= len(tables), 'table number out of range')
            return tables[number - 1]

        def put(rec, prop, value):
            target = pending.setdefault(rec.path, {})
            require(prop not in target or target[prop] == value, 'conflicting roles at ' + rec.path + ': ' + prop)
            target[prop] = value

        for group in request['groups']:
            _keys(group, ('role', 'table', 'range', 'fontName', 'fontSizePt', 'alignment', 'verticalAlignment', 'trimEmptyParagraphs', 'color', 'italic', 'bold', 'resetIndent', 'paddingMm', 'lineSpacingPercent'), ('role', 'table', 'range'))
            require(isinstance(group['role'], str) and group['role'].strip(), 'role name required')
            bounds = group['range']
            require(isinstance(bounds, list) and len(bounds) == 4 and all(type(v) is int and v >= 1 for v in bounds), 'range is [firstRow, firstColumn, lastRow, lastColumn]')
            top, left, bottom, right = bounds
            require(top <= bottom and left <= right, 'reversed range')
            owner = table(group['table'])
            selected = []
            for row in children.get(owner.path, []):
                for cell in children.get(row.path, []):
                    if cell.kind != 'cell':
                        continue
                    s = cell.summary
                    r, c = s['row'], s['column']
                    r2, c2 = r + s['rowSpan'] - 1, c + s['columnSpan'] - 1
                    if max(top, r) <= min(bottom, r2) and max(left, c) <= min(right, c2):
                        require(top <= r and r2 <= bottom and left <= c and c2 <= right, 'range cuts a merged cell: ' + cell.path)
                        selected.append(cell)
            require(selected and sum(c.summary['rowSpan'] * c.summary['columnSpan'] for c in selected) == (bottom-top+1)*(right-left+1), 'range does not cover existing cells exactly')
            require(type(group.get('trimEmptyParagraphs', False)) is bool, 'trimEmptyParagraphs must be boolean')
            if 'fontName' in group:
                require(isinstance(group['fontName'], str) and bool(group['fontName'].strip()), 'fontName must be nonempty')
            if 'fontSizePt' in group:
                value = group['fontSizePt']
                require(type(value) in (int, float) and math.isfinite(value) and value > 0, 'fontSizePt must be positive')
            for prop, allowed in [('alignment', {'LEFT', 'CENTER', 'RIGHT', 'JUSTIFY', 'DISTRIBUTE', 'DISTRIBUTE_SPACE'}), ('verticalAlignment', {'TOP', 'CENTER', 'BOTTOM'})]:
                if prop in group:
                    require(group[prop] in allowed, 'unsupported ' + prop)
            for cell in selected:
                if 'verticalAlignment' in group:
                    put(cell, 'verticalAlignment', group['verticalAlignment'])
                if 'paddingMm' in group:
                    put(cell, 'paddingMm', group['paddingMm'])
                paragraphs = [r for r in children.get(cell.path, []) if r.kind == 'paragraph']
                # Preserve empty input cells; trim only redundant blank paragraphs
                # in a cell which has actual nonempty content.
                if group.get('trimEmptyParagraphs') and any(p.native.text.strip() for p in paragraphs):
                    for para in paragraphs:
                        if _plain_empty(para.native):
                            removals[para.path] = records.index(para)
                for para in paragraphs:
                    for prop in ('resetIndent', 'lineSpacingPercent'):
                        if prop in group:put(para, prop, group[prop])
                    if 'alignment' in group:
                        put(para, 'alignment', group['alignment'])
                    for run in children.get(para.path, []):
                        if run.kind == 'run':
                            for prop in ('fontName', 'fontSizePt', 'color', 'italic', 'bold'):
                                if prop in group:
                                    put(run, prop, group[prop])
            roles.append({'role': group['role'], 'table': group['table'], 'cells': len(selected)})

        for spec in request.get('rowHeights', []):
            _keys(spec, ('table', 'rows', 'heightMm'), ('table', 'rows', 'heightMm'))
            owner = table(spec['table'])
            rows = [r for r in children.get(owner.path, []) if r.kind == 'row']
            requested = spec['rows']
            require(isinstance(requested, list) and requested and all(type(n) is int and 1 <= n <= len(rows) for n in requested), 'invalid row numbers')
            height = spec['heightMm']
            require(type(height) in (int, float) and math.isfinite(height) and height > 0, 'heightMm must be positive')
            for row in rows:
                for cell in children.get(row.path, []):
                    s = cell.summary
                    if cell.kind == 'cell' and s['rowSpan'] > 1:
                        require(not any(s['row'] <= n < s['row'] + s['rowSpan'] for n in requested), 'height change intersects vertical merge')
            for n in requested:
                put(rows[n - 1], 'heightMm', height)

        commands = []
        for path, props in pending.items():
            if path in removals or any(path.startswith(p + '/') for p in removals):
                continue
            rec = by_path[path]
            changed = {}
            for prop, value in props.items():
                if prop == 'fontName':
                    style = rec.native.style
                    refs = next((h.font_ref_for_face(value) for h in view.document.oxml.headers if h.font_ref_for_face(value) is not None), None)
                    require(refs is not None, 'font is not declared by this document: ' + value)
                    current = value if style is not None and style.child_attributes.get('fontRef') == refs else None
                else:
                    current = rec.summary.get(prop)
                if current != value:
                    changed[prop] = value
            if changed:
                commands.append({'commandId': 'layout-' + str(len(commands)+1), 'op': 'set', 'path': path, 'properties': changed})
        for path in sorted(removals, key=removals.get, reverse=True):
            commands.append({'commandId': 'layout-' + str(len(commands)+1), 'op': 'remove', 'path': path})
        plan = {'schemaVersion': 'hwpx.agent-batch/v1', 'input': {'filename': str(Path(source).resolve())}, 'output': {'filename': str(Path(output).absolute()), 'overwrite': False}, 'commands': commands, 'expectedRevision': view.revision, 'idempotencyKey': 'layout-' + hashlib.sha256(repr(request).encode()).hexdigest()[:24], 'dryRun': False, 'quality': 'transparent', 'verificationRequirements': ['package', 'reopen', 'openSafety', 'semanticDiff', 'bytePreservation']}
        return plan, {'roles': roles, 'commands': len(commands), 'removedEmptyParagraphs': len(removals)}

def apply_layout(source, output, request, dry_run=False):
    from hangul_task import batch, sha, need, stage_directory
    import os
    plan, summary = compile_layout(source, output, request)
    if plan['commands']:
        result = batch(plan, dry_run)
    else:
        # No edit engine call when all roles already match. Exclusive copy only.
        source, output = Path(source), Path(output)
        need(output.suffix.lower() == '.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and source.resolve() != output.resolve(), 'new .hwpx output required')
        data = source.read_bytes()
        original = hashlib.sha256(data).hexdigest()
        need('sha256:' + original == plan['expectedRevision'], 'stale layout revision')
        if not dry_run:
            with stage_directory(output.parent) as folder:
                candidate = Path(folder) / 'stage-0.hwpx'
                candidate.write_bytes(data)
                need(sha(source) == original, 'source changed during layout')
                os.link(candidate, output)
        result = {'status': 'PASS_STRUCTURE', 'documentPublished': not dry_run, 'dryRun': dry_run, 'outputSha256': original, 'noOp': True, 'native': 'NOT_CHECKED'}
    result['layout'] = summary
    return result
