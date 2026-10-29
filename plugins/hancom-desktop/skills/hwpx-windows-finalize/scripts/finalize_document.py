"""Run one native SaveAs job and collect evidence, then check an explicit review.

Repeating run inspects the same request and evidence without repeating COM.
Only check can return complete, after the existing completion gate validates
the current artifacts and the supplied preservation and per-page review.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

import hancom_completion_gate as gate
import run_native_job as native

SCHEMA = 'hangul.finalize-document.v1'


def _request(source, final, pdf, bundle, context, timeout):
    gate.require(context in ('ordinary-shell', 'host-approved'), 'invalid_execution_context')
    gate.require(type(timeout) is int and 10 <= timeout <= 300, 'invalid_timeout')
    source, final, pdf, bundle = (Path(p).resolve() for p in (source, final, pdf, bundle))
    gate.require(source.suffix.lower() == final.suffix.lower() == '.hwpx'
                 and pdf.suffix.lower() == '.pdf', 'invalid_extensions')
    gate.require(len({source, final, pdf, bundle}) == 4, 'paths_must_differ')
    gate.require(not source.is_relative_to(bundle), 'source_inside_evidence_bundle')
    return {
        'schema': SCHEMA, 'source': gate.ref(source), 'final': str(final),
        'pdf': str(pdf), 'bundle': str(bundle), 'context': context, 'timeout': timeout,
    }


def _plan(request):
    root = Path(request['bundle'])
    plan = gate.load(root / 'plan.json')
    gate.require(plan.get('schema') == gate.SCHEMA, 'wrong_plan_schema')
    expected = {
        'source': request['source'], 'final': request['final'], 'pdf': request['pdf'],
        'run': str(root / 'runner' / 'native'),
    }
    gate.require(all(plan.get(key) == value for key, value in expected.items()),
                 'native_plan_request_mismatch')
    return plan


def _collected_status(root, plan):
    evidence = gate.load(root / 'evidence.json')
    gate.require(evidence.get('schema') == gate.SCHEMA, 'wrong_evidence_schema')
    gate.require(evidence.get('plan') == gate.ref(root / 'plan.json'), 'evidence_plan_mismatch')
    gate.require(evidence.get('artifacts') == gate.native_evidence(plan), 'native_evidence_changed')
    gate.verify_ref(evidence['comparison'])
    differences = gate.load(evidence['comparison']['path'])
    gate.require(gate.json_digest(differences) == evidence.get('comparisonDigest'),
                 'comparison_changed')
    gate.require(evidence.get('render', {}).get('performed') is True
                 and bool(evidence.get('pages')), 'render_not_performed', 'pending')
    for page in evidence['pages']:
        gate.verify_ref(page['image'])
    failed = [key for key, passed in differences['invariants'].items() if not passed]
    return {
        'status': 'blocked' if failed else 'pending',
        'reason': ('native_content_counts_or_assets_changed' if failed
                   else 'preservation_and_visual_reviews_not_checked'),
        'failedInvariants': failed, 'evidence': gate.ref(root / 'evidence.json'),
        'comparisonReusedForStatusOnly': True,
    }


def run(source, final, pdf, bundle, context, timeout=120):
    """Create one native job, or inspect its matching immutable request on retry."""
    request = _request(source, final, pdf, bundle, context, timeout)
    root = Path(request['bundle'])
    reused = root.exists()
    if reused:
        gate.require(gate.load(root / 'request.json') == request, 'request_mismatch')
        plan = _plan(request)
    else:
        gate.prepare(root, request['source']['path'], request['final'], request['pdf'],
                     root / 'runner' / 'native')
        gate.write_new(root / 'request.json', request)
        plan = _plan(request)
        native.run(request['source']['path'], 'SaveAs', request['final'], request['pdf'],
                   root / 'runner', context, timeout)

    runner_result = root / 'runner' / 'runner-result.json'
    common = {'schema': SCHEMA, 'bundle': str(root), 'reused': reused,
              'automaticNativeRetry': False}
    if not runner_result.is_file():
        return {**common, 'status': 'blocked', 'reason': 'native_result_unresolved',
                'nextStep': 'Inspect the owned job and artifacts before starting another native job.'}
    result = gate.load(runner_result)
    if result.get('status') != 'PASS_NATIVE' or result.get('sourceUnchanged') is not True:
        return {**common, 'status': 'blocked', 'reason': 'native_job_not_successful',
                'nativeStatus': result.get('status'), 'runnerResult': gate.ref(runner_result)}

    gate.native_evidence(plan)
    if not (root / 'evidence.json').exists():
        gate.require(not any((root / name).exists() for name in
                             ('pages', 'differences.json', 'review-template.json')),
                     'partial_collection_requires_inspection')
        collected = gate.collect(root)
    else:
        collected = _collected_status(root, plan)
    return {**common, **collected, 'schema': SCHEMA,
            'nativeStatus': result['status'], 'reviewTemplate': str(root / 'review-template.json'),
            'nextStep': 'Review differences and every PDF page, then run check with that review.'}


def check(bundle, review):
    """Revalidate current bytes and an explicit review; never reuse a past verdict."""
    root = Path(bundle).resolve()
    saved = gate.load(root / 'request.json')
    gate.require(saved.get('schema') == SCHEMA, 'wrong_request_schema')
    current = _request(saved['source']['path'], saved['final'], saved['pdf'], root,
                       saved['context'], saved['timeout'])
    gate.require(current == saved, 'request_mismatch')
    _plan(current)
    return gate.check(root, review)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    launch = sub.add_parser('run')
    launch.add_argument('source', type=Path)
    for name in ('final', 'pdf', 'bundle'):
        launch.add_argument('--' + name, required=True, type=Path)
    launch.add_argument('--context', required=True, choices=['ordinary-shell', 'host-approved'])
    launch.add_argument('--timeout', type=int, default=120)
    review = sub.add_parser('check')
    review.add_argument('--bundle', required=True, type=Path)
    review.add_argument('--review', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'run':
            result = run(args.source, args.final, args.pdf, args.bundle, args.context, args.timeout)
        else:
            result = check(args.bundle, args.review)
    except gate.GateError as error:
        result = {'schema': SCHEMA, 'status': error.state, 'reason': error.reason}
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'schema': SCHEMA, 'status': 'blocked', 'reason': 'invalid_or_unreadable_job',
                  'error': str(error), 'errorType': type(error).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {'complete': 0, 'pending': 2, 'blocked': 3}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
