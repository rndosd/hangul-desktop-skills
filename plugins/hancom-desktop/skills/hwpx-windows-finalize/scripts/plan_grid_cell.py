"""Read-only merged-cell lookup. Coordinates are one-based; never edits HWPX."""
import argparse
import json
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import hancom_completion_gate as g


def grid(table):
    rows,cols=int(table.get('rowCnt')),int(table.get('colCnt'))
    g.require(0<rows<=100 and 0<cols<=100,'grid_bounds')
    covered={};cells=[]
    for tr in table.findall('{*}tr'):
        for cell in tr.findall('{*}tc'):
            a,s=cell.find('{*}cellAddr'),cell.find('{*}cellSpan')
            r,c=int(a.get('rowAddr')),int(a.get('colAddr'))
            rs,cs=int(s.get('rowSpan')),int(s.get('colSpan'))
            g.require(r>=0 and c>=0 and rs>0 and cs>0 and r+rs<=rows and c+cs<=cols,'invalid_cell_span')
            paragraph=cell.find('{*}subList/{*}p')
            nested=any(n.tag.rsplit('}',1)[-1]=='tbl' for n in cell.iter())
            text=''.join(n.text or '' for n in paragraph.iter() if n.tag.rsplit('}',1)[-1]=='t') if paragraph is not None else ''
            plain=paragraph is not None and all(n.tag.rsplit('}',1)[-1] in ('p','run','t','linesegarray','lineseg') for n in paragraph.iter())
            item={'row':r+1,'column':c+1,'rowSpan':rs,'columnSpan':cs,'text':text.strip(),'nested':nested,
                  'plainFirstParagraph':plain,'emptyFirstParagraph':plain and len(text)==0,
                  'paragraphCount':len(cell.findall('{*}subList/{*}p'))}
            for rr in range(r,r+rs):
                for cc in range(c,c+cs):
                    g.require((rr,cc) not in covered,'overlapping_cells')
                    covered[rr,cc]=len(cells)
            cells.append(item)
    g.require(len(covered)==rows*cols,'incomplete_cell_grid')
    g.require(covered.get((0,0))==0,'first_cell_not_origin')
    return cells,covered


def plan(source,ordinal,row,column):
    source_ref=g.ref(source);package=g.read_package(source)
    tables=[]
    with ZipFile(source) as z:
        for name in package['sections']:
            tables.extend(n for n in ET.fromstring(z.read(name)).iter() if n.tag.rsplit('}',1)[-1]=='tbl')
    g.require(1<=ordinal<=len(tables)<=100,'table_ordinal_out_of_range')
    table=tables[ordinal-1];cells,covered=grid(table)
    g.require(bool(cells[0]['text']),'first_cell_anchor_must_be_nonempty')
    g.require((row-1,column-1) in covered,'cell_coordinate_out_of_range')
    index=covered[row-1,column-1]
    queue=deque([(0,[0],[])])
    seen={0};found=None
    while queue:
        current,indices,actions=queue.popleft()
        cell=cells[current]
        if cell['nested'] or not cell['plainFirstParagraph']:
            continue
        if current==index:
            found=(indices,actions);break
        if len(actions)>=20:
            continue
        r,c=cell['row']-1,cell['column']-1
        for point,action in [((r,c+cell['columnSpan']),'TableRightCell'),((r+cell['rowSpan'],c),'TableLowerCell')]:
            nxt=covered.get(point)
            if nxt is not None and nxt not in seen:
                seen.add(nxt);queue.append((nxt,indices+[nxt],actions+[action]))
    g.require(found is not None,'no_supported_plain_paragraph_route')
    indices,actions=found;route=[cells[i] for i in indices]
    g.verify_ref(source_ref)
    return {'schema':'hwpx.grid-cell-plan.v3','source':source_ref,'tableCount':len(tables),
            'tableOrdinal':ordinal,'tableId':table.get('id'),'requested':{'row':row,'column':column},
            'ownerCell':cells[index],'route':route,'actions':actions,'scope':'read_only'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--table',type=int,required=True)
    p.add_argument('--row',type=int,required=True);p.add_argument('--column',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=plan(a.source,a.table,a.row,a.column);g.write_new(a.output,result)
    print(json.dumps(result,ensure_ascii=True))
