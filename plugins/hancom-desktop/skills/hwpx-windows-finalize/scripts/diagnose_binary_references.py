"""Read-only asset-reference diagnosis. Never grants completion or edits HWPX.

Separate serializer paths from owning pic/borderFill subtrees. Owner order is
diagnostic only: it does not prove document placement or style-use preservation.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import hancom_completion_gate as gate


def inventory(path):
    package = gate.read_package(path)
    records = []
    with ZipFile(path) as archive:
        for member in sorted(archive.namelist()):
            if not member.endswith('.xml'):
                continue
            root = ET.fromstring(archive.read(member))
            owners = Counter()

            def normalized(node, location):
                attrs = dict(node.attrib)
                for key in attrs:
                    if key.rsplit('}', 1)[-1] == 'binaryItemIDRef':
                        attrs[key] = package['binaryReferences'][location + '/' + key]
                return [node.tag, attrs,
                        node.text if node.tag.rsplit('}', 1)[-1] == 't' or (node.text and node.text.strip()) else None,
                        [normalized(child, location + '/' + str(i)) for i, child in enumerate(node)]]

            def walk(node, location, owner=None):
                tag = node.tag.rsplit('}', 1)[-1]
                if tag in ('pic', 'borderFill'):
                    owners[node.tag] += 1
                    owner = {'kind': node.tag, 'ordinal': owners[node.tag],
                             'subtreeSha256': gate.json_digest(normalized(node, location))}
                for key in node.attrib:
                    if key.rsplit('}', 1)[-1] == 'binaryItemIDRef':
                        records.append({'member': member, 'path': location + '/' + key,
                                        'payload': package['binaryReferences'][location + '/' + key],
                                        'owner': owner})
                for i, child in enumerate(node):
                    walk(child, location + '/' + str(i), owner)
            walk(root, member)
    return records


def diagnose(source, final):
    before_ref, after_ref = gate.ref(source), gate.ref(final)
    before, after = inventory(source), inventory(final)
    # Pair by member and owning object order, not raw child-index location.
    # Ambiguous multiple references and unrecognized owners stay unresolved.
    def group(records):
        groups = {}
        for item in records:
            owner = item['owner']
            key = (item['member'], owner['kind'], owner['ordinal']) if owner else (item['member'], 'unknown', item['path'])
            groups.setdefault(key, []).append(item)
        return groups
    a, b = group(before), group(after)
    findings = []
    for key in sorted(a.keys() | b.keys()):
        left, right = a.get(key, []), b.get(key, [])
        state = 'unresolved_owner_or_reference_count'
        if len(left) == len(right) == 1 and left[0]['owner'] and right[0]['owner']:
            x, y = left[0], right[0]
            if x['payload'] != y['payload']:
                state = 'payload_changed_at_owner_ordinal'
            elif x['owner']['subtreeSha256'] != y['owner']['subtreeSha256']:
                state = 'owner_subtree_changed'
            elif x['path'] != y['path']:
                state = 'identical_owner_subtree_at_different_xml_path'
            else:
                state = 'identical_owner_subtree_and_path'
        findings.append({'key': list(key), 'classification': state, 'before': left, 'after': right})
    gate.verify_ref(before_ref)
    gate.verify_ref(after_ref)
    return {'schema': 'hwpx.binary-reference-diagnosis.v1', 'status': 'diagnostic_only',
            'source': before_ref, 'final': after_ref,
            'summary': dict(Counter(item['classification'] for item in findings)),
            'findings': findings,
            'limitation': 'Owner ordinals and subtree equality do not prove placement or style-use preservation. Completion gate is unchanged.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('final', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    gate.require(not args.output.exists(), 'output_already_exists')
    result = diagnose(args.source, args.final)
    gate.write_new(args.output, result)
    print(json.dumps({'status': result['status'], 'summary': result['summary'], 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
