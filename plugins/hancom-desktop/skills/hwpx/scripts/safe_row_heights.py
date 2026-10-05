"""Explicit row heights for unmerged plain/native-empty cells; no other edits."""
from pathlib import Path
import argparse,copy,json,math,hashlib,os,tempfile
from importlib.metadata import version
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,require,sha,locate,geometry
from safe_cell_spacing import snapshot
from namespace_literal_guard import preserve_namespace_literals
SCHEMA='hwpx.explicit-row-heights.v1'
def checked(data,req):
 require(isinstance(req,dict) and set(req)=={'schema','source_sha256','table','heights_mm'} and req['schema']==SCHEMA and req['source_sha256']==hashlib.sha256(data).hexdigest(),'invalid/stale height request');require(type(req['table']) is int,'integer table required');m,part,root,t=locate(data,req['table']);cs,grid=geometry(t)
 require(t.get('lock','0')=='0' and t.get('noAdjust','0')=='0' and t.find(P+'sz').get('protect','0')=='0' and all(c.get('protect','0')=='0' for c in cs.values()),'protected/fixed target unsupported');require(t.getparent().getparent().getparent() is root and t.find(P+'pos').get('treatAsChar')=='0' and t.get('pageBreak')=='TABLE','direct floating whole-row table required');require(all(c.find(P+'cellSpan').get('rowSpan')==c.find(P+'cellSpan').get('colSpan')=='1' for c in cs.values()),'unmerged table required');heights=req['heights_mm'];require(isinstance(heights,list) and len(heights)==len(t.findall(P+'tr')) and all(type(v) in [int,float] and math.isfinite(v) and 5<=v<=60 for v in heights),'explicit bounded height for every row');return m,part,root,t,cs,[round(v*7200/25.4) for v in heights]
def verify(before,after,req):
 bm,part,root,t,cs,heights=checked(before,req);am,ap,ar,at=locate(after,req['table']);require(set(bm)==set(am) and part==ap,'package/part changed');expected=copy.deepcopy(root);et=list(expected.iter(P+'tbl'))[list(root.iter(P+'tbl')).index(t)];ec,_=geometry(et)
 for (y,x),c in ec.items():c.find(P+'cellSz').set('height',str(heights[y]))
 require(snapshot(expected)==snapshot(ar),'changed beyond explicit cell heights')
 for member in bm:
  if member!=part:require(bm[member]==am[member],'non-target member changed '+member)
 return dict(exactHeightsOnly=True,allTextStylesWidthsBordersAndNonTargetsExact=True)
@preserve_namespace_literals
def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0' and source.suffix.lower()==output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and source!=output.resolve(),'new hwpx/pinned core required');require(validate_editor_open_safety(source).ok,'source open safety failed');before=source.read_bytes();_,part,root,t,_,heights=checked(before,req);result=apply_table_ops(before,[dict(op='set_row_heights',section_path=part,table_index=list(root.iter(P+'tbl')).index(t),heights={i:v for i,v in enumerate(heights)})]);require(result.ok,'public row heights failed');after=result.data;checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='row-heights-',dir=output.parent) as folder:
  p=Path(folder)/'candidate.hwpx';p.write_bytes(after);require(validate_editor_open_safety(p).ok,'candidate open safety failed');require(sha(source)==req['source_sha256'],'source changed')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.explicit-row-heights-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',published=not dry_run,source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),checks=checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true');v=p.parse_args();print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
