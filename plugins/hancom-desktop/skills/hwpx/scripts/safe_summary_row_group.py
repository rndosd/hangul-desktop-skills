"""6.3.0 public paragraph/table creation plus bounded existing-row transfer.

Move nodes through exposed public objects. Never rebuild cell content, clone
paragraph styles, read/write raw ZIP members or attach to a user's Hangul.
"""
from pathlib import Path
from importlib.metadata import version
import copy,os
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
import safe_native_page_settings as pages
from workspace_candidate_directory import workspace_candidate_directory
P=pages.P;SCHEMA='hwpx.summary-row-group.v2';require=pages.require;sha=pages.sha;at=pages.at;location=pages.location;fingerprint=pages.fingerprint

def row_height(row):return max(int(c.find(P+'cellSz').get('height')) for c in row.findall(P+'tc'))
def table_host(t):
    run=t.getparent();host=run.getparent();require(host.tag==P+'p' and run.tag==P+'run' and len(host.findall(P+'run'))==1,'one table carrier run required');require([n.tag for n in run]==[P+'tbl',P+'t'] and not len(run[1]) and not (run[1].text or ''),'native empty trailing-text carrier required');require(set(host.attrib)=={'id','paraPrIDRef','styleIDRef','pageBreak','columnBreak','merged'} and host.get('pageBreak')==host.get('columnBreak')==host.get('merged')=='0','ordinary unbroken carrier required');return host

def inspect(source):
    sections=oracle.sections(source);require(len(sections)==1,'one section required');part,root=sections[0];tables=list(root.iter(P+'tbl'));require(len(tables) in [1,2],'one original table or its two adjacent groups required');hosts=[table_host(t) for t in tables];require(all(h.getparent() is root for h in hosts),'root-body table carriers required');require(len(tables)==1 or hosts[0].getnext() is hosts[1],'existing two groups must be adjacent');cols=[int(t.get('colCnt')) for t in tables];require(len(set(cols))==1 and 2<=cols[0]<=12,'consistent bounded logical columns required');counts=[int(t.get('rowCnt')) for t in tables];require(4<=sum(counts)<=100 and counts[0]>=2,'bounded report rows required');require(tables[0].find(P+'pos').get('treatAsChar')=='0','original prefix remains floating')
    if len(tables)==2:require(2<=counts[1]<=4 and tables[1].find(P+'pos').get('treatAsChar')=='1','existing small inline row group required')
    for t in tables:
        require(t.get('lock')==t.get('noAdjust')==t.find(P+'sz').get('protect')=='0','unprotected table required');require(t.get('cellSpacing')=='0' and t.find(P+'sz').get('heightRelTo')==t.find(P+'sz').get('widthRelTo')=='ABSOLUTE','ordinary absolute table required');require([pages.oracle.local(n) for n in t]==['sz','pos','outMargin','inMargin']+['tr']*int(t.get('rowCnt')),'unsupported table metadata');require(all(c.find(P+'cellSpan').get('rowSpan')=='1' and not list(c.iter(P+'tbl')) for c in t.iter(P+'tc')),'vertical crossing merges or nested tables unsupported')
    used={int(n.get('id')) for n in root.iter() if (n.get('id') or '').isdigit()};n=1
    while n in used:n+=1
    table_id=str(n);n+=1
    while n in used:n+=1
    return dict(part=part,sectionSha256=fingerprint(root),tableIds=[t.get('id') for t in tables],tablePaths=[list(location(t)) for t in tables],tableAttrs=[dict(t.attrib) for t in tables],tableSha256=[fingerprint(t) for t in tables],hostPaths=[list(location(h)) for h in hosts],hostAttrs=[dict(h.attrib) for h in hosts],runAttrs=[dict(t.getparent().attrib) for t in tables],rowCounts=counts,columns=cols[0],newTableId=table_id,newHostId=str(n))

