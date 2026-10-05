from workspace_candidate_directory import workspace_candidate_directory
# SPDX-License-Identifier: Apache-2.0
"""Restricted existing rectangular table edits via python-hwpx public primitives.
No direct XML writes. All unrequested XML and package payloads are verified.
"""

def _require(condition, message):
    if not condition:
        raise ValueError(message)
import pathlib, json, hashlib, zipfile, io, tempfile, os, math, argparse
from lxml import etree as E
from importlib.metadata import version
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_editor_open_safety
HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
P = '{' + HP + '}'
SCHEMA = 'hwpx.safe-table-layout.v1'

def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def local(n):
    return n.tag.rsplit('}', 1)[-1]

def archive(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('duplicate members')
        return {n: z.read(n) for n in z.namelist()}

def parse(data):
    root = E.fromstring(data, E.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    if root.getroottree().docinfo.doctype:
        raise ValueError('XML DTD unsupported')
    return root

def target(data, number):
    members = archive(data)
    found = []
    for name in sorted(members):
        if name.startswith('Contents/section') and name.endswith('.xml'):
            root = parse(members[name])
            found.extend(((name, root, t) for t in root.iter(P + 'tbl')))
    if not isinstance(number, int) or isinstance(number, bool) or (not 1 <= number <= len(found)):
        raise ValueError('table index outside document')
    item = found[number - 1]
    if any((a.tag == P + 'tbl' for a in item[2].iterancestors())):
        raise ValueError('nested target table unsupported')
    return (members, *item)

def plain(t):
    if any((local(n) in ['tbl', 'pic', 'ctrl', 'fieldBegin', 'fieldEnd', 'equation', 'rect', 'footNote', 'endNote'] for c in t for n in c.iter())):
        raise ValueError('nested or controlled target table unsupported')
    rows = t.findall(P + 'tr')
    columns = int(t.get('colCnt'))
    _require(len(rows) == int(t.get('rowCnt')), 'table preservation check failed')
    if not 2 <= len(rows) <= 100 or not 1 <= columns <= 12:
        raise ValueError('bounded rectangular table required')
    for ri, row in enumerate(rows):
        cells = row.findall(P + 'tc')
        if len(cells) != columns:
            raise ValueError('merged or sparse rows unsupported')
        for ci, c in enumerate(cells):
            a = c.find(P + 'cellAddr')
            span = c.find(P + 'cellSpan')
            if a is None or span is None or (int(a.get('rowAddr')), int(a.get('colAddr'))) != (ri, ci) or ((int(span.get('rowSpan')), int(span.get('colSpan'))) != (1, 1)):
                raise ValueError('merged or invalid cell geometry unsupported')
            ps = c.findall('./' + P + 'subList/' + P + 'p')
            if len(ps) != 1:
                raise ValueError('only one plain paragraph per target cell supported')
            rs = ps[0].findall(P + 'run')
            if len(rs) != 1 or len(rs[0]) != 1 or rs[0][0].tag != P + 't' or len(rs[0][0]):
                raise ValueError('one plain text run required in each target cell')
    return (rows, columns)

def cell_text(c):
    return ''.join(c.find('./' + P + 'subList/' + P + 'p/' + P + 'run/' + P + 't').itertext())

def num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or (not math.isfinite(x)):
        raise ValueError('finite numeric mm required')
    return round(x * 7200 / 25.4)

def row_index(x, n):
    if isinstance(x, bool) or not isinstance(x, int) or (not 2 <= x <= n):
        raise ValueError('data row must be 2..row count; header preserved')
    return x - 1

def inspect(source, table):
    data = pathlib.Path(source).read_bytes()
    _, part, root, t = target(data, table)
    rows, cols = plain(t)
    return dict(schema=SCHEMA, source_sha256=sha(source), table=table, part=part, table_id=t.get('id'), rows=[[cell_text(c) for c in r.findall(P + 'tc')] for r in rows], widths_mm=[round(int(c.find(P + 'cellSz').get('width')) * 25.4 / 7200, 3) for c in rows[0].findall(P + 'tc')], heights_mm=[round(max((int(c.find(P + 'cellSz').get('height')) for c in r.findall(P + 'tc'))) * 25.4 / 7200, 3) for r in rows], native='not_checked')

def tree(n, *, row_addr=None, width=None, height=None, new_id=False, new_text=None, drop_cache=False):
    if drop_cache and local(n).lower() == 'linesegarray':
        return None
    attrs = dict(n.attrib)
    text = n.text or ''
    if local(n) == 'cellAddr' and row_addr is not None:
        attrs['rowAddr'] = str(row_addr)
    if local(n) == 'cellSz':
        if width is not None:
            attrs['width'] = str(width)
        if height is not None:
            attrs['height'] = str(height)
    if local(n) == 'p' and new_id:
        attrs.pop('id', None)
    if local(n) == 't' and new_text is not None:
        text = new_text
    return (n.tag, tuple(sorted(attrs.items())), text, n.tail or '', tuple((x for c in n for x in [tree(c, row_addr=row_addr, width=width, height=height, new_id=new_id, new_text=new_text, drop_cache=drop_cache)] if x is not None)))

def verify(before, after, req):
    bm, part, br, bt = target(before, req['table'])
    am, apart, ar, at = target(after, req['table'])
    _require(apart == part, 'table preservation check failed')
    _require(set(bm) == set(am), 'table preservation check failed')
    for name in bm:
        if name != part:
            _require(bm[name] == am[name], ('non_target_member', name))

    def outside(n, t):
        if n is t:
            return ('selected-table',)
        return (n.tag, tuple(sorted(n.attrib.items())), n.text or '', n.tail or '', tuple((outside(c, t) for c in n)))
    _require(outside(br, bt) == outside(ar, at), 'non_target_xml_changed')
    brows, cols = plain(bt)
    arows, _ = plain(at)
    op = req['operation']
    mapping = list(range(len(brows)))
    cloned = None
    if op == 'insert_after':
        ref = req['row'] - 1
        mapping.insert(ref + 1, ref)
        cloned = ref + 1
    elif op == 'delete_row':
        mapping.pop(req['row'] - 1)
    _require(len(arows) == len(mapping), 'table preservation check failed')
    battrs = dict(bt.attrib)
    battrs['rowCnt'] = str(len(mapping))
    _require(battrs == dict(at.attrib), 'table attributes changed')
    _require([tree(c) for c in bt if local(c) != 'tr'] == [tree(c) for c in at if local(c) != 'tr'], 'table properties changed')
    for ri, bi in enumerate(mapping):
        oldcells = brows[bi].findall(P + 'tc')
        newcells = arows[ri].findall(P + 'tc')
        _require(dict(brows[bi].attrib) == dict(arows[ri].attrib), 'table preservation check failed')
        for ci, (old, new) in enumerate(zip(oldcells, newcells)):
            width = req['_widths'][ci] if op == 'resize' else None
            height = req['_heights'].get(ri) if op == 'resize' else None
            expected = tree(old, row_addr=ri, width=width, height=height, new_id=ri == cloned, new_text=req['values'][ci] if ri == cloned else None, drop_cache=ri == cloned)
            actual = tree(new, new_id=ri == cloned, drop_cache=ri == cloned)
            _require(expected == actual, ('cell_preservation', ri, ci))
    ids = [n.get('id') for n in ar.iter(P + 'p')]
    _require(len(ids) == len(set(ids)), 'paragraph ID collision')
    return dict(nonTargetPackagePayloadsEqual=True, nonTargetXmlEqual=True, requestedRowsAndSizesExact=True, paragraphIdsUnique=True)

def apply(source, output, request, *, dry_run=False):
    source = pathlib.Path(source).resolve()
    output = pathlib.Path(output).absolute()
    req = dict(request)
    if version('python-hwpx') != '6.3.0':
        raise ValueError('unverified library version')
    if source.suffix.lower() != '.hwpx' or output.suffix.lower() != '.hwpx' or output.exists() or (source == output.resolve()) or (not output.parent.is_dir()):
        raise ValueError('new .hwpx output in existing folder required')
    allowed = {'schema', 'source_sha256', 'table', 'operation', 'row', 'values', 'widths_mm', 'heights_mm'}
    if set(req) - allowed or req.get('schema') != SCHEMA or sha(source) != req.get('source_sha256'):
        raise ValueError('invalid or stale request')
    data = source.read_bytes()
    _, part, root, t = target(data, req['table'])
    rows, cols = plain(t)
    tables = list(root.iter(P + 'tbl'))
    common = dict(section_path=part, table_index=tables.index(t))
    op = req['operation']
    if op == 'insert_after':
        idx = row_index(req['row'], len(rows))
        values = req.get('values')
        if len(rows) >= 100 or not isinstance(values, list) or len(values) != cols or any((not isinstance(v, str) or any((c in v for c in '\r\n\t')) for v in values)):
            raise ValueError('one single-line value per cloned cell required')
        ops = [dict(op='insert_row_by_clone', ref_row=idx, count=1, **common)] + [dict(op='fill_cell', row=idx + 1, col=c, text=v, **common) for c, v in enumerate(values)]
    elif op == 'delete_row':
        idx = row_index(req['row'], len(rows))
        if len(rows) <= 2:
            raise ValueError('at least one data row required')
        ops = [dict(op='delete_row', row=idx, **common)]
    elif op == 'resize':
        widths = req.get('widths_mm')
        heights = req.get('heights_mm', {})
        if not isinstance(heights, dict):
            raise ValueError('heights map required')
        if not isinstance(widths, list) or len(widths) != cols or any((not 5 <= x <= 300 for x in widths)):
            raise ValueError('complete column widths required')
        widths = [num(x) for x in widths]
        total = sum((int(c.find(P + 'cellSz').get('width')) for c in rows[0].findall(P + 'tc')))
        if abs(sum(widths) - total) > 1:
            raise ValueError('total table width must be preserved')
        widths[-1] += total - sum(widths)
        hs = {}
        for key, value in heights.items():
            r = int(key) - 1
            if str(r + 1) != str(key) or not 0 <= r < len(rows) or (not 5 <= value <= 60):
                raise ValueError('row height out of bounded range')
            hs[r] = num(value)
        req['_widths'] = widths
        req['_heights'] = hs
        ops = [dict(op='set_column_widths', widths=widths, **common)]
        if hs:
            ops.append(dict(op='set_row_heights', heights=hs, **common))
    else:
        raise ValueError('unsupported operation')
    before = sha(source)
    result = apply_table_ops(data, ops, dry_run=dry_run)
    if not result.ok:
        raise ValueError(result.to_dict())
    checks = verify(data, result.data, req)
    with workspace_candidate_directory(prefix='table-layout-', dir=output.parent) as temp:
        path = pathlib.Path(temp) / 'candidate.hwpx'
        path.write_bytes(result.data)
        if not validate_editor_open_safety(path).ok:
            raise ValueError('open safety failed')
        if sha(source) != before:
            raise ValueError('source changed')
        if not dry_run:
            os.link(path, output)
    return dict(schema='hwpx.safe-table-layout-receipt.v1', source_sha256=before, output_sha256=hashlib.sha256(result.data).hexdigest(), published=not dry_run, status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE', operation=op, checks=checks, primitive=result.to_dict(), native='not_checked', completion='candidate_native_pending')
if __name__ == '__main__':
    a = argparse.ArgumentParser()
    s = a.add_subparsers(dest='command', required=True)
    i = s.add_parser('inspect')
    i.add_argument('source')
    i.add_argument('--table', type=int, required=True)
    i.add_argument('--output', required=True)
    x = s.add_parser('apply')
    x.add_argument('source')
    x.add_argument('output')
    x.add_argument('--request', required=True)
    x.add_argument('--dry-run', action='store_true')
    args = a.parse_args()
    if args.command == 'inspect':
        with open(args.output, 'x', encoding='utf-8') as f:
            json.dump(inspect(args.source, args.table), f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(apply(args.source, args.output, json.loads(pathlib.Path(args.request).read_text(encoding='utf-8-sig')), dry_run=args.dry_run), ensure_ascii=False, indent=2))
