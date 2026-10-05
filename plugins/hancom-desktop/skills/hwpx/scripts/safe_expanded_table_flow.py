"""Explicit conversion of one expanded inline table; header-only merged holdout."""
from pathlib import Path
import copy,hashlib,os
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from namespace_literal_guard import preserve_namespace_literals
import safe_body_structure as body
import safe_rich_row_delete as rich
from safe_native_story_text import shape,fingerprint
P=body.P;H=body.H;need=body.require
SCHEMA='hwpx.expanded-table-flow.v1'
def binding(data,table,header_rows,caption=None):
 from safe_cell_layout import locate
 m,part,root,t=locate(data,table);pos=t.find(P+'pos');size=t.find(P+'sz');need(2<=int(t.get('rowCnt'))<=100 and 1<=int(t.get('colCnt'))<=20,'bounded table required');need(pos is not None and size is not None and t.get('lock')=='0' and size.get('protect')=='0','unprotected table required');host=t.getparent().getparent();need(host.tag==P+'p' and host.getparent() is root and len(list(host.iter(P+'tbl')))==1,'one direct body table required');need(pos.get('treatAsChar') in ['0','1'] and pos.get('flowWithText')=='1' and pos.get('allowOverlap')=='0' and t.get('textWrap')=='TOP_AND_BOTTOM','normal nonoverlapping flow required')
 need(isinstance(header_rows,list) and all(type(x)is int for x in header_rows) and header_rows==list(range(1,len(header_rows)+1)) and 1<=len(header_rows)<=3,'explicit contiguous1..3header rows required');rows=t.findall(P+'tr');need(len(rows)==int(t.get('rowCnt')),'row count mismatch');grid={};headers=[]
 for y,row in enumerate(rows):
  for c in row.findall(P+'tc'):
   a=c.find(P+'cellAddr');s=c.find(P+'cellSpan');need(a is not None and s is not None,'cell grid required');x=int(a.get('colAddr'));cy=int(a.get('rowAddr'));w=int(s.get('colSpan'));v=int(s.get('rowSpan'));need(cy==y and w>0 and v>0 and x+w<=int(t.get('colCnt')) and y+v<=len(rows),'invalid cell span')
   for gy in range(y,y+v):
    for gx in range(x,x+w):need((gy,gx)not in grid,'overlapping cells');grid[gy,gx]=True
   if y<len(header_rows):
    need(y+v<=len(header_rows) and c.get('protect')=='0','header/body crossing or protected header');headers.append(dict(row=y+1,column=x+1,sha256=fingerprint(c)))
   else:need(c.get('header')!='1','existing body title marker unsupported')
 need(len(grid)==len(rows)*int(t.get('colCnt')),'incomplete grid');cap=None
 if caption is not None:
  p=host.getprevious();defs=body.package(data)[2];need(isinstance(caption,str) and caption and p is not None and body.eligible(p,defs,rich=True) and body.text(p)==caption,'exact adjacent plain caption required');cap=dict(index=list(root).index(p),sha256=fingerprint(p),paraPrIDRef=p.get('paraPrIDRef'),text=caption)
 return dict(part=part,table=table,id=t.get('id'),tableSha256=fingerprint(t),hostIndex=list(root).index(host),headerRows=header_rows,headerCells=headers,caption=cap,inline=pos.get('treatAsChar'),noAdjust=t.get('noAdjust'),pageBreak=t.get('pageBreak'))
def checked(data,q):
 need(set(q)=={'schema','sourceSha256','binding','convertInline','pageBreak','outsideSpacingHwpunit','editableReason'} and q['schema']==SCHEMA and q['sourceSha256']==hashlib.sha256(data).hexdigest(),'invalid/stale flow request');b=q['binding'];need(b==binding(data,b['table'],b['headerRows'],b['caption']['text'] if b['caption'] else None),'stale table/caption binding');need(type(q['convertInline'])is bool and isinstance(q['editableReason'],str) and len(q['editableReason'])>=8,'explicit conversion decision/reason required');spacing=q['outsideSpacingHwpunit'];need(isinstance(spacing,dict) and set(spacing)<= {'top','bottom'} and all(type(v)is int and 200<=v<=1800 for v in spacing.values()),'bounded2..18pt spacing only')
 from safe_cell_layout import locate
 _,_,_,t=locate(data,b['table']);pos=t.find(P+'pos')
 if q['convertInline']:
  need(b['inline']=='1' and b['noAdjust']=='0' and b['headerRows']==[1] and b['caption'] is not None and q['pageBreak']=='TABLE','explicit plain inline conversion requires caption/row splitting');need(pos.get('vertRelTo')=='PARA' and pos.get('horzRelTo')=='COLUMN' and pos.get('vertOffset')==pos.get('horzOffset')=='0','qualified zero-offset inline anchor required');rich.check_table(t)
 else:need(b['inline']=='0' and q['pageBreak'] is None and not spacing and b['caption'] is None,'floating merged route is header markers only; fixed sizes never changed')
 return b,t