def checked(source,q):
    require(isinstance(q,dict) and set(q)=={'schema','sourceSha256','binding','tailRows','joinGapHwpunit','editableReason'} and q['schema']==SCHEMA,'exact row-group schema required');require(sha(source)==q['sourceSha256'],'stale source');b=inspect(source);require(b==q['binding'],'stale table/group binding');gap=q['joinGapHwpunit'];require(type(gap) is int and 0<=gap<=600,'explicit bounded shared-boundary gap required');count=q['tailRows'];require(type(count) is int and 2<=count<=4,'explicit 2–4 row group required');old=b['rowCounts'][1] if len(b['rowCounts'])==2 else 0;require(count>old and b['rowCounts'][0]-(count-old)>=2,'grow a selected tail without emptying prefix');require(count-old<=3,'bounded row transfer required');oracle.single_line(q['editableReason'],search=True);require(len(q['editableReason'])>=8,'specific row grouping reason required')
    root=dict(oracle.sections(source))[b['part']];rows=list(at(root,b['tablePaths'][0]).findall(P+'tr'));moved=rows[-(count-old):];height=sum(row_height(x) for x in moved);require(height<int(at(root,b['tablePaths'][0]).find(P+'sz').get('height')),'prefix size must remain positive');total=height+(int(at(root,b['tablePaths'][1]).find(P+'sz').get('height')) if old else 0);require(total<=18000,'small row group must fit one page; do not inline a long table');return b,height

def expected_root(source,q):
    b,height=checked(source,q);root=copy.deepcopy(dict(oracle.sections(source))[b['part']]);prefix=at(root,b['tablePaths'][0]);host=at(root,b['hostPaths'][0]);old=b['rowCounts'][1] if len(b['rowCounts'])==2 else 0;move=q['tailRows']-old;rows=prefix.findall(P+'tr');moved=rows[-move:]
    if old:
        tail=at(root,b['tablePaths'][1]);tailhost=at(root,b['hostPaths'][1]);original_tail=list(tail.findall(P+'tr'))
        for n in original_tail:tail.remove(n)
    else:
        # Read-only oracle from the source carrier; never passed to writer.
        tailhost=copy.deepcopy(host);tailhost.set('id',b['newHostId']);tail=next(tailhost.iter(P+'tbl'));original_tail=[]
        for n in tail.findall(P+'tr'):tail.remove(n)
        tail.set('id',b['newTableId']);tail.set('zOrder',str(int(prefix.get('zOrder'))+1));tail.set('repeatHeader','0');tail.find(P+'pos').set('treatAsChar','1');tail.find(P+'sz').set('height','0');root.insert(list(root).index(host)+1,tailhost)
    prefix.find(P+'outMargin').set('bottom',str(q['joinGapHwpunit']));tail.find(P+'outMargin').set('top','0')
    for n in moved:prefix.remove(n);tail.append(n)
    for n in original_tail:tail.append(n)
    for i,row in enumerate(tail.findall(P+'tr')):
        for c in row.findall(P+'tc'):c.find(P+'cellAddr').set('rowAddr',str(i))
    prefix.set('rowCnt',str(b['rowCounts'][0]-move));prefix.find(P+'sz').set('height',str(int(prefix.find(P+'sz').get('height'))-height));tail.set('rowCnt',str(q['tailRows']));tail.find(P+'sz').set('height',str(int(tail.find(P+'sz').get('height'))+height));changed={(b['part'],tuple(location(h))) for h in [host,tailhost]};return b,root,changed

def verify(source,output,q):
    b,root,changed=expected_root(source,q);require(oracle.snapshot(source,xml_roots={b['part']:root},changed_paragraphs=changed)==oracle.snapshot(output,changed_paragraphs=changed),'row/group cells, IDs, styles, margins or non-target package changed');return dict(status='PASS_ROW_GROUP_PRESERVATION',allExistingCellsIdsTextSpansSizesBordersAndStylesExact=True,onlyLocalRowAddressesRebased=True,headerDefinitionsExact=True,selectedCarrierCachesOnly=True,onlyInternalBoundaryMarginsExplicitlyChanged=True,originalOuterTopAndBottomPreserved=True)

