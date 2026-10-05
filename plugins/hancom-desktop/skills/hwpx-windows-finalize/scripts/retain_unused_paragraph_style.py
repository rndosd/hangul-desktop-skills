"""Keep explicitly diagnosed unused paragraph formats as named PARA styles."""
from pathlib import Path
import sys,copy,shutil,json
from importlib.metadata import version
S=Path(__file__).resolve().parent
sys.path.insert(0,str(S.parent.parent/'hwpx/scripts'))
from candidate_runtime import activate
activate()
from hwpx import HwpxDocument
import safe_edit as oracle
from namespace_literal_guard import preserve_namespace_literals
H='{http://www.hancom.co.kr/hwpml/2011/head}'
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
def need(ok,message):
    if not ok:raise ValueError(message)
def inspect(source,ids):
    source=Path(source).resolve(strict=True);need(version('python-hwpx')=='6.3.0','qualified6.3.0required')
    need(isinstance(ids,list) and 1<=len(ids)<=5 and all(isinstance(x,str) and x.isdigit() for x in ids) and len(set(ids))==len(ids),'explicit1–5unique paragraph definitionIDs required')
    from zipfile import ZipFile
    with ZipFile(source) as z:header=oracle.parse(z.read('Contents/header.xml'))
    definitions=header.find('.//'+H+'paraProperties');styles=header.find('.//'+H+'styles');need(definitions is not None and styles is not None,'existing native containers required')
    native=styles.find(H+'style');need(native is not None and set(native.attrib)=={'id','type','name','engName','paraPrIDRef','charPrIDRef','nextStyleIDRef','langID','lockForm'} and native.get('type')=='PARA','complete existing PARA style template required')
    incoming={identity:[] for identity in ids}
    for part,root in oracle.sections(source)+[('Contents/header.xml',header)]:
        for n in root.iter():
            identity=n.get('paraPrIDRef')
            if identity in incoming:incoming[identity].append(dict(part=part,tag=n.tag))
    rows=[]
    for identity in ids:
        found=[n for n in definitions if n.get('id')==identity];need(len(found)==1,'missing/ambiguous diagnosed paragraph definition')
        if incoming[identity]:rows.append(dict(id=identity,alreadyReferenced=True,referenceCount=len(incoming[identity])));continue
        name='보존 문단서식 '+identity;need(not any(n.get('name')==name or n.get('engName')=='RetainedParagraph'+identity for n in styles),'retention Korean or English name collision')
        rows.append(dict(id=identity,alreadyReferenced=False,name=name,engName='RetainedParagraph'+identity,oldDefinition=oracle.shape(found[0]) if hasattr(oracle,'shape') else dict(found[0].attrib)))
    need(len(styles)+sum(not t['alreadyReferenced'] for t in rows)<=160,'native160style limit would be exceeded')
    styleids=[n.get('id') for n in styles]
    need(all(x and x.isdigit() for x in styleids) and len(set(styleids))==len(styleids),'unique numeric style IDs required')
    return dict(sourceSha256=oracle.digest(source),ids=ids,targets=rows,template=dict(native.attrib))
@preserve_namespace_literals
def apply(source,output,binding):
    source=Path(source).resolve(strict=True);output=Path(output).absolute();need(binding==inspect(source,binding['ids']),'stale retention binding');need(not output.exists() and output.parent.is_dir() and output.resolve()!=source and output.suffix.lower()=='.hwpx','new private HWPX required')
    selected=[t for t in binding['targets'] if not t['alreadyReferenced']];changes=[]
    if not selected:
        shutil.copyfile(source,output);need(source.read_bytes()==output.read_bytes(),'unchanged byte copy mismatch');return dict(status='NO_RETENTION_NEEDED_BYTE_COPY',sourceSha256=binding['sourceSha256'],outputSha256=oracle.digest(output),changes=[],allNonTargetPackageExact=True)
    from zipfile import ZipFile
    with ZipFile(source) as z:expected=oracle.parse(z.read('Contents/header.xml'))
    container=expected.find('.//'+H+'styles');base=binding['template'];nextid=max(int(n.get('id')) for n in container)+1
    with HwpxDocument.open(source) as doc:
        header=doc.parts.headers[0]
        for target in selected:
            wanted=dict(base,id=str(nextid),type='PARA',name=target['name'],engName=target['engName'],paraPrIDRef=target['id'])
            identity=header.ensure_style(wanted['name'],style_type='PARA',eng_name=wanted['engName'],para_pr_id_ref=wanted['paraPrIDRef'],char_pr_id_ref=wanted['charPrIDRef'],next_style_id_ref=wanted['nextStyleIDRef'],lang_id=int(wanted['langID']),lock_form=False)
            need(identity==str(nextid),'public style identity allocation differs')
            actual=next(n for n in header.element.iter(H+'style') if n.get('id')==identity)
            # ensure_style omits false lockForm on a fresh style; public6.3.0
            # exposed-element adapter pins the existing native template value.
            actual.set('lockForm',wanted['lockForm']);header.mark_dirty();need(dict(actual.attrib)==wanted,'public named style changed unrequested fields')
            clone=copy.deepcopy(container.find(H+'style'));clone.attrib.clear();clone.attrib.update(wanted);need(not len(clone),'non-empty style template unsupported');container.append(clone)
            changes.append(dict(paraPrID=target['id'],newStyleId=identity,newStyleName=wanted['name'],onlyNewHeaderStyle=True));nextid+=1
        container.set('itemCnt',str(len(container)));doc.save_to_path(output)
    need(oracle.snapshot(source,xml_roots={'Contents/header.xml':expected})==oracle.snapshot(output),'retention changed beyond exact new named styles')
    need(oracle.digest(source)==binding['sourceSha256'],'source changed')
    return dict(status='PASS_PUBLIC_NAMED_STYLE_RETENTION_ONLY',sourceSha256=binding['sourceSha256'],outputSha256=oracle.digest(output),changes=changes,allNonTargetPackageExact=True,originalDefinitionsTextCellsMarginsAssetsExact=True,newNamedStylesVisibleInStylePalette=True,native='NOT_CHECKED',scope='Explicit diagnosed unused paragraphs only; no save comparator exception or original definition deletion.')
