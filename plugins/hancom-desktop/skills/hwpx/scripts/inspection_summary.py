"""Compact views of existing inspection results; never read or edit a document."""
from collections import Counter
from pathlib import Path
import hashlib
import json


def text_summary(value, output):
    inspections = value if isinstance(value, list) else [value]
    queries = []
    for index, item in enumerate(inspections):
        targets = item['targets']
        supported = [t for t in targets if t['supported']]
        reasons = Counter(t['reason'] for t in targets if not t['supported'])
        queries.append(dict(query=index, find=item['find'], total=item['total'],
                            inspectionTruncated=item['truncated'],
                            supportedInInspection=len(supported), unsupportedReasons=dict(reasons),
                            candidates=[{k: t[k] for k in ('target_id', 'scope', 'supported', 'reason', 'context')}
                                        for t in targets[:3]],
                            additionalCandidatesInFile=max(0, len(targets)-3),
                            route='text-plan → text' if supported else None,
                            nextStep=('Review explicit target IDs in this inspection; no repeat inspection needed.'
                                      if supported else
                                      'No supported selected-text target here. Read the reason and the operation-specific route; do not auto-retry.')))
    return dict(status='INSPECTED', inspectionPath=str(Path(output).absolute()),
                sourceSha256=inspections[0]['source_sha256'], queries=queries,
                native='NOT_CHECKED')


def body_summary(value, output, find=None):
    paragraphs = value['paragraphs']
    matched = [p for p in paragraphs if find is None or find in p['binding']['text']]
    return dict(status='INSPECTED', inspectionPath=str(Path(output).absolute()),
                sourceSha256=value['sourceSha256'], paragraphCount=len(paragraphs),
                matchedParagraphCount=len(matched),
                paragraphs=[{k: p[k] for k in ('binding', 'cloneEligibility', 'directRunTextEdit')}
                            for p in matched[:8]],
                additionalParagraphsInFile=max(0, len(matched)-8),
                nextStep='Reuse the saved bindings. Clone eligibility and direct-run text candidates are different operations; batch still verifies support and preservation.',
                native='NOT_CHECKED')


def plan_summary(value, output):
    return dict(status='PLANNED', planPath=str(Path(output).absolute()),
                sourceSha256=value['source_sha256'], selectedEdits=len(value['edits']),
                route='text --plan', native='NOT_CHECKED')


def edit_summary(value, receipt):
    """Present a bounded view; all diagnostics remain in the linked full receipt."""
    summary = {key: value[key] for key in (
        'status', 'ok', 'rolledBack', 'dryRun', 'documentPublished', 'native',
        'inputRevision', 'documentRevision', 'sourceSha256', 'outputSha256',
        'output', 'noOp', 'selected_edits', 'reason', 'errorType', 'nextStep',
        'source_sha256', 'output_sha256', 'published', 'changed_runs', 'replacements',
    ) if key in value}
    summary['receiptPath'] = str(Path(receipt).absolute())
    commands = value.get('commandResults', [])
    if commands:
        summary['commands'] = {'total': len(commands),
                               'failed': sum(command.get('ok') is False for command in commands)}
    if 'stages' in value:
        summary['stageCount'] = len(value['stages'])
    if 'layout' in value:
        layout = value['layout']
        summary['layout'] = {key: layout[key] for key in ('commands', 'removedEmptyParagraphs') if key in layout}
        summary['layout']['roleCount'] = len(layout.get('roles', []))

    diagnostics = {'errors': {}, 'warnings': {}, 'followUp': {}}
    names = {'errors': 'errors', 'error': 'errors', 'warnings': 'warnings',
             'layout_follow_up': 'followUp'}

    def walk(node, path='result'):
        if isinstance(node, dict):
            for key, item in node.items():
                if key in names and item:
                    group = diagnostics[names[key]]
                    for message in item if isinstance(item, list) else [item]:
                        encoded = json.dumps(message, ensure_ascii=False, sort_keys=True)
                        group.setdefault(encoded, {'at': path + '.' + key,
                                                   'detail': message if len(encoded) <= 600 else encoded[:600] + '… (see receipt)'})
                else:
                    walk(item, path + '.' + key)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f'{path}[{index}]')

    walk(value)
    for name, entries in diagnostics.items():
        if entries:
            summary[name] = {'count': len(entries), 'items': list(entries.values())[:6],
                             'additionalInReceipt': max(0, len(entries) - 6)}
    return summary


def saved_edit_summary(value, output):
    """Archive an immutable receipt without changing a completed edit's status."""
    try:
        if not output:
            raise ValueError('output filename unavailable')
        data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        target = Path(output).absolute()
        receipt = target.with_name(target.name + '.receipt.' + hashlib.sha256(data).hexdigest()[:16] + '.json')
        if receipt.is_symlink():
            raise ValueError('receipt path is a symbolic link')
        try:
            with receipt.open('xb') as stream:
                stream.write(data)
        except FileExistsError:
            if receipt.read_bytes() != data:
                raise ValueError('receipt name collision; existing file preserved')
        summary = edit_summary(value, receipt)
        summary.setdefault('output', {'filename': str(target)})
        return summary
    except (OSError, ValueError) as exc:
        # The document may already have been published. Never report that edit
        # as rolled back or encourage a rerun just because presentation failed.
        return dict(value, receiptWarning=f'Full result printed because receipt storage failed: {exc}. Check documentPublished/output before any retry.')
