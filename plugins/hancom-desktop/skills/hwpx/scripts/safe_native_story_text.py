"""Existing physical native header/footer run text through public Paragraph API."""
from pathlib import Path
from hashlib import sha256
from importlib.metadata import version
import json,os
from hwpx import HwpxDocument
from hwpx.model import Paragraph
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
from workspace_candidate_directory import workspace_candidate_directory
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
SCHEMA='hwpx.native-story-run-text.v1'

def require(v,m):
    if not v:raise ValueError(m)
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def shape(n):return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(shape(c) for c in n))
def fingerprint(n):return sha256(json.dumps(shape(n),ensure_ascii=False).encode()).hexdigest()
def location(n):
    path=[]
    while n.getparent() is not None:p=n.getparent();path.append(list(p).index(n));n=p
    return tuple(reversed(path))
def at(n,path):
    for i in path:n=n[i]
    return n

def inspect(source,kind,ordinal=1):
    require(kind in ['header','footer'] and type(ordinal) is int and 1<=ordinal<=6,'bounded story kind and ordinal required');sections=oracle.sections(source);stories=[(part,n) for part,root in sections for n in root.iter(P+kind)];require(ordinal<=len(stories),'story outside inventory');part,story=stories[ordinal-1];ctrl=story.getparent();run=ctrl.getparent() if ctrl is not None else None;host=run.getparent() if run is not None else None
    require(ctrl is not None and ctrl.tag==P+'ctrl' and len(ctrl)==1 and run is not None and run.tag==P+'run' and host is not None and host.tag==P+'p' and host.getparent().tag.endswith('}sec'),'existing physical root body story required; logical/mirrored stories unsupported');identity=story.get('id');require(identity and sum(n.get('id')==identity for _,n in stories)==1 and story.get('applyPageType') in ['BOTH','EVEN','ODD'],'unique native story ID/page type required')
    subs=story.findall(P+'subList');require(len(subs)==1 and list(story)==subs,'one existing story subList required');paras=subs[0].findall(P+'p');require(len(paras)==1 and list(subs[0])==paras,'one existing story paragraph required');body=paras[0];require(all(c.tag in [P+'run',P+'linesegarray'] for c in body),'unsupported story paragraph child');runs=body.findall(P+'run');require(1<=len(runs)<=8,'bounded plain story runs required');values=[]
    for r in runs:
        ts=r.findall(P+'t');require(len(ts)==1 and list(r)==ts and not len(ts[0]),'plain story text only; fields/controls/tabs unsupported');values.append(dict(text=ts[0].text or '',charPrIDRef=r.get('charPrIDRef'),textPath=list(location(ts[0]))))
    return dict(kind=kind,ordinal=ordinal,part=part,storyId=identity,applyPageType=story.get('applyPageType'),storyPath=list(location(story)),storySha256=fingerprint(story),bodyPath=list(location(body)),bodyId=body.get('id'),bodySha256=fingerprint(body),hostPath=list(location(host)),runs=values)

def checked(source,req):
    require(isinstance(req,dict) and set(req)=={'schema','sourceSha256','stories','editableReason'} and req['schema']==SCHEMA,'exact story request schema required');require(sha(source)==req['sourceSha256'],'stale source');oracle.single_line(req['editableReason'],search=True);require(len(req['editableReason'])>=8,'specific reason required');require(isinstance(req['stories'],list) and 1<=len(req['stories'])<=6,'1..6 declared existing stories required');used=set();selected=[];text={};changed=set()
    for item in req['stories']:
        require(isinstance(item,dict) and set(item)=={'binding','edits'},'exact story edit record required');binding=item['binding'];b=inspect(source,binding['kind'],binding['ordinal']);require(b==binding,'stale/mismatched story binding');key=(b['part'],b['kind'],b['storyId']);require(key not in used,'duplicate story selection');used.add(key);require(isinstance(item['edits'],list) and 1<=len(item['edits'])<=8,'bounded run edits required');run_used=set()
        for e in item['edits']:
            require(isinstance(e,dict) and set(e)=={'run','expected','replacement'},'exact run edit required');i=e['run'];require(type(i) is int and 1<=i<=len(b['runs']) and i not in run_used,'unique existing run required');run_used.add(i);r=b['runs'][i-1];require(e['expected']==r['text'],'stale run text');oracle.single_line(e['replacement']);require(len(e['replacement'])<=160 and e['replacement']!=r['text'],'bounded actual story text change required');text[b['part'],tuple(r['textPath'])]=e['replacement']
        changed.add((b['part'],tuple(b['bodyPath'])));selected.append((b,item['edits']))
    return selected,text,changed

def verify(source,output,req):
    selected,text,changed=checked(source,req);require(oracle.snapshot(source,text,changed)==oracle.snapshot(output,changed_paragraphs=changed),'non-target story/body/style/page setting/package changed')
    for b,edits in selected:
        after=inspect(output,b['kind'],b['ordinal']);wanted=[x['text'] for x in b['runs']]
        for e in edits:wanted[e['run']-1]=e['replacement']
        require([x['text'] for x in after['runs']]==wanted and after['storyId']==b['storyId'] and after['bodyId']==b['bodyId'] and after['applyPageType']==b['applyPageType'],'story run text/ID/page type mismatch')
    return dict(status='PASS_NATIVE_STORY_TEXT_PRESERVATION',wholeNonTargetPackageExact=True,storyIDsRunStylesAndVisibilitySettingsExact=True,onlySelectedStoryParagraphCacheMayChange=True)

def apply(source,output,req,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified public story paragraph adapter version');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new workspace output required');selected,_,_=checked(source,req)
    with workspace_candidate_directory(prefix='native-story-text-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            sections={s.part_name:s for s in doc.sections}
            for b,edits in selected:
                section=sections.get(b['part']);require(section is not None,'public section missing');story=at(section.element,b['storyPath']);body=at(section.element,b['bodyPath']);require(fingerprint(story)==b['storySha256'] and fingerprint(body)==b['bodySha256'],'public story subtree mismatch');paragraph=Paragraph(body,section);runs=paragraph.runs;require([r.text for r in runs]==[x['text'] for x in b['runs']],'public story run readback mismatch')
                for e in edits:runs[e['run']-1].text=e['replacement']
            doc.save_to_path(candidate)
        checks=verify(source,candidate,req);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==req['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',sourceSha256=sha(source),candidateSha256=sha(candidate),checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
