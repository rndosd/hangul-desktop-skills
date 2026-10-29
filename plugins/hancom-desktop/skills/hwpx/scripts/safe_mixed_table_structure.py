"""Target-aware mixed-table operations; no global merged-table guard relaxation."""
from pathlib import Path
import copy,hashlib,os
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_editor_open_safety, editor_open_safety_scope
from hwpx.tools.toc_author import ensure_paragraph_anchor_id
from namespace_literal_guard import preserve_namespace_literals
import safe_body_structure as body
from safe_cell_layout import locate
from safe_rich_table import cell_model
from safe_native_story_text import shape,fingerprint
P=body.P;need=body.require;SCHEMA='hwpx.mixed-table-structure.v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def grid(t):
 rows=t.findall(P+'tr');cols=int(t.get('colCnt'));need(2<=len(rows)<=100 and len(rows)==int(t.get('rowCnt')) and 1<=cols<=20,'bounded mixed grid required');need(t.get('lock')==t.get('noAdjust')==t.find(P+'sz').get('protect')=='0','unprotected adjustable table only');g={}
 for y,row in enumerate(rows):
  for c in row.findall(P+'tc'):
   a=c.find(P+'cellAddr');s=c.find(P+'cellSpan');size=c.find(P+'cellSz');need(a is not None and s is not None and size is not None,'cell geometry required');x=int(a.get('colAddr'));cy=int(a.get('rowAddr'));w=int(s.get('colSpan'));h=int(s.get('rowSpan'));need(cy==y and w>0 and h>0 and x+w<=cols and y+h<=len(rows) and int(size.get('width'))>0 and int(size.get('height'))>0,'invalid geometry')
   for gy in range(y,y+h):
    for gx in range(x,x+w):need((gy,gx)not in g,'overlapping mixed grid');g[gy,gx]=c
 need(len(g)==len(rows)*cols,'hole in mixed grid');return rows,g
def plain(c):
 need(c.get('protect')=='0' and c.get('header')!='1','data cells only');sub=c.find(P+'subList');ps=sub.findall(P+'p');need(len(sub)==len(ps) and 1<=len(ps)<=5,'plain1..5paragraphs required')
 for p in ps:
  need(all(p.get(k,'0')=='0' for k in ['pageBreak','columnBreak','merged']) and all(n.tag in [P+'run',P+'linesegarray'] for n in p),'plain paragraph only');rs=p.findall(P+'run');need(1<=len(rs)<=20,'bounded runs required')
  for run in rs:need(set(run.attrib)=={'charPrIDRef'} and (len(run)==0 or len(run)==1 and run[0].tag==P+'t' and all(n.tag==P+'fwSpace' and not n.attrib and not len(n) and not n.text and not n.tail for n in run[0])),'plain styled run with literal fullwidth spaces only')
 return cell_model(c)
def nocache(n):
 for p in n.iter(P+'p'):
  for a in list(p.findall(P+'linesegarray')):p.remove(a)
def comparable(c):
 c=copy.deepcopy(c);nocache(c);c.find(P+'cellAddr').attrib.pop('rowAddr');
 for p in c.iter(P+'p'):p.attrib.pop('id')
 return shape(c)
def inspect(source,ordinal):
 return inspect_data(Path(source).read_bytes(),ordinal)

def inspect_data(data,ordinal):
 _,part,root,t=locate(data,ordinal);rows,g=grid(t)
 return dict(sourceSha256=hashlib.sha256(data).hexdigest(),table=ordinal,tableId=t.get('id'),tableSha256=fingerprint(t),part=part,rows=len(rows),columns=int(t.get('colCnt')),owners=[dict(row=int(c.find(P+'cellAddr').get('rowAddr'))+1,column=int(c.find(P+'cellAddr').get('colAddr'))+1,span=dict(c.find(P+'cellSpan').attrib),text=''.join(n.text or '' for n in c.iter(P+'t'))) for row in rows for c in row.findall(P+'tc')])
