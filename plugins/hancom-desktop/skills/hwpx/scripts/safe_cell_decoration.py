"""Bounded existing-cell borders/diagonals/fill adapter, preserving original style definitions."""
from pathlib import Path
import argparse,copy,hashlib,json,math,os,re,tempfile
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,H,require,parts,xml,locate,sha
from safe_cell_spacing import shape,snapshot
C='{http://www.hancom.co.kr/hwpml/2011/core}'
SCHEMA='hwpx.safe-cell-decoration.v1'
SIDES={'left':'leftBorder','right':'rightBorder','top':'topBorder','bottom':'bottomBorder'}
WIDTHS={.1,.12,.15,.2,.25,.3,.4,.5}
TYPES={'NONE','SOLID','DOT','DASH'}

def header(m):
 r=xml(m['Contents/header.xml']);lists=r.findall('.//'+H+'borderFills');require(len(lists)==1,'one border fill collection required');b=lists[0];styles={}
 for n in b:
  require(n.tag==H+'borderFill' and n.get('id','').isdigit() and n.get('id') not in styles,'invalid style IDs');styles[n.get('id')]=n
 require(int(b.get('itemCnt','-1'))==len(styles),'border fill item count invalid');return r,b,styles

def safe_style(n):
 require(n.get('threeD','0')=='0' and n.get('shadow','0')=='0','3D/shadow border unsupported')
 for local in [*SIDES.values(),'slash','backSlash']:
  require(len(n.findall(H+local))==1,'missing/duplicate border element '+local)
 for local in ['slash','backSlash']:
  v=n.find(H+local);require(v.get('type') in {'NONE','CENTER'} and v.get('Crooked','0')=='0' and v.get('isCounter','0')=='0','complex diagonal unsupported')
 require(n.get('centerLine','NONE')=='NONE','center-line editing not supported')
 diag=n.findall(H+'diagonal');require(len(diag)<=1 and (diag or all(n.find(H+k).get('type')=='NONE' for k in ['slash','backSlash'])),'missing active diagonal style')

def color(value):require(isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value),'RGB #RRGGBB required');return value.upper()

def diagonal_line(base):
 found=base.find(H+'diagonal')
 return found if found is not None else base.makeelement(H+'diagonal',{'type':'SOLID','width':'0.12 mm','color':'#000000'})

def line_spec(item,base):
 require(isinstance(item,dict) and item and set(item)<={'type','width_mm','color'},'explicit line properties required');out=dict(base.attrib)
 if 'type' in item:require(item['type'] in TYPES,'unsupported line type');out['type']=item['type']
 if 'width_mm' in item:
  v=item['width_mm'];require(type(v) in [int,float] and math.isfinite(v) and v in WIDTHS,'unsupported standard line width');out['width']=f'{v:g} mm'
 if 'color' in item:out['color']=color(item['color'])
 require(out.get('type') in TYPES and 'width' in out and 'color' in out,'unsupported existing line');return out

def edge_units(a,c,side):
 y,x=a;span=c.find(P+'cellSpan');sy,sx=int(span.get('rowSpan')),int(span.get('colSpan'))
 if side in ['top','bottom']:return {('H',y+(sy if side=='bottom' else 0),col) for col in range(x,x+sx)}
 return {('V',x+(sx if side=='right' else 0),row) for row in range(y,y+sy)}

