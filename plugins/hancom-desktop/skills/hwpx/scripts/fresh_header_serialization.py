"""Qualified fresh-only public 6.3.0 header serialization, not an existing editor.

Observed in Hangul13.0.0.3903; original first-save failures remain evidence.
"""
from pathlib import Path
from importlib.metadata import version
from weakref import WeakKeyDictionary
import os,hashlib,struct

H='{http://www.hancom.co.kr/hwpml/2011/head}'
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
FIELDS=('weight','proportion','contrast','strokeVariation','armStyle','letterform','midline','xHeight')
QUALIFIED_FONT_SHA='0086c19e81d293a542e7d75564c645fb58070cc850aefebf8fa1c397858e510c'
_fresh=WeakKeyDictionary()

def need(value,message):
    if not value:raise ValueError(message)

def register_new(doc):
    need(version('python-hwpx')=='6.3.0','fresh header requires qualified python-hwpx6.3.0')
    need(doc not in _fresh and len(doc.sections)==1 and len(doc.parts.headers)==1,'single new document lifecycle required')
    # Caller creates HwpxDocument.new immediately before this registration.
    need(not any(p.text for p in doc.paragraphs),'registration is only for empty new document')
    _fresh[doc]={n.get('id') for n in doc.parts.headers[0].element.iter(H+'paraPr')}

def font_metadata(path=None):
    path=Path(path) if path is not None else Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/malgun.ttf'
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    need(digest==QUALIFIED_FONT_SHA,'unqualified Malgun font: preserve source and qualify this font version first')
    tables={}
    for i in range(struct.unpack_from('>H',data,4)[0]):
        tag,_,off,length=struct.unpack_from('>4sIII',data,12+16*i);tables[tag.decode()]=(off,length)
    need('OS/2' in tables and tables['OS/2'][1]>=42,'OS/2 PANOSE data required')
    panose=list(data[tables['OS/2'][0]+32:tables['OS/2'][0]+42])
    need(panose==[2,11,5,3,2,0,0,2,0,4],'qualified Malgun PANOSE differs')
    return dict(path=str(path.resolve()),sha256=digest,bytes=len(data),panose=panose,typeInfo=dict(familyType='FCAT_GOTHIC',**{k:str(v) for k,v in zip(FIELDS,panose[2:])}))