def checked(data,q):
 need(isinstance(q,dict) and set(q)=={'schema','sourceSha256','table','tableId','tableSha256','operation','parameters','editableReason'} and q['schema']==SCHEMA and hashlib.sha256(data).hexdigest()==q['sourceSha256'],'invalid/stale request');need(type(q['table'])is int and q['table']>0 and isinstance(q['editableReason'],str) and len(q['editableReason'])>=8,'explicit binding/reason required');_,part,root,t=locate(data,q['table']);need(t.get('id')==q['tableId'] and fingerprint(t)==q['tableSha256'],'stale table binding');rows,g=grid(t);p=q['parameters'];op=q['operation']
 if op in ['clone_after','delete_row']:
  need(isinstance(p,dict) and set(p)==({'row','cells','heightHwpunit'} if op=='clone_after' else {'row'}),'exact row keys required');y=p['row'];need(type(y)is int and 2<=y<=len(rows),'data row required');y-=1
  cells=rows[y].findall(P+'tc');need(all(g[y,x] in cells and int(g[y,x].find(P+'cellSpan').get('rowSpan'))==1 for x in range(int(t.get('colCnt')))),'row intersects vertical merge');need(op!='clone_after' or len(rows)<100,'row limit');need(op!='delete_row' or len(rows)>=3,'retain data row');[plain(c) for c in cells]
  if op=='clone_after':
   need(type(p['heightHwpunit'])is int and 1000<=p['heightHwpunit']<=12000,'bounded explicit new row height');need(isinstance(p['cells'],list) and len(p['cells'])==len(cells),'complete owner cell map')
   for c,vals in zip(cells,p['cells']):validate_values(c,vals)
 elif op in ['merge_duplicate_vertical','merge_preserve_horizontal','unmerge_vertical']:
  need(isinstance(p,dict) and set(p)==({'range','newCellTexts'} if op=='unmerge_vertical' else {'range'}),'exact merge keys required');v=p['range'];need(isinstance(v,list) and len(v)==4 and all(type(x)is int for x in v),'integer range');y,x,yy,xx=[n-1 for n in v];need(1<=y<=yy<len(rows) and 0<=x<=xx<int(t.get('colCnt')),'data range required');selected={id(g[a,z]):g[a,z] for a in range(y,yy+1) for z in range(x,xx+1)};cells=list(selected.values())
  for c in cells:
   a=c.find(P+'cellAddr');s=c.find(P+'cellSpan');cy=int(a.get('rowAddr'));cx=int(a.get('colAddr'));need(y<=cy and x<=cx and cy+int(s.get('rowSpan'))<=yy+1 and cx+int(s.get('colSpan'))<=xx+1,'merge crosses selected boundary');plain(c)
  if op=='merge_duplicate_vertical':need(yy==y+1 and x==xx and len(cells)==2 and all(c.find(P+'cellSpan').get('colSpan')==c.find(P+'cellSpan').get('rowSpan')=='1' for c in cells) and comparable(cells[0])==comparable(cells[1]),'exact duplicate2vertical cells only')
  elif op=='merge_preserve_horizontal':need(y==yy and xx==x+1 and len(cells)==2 and all(c.find(P+'cellSpan').get('colSpan')==c.find(P+'cellSpan').get('rowSpan')=='1' for c in cells),'two simple horizontal cells only')
  else:
   need(yy==y+1 and x==xx and len(cells)==1 and cells[0].find(P+'cellSpan').get('rowSpan')=='2' and cells[0].find(P+'cellSpan').get('colSpan')=='1' and int(cells[0].find(P+'cellSz').get('height'))%2==0,'exact two equal-sized vertical split only');validate_values(cells[0],p['newCellTexts'])
 else:raise ValueError('unsupported mixed-table operation')
 return part,t
def validate_values(c,vals):
 model=plain(c);need(isinstance(vals,list) and len(vals)==len(model),'paragraph map mismatch')
 for p,values,rawp in zip(model,vals,c.findall('./'+P+'subList/'+P+'p')):
  need(isinstance(values,list) and len(values)==len(p['runs']) and all(isinstance(v,str) and not any(ch in v for ch in '\r\n\t') and len(v)<=500 for v in values),'complete bounded run map required')
  for run,value in zip(rawp.findall(P+'run'),values):need(len(run)==1 or value=='','childless run cannot acquire text')
