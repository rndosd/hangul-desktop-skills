"""Replace one embedded raster payload; all XML/captions/geometry stay byte-exact.

Same image type and pixel dimensions only. Shared/linked/unbound assets fail.
This is an explicit new bounded operation, never a fallback from another BLOCK.
"""
from pathlib import Path
import argparse,hashlib,json,zipfile,os,tempfile
import pymupdf
from lxml import etree as E
from hwpx.tools.package_validator import validate_editor_open_safety

SCHEMA='hwpx.picture-payload-replace.v1'
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
def require(v,m):
    if not v:raise ValueError(m)
def sha(data):return hashlib.sha256(data).hexdigest()
def parse(data):
    p=E.XMLParser(resolve_entities=False,no_network=True,load_dtd=False)
    r=E.fromstring(data,p);require(not r.getroottree().docinfo.doctype,'DTD unsupported');return r
def raster(data):
    fmt='png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'jpg' if data.startswith(b'\xff\xd8\xff') else None
    require(fmt,'embedded PNG/JPEG only')
    pix=pymupdf.Pixmap(data);require(pix.width*pix.height<=50000000,'oversized image')
    return dict(format=fmt,width=pix.width,height=pix.height)

def inspect(source,image,picture=1):
    source=Path(source).resolve(strict=True);image=Path(image).resolve(strict=True)
    require(source.suffix.lower()=='.hwpx' and type(picture) is int and picture>=1,'HWPX and 1-based picture required')
    raw=source.read_bytes();new=image.read_bytes()
    require(len(raw)<=100000000 and len(new)<=25000000,'file too large')
    with zipfile.ZipFile(source) as z:
        require(sum(x.file_size for x in z.infolist())<=200000000,'expanded package too large')
        require(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),'invalid ZIP')
        parts={n:z.read(n) for n in z.namelist()}
    manifest=parse(parts['Contents/content.hpf'])
    paths={n.get('id'):n.get('href') for n in manifest.findall('{*}manifest/{*}item')}
    require(len(paths)==len(manifest.findall('{*}manifest/{*}item')),'duplicate manifest ID')
    sections=[]
    for n in manifest.findall('{*}spine/{*}itemref'):
        path=paths[n.get('idref')]
        if path not in parts:path='Contents/'+path
        if path.startswith('Contents/section') and path.endswith('.xml'):sections.append(path)
    pics=[(name,p) for name in sections for p in parse(parts[name]).iter(P+'pic')]
    require(picture<=len(pics),'picture out of range')
    section,obj=pics[picture-1]
    refs=[n.get('binaryItemIDRef') for n in obj.iter() if n.get('binaryItemIDRef')]
    require(len(refs)==1,'one picture binding required')
    identity=refs[0];payload=paths.get(identity)
    if payload and payload not in parts:payload='Contents/'+payload
    require(payload and payload.startswith('BinData/') and payload in parts,'linked/unresolved image')
    uses=sum(n.get('binaryItemIDRef')==identity for name,data in parts.items() if name.endswith(('.xml','.hpf')) for n in parse(data).iter())
    require(uses==1,'shared image binding; other objects would change')
    old=parts[payload];before=raster(old);after=raster(new)
    require(before==after,'replacement must have same image format and pixel dimensions; explicit reframing is a separate operation')
    require(sha(old)!=sha(new),'replacement is identical')
    return dict(schema=SCHEMA,source=str(source),sourceSha256=sha(raw),image=str(image),imageSha256=sha(new),picture=picture,
        section=section,objectId=obj.get('id'),objectSha256=sha(E.tostring(obj)),binaryItemId=identity,payload=payload,
        oldPayloadSha256=sha(old),raster=before,policy='single-unshared-payload-all-other-members-byte-exact')

def apply(plan,output,dry_run=False):
    require(isinstance(plan,dict) and plan.get('schema')==SCHEMA,'invalid plan schema')
    now=inspect(plan['source'],plan['image'],plan['picture'])
    require(now==plan,'stale/modified source, image or plan')
    out=Path(output).resolve();receipt=out.with_suffix('.picture-receipt.json')
    require(out.suffix.lower()=='.hwpx' and out!=Path(plan['source']) and not out.exists() and not receipt.exists(),'new output/receipt required')
    if dry_run:return dict(status='DRY_RUN_PASS',plan=plan,noOutputWritten=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    new=Path(plan['image']).read_bytes()
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        candidate=Path(tmp)/'candidate.hwpx'
        with zipfile.ZipFile(plan['source']) as z,zipfile.ZipFile(candidate,'x') as dst:
            for info in z.infolist():dst.writestr(info,new if info.filename==plan['payload'] else z.read(info.filename))
        with zipfile.ZipFile(plan['source']) as z,zipfile.ZipFile(candidate) as dst:
            require(z.namelist()==dst.namelist() and dst.testzip() is None,'package changed')
            require(all(dst.read(n)==z.read(n) for n in z.namelist() if n!=plan['payload']),'non-target member changed')
            require(sha(dst.read(plan['payload']))==plan['imageSha256'],'new image missing')
        require(validate_editor_open_safety(candidate).ok,'editor open safety')
        require(sha(Path(plan['source']).read_bytes())==plan['sourceSha256'] and sha(Path(plan['image']).read_bytes())==plan['imageSha256'],'input changed during operation')
        with out.open('xb') as f:f.write(candidate.read_bytes())
    result=dict(status='PASS_STRUCTURE',native='PENDING',plan=plan,outputSha256=sha(out.read_bytes()),allNonTargetMembersByteExact=True)
    with receipt.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    return result
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('inspect');x.add_argument('source');x.add_argument('image');x.add_argument('--picture',type=int,default=1);x.add_argument('--plan',required=True)
    x=sub.add_parser('apply');x.add_argument('plan');x.add_argument('--output',required=True);x.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.command=='inspect':
        value=inspect(a.source,a.image,a.picture)
        with Path(a.plan).open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    else:value=apply(json.loads(Path(a.plan).read_text(encoding='utf-8-sig')),a.output,a.dry_run)
    print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
