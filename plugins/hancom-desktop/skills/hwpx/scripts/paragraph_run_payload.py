"""Map one intended payload to an explicit existing styled run span.
Pure planning only: no file edit, COM or automatic duplicate removal.
The caller chooses semantic style boundaries; XML/control guards belong to
its qualified editor. Coordinates are one-based and contiguous.
"""
from safe_edit import single_line

def integer(v):return isinstance(v,int) and not isinstance(v,bool)

def bounds(original,span,text):
 if not isinstance(original,list) or not 1<=len(original)<=20:raise ValueError('1..20 plain run strings required')
 for x in original:single_line(x)
 if not isinstance(span,list) or len(span)!=2 or not all(integer(x) for x in span):raise ValueError('two integer span coordinates required')
 lo,hi=span
 if not 1<=lo<=hi<=len(original):raise ValueError('span out of bounds')
 single_line(text)
 if len(text)>10000:raise ValueError('payload too long')
 return lo-1,hi

def verify(original,span,text,result):
 lo,hi=bounds(original,span,text)
 if not isinstance(result,list) or len(result)!=len(original):raise ValueError('run shape changed')
 for x in result:single_line(x)
 if result[:lo]!=original[:lo] or result[hi:]!=original[hi:]:raise ValueError('unselected run changed')
 if ''.join(result[lo:hi])!=text:raise ValueError('selected span does not equal intended payload')
 if any(old and not new for old,new in zip(original[lo:hi],result[lo:hi])):raise ValueError('nonempty styled run would be erased; choose style policy first')
 return True

def plan(original,span,text,segments=None):
 lo,hi=bounds(original,span,text);old=original[lo:hi]
 if segments is None:
  if len(old)>1:raise ValueError('multi-run payload requires explicit semantic style segments')
  segments=[text]
 if not isinstance(segments,list) or len(segments)!=len(old):raise ValueError('one segment per selected run required')
 result=list(original);result[lo:hi]=segments
 verify(original,span,text,result)
 return result

def map_cell(model,rules):
 if not isinstance(model,list) or not 1<=len(model)<=5:raise ValueError('1..5 paragraphs required')
 values=[[x['text'] for x in p['runs']]for p in model];taken=set()
 if not isinstance(rules,list) or not rules:raise ValueError('explicit payload rules required')
 for q in rules:
  if not isinstance(q,dict) or set(q)-{'paragraph','span','text','segments'}:raise ValueError('unknown paragraph rule')
  p=q.get('paragraph')
  if not integer(p) or not 1<=p<=len(values):raise ValueError('paragraph out of bounds')
  original=values[p-1];lo,hi=bounds(original,q.get('span'),q.get('text'))
  for k in range(lo,hi):
   if (p,k) in taken:raise ValueError('overlapping payload rules')
   taken.add((p,k))
  values[p-1]=plan(original,q['span'],q['text'],q.get('segments'))
 return values
