"""Optional fresh-report objects on top of the validated new-document composer.

This module never opens an existing report to rewrite its XML. Public 6.3.0
authoring APIs are used; the note adapter below affects newly created notes only.
Native output/reopen and visual completion are separate from PASS_STRUCTURE.
"""
from pathlib import Path
import argparse, hashlib, json, math, tempfile, zipfile
from urllib.parse import urlsplit
import xml.etree.ElementTree as E
import pymupdf
import create_new_document as base
from hwpx.tools.package_validator import validate_editor_open_safety

SCHEMA='hwpx.report-objects.v1'
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'

def require(v,m):
    if not v: raise ValueError(m)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mm(v,low,high):
    require(type(v) in (int,float) and math.isfinite(v) and low<=v<=high,'invalid size')
    return round(v*7200/25.4)
def string(v):
    require(isinstance(v,str) and bool(v.strip()) and '\r' not in v and '\x00' not in v,'nonempty text required')
    return v
def checked_image(path):
    p=Path(path).resolve(strict=True)
    require(p.stat().st_size<=25000000,'image file too large')
    data=p.read_bytes()
    fmt='png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'jpg' if data.startswith(b'\xff\xd8\xff') else None
    require(fmt and p.suffix.lower() in (('.png',) if fmt=='png' else ('.jpg','.jpeg')),'PNG/JPEG signature and extension must agree')
    pix=pymupdf.Pixmap(data)
    require(pix.width*pix.height<=50000000,'image pixel count too large')
    return data,pix,fmt

def validate(brief,design,objects):
    require(isinstance(objects,dict) and set(objects)=={'schema','items'} and objects['schema']==SCHEMA,'invalid object schema')
    require(isinstance(objects['items'],list) and 0<len(objects['items'])<=30,'1..30 objects required')
    checked=base.validate(brief,base.prepare_design(brief,design))
    require(checked['ok'],'base design validation failed')
    fmt=checked['resolved_format']
    usable=(297 if fmt['orientation']=='landscape' else 210)-fmt['margins_mm']['left']-fmt['margins_mm']['right']
    blocks={b['id']:b for b in design['plan']['blocks']}
    kinds={
        'picture':{'kind','block','path','sha256','width_mm','caption','gap_mm'},
        'box':{'kind','block','text','width_mm','height_mm'},
        'footnote':{'kind','block','text'},'endnote':{'kind','block','text'},
        'bookmark':{'kind','block','name'},
        'hyperlink':{'kind','block','url','text'},
    }
    replacing=set();bookmarks=set()
    for s in objects['items']:
        require(isinstance(s,dict) and s.get('kind') in kinds and not set(s)-kinds[s['kind']],'unsupported object/options')
        b=blocks.get(s.get('block'))
        require(b and b['type']=='paragraph' and not b.get('list'),'target must be a plain planned body paragraph')
        require(sum(x.get('text')==b['text'] for x in design['plan']['blocks'])==1,'ambiguous anchor text')
        kind=s['kind']
        if kind in ('picture','box','hyperlink'):
            require(s['block'] not in replacing,'duplicate replacement anchor')
            replacing.add(s['block'])
        if kind in ('footnote','endnote','box','hyperlink'):string(s.get('text'))
        if kind=='picture':
            p=Path(s['path']).resolve(strict=True)
            require(p.suffix.lower() in ('.png','.jpg','.jpeg') and sha(p)==s.get('sha256'),'image type/hash mismatch')
            _,pix,_=checked_image(p)
            mm(s['width_mm'],10,170);mm(s['width_mm']*pix.height/pix.width,5,180)
            require(s['width_mm']<=usable,'picture wider than usable page')
            string(s.get('caption'));mm(s.get('gap_mm',3),0,8)
        if kind=='box':
            mm(s['width_mm'],20,170);mm(s['height_mm'],10,80)
            require(s['width_mm']<=usable,'box wider than usable page')
        if kind=='bookmark':
            name=string(s.get('name'));require(len(name)<=40 and name not in bookmarks,'duplicate/long bookmark')
            bookmarks.add(name)
        if kind=='hyperlink':
            u=urlsplit(string(s.get('url')))
            require(u.scheme in ('https','http') and u.hostname and not u.username and not u.password and ';' not in s['url'] and not any(c.isspace() for c in s['url']),'web URL only; encode literal semicolons/whitespace')
    # These combinations can otherwise alter which text a note belongs to.
    require(not any(s['block'] in replacing and s['kind'] in ('footnote','endnote','bookmark') for s in objects['items']),'mixed anchor ownership')
    return checked