def expected(before,q):
 part,t=checked(before,q);members,roots,defs=body.package(before);root=copy.deepcopy(roots[part]);matches=[z for z in root.iter(P+'tbl') if z.get('id')==q['tableId'] and fingerprint(z)==q['tableSha256']];need(len(matches)==1,'independent exact table required');t=matches[0];rows,g=grid(t);p=q['parameters'];op=q['operation'];fresh=[]
 if op in ['clone_after','delete_row']:
  y=p['row']-1
  if op=='clone_after':
   new=copy.deepcopy(rows[y]);nocache(new)
   for c,vals in zip(new.findall(P+'tc'),p['cells']):
    c.find(P+'cellSz').set('height',str(p['heightHwpunit']))
    for para,values in zip(c.findall('./'+P+'subList/'+P+'p'),vals):
     fresh.append(para)
     for run,value in zip(para.findall(P+'run'),values):
      if len(run):run[0].text=value or None
   rows.insert(y+1,new);delta=p['heightHwpunit']
  else:delta=-max(int(c.find(P+'cellSz').get('height')) for c in rows[y].findall(P+'tc'));rows.pop(y)
  for row in list(t.findall(P+'tr')):t.remove(row)
  for i,row in enumerate(rows):
   for c in row.findall(P+'tc'):c.find(P+'cellAddr').set('rowAddr',str(i))
   t.append(row)
  t.set('rowCnt',str(len(rows)));size=t.find(P+'sz');size.set('height',str(int(size.get('height'))+delta))
 else:
  y,x,yy,xx=[n-1 for n in p['range']];a=g[y,x];b=g[yy,xx]
  if op.startswith('merge_'):
   if op=='merge_preserve_horizontal':
    for para in b.findall('./'+P+'subList/'+P+'p'):a.find(P+'subList').append(copy.deepcopy(para))
   a.find(P+'cellSpan').set('rowSpan',str(yy-y+1));a.find(P+'cellSpan').set('colSpan',str(xx-x+1));a.find(P+'cellSz').set('width',str(int(a.find(P+'cellSz').get('width'))+(int(b.find(P+'cellSz').get('width')) if x!=xx else 0)));a.find(P+'cellSz').set('height',str(int(a.find(P+'cellSz').get('height'))+(int(b.find(P+'cellSz').get('height')) if y!=yy else 0)));rows[yy].remove(b);nocache(a)
  else:
   a.find(P+'cellSpan').set('rowSpan','1');a.find(P+'cellSz').set('height',str(int(a.find(P+'cellSz').get('height'))//2));new=copy.deepcopy(a);new.find(P+'cellAddr').set('rowAddr',str(yy));nocache(new)
   for para,values in zip(new.findall('./'+P+'subList/'+P+'p'),p['newCellTexts']):
    fresh.append(para)
    for run,value in zip(para.findall(P+'run'),values):
     if len(run):run[0].text=value or None
   siblings=rows[yy].findall(P+'tc');index=next((i for i,c in enumerate(siblings) if int(c.find(P+'cellAddr').get('colAddr'))>x),len(siblings));rows[yy].insert(index,new)
 grid(t);return members,roots,part,root,fresh
def verify(before,after,q):
 return verify_expected(*expected(before,q),after)

def verify_expected(bm,br,part,want,fresh,after):
 am,ar,ad=body.package(after);need(list(bm)==list(am) and list(br)==list(ar),'package inventory/spine changed');originalids={p.get('id') for root in br.values() for p in root.iter(P+'p')};newids=[]
 def bind(a,b):
  need(a.tag==b.tag and len(a)==len(b),'expected structure mismatch')
  if any(a is p for p in fresh):need(b.get('id')not in originalids and b.get('id')not in newids,'new paragraph ID collision');newids.append(b.get('id'));a.set('id',b.get('id'))
  for x,y in zip(a,b):bind(x,y)
 bind(want,ar[part]);need(shape(want)==shape(ar[part]),'requested rows/cells/content/styles/sizes or other section changed')
 for name in br:
  if name!=part:need(shape(br[name])==shape(ar[name]),'non-target section changed')
 for name in bm:
  if name not in br:need(bm[name]==am[name],'header/assets/non-target package changed:'+name)
 return dict(status='PASS_MIXED_TABLE_PRESERVATION',entireNonTargetPackageExact=True,originalCellsTextRunsSpansSizesBordersExact=True,requestedGridExact=True,newParagraphIdsFresh=len(newids),onlySelectedRowAddressesAndExplicitLocalGeometryChanged=True)
def api_table(doc,q):
 matches=[t for t in doc.tables.all if t.element.get('id')==q['tableId'] and fingerprint(t.element)==q['tableSha256']];need(len(matches)==1,'public table identity required');return matches[0]

@preserve_namespace_literals
@editor_open_safety_scope()
def apply_sequence(source,output,headers,operations,reason,dry_run=False):
    need(version('python-hwpx')=='6.3.0','qualified core6.3.0 required')
    from lxml import etree as E
    from hwpx.patch import _patch_zip_entries, _rewrite_zip_entries
    import semantic_table_binding as binding
    source=Path(source).resolve(strict=True)
    output=Path(output).absolute()
    need(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and not output.is_symlink() and source!=output.resolve(),'new output required')
    need(isinstance(operations,list) and 1<=len(operations)<=20,'bounded operation list required')
    data=source.read_bytes()
    original_sha=hashlib.sha256(data).hexdigest()
    need(validate_editor_open_safety(data).ok,'source safety failed')
    bm,br,_=body.package(data)
    original_ids={p.get('id') for root in br.values() for p in root.iter(P+'p')}
    used_ids=set(original_ids)
    next_id=max((int(v) for v in used_ids if v is not None and v.isdecimal()),default=0)+1
    virtual=data
    calls=[]
    stages=[]
    for op in operations:
        need(isinstance(op,dict) and op.get('op') in ('delete','insert_after'),'delete/insert_after only')
        insert=op['op']=='insert_after'
        required={'op','key','cells','heightHwpunit'} if insert else {'op','key'}
        need(set(op)==required,'exact operation keys required')
        target=binding.bind_data(virtual,headers,op['key'])
        parameters={'row':target['row']}
        if insert:
            values=op['cells']
            need(isinstance(values,list) and len(values)==len(headers) and all(isinstance(v,str) for v in values),'complete cell values required')
            need(all(len(model)==1 and len(model[0]['runs'])==1 for model in target['models']),'simple insertion requires one paragraph/run in every source cell')
            parameters.update(cells=[[[v]] for v in values],heightHwpunit=op['heightHwpunit'])
        q=dict(schema=SCHEMA,sourceSha256=target['sourceSha256'],table=target['table'],tableId=target['tableId'],
               tableSha256=target['tableSha256'],operation='clone_after' if insert else 'delete_row',parameters=parameters,editableReason=reason)
        _,_,part,want,fresh=expected(virtual,q)
        _,_,root,raw=locate(virtual,target['table'])
        table_index=next(i for i,t in enumerate(root.iter(P+'tbl')) if t is raw)
        call=dict(op='insert_row_by_clone' if insert else 'delete_row',section_path=part,table_index=table_index)
        call.update(dict(ref_row=target['row']-1,count=1) if insert else dict(row=target['row']-1))
        calls.append(call)
        for paragraph in fresh:
            while str(next_id) in used_ids:next_id+=1
            paragraph.set('id',str(next_id))
            used_ids.add(str(next_id));next_id+=1
        payload=E.tostring(want,encoding='utf-8',xml_declaration=True,standalone=True)
        try:virtual=_patch_zip_entries(virtual,{part:payload})
        except ValueError:virtual=_rewrite_zip_entries(virtual,{part:payload})
        stages.append(dict(operation=op,binding=q,checks={'status':'CHECKED_OPERATION_PLAN'}))
    final_tables=[t for t in want.iter(P+'tbl') if t.get('id')==q['tableId']]
    need(len(final_tables)==1,'unique final table required')
    wanted_table=final_tables[0]
    fresh=[p for p in want.iter(P+'p') if p.get('id') not in original_ids]
    result=apply_table_ops(data,calls)
    need(result.ok,'public row patch failed:'+str(result.to_dict()))
    with body.workspace_candidate(output.parent) as candidate:
        candidate=Path(candidate)
        with HwpxDocument.open(result.data) as document:
            matches=[t for t in document.tables.all if t.element.get('id')==q['tableId']]
            need(len(matches)==1,'unique public table identity required')
            table=matches[0]
            for y,row in enumerate(wanted_table.findall(P+'tr')):
                if not any(p.get('id') not in original_ids for p in row.iter(P+'p')):continue
                for raw_cell in row.findall(P+'tc'):
                    x=int(raw_cell.find(P+'cellAddr').get('colAddr'))
                    cell=table.cell(y,x)
                    cell.set_size(cell.width,int(raw_cell.find(P+'cellSz').get('height')))
                    for paragraph,raw_paragraph in zip(cell.paragraphs,raw_cell.findall('./'+P+'subList/'+P+'p')):
                        for run,raw_run in zip(paragraph.runs,raw_paragraph.findall(P+'run')):
                            text=raw_run.find(P+'t')
                            value=text.text or '' if text is not None else ''
                            if run.text!=value:run.text=value
                        nocache(paragraph.element)
            table.element.find(P+'sz').set('height',wanted_table.find(P+'sz').get('height'))
            table.mark_dirty()
            document.save_to_path(candidate)
        after=candidate.read_bytes()
        checks=verify_expected(bm,br,part,want,fresh,after)
        need(validate_editor_open_safety(after).ok,'output safety failed')
        need(sha(source)==original_sha,'source changed')
        if not dry_run:os.link(candidate,output)
    return dict(status='PASS_STRUCTURE',dryRun=dry_run,documentPublished=not dry_run,sourceSha256=original_sha,
                outputSha256=hashlib.sha256(after).hexdigest(),stages=stages,checks=checks,
                execution={'rowPatchCalls':1,'documentSaveCalls':1,'operations':len(operations)},native='NOT_CHECKED')

@preserve_namespace_literals
def apply(source,output,q,dry_run=False):
 source=Path(source).resolve(strict=True);output=Path(output).absolute();need(version('python-hwpx')=='6.3.0','qualified core6.3.0 required');need(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and not output.is_symlink() and source!=output.resolve(),'new output required');data=source.read_bytes();part,raw=checked(data,q);p=q['parameters'];op=q['operation'];need(validate_editor_open_safety(source).ok,'source safety failed')
 with body.workspace_candidate(output.parent) as candidate:
  candidate=Path(candidate)
  if op in ['clone_after','delete_row']:
   _,_,root,_=locate(data,q['table']);call=dict(op='insert_row_by_clone' if op=='clone_after' else 'delete_row',section_path=part,table_index=list(root.iter(P+'tbl')).index(raw) if raw in list(root.iter(P+'tbl')) else next(i for i,n in enumerate(root.iter(P+'tbl')) if n.get('id')==q['tableId']))
   call.update(dict(ref_row=p['row']-1,count=1) if op=='clone_after' else dict(row=p['row']-1));result=apply_table_ops(data,[call]);need(result.ok,'public row patch failed:'+str(result.to_dict()));candidate.write_bytes(result.data)
   with HwpxDocument.open(candidate) as doc:
    table=next(t for t in doc.tables.all if t.element.get('id')==q['tableId']);delta=0
    if op=='clone_after':
     new=table.element.findall(P+'tr')[p['row']]
     for c,values in zip(new.findall(P+'tc'),p['cells']):
      x=int(c.find(P+'cellAddr').get('colAddr'));cell=table.cell(p['row'],x);cell.set_size(cell.width,p['heightHwpunit'])
      for para,vals in zip(cell.paragraphs,values):
       for run,value in zip(para.runs,vals):
        if run.text!=value:run.text=value
       nocache(para.element)
     delta=p['heightHwpunit']
    else:delta=-max(int(c.find(P+'cellSz').get('height')) for c in raw.findall(P+'tr')[p['row']-1].findall(P+'tc'))
    table.element.find(P+'sz').set('height',str(int(raw.find(P+'sz').get('height'))+delta));table.mark_dirty();doc.save_to_path(candidate)
  else:
   with HwpxDocument.open(source) as doc:
    table=api_table(doc,q);y,x,yy,xx=[n-1 for n in p['range']]
    if op.startswith('merge_'):
     right=table.cell(yy,xx);plain(right.element);paragraphs=[p.element for p in right.paragraphs];left=table.merge_cells(y,x,yy,xx)
     if op=='merge_preserve_horizontal':
      for para in paragraphs:left.element.find(P+'subList').append(para)
     nocache(left.element)
    else:
     old=copy.deepcopy(table.cell(y,x).element);model=plain(old);table.split_merged_cell(y,x);cell=table.cell(yy,x);cell.element.find(P+'subList').attrib.clear();cell.element.find(P+'subList').attrib.update(old.find(P+'subList').attrib)
     for i,(m,values) in enumerate(zip(model,p['newCellTexts'])):
      para=cell.paragraphs[0] if i==0 else cell.add_paragraph();newid=para.element.get('id');para.element.attrib.clear();para.element.attrib.update({k:v for k,v in m['attrs'].items() if k!='id'});para.element.set('id',newid);ensure_paragraph_anchor_id(doc,para)
      para.para_pr_id_ref=m['attrs']['paraPrIDRef'];para.style_id_ref=m['attrs']['styleIDRef'];run=para.runs[0];run.char_pr_id_ref=m['runs'][0]['attrs']['charPrIDRef'];run.text=values[0]
      for rm,value in zip(m['runs'][1:],values[1:]):para.add_run(value,char_pr_id_ref=rm['attrs']['charPrIDRef'])
     nocache(cell.element)
    table.mark_dirty();doc.save_to_path(candidate)
  checks=verify(data,candidate.read_bytes(),q);need(validate_editor_open_safety(candidate).ok,'output safety failed');need(sha(source)==q['sourceSha256'],'source changed')
  if not dry_run:os.link(candidate,output)
 return dict(**checks,dryRun=dry_run,native='NOT_CHECKED')
