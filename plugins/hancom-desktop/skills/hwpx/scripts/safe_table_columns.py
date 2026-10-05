"""Existing unmerged plain multi-paragraph table column redistribution only."""
from pathlib import Path
import argparse,copy,hashlib,json,math,os,tempfile
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,require,sha,locate
from safe_cell_spacing import shape,snapshot,effective
SCHEMA='hwpx.table-columns.v1'
def plan(data,req):
 require(isinstance(req,dict) and set(req)=={'schema','source_sha256','table','widths_mm'} and req['schema']==SCHEMA and req['source_sha256']==hashlib.sha256(data).hexdigest(),'invalid/stale columns request')
 m,part,r,t=locate(data,req['table']);cs,g=shape(t);require(all(c.find(P+'cellSpan').get('rowSpan')==c.find(P+'cellSpan').get('colSpan')=='1' for c in cs.values()),'unmerged table required')
 require(t.get('lock','0')=='0' and t.get('noAdjust','0')=='0' and t.find(P+'sz').get('protect','0')=='0' and all(c.get('protect','0')=='0' for c in cs.values()),'protected/fixed table unsupported');require(t.find(P+'pos').get('treatAsChar')=='0' and t.get('pageBreak')=='TABLE','floating whole-row table required');require(t.getparent().getparent().getparent() is r,'direct body table required')
 widths=req['widths_mm'];require(isinstance(widths,list) and len(widths)==int(t.get('colCnt')) and all(type(v)in[int,float] and math.isfinite(v) and 5<=v<=250 for v in widths),'explicit finite widths for every column required');total=int(t.find(P+'sz').get('width'));require(abs(sum(widths)*7200/25.4-total)<=6,'preserve total table width');result=[];allocated=0
 for i,v in enumerate(widths):
  w=total-allocated if i==len(widths)-1 else round(total*v/sum(widths));result.append(w);allocated+=w
 for a,c in cs.items():
  require(int(c.find(P+'cellSz').get('width'))==int(cs[0,a[1]].find(P+'cellSz').get('width')),'uneven existing columns unsupported');margins=effective(c,t);require(result[a[1]]-margins['left']-margins['right']>=round(5*7200/25.4),'usable cell width below 5mm')
 require(any(int(cs[0,x].find(P+'cellSz').get('width'))!=w for x,w in enumerate(result)),'no changes');return m,part,r,t,cs,result

def verify(before,after,req):
 bm,part,br,bt,bc,widths=plan(before,req);am,ap,ar,at=locate(after,req['table']);expected=copy.deepcopy(br);et=list(expected.iter(P+'tbl'))[list(br.iter(P+'tbl')).index(bt)];ec,_=shape(et)
 for a,c in ec.items():c.find(P+'cellSz').set('width',str(widths[a[1]]))
 require(ap==part and set(bm)==set(am) and snapshot(expected)==snapshot(ar),'changed beyond exact column widths')
 for name in bm:
  if name!=part:require(bm[name]==am[name],'non-target package changed '+name)
 return dict(exactColumnWidths=True,tableWidthHeightAndBodyGeometryPreserved=True,allParagraphsRunsListsStylesBordersPreserved=True,nonTargetPayloadEqual=True)
def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0' and source.suffix.lower()=='.hwpx' and output.suffix.lower()=='.hwpx' and not output.exists() and output.parent.is_dir() and source!=output.resolve(),'new hwpx output and pinned core required');before=source.read_bytes();_,part,_,t,_,widths=plan(before,req)
 with HwpxDocument.open(source) as doc:
  found=[x for s in doc.sections for p in s.paragraphs for x in p.tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous table');found[0].set_column_widths(req['widths_mm']);after=doc.to_bytes()
 checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='columns-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(after);require(validate_editor_open_safety(p).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.table-columns-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',published=not dry_run,source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),request=req,checks=checks,native='pending')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true');v=p.parse_args();print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
