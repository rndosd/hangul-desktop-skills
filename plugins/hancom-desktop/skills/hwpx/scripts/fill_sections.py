"""Repeat or omit whole template sections in fill (two passes).

A manifest may declare sections: a run of top-level paragraphs that holds its own slots and repeats,
such as one activity area under a numbered heading.

    "sections": {"activities": {"label": "활동 영역", "first": "<paragraph path>", "last": "<paragraph path>",
                                "min": 0, "max": 6, "headingText": "운영 개요"}}

Values then give one record per wanted instance, keyed by the section's own input names:

    {"sections": {"activities": [{"task1_title": "...", "task1_details": [...]}, {...}]}}

Pass 1 copies the section's paragraphs once per extra record (in one batch, in order). Pass 2 re-reads the
expanded document, maps every binding to its new place by structure (the n-th record inside the n-th copied
paragraph, never by ids), renumbers circled-number headings in the copies (① → ②), and returns a derived
manifest and flattened values for the normal fill. An empty list removes the section after filling.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

CIRCLED = [chr(c) for c in range(0xF02B1, 0xF02C5)] + [chr(c) for c in range(0x2460, 0x2474)]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _bump(glyph, step):
    if glyph in CIRCLED:
        index = CIRCLED.index(glyph)
        block = 0 if index < 20 else 20
        _require(index - block + step < 20, 'section numbering beyond ⑳')
        return CIRCLED[index + step]
    return glyph


def _top(view):
    return [r for r in view.records if r.kind == 'paragraph' and r.parent_path.count('/') == 1]


def _owner(path, top_paths):
    for index, paragraph in enumerate(top_paths):
        if path == paragraph or path.startswith(paragraph + '/'):
            return index
    raise ValueError('binding outside top-level paragraphs: ' + path)


def section_inputs(manifest, view):
    """Section name -> (first index, last index, slot names, repeat names) in the template."""
    top_paths = [r.path for r in _top(view)]
    result = {}
    for name, spec in manifest.get('sections', {}).items():
        _require(spec['first'] in top_paths and spec['last'] in top_paths, 'section bounds must be top-level paragraphs: ' + name)
        a, b = top_paths.index(spec['first']), top_paths.index(spec['last'])
        _require(a <= b, 'section bounds out of order: ' + name)
        inside = lambda path: a <= _owner(path, top_paths) <= b
        slots = [n for n, s in manifest['slots'].items() if inside(s['path']) and 'valueFrom' not in s]
        repeats = [n for n, r in manifest.get('repeats', {}).items() if inside(r['path'])]
        result[name] = (a, b, slots, repeats)
    spans = sorted((a, b) for a, b, *_ in result.values())
    _require(all(prev[1] < cur[0] for prev, cur in zip(spans, spans[1:])), 'sections must not overlap')
    return result


def describe_sections(manifest, view):
    return {name: {'label': spec.get('label', name), 'min': spec.get('min', 0), 'max': spec.get('max', 1),
                   'inputs': slots + repeats + (['heading'] if spec.get('headingText') else [])}
            for name, spec in manifest.get('sections', {}).items()
            for slots, repeats in [section_inputs(manifest, view)[name][2:]]}


def prepare(manifest, source, values, folder, run_batch, open_view):
    """Return (source, manifest, values, removal paths, summary) for the normal fill."""
    requested = values.get('sections')
    if not requested:
        return source, manifest, values, [], None
    _require(isinstance(requested, dict), 'sections must be an object of lists')
    specs = manifest.get('sections', {})
    _require(set(requested) <= set(specs), 'unknown section: ' + ', '.join(set(requested) - set(specs)))
    with open_view(source) as view:
        layout = section_inputs(manifest, view)
        top = _top(view)
        top_paths = [r.path for r in top]
        records = [r.path for r in view.records]
        revision = view.revision
    plain = {k: v for k, v in values.items() if k != 'sections'}
    shared = {s['valueFrom'] for s in manifest['slots'].values() if 'valueFrom' in s}
    counts = {}
    for name, items in requested.items():
        spec, (a, b, slots, repeats) = specs[name], layout[name]
        _require(isinstance(items, list) and spec.get('min', 0) <= len(items) <= spec.get('max', 1),
                 f"section {name} takes {spec.get('min', 0)}~{spec.get('max', 1)} items")
        allowed = set(slots) | set(repeats) | ({'heading'} if spec.get('headingText') else set())
        for item in items:
            _require(isinstance(item, dict) and set(item) <= allowed, f'unknown input in section {name}: ' + ', '.join(set(item) - allowed))
        # Inputs that other places link to (valueFrom) are shared: a top-level value feeds those links.
        _require(not (set(plain) & (set(slots) | set(repeats)) - shared), f'give inputs of section {name} inside its section records only')
        counts[name] = len(items)

    # Pass 1: copy each repeated section after itself, last section first so earlier positions never move.
    commands, stage = [], source
    for name in sorted(counts, key=lambda n: layout[n][0], reverse=True):
        a, b = layout[name][:2]
        cursor = top_paths[b]
        for _ in range(counts[name] - 1):
            for index in range(a, b + 1):
                identity = f'section-{len(commands) + 1}'
                commands.append({'commandId': identity, 'op': 'copy', 'path': top_paths[index], 'parent': top[index].parent_path,
                                 'position': {'mode': 'after', 'path': cursor}})
                cursor = f'${identity}.path'
    if commands:
        stage = Path(folder) / 'sections.hwpx'
        result = run_batch({'schemaVersion': 'hwpx.agent-batch/v1', 'input': {'filename': str(source)},
                            'output': {'filename': str(stage), 'overwrite': False}, 'commands': commands,
                            'expectedRevision': revision, 'idempotencyKey': 'sections-' + hashlib.sha256(str(counts).encode()).hexdigest()[:16],
                            'dryRun': False, 'quality': 'transparent',
                            'verificationRequirements': ['package', 'reopen', 'openSafety', 'semanticDiff', 'bytePreservation']})
        _require(result.get('ok') and stage.is_file(), 'section copy failed: ' + str(result.get('errors') or result.get('status')))

    # Pass 2: map template records to the expanded document by position.
    def stage_index(i, instance=0):
        shift = sum((counts[n] - 1) * (layout[n][1] - layout[n][0] + 1) for n in counts if layout[n][1] < i and counts[n] > 1)
        for n in counts:
            a, b = layout[n][:2]
            if a <= i <= b:
                before = sum((counts[m] - 1) * (layout[m][1] - layout[m][0] + 1) for m in counts if layout[m][1] < a and counts[m] > 1)
                return a + before + instance * (b - a + 1) + (i - a)
        return i + shift

    with open_view(stage) as expanded:
        new_top = [r.path for r in _top(expanded)]
        new_records = [r.path for r in expanded.records]
        new_revision = expanded.revision
        heading_runs = {}

        def mapped(path, instance=0):
            i = _owner(path, top_paths)
            target = new_top[stage_index(i, instance)]
            if path == top_paths[i]:
                return target
            inner = [p for p in records if p.startswith(top_paths[i] + '/')]
            new_inner = [p for p in new_records if p.startswith(target + '/')]
            _require(len(inner) == len(new_inner), 'copied section changed shape')
            return new_inner[inner.index(path)]

        derived = copy.deepcopy(manifest)
        derived['template'] = dict(manifest['template'], sha256=new_revision.split(':', 1)[1])
        derived['slots'] = {name: dict(s, path=mapped(s['path'])) for name, s in manifest['slots'].items()}
        derived['repeats'] = {name: dict(r, path=mapped(r['path']), fields={k: dict(f, path=mapped(f['path'])) for k, f in r['fields'].items()})
                              for name, r in manifest.get('repeats', {}).items()}
        flat = dict(plain)
        removals = []
        # A linked placement whose source sits in a section would copy one instance's value (the first area's
        # period into the support block). Detach it and feed it the shared top-level value instead.
        in_section = {n: name for name in requested for n in layout[name][2]}
        for alias, s in manifest['slots'].items():
            target = s.get('valueFrom')
            if target in in_section:
                derived['slots'][alias] = {k: v for k, v in derived['slots'][alias].items() if k != 'valueFrom'}
                first = (requested[in_section[target]] or [{}])[0]
                value = plain.get(target, first.get(target, manifest['slots'][target].get('default')))
                if value is not None:
                    flat[alias] = value
        for name, items in requested.items():
            spec, (a, b, slots, repeats) = specs[name], layout[name]
            if not items:
                removals += [new_top[stage_index(i)] for i in range(b, a - 1, -1)]
                for n in slots:
                    derived['slots'].pop(n)
                for n in repeats:
                    derived['repeats'].pop(n)
                continue
            first_runs = [p for p in new_records if p.startswith(new_top[stage_index(a)] + '/') and '/run[' in p.rsplit('/', 1)[-1]]
            for instance, item in enumerate(items):
                tag = '' if instance == 0 else f'@{instance + 1}'
                for n in slots:
                    s = manifest['slots'][n]
                    prefix = s.get('prefix', '')
                    if instance and prefix.lstrip()[:1] in CIRCLED:
                        glyph = prefix.lstrip()[0]
                        prefix = prefix.replace(glyph, _bump(glyph, instance), 1)
                    derived['slots'][n + tag] = dict(s, path=mapped(s['path'], instance), prefix=prefix)
                    if item.get(n) is not None:
                        flat[n + tag] = item[n]
                for n in repeats:
                    r = manifest['repeats'][n]
                    derived['repeats'][n + tag] = dict(r, path=mapped(r['path'], instance),
                                                      fields={k: dict(f, path=mapped(f['path'], instance)) for k, f in r['fields'].items()})
                    if item.get(n) is not None:
                        flat[n + tag] = item[n]
                # Heading: renumber an unbound circled number in copies, and/or replace a fixed heading text.
                heading = new_top[stage_index(a, instance)]
                texts = {r.path: (r.search_text or '') for r in expanded.records if r.path.startswith(heading + '/') and r.path.rsplit('/', 1)[-1].startswith('run[')}
                glyph = next((c for t in texts.values() for c in t.strip()[:1] if c in CIRCLED), None)
                bound = any(manifest['slots'][n].get('prefix', '').lstrip()[:1] in CIRCLED for n in slots)
                renumber = glyph is not None and instance > 0 and not bound
                retitle = bool(spec.get('headingText') and item.get('heading'))
                replacements = {}
                if renumber:
                    replacements[next(p for p, t in texts.items() if glyph in t)] = [(glyph, _bump(glyph, instance))]
                if retitle:
                    run = next(p for p, t in texts.items() if spec['headingText'] in t)
                    replacements.setdefault(run, []).append((spec['headingText'], item['heading']))
                role = next(iter(manifest['slots'].values()))['role']
                for run, pairs in replacements.items():
                    # One binding per run: when number and title share a run, replace the span covering both.
                    text = texts[run]
                    start = min(text.index(old) for old, _ in pairs)
                    end = max(text.index(old) + len(old) for old, _ in pairs)
                    marker, value = text[start:end], text[start:end]
                    for old, new in pairs:
                        value = value.replace(old, new, 1)
                    key = f'_heading@{name}{tag}@{len(derived["slots"])}'
                    derived['slots'][key] = {'path': run, 'role': role, 'marker': marker, 'prefix': '', 'suffix': ''}
                    flat[key] = value
        # Fixed slots keep their defaults; slots only reachable through sections must not be filled twice.
        return stage, derived, flat, removals, {name: len(items) for name, items in requested.items()}
