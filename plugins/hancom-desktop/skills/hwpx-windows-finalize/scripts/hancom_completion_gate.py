"""Bind COM candidate/native/PDF verification to actual bytes; never invokes COM.

prepare: before COM, freeze candidate hash and planned new output/run paths.
collect: verify native receipt and capture XML differences + PDF page renders.
check: recheck bytes and require specific performed preservation/visual reviews.
This gate verifies the candidate-to-native stage, not an earlier content edit.
Review records are attestations, not proof that a person actually looked.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import posixpath
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

SCHEMA = 'hwpx.completion-gate.v1'
CHECKS = ('content_and_counts', 'non_target_structure', 'formatting_and_assets')


class GateError(Exception):
    def __init__(self, reason, state='blocked'):
        self.reason, self.state = reason, state


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_digest(data):
    return digest(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8'))


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        raise GateError(f'missing:{path}', 'pending')
    except (ValueError, OSError):
        raise GateError(f'unreadable_json:{path}')


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def ref(path):
    p = Path(path).resolve()
    if not p.is_file():
        raise GateError(f'missing:{p}', 'pending')
    return {'path': str(p), 'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}


def require(condition, reason, state='blocked'):
    if not condition:
        raise GateError(reason, state)


def verify_ref(item):
    require(ref(item['path']) == item, f'file_changed:{item["path"]}')


def read_package(path):
    """Read all XML nodes and binary hashes. Do not silently omit layout nodes."""
    with ZipFile(path) as z:
        require(z.testzip() is None, 'corrupt_hwpx')
        require(len(z.namelist()) == len(set(z.namelist())), 'duplicate_zip_entries')
        section_inventory = {n for n in z.namelist() if n.startswith('Contents/section') and n.endswith('.xml')}
        require(bool(section_inventory), 'missing_hwpx_sections')
        require('Contents/content.hpf' in z.namelist(), 'missing_manifest_spine')
        package = ET.fromstring(z.read('Contents/content.hpf'))
        manifest = {}
        for item in package.findall('{*}manifest/{*}item'):
            identity, href = item.get('id'), item.get('href', '')
            require(bool(identity) and identity not in manifest, 'invalid_manifest_identity')
            resolved = href if href in z.namelist() else posixpath.normpath(posixpath.join('Contents', href))
            manifest[identity] = resolved
        sections = []
        for item in package.findall('{*}spine/{*}itemref'):
            require(item.get('idref') in manifest, 'unknown_spine_reference')
            name = manifest[item.get('idref')]
            if name in section_inventory:
                sections.append(name)
        require(len(sections) == len(section_inventory) and set(sections) == section_inventory, 'incomplete_or_duplicate_section_spine')
        flat, texts, counts, binaries = {}, [], Counter(), {}
        controls = {}
        for name in sorted(z.namelist()):
            if name.endswith('/'):
                continue
            raw = z.read(name)
            if name.startswith('BinData/'):
                binaries[name] = digest(raw)
            if name.endswith(('.xml', '.hpf')):
                root = ET.fromstring(raw)
                def walk(node, location):
                    # Ignore serializer indentation, retain text in visible text nodes.
                    tag = node.tag.rsplit('}', 1)[-1]
                    text = node.text if tag == 't' or (node.text and node.text.strip()) else None
                    flat[location] = {'tag': node.tag, 'attributes': dict(node.attrib), 'text': text}
                    for i, child in enumerate(node):
                        walk(child, f'{location}/{i}')
                walk(root, name)
            else:
                flat[name] = {'sha256': digest(raw)}
        for name in sections:
            controls[name] = []
            def control_tree(node):
                return [node.tag, dict(node.attrib),
                        node.text if node.text and node.text.strip() else None,
                        [control_tree(child) for child in node]]
            for node in ET.fromstring(z.read(name)).iter():
                kind = node.tag.rsplit('}', 1)[-1]
                if kind == 'ctrl':
                    controls[name].append(control_tree(node))
                if kind == 't':
                    texts.append(node.text or '')
                if kind in ('p', 'tbl', 'pic'):
                    counts[kind] += 1
    references = {}
    for location, node in flat.items():
        for key, identity in node.get('attributes', {}).items():
            if key.rsplit('}', 1)[-1] == 'binaryItemIDRef':
                if not identity:
                    references[location+'/'+key] = None
                else:
                    require(identity in manifest and manifest[identity] in binaries, 'unresolved_binary_reference')
                    references[location+'/'+key] = binaries[manifest[identity]]
    return {'flat': flat, 'texts': texts, 'counts': dict(counts), 'sections': sections,
            'binaries': binaries, 'binaryPayloads': sorted(binaries.values()), 'binaryReferences': references,
            'controls': controls}


def compare(source, final):
    a, b = read_package(source), read_package(final)
    changes = [{'path': k, 'before': a['flat'].get(k), 'after': b['flat'].get(k)}
               for k in sorted(a['flat'].keys() | b['flat'].keys()) if a['flat'].get(k) != b['flat'].get(k)]
    invariants = {key: a[key] == b[key] for key in ('texts', 'counts', 'sections', 'binaryPayloads', 'binaryReferences', 'controls')}
    def member(location):
        for extension in ('.xml', '.hpf'):
            if extension in location:
                return location.split(extension, 1)[0] + extension
        return location
    return {'invariants': invariants, 'beforeCounts': a['counts'], 'afterCounts': b['counts'],
            'binaryPathsEqual': a['binaries'] == b['binaries'],
            'changedMembers': sorted({member(x['path']) for x in changes}),
            'changes': changes}


def prepare(bundle, source, final, pdf, run):
    paths = [Path(x).resolve() for x in (source, final, pdf, run, bundle)]
    require(len(set(paths)) == len(paths), 'paths_must_differ')
    src, dst, pdf_path, run_path, root = paths
    require(src.suffix.lower() == '.hwpx' and dst.suffix.lower() == '.hwpx' and pdf_path.suffix.lower() == '.pdf', 'invalid_extensions')
    source_ref = ref(src)
    for p in (dst, pdf_path, run_path, root):
        require(not p.exists(), f'planned_path_already_exists:{p}')
    root.mkdir(parents=True)
    plan = {'schema': SCHEMA, 'scope': 'COM_candidate_to_native_and_pdf', 'source': source_ref,
            'final': str(dst), 'pdf': str(pdf_path), 'run': str(run_path),
            'requiredChecks': list(CHECKS) + ['all_pdf_pages_visual'], 'status': 'pending'}
    write_new(root / 'plan.json', plan)
    return {'schema': SCHEMA, 'status': 'pending', 'reason': 'COM_and_followup_checks_not_performed', 'bundle': str(root)}


def native_evidence(plan):
    verify_ref(plan['source'])
    run = Path(plan['run'])
    receipt, job = load(run / 'receipt.json'), load(run / 'job.json')
    general = receipt.get('evidenceSchema') == 'hwpx.hancom-finalize.v2'
    require(receipt.get('status') == ('PASS_FULL' if general else 'PASS_COM') and receipt.get('sourceUnchanged') is True, 'COM_not_successful')
    require(Path(job['input']).resolve() == Path(plan['source']['path']) and Path(job['output']).resolve() == Path(plan['final']) and Path(job['pdf']).resolve() == Path(plan['pdf']), 'COM_job_path_mismatch')
    worker = receipt if general else (receipt.get('worker') or {})
    if general:
        require(receipt.get('sourceSha256Before', '').lower() == receipt.get('sourceSha256After', '').lower() == plan['source']['sha256'], 'COM_source_hash_mismatch')
        require(Path(receipt['candidatePath']).resolve() == Path(plan['source']['path']) and Path(receipt['finalPath']).resolve() == Path(plan['final']), 'COM_receipt_path_mismatch')
        require(receipt.get('mode') == 'SaveAs' and worker.get('cleanup', {}).get('owned') is True, 'COM_general_scope_or_ownership_mismatch')
    require(all(worker.get(k) is True for k in ('firstOpen', 'saveAs', 'reopen', 'pdfExport')), 'COM_steps_not_performed')
    require(worker.get('cleanup', {}).get('quit') is True and receipt.get('cleanup', {}).get('forced') is False and receipt.get('cleanup', {}).get('remaining') == [], 'COM_cleanup_incomplete')
    final, pdf = ref(plan['final']), ref(plan['pdf'])
    for item in (final, pdf):
        matches = [x for x in receipt.get('artifacts', []) if Path(x['path']).resolve() == Path(item['path'])]
        require(len(matches) == 1 and matches[0].get('sha256', '').lower() == item['sha256'] and matches[0].get('bytes') == item['bytes'], 'COM_artifact_hash_mismatch')
    return {'source': plan['source'], 'final': final, 'pdf': pdf,
            'receipt': ref(run / 'receipt.json'), 'job': ref(run / 'job.json')}


def collect(bundle):
    root = Path(bundle).resolve()
    plan = load(root / 'plan.json')
    require(plan.get('schema') == SCHEMA, 'wrong_plan_schema')
    refs = native_evidence(plan)
    differences = compare(plan['source']['path'], plan['final'])
    # Import only here: missing renderer remains pending, never a visual pass.
    try:
        import pymupdf
    except ImportError:
        raise GateError('missing_dependency:pymupdf', 'pending')
    require(not (root / 'evidence.json').exists() and not (root / 'pages').exists(), 'evidence_already_exists')
    (root / 'pages').mkdir()
    pages = []
    with pymupdf.open(plan['pdf']) as doc:
        require(len(doc) > 0, 'empty_pdf')
        for i, page in enumerate(doc):
            out = root / 'pages' / f'{i+1:04d}.png'
            page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(out)
            pages.append({'page': i+1, 'image': ref(out), 'extractedTextSha256': digest(page.get_text().encode('utf-8'))})
    write_new(root / 'differences.json', differences)
    evidence = {'schema': SCHEMA, 'plan': ref(root / 'plan.json'), 'artifacts': refs,
                'comparison': ref(root / 'differences.json'), 'comparisonDigest': json_digest(differences),
                'pages': pages, 'render': {'performed': True, 'engine': 'pymupdf', 'version': pymupdf.VersionBind, 'scale': 1.5},
                'inspection_state': 'not_checked'}
    write_new(root / 'evidence.json', evidence)
    review = {'schema': SCHEMA, 'evidence': ref(root / 'evidence.json'), 'reviewer': '', 'reviewedAt': '',
              'preservation': {'performed': False, 'comparisonDigest': evidence['comparisonDigest'],
                               'checks': {x: {'outcome': 'not_checked', 'observation': ''} for x in CHECKS},
                               'reviewedMembers': [{'member': x, 'reason': ''} for x in differences['changedMembers']]},
              'visual': {'performed': False, 'pdf': refs['pdf'], 'pages': [dict(page=x['page'], image=x['image'], outcome='not_checked', observation='') for x in pages]}}
    write_new(root / 'review-template.json', review)
    invariant_pass = all(differences['invariants'].values())
    return {'schema': SCHEMA, 'status': 'pending' if invariant_pass else 'blocked',
            'reason': 'preservation_and_visual_reviews_not_checked' if invariant_pass else 'native_content_counts_or_assets_changed',
            'failedInvariants': [key for key, passed in differences['invariants'].items() if not passed],
            'evidence': ref(root / 'evidence.json')}


def check(bundle, review_path):
    root = Path(bundle).resolve()
    plan, evidence = load(root / 'plan.json'), load(root / 'evidence.json')
    require(plan.get('schema') == evidence.get('schema') == SCHEMA, 'wrong_schema')
    verify_ref(evidence['plan'])
    require(native_evidence(plan) == evidence['artifacts'], 'native_evidence_changed')
    verify_ref(evidence['comparison'])
    differences = compare(plan['source']['path'], plan['final'])
    require(differences['invariants']['controls'], 'native_control_elements_changed')
    require(all(differences['invariants'].values()), 'native_content_counts_or_assets_changed')
    require(json_digest(differences) == evidence['comparisonDigest'] and load(evidence['comparison']['path']) == differences, 'comparison_changed')
    require(evidence.get('render', {}).get('performed') is True and bool(evidence.get('pages')), 'render_not_performed', 'pending')
    # Re-render from the current PDF to establish image/PDF linkage, not just PNG existence.
    try:
        import pymupdf
    except ImportError:
        raise GateError('missing_dependency:pymupdf', 'pending')
    with pymupdf.open(plan['pdf']) as doc:
        require(len(doc) == len(evidence['pages']), 'page_inventory_mismatch')
        for number, (page, saved) in enumerate(zip(doc, evidence['pages']), 1):
            require(saved['page'] == number, 'page_order_mismatch')
            verify_ref(saved['image'])
            require(digest(page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes('png')) == saved['image']['sha256'], 'render_does_not_match_pdf')
    review = load(review_path)
    require(review.get('schema') == SCHEMA and review.get('evidence') == ref(root / 'evidence.json'), 'review_not_bound_to_evidence')
    require(bool(str(review.get('reviewer', '')).strip()) and bool(str(review.get('reviewedAt', '')).strip()), 'review_identity_missing', 'pending')
    preservation, visual = review.get('preservation', {}), review.get('visual', {})
    require(preservation.get('performed') is True and visual.get('performed') is True, 'reviews_not_performed', 'pending')
    require(preservation.get('comparisonDigest') == evidence['comparisonDigest'], 'review_comparison_mismatch')
    for name in CHECKS:
        item = preservation.get('checks', {}).get(name, {})
        require(item.get('outcome') != 'fail', f'preservation_failed:{name}')
        require(item.get('outcome') == 'pass' and len(str(item.get('observation', '')).strip()) >= 12, f'preservation_not_checked:{name}', 'pending')
    reviewed = preservation.get('reviewedMembers', [])
    require(sorted(x['member'] for x in reviewed) == differences['changedMembers'] and all(len(str(x.get('reason', '')).strip()) >= 12 for x in reviewed), 'unreviewed_structural_differences', 'pending')
    require(visual.get('pdf') == evidence['artifacts']['pdf'], 'visual_pdf_mismatch')
    require(len(visual.get('pages', [])) == len(evidence['pages']), 'visual_pages_missing', 'pending')
    for actual, recorded in zip(evidence['pages'], visual['pages']):
        require(recorded.get('page') == actual['page'] and recorded.get('image') == actual['image'], 'visual_page_binding_mismatch')
        require(recorded.get('outcome') != 'fail', 'visual_review_failed')
        require(recorded.get('outcome') == 'pass' and len(str(recorded.get('observation', '')).strip()) >= 12, 'visual_page_not_checked', 'pending')
    return {'schema': SCHEMA, 'status': 'complete', 'scope': plan['scope'], 'artifacts': evidence['artifacts'],
            'evidence': ref(root / 'evidence.json'), 'review': ref(review_path),
            'limitation': 'Recorded reviews are attestations; this is not authentication of a reviewer or validation of an earlier edit.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    for name in ('bundle', 'source', 'final', 'pdf', 'run'):
        prep.add_argument('--'+name, required=True, type=Path)
    col = sub.add_parser('collect')
    col.add_argument('--bundle', required=True, type=Path)
    chk = sub.add_parser('check')
    chk.add_argument('--bundle', required=True, type=Path)
    chk.add_argument('--review', required=True, type=Path)
    chk.add_argument('--output', type=Path)
    args = p.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.bundle, args.source, args.final, args.pdf, args.run)
        elif args.command == 'collect':
            result = collect(args.bundle)
        else:
            if args.output:
                require(not args.output.exists(), 'output_already_exists')
            result = check(args.bundle, args.review)
    except GateError as error:
        result = {'schema': SCHEMA, 'status': error.state, 'reason': error.reason}
    except Exception as error:
        result = {'schema': SCHEMA, 'status': 'blocked', 'reason': 'invalid_or_unreadable_evidence', 'error': type(error).__name__}
    if args.command == 'check' and args.output and not args.output.exists():
        write_new(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {'complete': 0, 'pending': 2, 'blocked': 3}[result['status']]


if __name__ == '__main__':
    sys.exit(main())