def verify(before,after,q):
 b,t=checked(before,q);bm,br,bd=body.package(before);am,ar,ad=body.package(after);need(list(bm)==list(am) and list(br)==list(ar),'package/spine changed');want=copy.deepcopy(br);matches=[i for i,n in enumerate(br[b['part']].iter(P+'tbl')) if n.get('id')==b['id'] and fingerprint(n)==b['tableSha256']];need(len(matches)==1,'independent exact source table binding required');et=list(want[b['part']].iter(P+'tbl'))[matches[0]]
 et.set('repeatHeader','1')
 for row in et.findall(P+'tr')[:len(b['headerRows'])]:
  for c in row.findall(P+'tc'):c.set('header','1')
 if q['convertInline']:
  et.set('pageBreak','TABLE');et.find(P+'pos').set('treatAsChar','0');et.find(P+'pos').set('holdAnchorAndSO','1')
  for k,v in q['outsideSpacingHwpunit'].items():et.find(P+'outMargin').set(k,str(v))
  cap=want[b['part']][b['caption']['index']];ac=ar[b['part']][b['caption']['index']];pid=ac.get('paraPrIDRef');need(pid in ad,'caption style missing');style=copy.deepcopy(bd[b['caption']['paraPrIDRef']]);style.set('id',pid);style.find(H+'breakSetting').set('keepWithNext','1');need(shape(style)==shape(ad[pid]),'caption style changed beyond keepWithNext');cap.set('paraPrIDRef',pid)
  for cache in cap.findall(P+'linesegarray'):cap.remove(cache)
  need(all(k in ad and shape(n)==shape(ad[k]) for k,n in bd.items()),'old shared definition changed');added=set(ad)-set(bd);need(added<={pid},'unrelated definition added');hb=body.parse(bm['Contents/header.xml']);ha=body.parse(am['Contents/header.xml']);ap=ha.find('.//'+H+'paraProperties');bp=hb.find('.//'+H+'paraProperties');need(int(ap.get('itemCnt'))==len(ad),'definition count mismatch')
  for n in list(ap):
   if n.get('id') in added:ap.remove(n)
  ap.set('itemCnt',bp.get('itemCnt'));need(shape(hb)==shape(ha),'non-target header changed')
 else:need(bm['Contents/header.xml']==am['Contents/header.xml'],'header definitions changed on title-cell-only route')
 for name,n in want.items():need(shape(n)==shape(ar[name]),'non-target section/text/cells/geometry changed')
 for name in bm:
  if name not in br and name!='Contents/header.xml':need(bm[name]==am[name],'non-target payload changed:'+name)
 return dict(status='PASS_EXPANDED_FLOW_PRESERVATION',allCellTextRunsSpansSizesBordersAndOldDefinitionsExact=True,onlyExplicitAnchorSplitHeaderGapAndCaptionKeepChanged=True,fixedMergedTableDimensionsNotChanged=True)
@preserve_namespace_literals
def apply(source,output,q,dry_run=False):
 source=Path(source).resolve(strict=True);output=Path(output).absolute();need(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and not output.is_symlink() and output.resolve()!=source,'new output required');data=source.read_bytes();b,t=checked(data,q);need(validate_editor_open_safety(source).ok,'source safety failed')
 with body.workspace_candidate(output.parent) as candidate:
  out=Path(candidate)
  with HwpxDocument.open(source) as doc:
   matches=[x for s in doc.sections for p in s.paragraphs for x in p.tables if s.part_name==b['part'] and fingerprint(x.element)==b['tableSha256']];need(len(matches)==1,'public table binding required');table=matches[0];table.element.set('repeatHeader','1')
   for row in table.element.findall(P+'tr')[:len(b['headerRows'])]:
    for c in row.findall(P+'tc'):c.set('header','1')
   if q['convertInline']:
    table.element.set('pageBreak','TABLE');table.element.find(P+'pos').set('treatAsChar','0');table.element.find(P+'pos').set('holdAnchorAndSO','1')
    for k,v in q['outsideSpacingHwpunit'].items():table.element.find(P+'outMargin').set(k,str(v))
    p=table.paragraph.section.paragraphs[b['caption']['index']];need(fingerprint(p.element)==b['caption']['sha256'],'public caption binding mismatch');p.para_pr_id_ref=doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref,break_setting={'keep_with_next':True})
    for cache in p.element.findall(P+'linesegarray'):p.element.remove(cache)
    p.section.mark_dirty()
   table.mark_dirty();doc.save_to_path(out)
  result=verify(data,out.read_bytes(),q);need(validate_editor_open_safety(out).ok,'output safety failed');need(body.sha(source)==q['sourceSha256'],'source changed')
  if not dry_run:os.link(out,output)
 return dict(**result,dryRun=dry_run,native='NOT_CHECKED')
