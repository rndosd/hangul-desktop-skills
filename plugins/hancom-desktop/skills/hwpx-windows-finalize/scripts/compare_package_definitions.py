"""Read-only package comparison, including definitions unused by rendered content."""
import sys,json,hashlib
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
def node(n):return [n.tag,dict(sorted(n.attrib.items())),n.text if n.text and n.text.strip() else None,n.tail if n.tail and n.tail.strip() else None,[node(c) for c in n]]
def audit(a,b):
 from compare_active_semantics import Package,H,first_differences
 before,after=Package(a),Package(b)
 ar,br=before.header.find(H+'refList'),after.header.find(H+'refList')
 da,db=node(ar),node(br)
 changed=[]
 for name in sorted(before.members.keys()|after.members.keys()):
  left,right=before.members.get(name),after.members.get(name)
  if left!=right:
   changed.append(dict(member=name,beforeSha256=hashlib.sha256(left).hexdigest() if left is not None else None,afterSha256=hashlib.sha256(right).hexdigest() if right is not None else None,category='binary asset' if name.startswith('BinData/') else 'preview' if name.startswith('Preview/') else 'definitions' if name=='Contents/header.xml' else 'section serialization/layout/selected geometry' if name.startswith('Contents/section') else 'package metadata/version/other'))
 return dict(source=before.ref,final=after.ref,fileByteExact=Path(a).read_bytes()==Path(b).read_bytes(),packageInventoryExact=before.members.keys()==after.members.keys(),allHeaderDefinitionsExact=da==db,definitionDifferences=first_differences(da,db),memberDifferences=changed,fullBytePreservation='PASS' if not changed else 'DIFFERENT',note='Byte differences are reported; active content proof, every-page output and re-edit tests are separate. Unused definition differences are not waived.')
if __name__=='__main__':
 sys.path.insert(0,sys.argv[1]);v=audit(sys.argv[2],sys.argv[3]);Path(sys.argv[4]).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v[k] for k in ['fileByteExact','allHeaderDefinitionsExact','definitionDifferences']},ensure_ascii=False))
