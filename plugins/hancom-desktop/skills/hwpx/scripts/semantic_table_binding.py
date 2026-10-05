"""Read-only exact table/header and row-key binding. Does not infer intent."""
from pathlib import Path
import hashlib
import safe_mixed_table_structure as ed
from safe_rich_table import cell_model
from safe_body_structure import package,P

def cell_text(c):
 return '\n'.join(''.join(r['text'] for r in p['runs'])for p in cell_model(c))

def header_cells(t):
 rows=t.findall(P+'tr')
 if not rows:return []
 cs=rows[0].findall(P+'tc')
 if any(c.find(P+'cellSpan') is None or c.find(P+'cellSpan').get('rowSpan')!='1' or c.find(P+'cellSpan').get('colSpan')!='1' for c in cs):return []
 cs=sorted(cs,key=lambda c:int(c.find(P+'cellAddr').get('colAddr')))
 return [cell_text(c)for c in cs]

def bind(source,headers,key=None,source_sha256=None):
 source=Path(source);data=source.read_bytes();sha=hashlib.sha256(data).hexdigest()
 if source_sha256 is not None and sha!=source_sha256:raise ValueError('stale source SHA256')
 if not isinstance(headers,list)or not headers or any(not isinstance(x,str)or not x for x in headers)or len(set(headers))!=len(headers):raise ValueError('unique exact nonempty header signature required')
 if key is not None and (not isinstance(key,dict)or not key or any(k not in headers or not isinstance(v,str)or not v for k,v in key.items())):raise ValueError('complete nonempty values under existing header names required')
 _,roots,_=package(data);matches=[];ordinal=0
 for root in roots.values():
  for table in root.iter(P+'tbl'):
   ordinal+=1
   if header_cells(table)==headers:matches.append((ordinal,table))
 if len(matches)!=1:raise ValueError('exact header signature is absent or ambiguous: '+str(len(matches)))
 ordinal,table=matches[0];rows,grid=ed.grid(table);v=ed.inspect(source,ordinal);v['headers']=headers;v['rowKey']=key
 if key is None:return v
 hits=[]
 for y,row in enumerate(rows[1:],1):
  cells=row.findall(P+'tc')
  if all(cell_text(grid[y,headers.index(k)])==value for k,value in key.items()):
   if any(c.find(P+'cellSpan').get('rowSpan')!='1' or c.find(P+'cellSpan').get('colSpan')!='1'for c in cells):raise ValueError('semantic mutation target must be a simple complete row')
   models=[ed.plain(c)for c in cells];hits.append(dict(row=y+1,models=models,values=[cell_text(c)for c in cells]))
 if len(hits)!=1:raise ValueError('exact complete-cell row key is absent or ambiguous: '+str(len(hits)))
 return dict(**v,**hits[0])

def row_request(source,binding,operation,parameters,reason):
 fresh=bind(source,binding['headers'],binding['rowKey'],binding['sourceSha256'])
 for k in ['table','tableId','tableSha256','row']:
  if fresh[k]!=binding[k]:raise ValueError('stale table/row binding')
 if operation not in ['delete_row','clone_after']or not isinstance(parameters,dict)or 'row'in parameters:raise ValueError('explicit supported parameters without manual row override required')
 return dict(schema=ed.SCHEMA,sourceSha256=fresh['sourceSha256'],table=fresh['table'],tableId=fresh['tableId'],tableSha256=fresh['tableSha256'],operation=operation,parameters=dict(row=fresh['row'],**parameters),editableReason=reason)
