"""Optional native page elements for a freshly composed report, never existing XML fallback."""
from pathlib import Path
import sys,json,hashlib,copy,warnings,argparse,os,tempfile
from importlib.metadata import version
import create_new_document as author
from hwpx.tools.package_validator import validate_editor_open_safety
P='{'+author.NS['hp']+'}'
SCHEMA='hwpx.report-page-elements.v1'
def require(v,message):
 if not v:raise ValueError(message)
def apply_new(doc,options):
 require(version('python-hwpx')=='6.3.0','unverified core version');require(len(doc.sections)==1,'single newly authored section required');require(isinstance(options,dict),'options object required')
 allowed={'schema','header_text','footer_text','cover','body_start_text'};require(not(set(options)-allowed) and options.get('schema')==SCHEMA,'invalid page-elements options');cover=options.get('cover',False);require(type(cover) is bool,'cover boolean required')
 for k in ['header_text','footer_text']:
  v=options.get(k,'');require(isinstance(v,str) and len(v)<=80 and not any(c in v for c in '\n\r\t'),'short single-line page text required')
 fresh_header=doc.parts.headers[0];prior_character_ids={n.get('id') for n in fresh_header.element.iter('{'+author.NS['hh']+'}charPr')}
 section=doc.sections[0];require(not any(n.tag==P+'ctrl' and any(c.tag!=P+'colPr' for c in n) for n in section.element.iter()),'unexpected existing controls in new document')
 body=None
 if cover:
  label=options.get('body_start_text');require(isinstance(label,str) and label,'body start required');matches=[p for p in section.paragraphs if p.text==label];require(len(matches)==1,'unique body start required');body=matches[0]
  defs=doc.parts.headers[0].element;pr=next(n for n in defs.iter('{'+author.NS['hh']+'}paraPr') if n.get('id')==body.para_pr_id_ref);br=pr.find('{'+author.NS['hh']+'}breakSetting');require(br is not None and br.get('pageBreakBefore')=='1','body must begin on a planned new page');require(next(i for i,p in enumerate(section.paragraphs) if p.element is body.element)>1,'cover content required')
 else:require('body_start_text' not in options,'body start only applies to cover reports')
 doc.page.setup(header_margin_mm=10,footer_margin_mm=10)
 for kind,align in [('header','LEFT'),('footer','RIGHT')]:
  value=options.get(kind+'_text','')
  if value:getattr(doc.page,'set_'+kind)(content=[dict(align=align,children=[dict(type='run',text=value,font='맑은 고딕',size=9,color='#606060')])])
 # 6.3.0 mirrors stories under secPr and body ctrl. Only new generated stories
 # are converted to the observed native body-ctrl representation before saving.
 for n in list(section.properties.element):
  if n.tag in [P+x for x in ['header','footer','headerApply','footerApply']]:section.properties.element.remove(n)
 p=section.paragraphs[0]
 with warnings.catch_warnings():
  warnings.filterwarnings('ignore',message=r'add_control\(\) produced an .*',category=UserWarning)
  ctrl=p.add_control().element
 ctrl.append(ctrl.makeelement(P+'pageNum',dict(pos='BOTTOM_CENTER',formatType='DIGIT',sideChar='-')))
 if cover:
  doc.page.set_visibility(hide_first_header=True,hide_first_footer=True,hide_first_page_num=True)
  doc.page.restart_page_number(body,number=1);body.runs[-1].text=''
 else:section.properties.set_start_numbering(page=1)
 # Native empty cells have a styled run without an empty text child.
 for t in doc.tables.all:
  for cell in t.element.iter(P+'tc'):
   for n in list(cell.iter(P+'t')):
    if not (n.text or '') and not len(n):n.getparent().remove(n)
  t.mark_dirty()
 for new_character in fresh_header.element.iter('{'+author.NS['hh']+'}charPr'):
  if new_character.get('id') not in prior_character_ids:author.canonicalize_fresh_character(doc,new_character.get('id'))
 section.mark_dirty()
 require(len(list(section.element.iter(P+'pageNum')))==1,'exactly one numeric display required')
 require(len(list(section.element.iter(P+'newNum')))==(1 if cover else 0),'restart inventory invalid')
 preparation=author.fresh_header.prepare(doc)
 return dict(cover=cover,body_start_text=options.get('body_start_text'),pageNumber='native PAGE / DIGIT / BOTTOM_CENTER',headerMarginMm=10,footerMarginMm=10,freshHeaderPreparation=preparation)
def create(brief,design,options,output):
 output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not Path(str(output)+'.receipt.json').exists(),'new hwpx and receipt required');prepared=author.prepare_design(brief,copy.deepcopy(design));doc,validation=author.compose(brief,prepared)
 try:
  result=apply_new(doc,options)
  with tempfile.TemporaryDirectory(prefix='page-elements-',dir=output.parent) as folder:
   p=Path(folder)/'candidate.hwpx';doc.save_to_path(p);require(validate_editor_open_safety(p).ok,'open safety failed');os.link(p,output)
 finally:doc.close()
 receipt=dict(schema='hwpx.report-page-elements-receipt.v1',status='PASS_STRUCTURE',native='pending',options=options,pageElements=result,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),authorSha256=hashlib.sha256(Path(author.__file__).read_bytes()).hexdigest(),design=prepared)
 with open(str(output)+'.receipt.json','x',encoding='utf8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
 return receipt
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--brief',required=True);p.add_argument('--design',required=True);p.add_argument('--options',required=True);p.add_argument('--output',required=True);a=p.parse_args();load=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));r=create(load(a.brief),load(a.design),load(a.options),a.output);print(json.dumps(dict(status=r['status'],native=r['native'],pageElements=r['pageElements']),ensure_ascii=False))

