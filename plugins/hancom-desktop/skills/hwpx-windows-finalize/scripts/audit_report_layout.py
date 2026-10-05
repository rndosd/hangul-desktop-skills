"""Source-declared heading/TOC/sparse-page checks; visual review stays separate."""
from pathlib import Path
import hashlib,re,json,argparse
import pymupdf as pdf
SCHEMA='hwpx.report-layout-subset.v1'
def norm(value):return re.sub(r'\s+','',value)
def lines(page):return [dict(text=''.join(s['text'] for s in ln['spans']),box=ln['bbox']) for b in page.get_text('dict')['blocks'] if b.get('type')==0 for ln in b['lines']]
def audit(path,q):
 if set(q)!={'schema','pdfSha256','expectedPhysicalPages','intentionalBlankPages','headingPairs','tocEntries','sparseRules'} or q['schema']!=SCHEMA:raise ValueError('exact layout expectation schema required')
 if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=q['pdfSha256']:raise ValueError('stale PDF hash')
 if type(q['expectedPhysicalPages'])is not int or q['expectedPhysicalPages']<1:raise ValueError('positive physical page count required')
 if not all(isinstance(q[k],list) and len(q[k])<=40 for k in ['intentionalBlankPages','headingPairs','tocEntries','sparseRules']):raise ValueError('bounded explicit checks required')
 checks=[];errors=[]
 with pdf.open(path) as doc:
  if len(doc)!=q['expectedPhysicalPages']:errors.append(dict(kind='page-count',expected=q['expectedPhysicalPages'],actual=len(doc)))
  for n in q['intentionalBlankPages']:
   if type(n)is not int or not 1<=n<=len(doc):raise ValueError('invalid intentional blank page')
   if doc[n-1].get_text().strip():errors.append(dict(kind='intentional-blank-has-text',page=n))
  for pair in q['headingPairs']:
   if set(pair)!={'headingLine','nextText'} or not all(isinstance(v,str) and v.strip() for v in pair.values()):raise ValueError('exact heading line and next text required')
   found=[p for p in doc if any(norm(ln['text'])==norm(pair['headingLine']) for ln in lines(p))]
   if len(found)!=1 or norm(pair['nextText']) not in norm(found[0].get_text()):errors.append(dict(kind='heading-next-body',expectation=pair,headingPages=[p.number+1 for p in found]))
   else:checks.append(dict(kind='heading-next-body',page=found[0].number+1,expectation=pair))
  for item in q['tocEntries']:
   if set(item)!={'tocPage','title','bodyTitle','bodyMinPage'}:raise ValueError('exact fixed TOC source expectation required')
   if any(type(item[k])is not int or not 1<=item[k]<=len(doc) for k in ['tocPage','bodyMinPage']):raise ValueError('invalid TOC page boundary')
   if not all(isinstance(item[k],str) and item[k].strip() for k in ['title','bodyTitle']):raise ValueError('nonempty TOC titles required')
   p=doc[item['tocPage']-1];tl=[ln for ln in lines(p) if norm(item['title']) in norm(ln['text'])];body=[x for x in doc if x.number+1>=item['bodyMinPage'] and norm(item['bodyTitle']) in norm(x.get_text())]
   if len(tl)!=len(body) or len(tl)!=1:errors.append(dict(kind='toc-binding-ambiguous',expectation=item));continue
   y=(tl[0]['box'][1]+tl[0]['box'][3])/2;digits=[int(w[4]) for w in p.get_text('words') if w[0]>p.rect.width*.75 and abs((w[1]+w[3])/2-y)<5 and re.fullmatch(r'[0-9]+',w[4])]
   bp=body[0];numbers=[int(n) for n in re.findall(r'-\s*(\d+)\s*-',bp.get_text(clip=pdf.Rect(0,bp.rect.height*.9,bp.rect.width,bp.rect.height)))]
   if len(digits)!=1 or len(numbers)!=1 or digits!=numbers:errors.append(dict(kind='toc-printed-number-mismatch',expectation=item,tocNumbers=digits,bodyPrintedNumbers=numbers,bodyPhysicalPage=bp.number+1))
   else:checks.append(dict(kind='toc-printed-number',title=item['title'],number=digits[0],bodyPhysicalPage=bp.number+1))
  for rule in q['sparseRules']:
   if set(rule)!={'trigger','minimumCharacters','bodyMinPage'} or not isinstance(rule['trigger'],str) or not rule['trigger'] or type(rule['minimumCharacters'])is not int or rule['minimumCharacters']<=0 or type(rule['bodyMinPage'])is not int or rule['bodyMinPage']<1:raise ValueError('explicit sparse-page rule required')
   for p in doc:
    text=norm(p.get_text())
    if p.number+1>=rule['bodyMinPage'] and norm(rule['trigger']) in text and len(text)<rule['minimumCharacters']:errors.append(dict(kind='sparse-trigger-page',page=p.number+1,trigger=rule['trigger'],characters=len(text)))
 return dict(status='FAIL_REPORT_LAYOUT_SUBSET' if errors else 'PASS_REPORT_LAYOUT_SUBSET',checks=checks,errors=errors,nativeCalls=0,allDocumentContentOrVisualAcceptance='SEPARATE_NOT_GRANTED',logicalNupPages='NOT_INFERRED',autoFix=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('pdf');p.add_argument('--expectations',required=True);a=p.parse_args();result=audit(a.pdf,json.loads(Path(a.expectations).read_text(encoding='utf-8-sig')));print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['status']=='PASS_REPORT_LAYOUT_SUBSET' else 3)
if __name__=='__main__':main()