def plan(data,req):
 require(isinstance(req,dict) and set(req)=={'schema','source_sha256','table','edits'} and req['schema']==SCHEMA,'request schema invalid');require(hashlib.sha256(data).hexdigest()==req['source_sha256'],'stale source hash');m,part,section,t=locate(data,req['table']);cs,grid=shape(t);hr,collection,styles=header(m);items=req['edits'];require(isinstance(items,list) and 1<=len(items)<=50,'1..50 edits required');changes={};seen=set();unit_specs={}
 def original(a):
  require(a in cs,'exact merged anchor required');c=cs[a];require(c.get('protect','0')=='0','protected target');k=c.get('borderFillIDRef');require(k in styles,'missing border fill reference');safe_style(styles[k]);return styles[k]
 for item in items:
  require(isinstance(item,dict) and {'row','column'}<=set(item) and not(set(item)-{'row','column','borders','diagonal','fill_color'}),'cell edit keys invalid');require(type(item['row']) is int and type(item['column']) is int,'integer 1-based anchor required');a=item['row']-1,item['column']-1;require(a not in seen,'duplicate cell request');seen.add(a);base=original(a);spec=changes.setdefault(a,{});has=False
  if 'borders' in item:
   borders=item['borders'];require(isinstance(borders,dict) and borders and set(borders)<=set(SIDES),'explicit border sides required')
   for side,value in borders.items():
    target=line_spec(value,base.find(H+SIDES[side]));has=True
    for unit in edge_units(a,cs[a],side):require(unit not in unit_specs or unit_specs[unit]==target,'conflicting shared edge requests');unit_specs[unit]=target
  if 'diagonal' in item:
   v=item['diagonal'];require(isinstance(v,dict) and 'direction' in v and set(v)<={'direction','type','width_mm','color'},'diagonal request invalid');require(v['direction'] in ['NONE','NW_SE','NE_SW','CROSS'],'unknown diagonal direction');spec['diagonal']=dict(direction=v['direction'],line=line_spec({k:w for k,w in v.items() if k!='direction'} or {'type':'SOLID' if v['direction']!='NONE' else diagonal_line(base).get('type')},diagonal_line(base)));has=True
   require(spec['diagonal']['line']['type']!='NONE','use direction NONE to disable the diagonal, retain a visible line style')
  if 'fill_color' in item:
   fills=base.findall(C+'fillBrush');require(len(fills)<=1 and (not fills or len(fills[0])==1 and fills[0][0].tag==C+'winBrush'),'only plain color fill can be replaced');spec['fill_color']=None if item['fill_color'] is None else color(item['fill_color']);has=True
  require(has,'empty cell edit')
 # Mirror every requested shared physical edge to each touching cell. A merged
 # cell with a larger edge cannot be partially styled; require the complete edge.
 for a,c in cs.items():
  for side in SIDES:
   units=edge_units(a,c,side);hit=units&set(unit_specs)
   if not hit:continue
   require(hit==units,'partial merged neighbor edge; explicitly cover its entire edge');values=[unit_specs[u] for u in units];require(all(v==values[0] for v in values),'mixed styles on one merged-cell edge unsupported');original(a);changes.setdefault(a,{}).setdefault('borders',{})[side]=values[0]
 changes={a:v for a,v in changes.items() if v};require(len(changes)<=100,'too many explicit/mirrored cells');return m,part,section,t,cs,hr,collection,styles,changes

def decorate(base,spec):
 out=copy.deepcopy(base)
 for side,attrs in spec.get('borders',{}).items():n=out.find(H+SIDES[side]);n.attrib.clear();n.attrib.update(attrs)
 if 'diagonal' in spec:
  v=spec['diagonal'];direction=v['direction']
  for local,active in [('slash',direction in ['NE_SW','CROSS']),('backSlash',direction in ['NW_SE','CROSS'])]:out.find(H+local).set('type','CENTER' if active else 'NONE')
  line=out.find(H+'diagonal')
  if line is None:line=out.makeelement(H+'diagonal',{});out.insert(list(out).index(out.find(H+'bottomBorder'))+1,line)
  line.attrib.clear();line.attrib.update(v['line'])
 if 'fill_color' in spec:
  for n in list(out.findall(C+'fillBrush')):out.remove(n)
  if spec['fill_color'] is not None:
   brush=out.makeelement(C+'fillBrush',{});brush.append(out.makeelement(C+'winBrush',{'faceColor':spec['fill_color'],'hatchColor':'#000000','alpha':'0'}));out.append(brush)
 return out

