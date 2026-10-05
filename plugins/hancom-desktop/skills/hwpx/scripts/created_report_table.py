"""Explicit layout choices for a newly created EMPTY report table only.

Bounded public table-object adapter, no XML package fallback or implicit changes
to an existing filled/merged/user table. Call before filling or freezing source.
"""
def configure(table,*,multipage=False,repeat_header=False,page_break='TABLE',before_pt=6,after_pt=8):
 if type(multipage) is not bool or type(repeat_header) is not bool:raise ValueError('explicit boolean layout choices required')
 if repeat_header and not multipage:raise ValueError('repeat header requires multipage layout')
 if page_break not in ['TABLE','CELL']:raise ValueError('explicit TABLE/CELL page break required')
 if not all(type(v) in (int,float) and 0<=v<=36 for v in [before_pt,after_pt]):raise ValueError('bounded explicit spacing required')
 if not 2<=table.row_count<=100 or not 1<=table.column_count<=12:raise ValueError('bounded new rectangular table required')
 cells=[c for row in table.rows for c in row.cells]
 if len(cells)!=table.row_count*table.column_count or any(c.text or c.span!=(1,1) or len(c.paragraphs)!=1 for c in cells):raise ValueError('only newly created empty unmerged cells supported')
 for c in cells:
  runs=c.paragraphs[0].runs
  if len(runs)!=1 or any(n.tag.rsplit('}',1)[-1]!='t' or len(n) for n in runs[0].element):raise ValueError('empty plain new cells only')
 P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
 pos=table.element.find(P+'pos');margin=table.element.find(P+'outMargin')
 if pos is None or margin is None or pos.get('treatAsChar')!='1':raise ValueError('known freshly created SDK table required')
 if multipage:
  pos.set('treatAsChar','0');table.element.set('pageBreak',page_break)
  table.element.set('repeatHeader',str(int(repeat_header)))
  if repeat_header:
   for c in table.rows[0].cells:c.element.set('header','1')
 margin.set('top',str(round(before_pt*100)));margin.set('bottom',str(round(after_pt*100)));table.mark_dirty()
 return dict(multipage=multipage,repeatHeader=repeat_header,pageBreak=page_break,beforePt=before_pt,afterPt=after_pt,scope='Explicit new empty table layout before filling only')
