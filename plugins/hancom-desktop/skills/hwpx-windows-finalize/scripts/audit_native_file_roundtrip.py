"""Read-only native HWPX round-trip audit; PDF equality is not an input."""
from pathlib import Path
from zipfile import ZipFile
import hashlib,json,argparse
import compare_active_semantics as semantics
import compare_package_definitions as definitions

def ref(p):
    p=Path(p)
    return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)

def raw_tree(n):
    return [n.tag,dict(sorted(n.attrib.items())),n.text,n.tail,[raw_tree(c) for c in n]]

def archive(a,b):
    with ZipFile(a) as x,ZipFile(b) as y:
        def collect(z):
            infos=z.infolist()
            if len(infos)!=len(set(i.filename for i in infos)):raise ValueError('duplicate archive member')
            return {i.filename:z.read(i) for i in infos},{i.filename:dict(dateTime=i.date_time,compression=i.compress_type,compressedBytes=i.compress_size,crc=i.CRC,externalAttributes=i.external_attr,extraHex=i.extra.hex(),commentHex=i.comment.hex()) for i in infos}
        aa,am=collect(x);bb,bm=collect(y);rows=[]
        for name in sorted(aa.keys()|bb.keys()):
            av,bv=aa.get(name),bb.get(name)
            if av==bv:continue
            row=dict(member=name,beforeSha256=hashlib.sha256(av).hexdigest() if av is not None else None,afterSha256=hashlib.sha256(bv).hexdigest() if bv is not None else None)
            if av is not None and bv is not None and name.endswith(('.xml','.hpf')):
                at,bt=raw_tree(semantics.parse(av)),raw_tree(semantics.parse(bv))
                row.update(expandedXmlTreeExact=at==bt,rawTreeDifferences=semantics.first_differences(at,bt),normalization='None: all attributes, text, tail and ordered children retained; namespace prefix/declaration bytes reported by member hashes.')
            rows.append(row)
        return dict(fileByteExact=Path(a).read_bytes()==Path(b).read_bytes(),memberInventoryExact=aa.keys()==bb.keys(),memberOrderExact=x.namelist()==y.namelist(),archiveCommentExact=x.comment==y.comment,allUncompressedMemberBytesExact=aa==bb,
            memberChanges=rows,containerMetadataChanges=[dict(member=n,before=am.get(n),after=bm.get(n)) for n in sorted(am.keys()|bm.keys()) if am.get(n)!=bm.get(n)])

def audit(a,b):
    inputs=[ref(a),ref(b)];active=semantics.compare(a,b);all_defs=definitions.audit(a,b);raw=archive(a,b)
    if [ref(a),ref(b)]!=inputs:raise ValueError('input changed during read-only audit')
    strict='PASS' if active['status']=='PASS_ACTIVE_SEMANTICS' and all_defs['allHeaderDefinitionsExact'] else 'FAIL'
    return dict(schema='hwpx.native-file-roundtrip.v1',source=inputs[0],final=inputs[1],archive=raw,active=active,allDefinitions=all_defs,strictActiveAndAllDefinitions=strict,
        strictFileIdentity='EXACT' if raw['fileByteExact'] else 'DIFFERENT',inputsUnchanged=True,noNativeCalls=True,noWritesToInputs=True,
        pdfComparison='SEPARATE_NOT_CHECKED',sameFeatureReedit='SEPARATE_NOT_CHECKED',visual='SEPARATE_NOT_CHECKED',overallCompletion='NOT_GRANTED',
        policy='Every difference remains reported. No height, cache, metadata or unused-definition allowance added. Byte identity, raw XML, active meaning and full definition inventory are separate. PDF equality never grants HWPX preservation.')

def main():
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('final');p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output).resolve();inputs=[Path(args.source).resolve(strict=True),Path(args.final).resolve(strict=True)]
    if out in inputs or out.exists():raise ValueError('new output separate from source/final required')
    v=audit(*inputs)
    with out.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v[k] for k in ['strictFileIdentity','strictActiveAndAllDefinitions','overallCompletion']},ensure_ascii=False))
    return 0 if v['strictFileIdentity']=='EXACT' and v['strictActiveAndAllDefinitions']=='PASS' else 3

if __name__=='__main__':raise SystemExit(main())
