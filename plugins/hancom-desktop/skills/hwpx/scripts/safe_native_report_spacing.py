"""Native-existing report role spacing; exact shared style ownership required."""
from pathlib import Path
from importlib.metadata import version
import os,zipfile
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
import safe_native_page_settings as pages
from workspace_candidate_directory import workspace_candidate_directory
P=pages.P;H='{http://www.hancom.co.kr/hwpml/2011/head}';K='{http://www.hancom.co.kr/hwpml/2011/core}'
SCHEMA='hwpx.native-report-spacing.v1';require=pages.require;sha=pages.sha;at=pages.at;location=pages.location;fingerprint=pages.fingerprint

def inspect(source,heading_texts):
    require(isinstance(heading_texts,list) and 2<=len(heading_texts)<=32 and len(set(heading_texts))==len(heading_texts) and all(isinstance(t,str) and t for t in heading_texts),'explicit unique major heading texts required');sections=oracle.sections(source);require(len(sections)==1,'one section required');part,root=sections[0];headings=[]
    for text in heading_texts:
        found=[p for p in root.findall(P+'p') if not list(p.iter(P+'tbl')) and ''.join(t.text or '' for t in p.iter(P+'t'))==text];require(len(found)==1,'major heading missing or ambiguous');p=found[0];headings.append(dict(text=text,path=list(location(p)),id=p.get('id'),paraPrIDRef=p.get('paraPrIDRef'),sha256=fingerprint(p)))
    table_nodes=list(root.iter(P+'tbl'));require(0<=len(table_nodes)<=10,'bounded report tables required');tables=[]
    for t in table_nodes:
        host=t.getparent().getparent();require(host.getparent() is root and host.tag==P+'p','root-body table carriers only');require(t.get('lock')==t.get('noAdjust')==t.find(P+'sz').get('protect')=='0','unprotected tables required');require(t.find(P+'pos').get('treatAsChar')=='0','floating tables required');m=t.find(P+'outMargin');require(m is not None and set(m.attrib)=={'left','right','top','bottom'},'existing exact table outside margin required');tables.append(dict(id=t.get('id'),path=list(location(t)),sha256=fingerprint(t),hostPath=list(location(host)),marginPath=list(location(m)),marginAttrs=dict(m.attrib)))
    definitions=[]
    with zipfile.ZipFile(source) as z:
        header=oracle.parse(z.read('Contents/header.xml'))
        for pid in sorted({p['paraPrIDRef'] for p in headings}):
            refs=[]
            for name in z.namelist():
                if not name.endswith(('.xml','.hpf')):continue
                for n in oracle.parse(z.read(name)).iter():
                    if n.get('paraPrIDRef')==pid:refs.append((name,list(location(n))))
            expected=[(part,p['path']) for p in headings if p['paraPrIDRef']==pid];require(sorted(refs)==sorted(expected),'major style shared with non-target paragraph or style; refuse global change');defs=[n for n in header.iter(H+'paraPr') if n.get('id')==pid];require(len(defs)==1,'major paragraph definition ambiguous');pr=defs[0];paths={}
            for side in ['prev','next']:
                modern=pr.findall(P+'switch/'+P+'case/'+H+'margin/'+K+side);fallback=pr.findall(P+'switch/'+P+'default/'+H+'margin/'+K+side);require(len(modern)==len(fallback)==1,'existing modern/fallback paragraph margin required');a,b=modern[0],fallback[0];require(a.get('unit')==b.get('unit')=='HWPUNIT' and int(b.get('value'))==2*int(a.get('value')),'unsupported native margin branch relation');paths[side]=dict(modern=list(location(a)),fallback=list(location(b)),value=int(a.get('value')))
            definitions.append(dict(id=pid,path=list(location(pr)),sha256=fingerprint(pr),margins=paths,referenceCount=len(refs)))
    return dict(part=part,sectionSha256=fingerprint(root),headingTexts=heading_texts,headings=headings,tables=tables,headerPart='Contents/header.xml',definitions=definitions)

def checked(source,q):
    keys={'schema','sourceSha256','binding','majorBeforeHwpunit','majorAfterHwpunit','tableBeforeHwpunit','tableAfterHwpunit','editableReason'};require(isinstance(q,dict) and set(q)==keys and q['schema']==SCHEMA,'exact report spacing schema required');require(q['sourceSha256']==sha(source),'stale source');b=inspect(source,q['binding']['headingTexts']);require(b==q['binding'],'stale role/table binding');require(all(type(q[k]) is int and 200<=q[k]<=2400 for k in keys if k.endswith('Hwpunit')),'bounded explicit 2–24pt spacing required');oracle.single_line(q['editableReason'],search=True);require(len(q['editableReason'])>=8,'specific spacing reason required');attrs={}
    for d in b['definitions']:
        for side,key in [('prev','majorBeforeHwpunit'),('next','majorAfterHwpunit')]:
            paths=d['margins'][side];attrs[(b['headerPart'],tuple(paths['modern']))]={'value':str(q[key])};attrs[(b['headerPart'],tuple(paths['fallback']))]={'value':str(q[key]*2)}
    for t in b['tables']:attrs[(b['part'],tuple(t['marginPath']))]={'top':str(q['tableBeforeHwpunit']),'bottom':str(q['tableAfterHwpunit'])}
    changed={(b['part'],tuple(p['path'])) for p in b['headings']}|{(b['part'],tuple(t['hostPath'])) for t in b['tables']};require(oracle.snapshot(source,attribute_overrides=attrs)!=oracle.snapshot(source),'actual spacing change required');return b,attrs,changed

def verify(source,output,q):
    b,attrs,changed=checked(source,q);require(oracle.snapshot(source,attribute_overrides=attrs,changed_paragraphs=changed)==oracle.snapshot(output,changed_paragraphs=changed),'non-target text/numbering/styles/tables/margins/package changed');return dict(status='PASS_REPORT_SPACING_PRESERVATION',onlyDeclaredExistingMajorStyleMarginsAndTableOutsideTopBottomChanged=True,allDefinitionIdsNumberingCellsTextAndOtherGeometryExact=True,onlySelectedCarrierAndHeadingCachesCleared=True)

def apply(source,output,q,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified native style/table adapter');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and output.resolve()!=source,'new workspace output required');b,attrs,changed=checked(source,q)
    with workspace_candidate_directory(prefix='native-report-spacing-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            require(len(doc.parts.headers)==len(doc.sections)==1,'one public header/section required');header=doc.parts.headers[0];section=doc.sections[0];require(fingerprint(section.element)==b['sectionSha256'],'public section mismatch')
            for d in b['definitions']:require(fingerprint(at(header.element,d['path']))==d['sha256'],'public major definition mismatch')
            for (part,path),changes in attrs.items():
                node=at(header.element if part==b['headerPart'] else section.element,path)
                for key,value in changes.items():node.set(key,value)
            header.mark_dirty()
            for part,path in changed:
                node=at(section.element,path)
                for cache in list(node.findall(P+'linesegarray')):node.remove(cache)
            section.mark_dirty();doc.save_to_path(candidate)
        checks=verify(source,candidate,q);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==q['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
