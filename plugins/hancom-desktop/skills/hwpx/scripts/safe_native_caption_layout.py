"""Explicit caption/table grouping on one exclusive existing caption style."""
from pathlib import Path
from importlib.metadata import version
import zipfile,os
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
import safe_table_flow as flow
import safe_native_page_settings as pages
from workspace_candidate_directory import workspace_candidate_directory
H='{http://www.hancom.co.kr/hwpml/2011/head}';K='{http://www.hancom.co.kr/hwpml/2011/core}';P=pages.P
SCHEMA='hwpx.native-caption-layout.v1';require=pages.require;sha=pages.sha;at=pages.at;location=pages.location;fingerprint=pages.fingerprint

def inspect(source,table,caption):
    req=dict(schema=flow.SCHEMA,source_sha256=sha(source),table=table,caption={'expected_text':caption,'keep_with_next':True},anchor_same_page=True)
    _,part,root,t,cs,host,cap=flow.plan(Path(source).read_bytes(),req);require(t.get('rowCnt') and 2<=int(t.get('rowCnt'))<=20,'bounded small table required');require(all(n.tag==P+'run' or n.tag==P+'linesegarray' for n in host),'ordinary table carrier required');pid=cap.get('paraPrIDRef')
    with zipfile.ZipFile(source) as z:
        header=oracle.parse(z.read('Contents/header.xml'));defs=[n for n in header.iter(H+'paraPr') if n.get('id')==pid];require(len(defs)==1,'one caption definition required');pr=defs[0];refs=[]
        for name in z.namelist():
            if not name.endswith(('.xml','.hpf')):continue
            for n in oracle.parse(z.read(name)).iter():
                if n.get('paraPrIDRef')==pid:refs.append((name,list(location(n))))
        require(refs==[(part,list(location(cap)))],'caption definition shared; refuse global change')
        br=pr.findall(H+'breakSetting');a=pr.findall(P+'switch/'+P+'case/'+H+'margin/'+K+'next');b=pr.findall(P+'switch/'+P+'default/'+H+'margin/'+K+'next');require(len(br)==len(a)==len(b)==1,'native break and margin branches required');require(br[0].get('keepWithNext') in ['0','1'] and br[0].get('pageBreakBefore') in ['0','1'],'native caption flags required');require(a[0].get('unit')==b[0].get('unit')=='HWPUNIT' and int(b[0].get('value'))==2*int(a[0].get('value')),'native margin branch relation required')
        return dict(table=table,caption=caption,part=part,sectionSha256=fingerprint(root),tablePath=list(location(t)),tableSha256=fingerprint(t),captionPath=list(location(cap)),captionSha256=fingerprint(cap),captionAttrs=dict(cap.attrib),positionPath=list(location(t.find(P+'pos'))),headerPart='Contents/header.xml',definitionPath=list(location(pr)),definitionSha256=fingerprint(pr),definitionId=pid,breakPath=list(location(br[0])),modernPath=list(location(a[0])),fallbackPath=list(location(b[0])),referenceCount=len(refs))

def checked(source,q):
    require(isinstance(q,dict) and set(q)=={'schema','sourceSha256','binding','breakBeforeCaption','captionAfterHwpunit','editableReason'} and q['schema']==SCHEMA,'exact caption layout schema required');require(q['sourceSha256']==sha(source),'stale source');b=inspect(source,q['binding']['table'],q['binding']['caption']);require(b==q['binding'],'stale caption/table binding');require(type(q['breakBeforeCaption']) is bool,'explicit caption break boolean required');n=q['captionAfterHwpunit'];require(type(n) is int and 200<=n<=1800,'bounded 2–18pt caption spacing required');oracle.single_line(q['editableReason'],search=True);require(len(q['editableReason'])>=8,'specific source layout reason required')
    attrs={(b['headerPart'],tuple(b['breakPath'])):{'keepWithNext':'1','pageBreakBefore':str(int(q['breakBeforeCaption']))},(b['headerPart'],tuple(b['modernPath'])):{'value':str(n)},(b['headerPart'],tuple(b['fallbackPath'])):{'value':str(n*2)},(b['part'],tuple(b['positionPath'])):{'holdAnchorAndSO':'1'}}
    require(oracle.snapshot(source,attribute_overrides=attrs)!=oracle.snapshot(source),'actual caption layout change required');return b,attrs

def verify(source,output,q):
    b,attrs=checked(source,q);require(oracle.snapshot(source,attribute_overrides=attrs)==oracle.snapshot(output),'non-target caption/table/package changed');return dict(status='PASS_CAPTION_LAYOUT_PRESERVATION',existingExclusiveStyleUpdatedWithoutClone=True,allTextIdsCellsGeometryAndOtherStylesExact=True)

def apply(source,output,q,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified caption/header adapter');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new workspace output required');b,attrs=checked(source,q)
    with workspace_candidate_directory(prefix='caption-layout-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            require(len(doc.parts.headers)==1,'one header required');header=doc.parts.headers[0];require(fingerprint(at(header.element,b['definitionPath']))==b['definitionSha256'],'public caption definition mismatch')
            for (part,path),changes in attrs.items():
                if part==b['headerPart']:
                    node=at(header.element,path)
                    for k,v in changes.items():node.set(k,v)
            header.mark_dirty();found=[t for s in doc.sections for p in s.paragraphs for t in p.tables if s.part_name==b['part'] and fingerprint(t.element)==b['tableSha256']];require(len(found)==1,'public table binding ambiguous');table=found[0];table.element.find(P+'pos').set('holdAnchorAndSO','1');table.mark_dirty();doc.save_to_path(candidate)
        checks=verify(source,candidate,q);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==q['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