def canonical_new_note(note):
    # 6.3.0 emits lowercase instid, but native Hangul serializes instId.
    # Only our just-created note is adapted; existing controls are never touched.
    n=note.element
    if 'instid' in n.attrib:n.set('instId',n.attrib.pop('instid'))

def apply(doc,design,objects,fmt):
    blocks={b['id']:b for b in design['plan']['blocks']}
    body=doc.styles.ensure_run(font=fmt['font'],size=fmt['body_pt'])
    small=doc.styles.ensure_run(font=fmt['font'],size=max(8,fmt['body_pt']-2))
    for s in objects['items']:
        found=[p for p in doc.paragraphs if p.text==blocks[s['block']]['text']]
        require(len(found)==1,'unique paragraph not found')
        p=found[0];kind=s['kind']
        if kind=='picture':
            asset=Path(s['path']);data,pix,fmt_image=checked_image(asset);width=mm(s['width_mm'],10,170)
            require(hashlib.sha256(data).hexdigest()==s['sha256'],'image changed during authoring')
            p.text=''
            image=doc.media.add_image(data,fmt_image)
            obj=p.add_picture(str(image),width=width,height=round(width*pix.height/pix.width),treat_as_char=True,char_pr_id_ref=body)
            obj.set_caption(s['caption'],side='BOTTOM',gap=mm(s.get('gap_mm',3),0,8),char_pr_id_ref=small)
        elif kind=='box':
            p.text=''
            obj=doc.shapes.add_rectangle(width=mm(s['width_mm'],20,170),height=mm(s['height_mm'],10,80),fill_color='#EFF4F7',line_color='#CBD7DF',paragraph=p)
            draw=obj.set_draw_text('',editable=True,char_pr_id_ref=body,margin={k:mm(2,0,8) for k in ('left','right','top','bottom')})
            inner=draw.paragraphs[0]
            for run in list(inner.runs):run.remove()
            # Public opt-in native lineBreak fixes literal newline serialization.
            inner.add_run(s['text'],char_pr_id_ref=body,expand_special_characters=True)
        elif kind in ('footnote','endnote'):
            note=getattr(doc.notes,'add_'+kind)(' '+s['text'],paragraph=p,char_pr_id_ref=small)
            canonical_new_note(note)
        elif kind=='bookmark':doc.refs.add_bookmark(s['name'],paragraph=p)
        elif kind=='hyperlink':
            p.text=''
            link=doc.refs.add_hyperlink(s['url'],s['text'],paragraph=p,char_pr_id_ref=doc.styles.ensure_run(font=fmt['font'],size=fmt['body_pt'],color='#225A90',underline=True))
            # Explicit fresh-field adapter. 6.3.0 puts URL in name alone,
            # so Hangul interprets the field as an internal bookmark link.
            # Official ParameterSetTable_2504 pp174-175 defines URL;1;0;0.
            field=link.element.find(P+'fieldBegin')
            require(field is not None and field.find(P+'parameters') is None,'unexpected new hyperlink')
            field.set('editable','0');field.set('dirty','0')
            params=field.makeelement(P+'parameters',{'cnt':'2','name':''});field.append(params)
            prop=params.makeelement(P+'integerParam',{'name':'Prop'});prop.text='0';params.append(prop)
            command=params.makeelement(P+'stringParam',{'name':'Command'});command.text=s['url']+';1;0;0';params.append(command)
    # Fresh sub-stories can have a default paragraph ID of zero in 6.3.0.
    # Remap duplicates before the first publication, never an existing document.
    used=set();nextid=100000
    for sec in doc.sections:
        for p in sec.element.iter(P+'p'):
            if p.get('id') in used:
                while str(nextid) in used:nextid+=1
                p.set('id',str(nextid));nextid+=1
            used.add(p.get('id'))
        sec.mark_dirty()

