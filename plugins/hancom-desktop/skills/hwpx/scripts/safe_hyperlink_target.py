"""Bounded existing HTTPS hyperlink target adapter.

The public InlineObject name setter and source-bound exposed field parameter
leaves are updated together. No raw package XML rewriting or fallback authoring.
"""
from pathlib import Path
from hashlib import sha256
from importlib.metadata import version
from urllib.parse import urlsplit
import json,os
from hwpx import HwpxDocument
from hwpx.model import InlineObject
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
from workspace_candidate_directory import workspace_candidate_directory
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
SCHEMA='hwpx.hyperlink-target.v1'

def require(v,m):
    if not v:raise ValueError(m)
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def shape(n):return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(shape(c) for c in n))
def fingerprint(n):return sha256(json.dumps(shape(n),ensure_ascii=False).encode()).hexdigest()
def at(n,path):
    for i in path:n=n[i]
    return n
def location(n):
    path=[]
    while n.getparent() is not None:p=n.getparent();path.append(list(p).index(n));n=p
    return tuple(reversed(path))
def url(value):
    oracle.single_line(value,search=True);u=urlsplit(value)
    require(len(value)<=2048 and u.scheme=='https' and u.hostname and not u.username and not u.password and not any(c.isspace() or c in ';\\<>' for c in value),'bounded HTTPS web URL required; no file/mail/internal/command separator')
    require(u.port in [None,443],'only default HTTPS port supported')
    return value

def inspect(source,ordinal=1):
    require(type(ordinal) is int and 1<=ordinal<=20,'bounded hyperlink ordinal required');sections=oracle.sections(source);fields=[(part,n) for part,root in sections for n in root.iter(P+'fieldBegin') if n.get('type')=='HYPERLINK'];require(ordinal<=len(fields),'hyperlink outside inventory');part,field=fields[ordinal-1];old=url(field.get('name'))
    require(field.get('id') and sum(n.get('id')==field.get('id') for _,root in sections for n in root.iter(P+'fieldBegin'))==1,'unique hyperlink field identity required')
    ctrl=field.getparent();run=ctrl.getparent() if ctrl is not None else None;host=run.getparent() if run is not None else None
    require(ctrl is not None and ctrl.tag==P+'ctrl' and len(ctrl)==1 and run is not None and run.tag==P+'run' and host is not None and host.tag==P+'p' and host.getparent().tag.endswith('}sec'),'root body field required')
    params=field.findall(P+'parameters');require(len(params)==1 and list(field)==params,'one explicit native parameter group required');params=params[0];required={'Prop','Command','Path','Category','TargetType','DocOpenType'};values={}
    for n in params:
        require(n.tag in [P+'stringParam',P+'integerParam'] and set(n.attrib)=={'name'} and not len(n) and n.get('name') not in values,'plain unique parameter leaves required');values[n.get('name')]=n
    require(set(values)==required and params.get('cnt')=='6','exact six-parameter native web-field shape required')
    require(values['Command'].tag==values['Path'].tag==P+'stringParam' and values['Command'].text==old+';1;0;0' and values['Path'].text==old and values['Category'].text=='HWPHYPERLINK_TYPE_URL','name/Command/Path inconsistent or nonweb link')
    ends=[n for _,root in sections for n in root.iter(P+'fieldEnd') if n.get('beginIDRef')==field.get('id')];require(len(ends)==1,'one matching fieldEnd required');end=ends[0];require(end.get('fieldid')==field.get('fieldid'),'paired native fieldid mismatch')
    displayed=[];inside=False;started=False;finished=False
    for r in host:
        if r.tag==P+'linesegarray':continue
        require(r.tag==P+'run','unsupported host paragraph child')
        for n in r:
            if n.tag==P+'t':
                require(not len(n),'only plain host text supported')
                if inside:displayed.append(n.text or '')
            elif n.tag==P+'ctrl':
                require(len(n)==1 and n[0] in [field,end],'multiple/nested/other host controls unsupported')
                if n[0] is field:require(not started and not finished,'duplicate start');inside=True;started=True
                else:require(inside and not finished,'mispaired field end');inside=False;finished=True
            else:raise ValueError('unsupported host run element')
    require(started and finished and not inside and ''.join(displayed),'complete visible hyperlink span required')
    return dict(ordinal=ordinal,part=part,fieldId=field.get('id'),nativeFieldId=field.get('fieldid'),fieldPath=list(location(field)),fieldSha256=fingerprint(field),endPath=list(location(end)),endSha256=fingerprint(end),hostPath=list(location(host)),hostId=host.get('id'),hostSha256=fingerprint(host),url=old,displayText=''.join(displayed),parameters={k:dict(path=list(location(n)),tag=n.tag,text=n.text) for k,n in values.items()})