def prepare(doc):
    need(doc in _fresh,'existing documents cannot enter fresh serialization')
    need(version('python-hwpx')=='6.3.0','fresh serialization requires6.3.0')
    header=doc.parts.headers[0];root=header.element;seed=_fresh[doc];font=font_metadata();faces=list(root.iter(H+'fontface'));pr=list(root.iter(H+'paraPr'));styles=root.find('.//'+H+'styles')
    need(len(faces)==7 and styles is not None,'qualified7language fonts/styles required')
    # Validate all supported structures before changing any field.
    fontplans=[];paragraphplans=[]
    for face in faces:
        fonts=list(face);need({n.get('face') for n in fonts}=={'맑은 고딕','함초롬돋움','함초롬바탕'} and len(fonts)==3,'qualified Malgun/seed font set required')
        wanted=[next(n for n in fonts if n.get('face')==name) for name in ['맑은 고딕','함초롬돋움','함초롬바탕']]
        mapping={n.get('id'):str(i) for i,n in enumerate(wanted)}
        need(len(mapping)==3 and all(n.get('type')=='TTF' and n.get('isEmbedded')=='0' for n in fonts),'unembedded unique TTF font IDs required')
        m=wanted[0];info=m.find(H+'typeInfo');need(info is None or dict(info.attrib)==font['typeInfo'],'existing Malgun metadata differs')
        fontplans.append((face,wanted,mapping,info is None))
    for n in pr:
        if n.get('id') in seed:continue
        modern=n.find(P+'switch/'+P+'case');fallback=n.find(P+'switch/'+P+'default')
        need(modern is not None and fallback is not None,'new paragraph requires both compatibility branches')
        cm=modern.find(H+'margin');dm=fallback.find(H+'margin');cl=modern.find(H+'lineSpacing');dl=fallback.find(H+'lineSpacing')
        need(cm is not None and dm is not None and cl is not None and dl is not None and len(cm)==len(dm)==5,'qualified margin and lineSpacing shape required')
        need([x.tag for x in cm]==[x.tag for x in dm] and all(x.get('unit')=='HWPUNIT' for x in list(cm)+list(dm)),'qualified HWPUNIT margins required')
        need(all(int(y.get('value')) in (int(x.get('value')),2*int(x.get('value'))) for x,y in zip(cm,dm)),'unqualified compatibility margin relation')
        need(cl.get('type')==dl.get('type')=='PERCENT' and cl.get('value')==dl.get('value') and all(x.get('unit') in ('PERCENT','HWPUNIT') for x in [cl,dl]),'qualified percentage line spacing required')
        paragraphplans.append((n,cm,dm,cl,dl))
    refs={n.get('paraPrIDRef') for section in doc.sections for n in section.element.iter() if n.get('paraPrIDRef') is not None}
    refs|={n.get('paraPrIDRef') for n in root.iter(H+'style')}
    unused=[n.get('id') for n in pr if n.get('id') not in seed and n.get('id') not in refs]
    need(len(styles)+len(unused)<=160,'fresh retention would exceed native160styles')
    for identity in unused:
        need(not any(n.get('name')=='작성 보존 문단서식 '+identity or n.get('engName')=='FreshRetainedParagraph'+identity for n in styles),'fresh retention name collision')
    changes=[]
    langkeys=dict(HANGUL='hangul',LATIN='latin',HANJA='hanja',JAPANESE='japanese',OTHER='other',SYMBOL='symbol',USER='user')
    for face,wanted,mapping,missing in fontplans:
        lang=langkeys[face.get('lang')]
        for ref in root.iter(H+'fontRef'):
            need(ref.get(lang) in mapping,'dangling fresh fontRef')
            ref.set(lang,mapping[ref.get(lang)])
        if missing:wanted[0].append(wanted[0].makeelement(H+'typeInfo',font['typeInfo']))
        for n in list(face):face.remove(n)
        for i,n in enumerate(wanted):n.set('id',str(i));face.append(n)
        changes.append(dict(kind='font',language=lang,idRemap=mapping,typeInfoAdded=missing))
    for n,cm,dm,cl,dl in paragraphplans:
        for x,y in zip(cm,dm):y.set('value',str(2*int(x.get('value'))))
        cl.set('unit','HWPUNIT');dl.set('unit','HWPUNIT')
        changes.append(dict(kind='paragraph',id=n.get('id'),modernIntentUnchanged=True,fallbackFactor=2,lineSpacingTypeAndValueUnchanged=True))
    for identity in unused:
        i=header.ensure_style('작성 보존 문단서식 '+identity,style_type='PARA',eng_name='FreshRetainedParagraph'+identity,para_pr_id_ref=identity,char_pr_id_ref='0',next_style_id_ref='0',lang_id=1042,lock_form=False)
        n=next(n for n in root.iter(H+'style') if n.get('id')==i);n.set('lockForm','0')
        changes.append(dict(kind='namedStyle',id=i,paraPrID=identity,name=n.get('name'),engName=n.get('engName')))
    header.mark_dirty()
    return dict(status='PASS_FRESH_HEADER_PREPARATION',changes=changes,font=font,seedParagraphIds=sorted(seed,key=int),newNamedStylesVisible=bool(unused),native='NOT_CHECKED',otherPCAndEngine='UNVERIFIED')

def margin_matches(shape,tag,value,tolerance=1):
    """Readback of intended modern values AND explicitly doubled fallback values."""
    a=shape.findall('hp:switch/hp:case/hh:margin/hc:'+tag,NS)
    b=shape.findall('hp:switch/hp:default/hh:margin/hc:'+tag,NS)
    return len(a)==len(b)==1 and a[0].get('unit')==b[0].get('unit')=='HWPUNIT' and abs(int(a[0].get('value','999999'))-value)<=tolerance and abs(int(b[0].get('value','999999'))-2*value)<=2*tolerance

NS={'hp':P[1:-1],'hh':H[1:-1],'hc':'http://www.hancom.co.kr/hwpml/2011/core'}