def body_texts(path):
    with zipfile.ZipFile(path) as z:
        return [''.join(t.text or '' for t in p.findall(P+'run/'+P+'t')) for n in z.namelist() if n.startswith('Contents/section') and n.endswith('.xml') for p in E.fromstring(z.read(n)).findall(P+'p')]

def readback(path,design,objects,baseline=None):
    with zipfile.ZipFile(path) as z:
        roots=[E.fromstring(z.read(n)) for n in z.namelist() if n.startswith('Contents/section') and n.endswith('.xml')]
        def text(t):
            return (t.text or '')+''.join(('\n' if c.tag==P+'lineBreak' else ''.join(c.itertext()))+(c.tail or '') for c in t)
        texts='\n'.join(text(t) for root in roots for t in root.iter(P+'t'))
        ids=[p.get('id') for root in roots for p in root.iter(P+'p')]
        require(len(ids)==len(set(ids)),'duplicate paragraph IDs')
        for s in objects['items']:
            expected=s.get('caption') if s['kind']=='picture' else s.get('text')
            if expected:require(expected in texts,'object text missing')
        inv={k:sum(len(list(r.iter(P+k))) for r in roots) for k in ('pic','caption','rect','footNote','endNote','bookmark','fieldBegin')}
        require(inv['pic']==sum(s['kind']=='picture' for s in objects['items']),'picture count')
        require(inv['caption']==inv['pic'],'attached caption count')
        require(inv['footNote']==sum(s['kind']=='footnote' for s in objects['items']),'footnote count')
        require(inv['endNote']==sum(s['kind']=='endnote' for s in objects['items']),'endnote count')
        require(inv['bookmark']==sum(s['kind']=='bookmark' for s in objects['items']),'bookmark count')
        require(inv['fieldBegin']==sum(s['kind']=='hyperlink' for s in objects['items']),'hyperlink count')
        blocks={b['id']:b for b in design['plan']['blocks']}
        replacements={blocks[s['block']]['text']:s['text'] if s['kind']=='hyperlink' else '' for s in objects['items'] if s['kind'] in ('picture','box','hyperlink')}
        if baseline is not None:
            require(body_texts(path)==[replacements.get(t,t) for t in body_texts(baseline)],'non-target body paragraphs changed')
        for s in objects['items']:
            if s['kind']=='hyperlink':
                fields=[f for r in roots for f in r.iter(P+'fieldBegin') if f.get('name')==s['url']]
                require(len(fields)==1,'unique hyperlink missing')
                commands=fields[0].findall(P+'parameters/'+P+'stringParam')
                require(any(n.get('name')=='Command' and n.text==s['url']+';1;0;0' for n in commands),'web target command missing')
            if s['kind']=='bookmark':
                require(sum(n.get('name')==s['name'] for r in roots for n in r.iter(P+'bookmark'))==1,'bookmark name missing')
    require(validate_editor_open_safety(path).ok,'editor open safety')
    return inv

def create(brief,design,objects,output):
    output=Path(output).resolve();receipt=output.with_suffix('.objects-receipt.json')
    require(output.suffix.lower()=='.hwpx' and not output.exists() and not receipt.exists(),'new HWPX/receipt paths required')
    design=base.prepare_design(brief,design);check=validate(brief,design,objects)
    doc,_=base.compose(brief,design)
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
            pre=Path(tmp)/'base.hwpx';doc.save_to_path(pre)
            require(base.audit_output(pre,brief,design)['status']=='PASS_STRUCTURE','base output audit')
            apply(doc,design,objects,check['resolved_format'])
            candidate=Path(tmp)/'candidate.hwpx';doc.save_to_path(candidate)
            inventory=readback(candidate,design,objects,pre)
            with output.open('xb') as f:f.write(candidate.read_bytes())
    finally:doc.close()
    result=dict(schema=SCHEMA,status='PASS_STRUCTURE',native='PENDING',outputSha256=sha(output),inventory=inventory,baseValidated=check['ok'],objects=objects)
    with receipt.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--brief',required=True);p.add_argument('--design',required=True);p.add_argument('--objects',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();read=lambda x:json.loads(Path(x).read_text(encoding='utf-8-sig'))
    print(json.dumps(create(read(a.brief),read(a.design),read(a.objects),a.output),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