def checked(source,req):
    require(isinstance(req,dict) and set(req)=={'schema','sourceSha256','hyperlink','replacement','editableReason'} and req['schema']==SCHEMA,'exact hyperlink request schema required');require(sha(source)==req['sourceSha256'],'stale source');oracle.single_line(req['editableReason'],search=True);require(len(req['editableReason'])>=8,'specific reason required');bound=inspect(source,req['hyperlink']['ordinal']);require(bound==req['hyperlink'],'stale/mismatched full hyperlink binding');new=url(req['replacement']);require(new!=bound['url'],'actual web target change required')
    text={(bound['part'],tuple(bound['parameters'][k]['path'])):new+(';1;0;0' if k=='Command' else '') for k in ['Command','Path']};attrs={(bound['part'],tuple(bound['fieldPath'])):{'name':new}}
    return bound,text,attrs

def verify(source,output,req):
    bound,text,attrs=checked(source,req);require(oracle.snapshot(source,text,attribute_overrides=attrs)==oracle.snapshot(output),'non-target structure/style/text/member changed or target metadata incomplete');after=inspect(output,bound['ordinal']);require(after['url']==req['replacement'] and after['fieldId']==bound['fieldId'] and after['nativeFieldId']==bound['nativeFieldId'] and after['hostId']==bound['hostId'] and after['displayText']==bound['displayText'],'target/span/identity mismatch')
    return dict(status='PASS_HYPERLINK_TARGET_PRESERVATION',nameCommandAndPathUpdatedTogether=True,fieldPairDisplayTextStylesExact=True,wholeNonTargetPackageExact=True,noLayoutCacheException=True)

def apply(source,output,req,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified exposed-field adapter version');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new workspace output required');bound,_,_=checked(source,req)
    with workspace_candidate_directory(prefix='hyperlink-target-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            sections={s.part_name:s for s in doc.sections};section=sections.get(bound['part']);require(section is not None,'public section missing');field=at(section.element,bound['fieldPath']);host=at(section.element,bound['hostPath']);require(fingerprint(field)==bound['fieldSha256'] and fingerprint(host)==bound['hostSha256'],'public exposed field subtree mismatch');hosts=[p for p in section.paragraphs if p.element is host];require(len(hosts)==1,'public host missing');adapter=InlineObject(field,hosts[0]);require(adapter.get_attribute('name')==bound['url'],'public field name mismatch')
            # Explicit, version-bound existing-field adapter: only the two
            # pre-inspected plain parameter leaves; no new nodes or attributes.
            for key in ['Command','Path']:
                leaf=at(section.element,bound['parameters'][key]['path']);require(leaf.get('name')==key and leaf.text==bound['parameters'][key]['text'],'bound parameter mismatch');leaf.text=req['replacement']+(';1;0;0' if key=='Command' else '')
            adapter.set_attribute('name',req['replacement']);doc.save_to_path(candidate)
        checks=verify(source,candidate,req);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==req['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',sourceSha256=sha(source),candidateSha256=sha(candidate),checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