def apply(source,output,q,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified public row-transfer adapter');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and output.resolve()!=source,'new workspace output required');b,height=checked(source,q)
    with workspace_candidate_directory(prefix='summary-row-group-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            require(len(doc.sections)==1 and fingerprint(doc.sections[0].element)==b['sectionSha256'],'public section mismatch');section=doc.sections[0];tables=[t for p in section.paragraphs for t in p.tables];require([t.element.get('id') for t in tables]==b['tableIds'],'public table IDs mismatch');prefix=tables[0];old=b['rowCounts'][1] if len(tables)==2 else 0;move=q['tailRows']-old;rows=prefix.element.findall(P+'tr');moved=rows[-move:]
            if old:tail=tables[1];oldrows=tail.element.findall(P+'tr')
            else:
                attrs=b['hostAttrs'][0];runattrs=b['runAttrs'][0];newp=section.add_paragraph('',para_pr_id_ref=attrs['paraPrIDRef'],style_id_ref=attrs['styleIDRef'],char_pr_id_ref=runattrs['charPrIDRef'],inherit_style=False,id=b['newHostId']);tail=newp.add_table(q['tailRows'],b['columns'],width=int(prefix.element.find(P+'sz').get('width')),height=height,border_fill_id_ref=prefix.element.get('borderFillIDRef'),char_pr_id_ref=runattrs['charPrIDRef'])
                # Consolidate only the freshly created empty text scaffold.
                empty_run,object_run=list(newp.element);require(len(empty_run)==1 and empty_run[0].tag==P+'t' and not (empty_run[0].text or ''),'fresh empty paragraph scaffold required');text=empty_run[0];empty_run.remove(text);object_run.append(text);newp.element.remove(empty_run)
                tail.element.attrib.clear();tail.element.attrib.update(dict(prefix.element.attrib));tail.element.set('id',b['newTableId']);tail.element.set('zOrder',str(int(prefix.element.get('zOrder'))+1));tail.element.set('repeatHeader','0');tail.element.set('rowCnt',str(q['tailRows']))
                for tag in ['sz','pos','outMargin','inMargin']:
                    node=tail.element.find(P+tag);node.attrib.clear();node.attrib.update(dict(prefix.element.find(P+tag).attrib))
                tail.element.find(P+'pos').set('treatAsChar','1');tail.element.find(P+'sz').set('height','0')
                for row in tail.element.findall(P+'tr'):tail.element.remove(row)
                section.element.remove(newp.element);section.element.insert(list(section.element).index(prefix.paragraph.element)+1,newp.element);oldrows=[]
            prefix.element.find(P+'outMargin').set('bottom',str(q['joinGapHwpunit']));tail.element.find(P+'outMargin').set('top','0')
            for row in oldrows:tail.element.remove(row)
            for row in moved:prefix.element.remove(row);tail.element.append(row)
            for row in oldrows:tail.element.append(row)
            for i,row in enumerate(tail.element.findall(P+'tr')):
                for c in row.findall(P+'tc'):c.find(P+'cellAddr').set('rowAddr',str(i))
            prefix.element.set('rowCnt',str(b['rowCounts'][0]-move));prefix.element.find(P+'sz').set('height',str(int(prefix.element.find(P+'sz').get('height'))-height));tail.element.set('rowCnt',str(q['tailRows']));tail.element.find(P+'sz').set('height',str(int(tail.element.find(P+'sz').get('height'))+height))
            for t in [prefix,tail]:
                for cache in list(t.paragraph.element.findall(P+'linesegarray')):t.paragraph.element.remove(cache)
                t.mark_dirty()
            doc.save_to_path(candidate)
        checks=verify(source,candidate,q);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==q['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