def prepared(data,req):
 m,part,section,t,cs,hr,collection,styles,changes=plan(data,req);nextid=max(map(int,styles))+1;assign={};new=[]
 def complete_style(node):
  # Identity is the entire definition, including all four lines, diagonal
  # settings and fill. Never deduplicate on a fill color alone.
  copy_node=copy.deepcopy(node);copy_node.attrib.pop('id',None)
  return snapshot(copy_node)
 existing={complete_style(node):identity for identity,node in styles.items()}
 for a,spec in sorted(changes.items()):
  n=decorate(styles[cs[a].get('borderFillIDRef')],spec);key=complete_style(n)
  identity=existing.get(key)
  if identity is None:
   identity=str(nextid);nextid+=1;n.set('id',identity)
   new.append(n);collection.append(n);existing[key]=identity
  assign[a]=identity
 collection.set('itemCnt',str(len(styles)+len(new)));return m,part,section,t,cs,hr,new,assign,changes

def verify(before,after,req):
 bm,part,br,bt,bc,expected_header,new,assign,changes=prepared(before,req);am,ap,ar,at=locate(after,req['table']);ac,ag=shape(at);require(set(bm)==set(am) and part==ap,'package inventory changed');require(snapshot(expected_header)==snapshot(xml(am['Contents/header.xml'])),'old/new border style mismatch');expected=copy.deepcopy(br);et=list(expected.iter(P+'tbl'))[list(br.iter(P+'tbl')).index(bt)];ec,eg=shape(et)
 for a,k in assign.items():ec[a].set('borderFillIDRef',k)
 require(snapshot(expected)==snapshot(ar),'content/structure changed beyond cell style references')
 for k in bm:
  if k not in {part,'Contents/header.xml'}:require(bm[k]==am[k],'non-target payload changed: '+k)
 return dict(oldSharedDefinitionsUnchanged=True,requestedNewDefinitionsExact=True,cellTextRunsAndLineBreakTailsEqual=True,allNonTargetPackageContentEqual=True,cellGeometryAndParagraphStylesEqual=True,sharedEdgesMirrored=True)

def inspect_source(source,table):
 data=Path(source).read_bytes();m,part,section,t=locate(data,table);cs,g=shape(t);hr,b,styles=header(m)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,cells=[dict(row=a[0]+1,column=a[1]+1,border_fill_id=c.get('borderFillIDRef'),text=[''.join(n.itertext()) for n in c.iter(P+'t')],span=dict(c.find(P+'cellSpan').attrib),border_style=snapshot(styles[c.get('borderFillIDRef')])) for a,c in cs.items()])

def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0','unverified core version');require(source.suffix.lower()=='.hwpx' and output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new hwpx output required');before=source.read_bytes();m,part,section,t,cs,expected_header,new,assign,changes=prepared(before,req)
 with HwpxDocument.open(source) as doc:
  tables=[x for s in doc.sections for p in s.paragraphs for x in p.tables];found=[x for x in tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous public table binding');table=found[0];heads=[h for h in doc.oxml.headers if h.part_name=='Contents/header.xml'];require(len(heads)==1,'ambiguous public header binding');h=heads[0];collections=h.element.findall('.//'+H+'borderFills');require(len(collections)==1,'missing header collection');b=collections[0]
  # Dedicated, declared bounded style-clone adapter: preserve every existing
  # definition, append only expected clones, never use the fill-only dedupe API.
  for n in new:b.append(copy.deepcopy(n))
  b.set('itemCnt',str(len(b)));h.mark_dirty()
  for (y,x),k in assign.items():require(table.cell(y,x).address==(y,x),'covered cell binding');table.set_cell_border_fill(y,x,k)
  after=doc.to_bytes()
 checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='cell-decoration-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(after);require(validate_editor_open_safety(p).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.safe-cell-decoration-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),published=not dry_run,request=req,affectedCells=[dict(row=a[0]+1,column=a[1]+1,explicit=a in {(v['row']-1,v['column']-1) for v in req['edits']},changes=spec) for a,spec in sorted(changes.items())],checks=checks)

if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True);i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True);a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.cmd=='inspect':
  with open(v.output,'x',encoding='utf8') as f:json.dump(inspect_source(v.source,v.table),f,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
