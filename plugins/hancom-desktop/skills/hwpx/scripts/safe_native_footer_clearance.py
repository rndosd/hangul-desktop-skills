"""6.3.0 exposed-header adapter: reserve right page-number clearance.

Only an existing, exclusively owned, right-aligned physical footer definition.
No new definition, inherited/global style change or raw package writer.
"""
from pathlib import Path
from importlib.metadata import version
import os,zipfile
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
import safe_native_story_text as stories
import safe_native_page_settings as pages
from workspace_candidate_directory import workspace_candidate_directory
H='{http://www.hancom.co.kr/hwpml/2011/head}'
C='{http://www.hancom.co.kr/hwpml/2011/core}'
P=pages.P
SCHEMA='hwpx.native-footer-clearance.v1'
require=pages.require;sha=pages.sha;at=pages.at;location=pages.location;fingerprint=pages.fingerprint

def inspect(source):
    b=stories.inspect(source,'footer');root=dict(oracle.sections(source))[b['part']];body=at(root,b['bodyPath']);pid=body.get('paraPrIDRef')
    with zipfile.ZipFile(source) as z:
        header=oracle.parse(z.read('Contents/header.xml'));defs=[n for n in header.iter(H+'paraPr') if n.get('id')==pid];require(len(defs)==1,'one footer definition required');pr=defs[0]
        refs=[]
        for name in z.namelist():
            if not name.endswith(('.xml','.hpf')):continue
            r=oracle.parse(z.read(name))
            for n in r.iter():
                if n.get('paraPrIDRef')==pid:refs.append((name,list(location(n))))
        require(refs==[(b['part'],b['bodyPath'])],'footer definition shared with another paragraph/style; refuse global change')
        align=pr.find(H+'align');require(align is not None and align.get('horizontal')=='RIGHT','existing RIGHT footer only')
        modern=pr.findall(P+'switch/'+P+'case/'+H+'margin/'+C+'right');fallback=pr.findall(P+'switch/'+P+'default/'+H+'margin/'+C+'right')
        require(len(modern)==len(fallback)==1,'one existing modern/fallback right margin required');a,c=modern[0],fallback[0];require(a.get('unit')==c.get('unit')=='HWPUNIT','native HWPUNIT right margin required');require(0<=int(a.get('value'))<=9000 and int(c.get('value'))==2*int(a.get('value')),'unsupported native branch margin relation')
        return dict(story=b,paragraphAttrs=dict(body.attrib),headerPart='Contents/header.xml',definitionPath=list(location(pr)),definitionSha256=fingerprint(pr),definitionId=pid,modernPath=list(location(a)),modernAttrs=dict(a.attrib),fallbackPath=list(location(c)),fallbackAttrs=dict(c.attrib),referenceCount=len(refs))

def checked(source,q):
    require(isinstance(q,dict) and set(q)=={'schema','sourceSha256','binding','rightMarginHwpunit','editableReason'} and q['schema']==SCHEMA,'exact footer clearance request required');require(q['sourceSha256']==sha(source),'stale source');b=inspect(source);require(b==q['binding'],'stale footer binding');n=q['rightMarginHwpunit'];require(type(n) is int and 1000<=n<=9000,'bounded 10–90pt clearance required');require(n!=int(b['modernAttrs']['value']),'actual footer margin change required');oracle.single_line(q['editableReason'],search=True);require(len(q['editableReason'])>=8,'explicit layout reason required')
    attrs={(b['headerPart'],tuple(b['modernPath'])):{'value':str(n)},(b['headerPart'],tuple(b['fallbackPath'])):{'value':str(n*2)}}
    return b,attrs

def verify(source,output,q):
    b,attrs=checked(source,q);require(oracle.snapshot(source,attribute_overrides=attrs)==oracle.snapshot(output),'non-target footer/story/body/style/package changed');return dict(status='PASS_FOOTER_CLEARANCE_PRESERVATION',onlyExistingExclusiveDefinitionRightMarginChanged=True,modernAndFallbackBound=True,definitionIdsAndAllOtherPropertiesExact=True)

def apply(source,output,q,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified header adapter version');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and output.resolve()!=source,'new workspace output required');b,attrs=checked(source,q)
    with workspace_candidate_directory(prefix='footer-clearance-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            require(len(doc.parts.headers)==1,'single public header required');header=doc.parts.headers[0];node=at(header.element,b['definitionPath']);require(fingerprint(node)==b['definitionSha256'],'public header binding mismatch')
            for path,n in [(b['modernPath'],q['rightMarginHwpunit']),(b['fallbackPath'],q['rightMarginHwpunit']*2)]:at(header.element,path).set('value',str(n))
            header.mark_dirty();doc.save_to_path(candidate)
        checks=verify(source,candidate,q);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==q['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
