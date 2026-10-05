"""Compare resolved border-fill uses, not definition numbers. Read-only.

Scope: section borderFillIDRef and section charPrIDRef/paraPrIDRef consumers.
Other style inheritance and rendered placement remain outside this check.
"""
import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import hancom_completion_gate as g


def local(tag):
    return tag.rsplit('}', 1)[-1]


def inventory(path):
    package = g.read_package(path)
    with ZipFile(path) as z:
        header = ET.fromstring(z.read('Contents/header.xml'))
        definitions = {name: {} for name in ('borderFill', 'charPr', 'paraPr')}
        for node in header.iter():
            kind = local(node.tag)
            if kind in definitions:
                identity = node.get('id')
                g.require(identity is not None and identity not in definitions[kind], 'duplicate_or_missing_style_identity')
                definitions[kind][identity] = node
        # Resolve binary references through the already validated manifest map.
        binary_lookup = {}
        def bind(node, location):
            for key in node.attrib:
                if local(key) == 'binaryItemIDRef':
                    binary_lookup[id(node), key] = package['binaryReferences'][location+'/'+key]
            for i, child in enumerate(node):
                bind(child, location+'/'+str(i))
        bind(header, 'Contents/header.xml')

        def canonical(node, root=False):
            attrs = {}
            for key, value in node.attrib.items():
                if root and key == 'id':
                    continue
                if local(key) == 'binaryItemIDRef':
                    value = binary_lookup[id(node), key]
                attrs[key] = value
            return [node.tag, attrs, node.text.strip() if node.text and node.text.strip() else None,
                    [canonical(child) for child in node]]

        def border(identity):
            g.require(identity in definitions['borderFill'], 'unresolved_border_fill')
            node = definitions['borderFill'][identity]
            return {'definitionSha256': g.json_digest(canonical(node, True)),
                    'payloads': [binary_lookup[id(n), k] for n in node.iter() for k in n.attrib if local(k) == 'binaryItemIDRef']}

        def resolve(attribute, identity):
            if attribute == 'borderFillIDRef':
                return [{'definitionPath': 'self', **border(identity)}]
            kind = {'charPrIDRef': 'charPr', 'paraPrIDRef': 'paraPr'}[attribute]
            g.require(identity in definitions[kind], 'unresolved_style_consumer')
            found = []
            def walk(node, location):
                for key, value in node.attrib.items():
                    if local(key) == 'borderFillIDRef':
                        found.append({'definitionPath': location+'/'+key, **border(value)})
                for i, child in enumerate(node):
                    walk(child, location+'/'+str(i))
            walk(definitions[kind][identity], kind)
            return found

        uses = {}
        for member in package['sections']:
            def walk(node, location):
                for key, value in node.attrib.items():
                    if local(key) in ('borderFillIDRef', 'charPrIDRef', 'paraPrIDRef'):
                        uses[location+'/'+key] = resolve(local(key), value)
                # Same-tag sibling ordinals avoid shifts from unrelated tags, but
                # intentionally do not collapse empty runs or merge consumers.
                counts = {}
                for child in node:
                    counts[child.tag] = counts.get(child.tag, 0)+1
                    walk(child, location+'/'+child.tag+'['+str(counts[child.tag])+']')
            root = ET.fromstring(z.read(member))
            walk(root, member+'/'+root.tag)
    return uses


def compare(source, final):
    source_ref, final_ref = g.ref(source), g.ref(final)
    a, b = inventory(source), inventory(final)
    changes = [{'consumer': key, 'before': a.get(key), 'after': b.get(key)}
               for key in sorted(a.keys() | b.keys()) if a.get(key) != b.get(key)]
    image_a = {k:v for k,v in a.items() if any(any(x['payloads']) for x in v)}
    image_b = {k:v for k,v in b.items() if any(any(x['payloads']) for x in v)}
    g.verify_ref(source_ref)
    g.verify_ref(final_ref)
    return {'schema': 'hwpx.border-fill-usage.v1', 'status': 'scoped_equal' if not changes else 'unresolved_or_changed',
            'source': source_ref, 'final': final_ref, 'beforeConsumers': len(a), 'afterConsumers': len(b),
            'changedConsumers': len(changes), 'changes': changes,
            'imageConsumers': {'before': len(image_a), 'after': len(image_b), 'bindingsEqual': image_a == image_b},
            'limitation': 'Direct and charPr/paraPr border-fill bindings only; not full style inheritance or rendered placement. Does not grant completion.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('final', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    g.require(not args.output.exists(), 'output_already_exists')
    result = compare(args.source, args.final)
    g.write_new(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'changes'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
