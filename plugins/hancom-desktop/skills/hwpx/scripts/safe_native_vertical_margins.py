"""Pinned existing-file vertical margin adapter; no report regeneration."""
from pathlib import Path
from importlib.metadata import version
import os,zipfile
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
import safe_native_page_settings as pages
from workspace_candidate_directory import workspace_candidate_directory
P=pages.P;SCHEMA='hwpx.native-vertical-margins.v1';require=pages.require;sha=pages.sha

def inspect(source):
    sections=oracle.sections(source);require(len(sections)==1,'one existing section required')
    part,root=sections[0];ps=list(root.iter(P+'pagePr'));require(len(ps)==1,'one page geometry required')
    page=ps[0];m=page.find(P+'margin');require(m is not None and m.get('gutter')=='0','existing zero gutter required')
    require(all(m.get(k,'').isdigit() for k in ['left','right','top','bottom','header','footer']),'integer native margins required')
    require(not any(p.get('pageBreak') in ['1','true'] or p.get('columnBreak') in ['1','true'] for p in root.iter(P+'p')),'intentional page/column breaks excluded')
    used={p.get('paraPrIDRef') for p in root.iter(P+'p')};H='{http://www.hancom.co.kr/hwpml/2011/head}'
    with zipfile.ZipFile(source) as z:header=oracle.parse(z.read('Contents/header.xml'))
    require(not any(n.get('pageBreakBefore') in ['1','true'] for pr in header.iter(H+'paraPr') if pr.get('id') in used for n in pr.iter(H+'breakSetting')),'intentional referenced paragraph-style page break excluded')
    require(len(list(root.iter(P+'tbl')))<=10,'bounded existing report only')
    return dict(part=part,sectionSha256=pages.fingerprint(root),marginPath=list(pages.location(m)),
        pageAttrs=dict(page.attrib),marginAttrs=dict(m.attrib),paragraphPaths=[list(pages.location(p)) for p in root.iter(P+'p')])

def checked(source,q):
    require(isinstance(q,dict) and set(q)=={'schema','sourceSha256','binding','top','bottom','editableReason'} and q['schema']==SCHEMA,'exact vertical margin request required')
    require(q['sourceSha256']==sha(source),'stale source');b=inspect(source);require(b==q['binding'],'stale margin binding')
    require(all(type(q[k]) is int and 2835<=q[k]<=int(b['marginAttrs'][k]) for k in ['top','bottom']),'integer shrinking margins with10mm floor required')
    require(int(b['marginAttrs']['top'])-q['top']==int(b['marginAttrs']['bottom'])-q['bottom']>0,'positive equal opposing reduction required')
    oracle.single_line(q['editableReason'],search=True);require(len(q['editableReason'])>=8,'specific reason required')
    changes={(b['part'],tuple(b['marginPath'])):dict(top=str(q['top']),bottom=str(q['bottom']))}
    caches={(b['part'],tuple(p)) for p in b['paragraphPaths']}
    return b,changes,caches

def verify(source,output,q):
    b,attrs,caches=checked(source,q)
    require(oracle.snapshot(source,attribute_overrides=attrs,changed_paragraphs=caches)==oracle.snapshot(output,changed_paragraphs=caches),'non-target package changed')
    return dict(status='PASS_VERTICAL_MARGIN_PRESERVATION',onlyExistingTopBottomChanged=True,
        leftRightHeaderFooterGutterStoriesTextNumberingAllDefinitionsTablesAndAssetsExact=True,
        explicitlyClearedCaches='paragraph lineSegArray only; all paragraphs relayout after page geometry change')

def apply(source,output,q,dry_run=False):
    require(version('python-hwpx')=='6.3.0','pinned adapter required');source=Path(source).resolve(strict=True);output=Path(output).absolute()
    require(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and output.resolve()!=source,'new workspace output required')
    b,attrs,caches=checked(source,q)
    with workspace_candidate_directory(prefix='vertical-margins-',dir=output.parent) as folder:
        trial=Path(folder)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            require(len(doc.sections)==1 and pages.fingerprint(doc.sections[0].element)==b['sectionSha256'],'public section mismatch')
            doc.page.set_margins(top=q['top'],bottom=q['bottom'])
            section=doc.sections[0]
            for path in b['paragraphPaths']:
                node=pages.at(section.element,path)
                for cache in list(node.findall(P+'linesegarray')):node.remove(cache)
            section.mark_dirty();doc.save_to_path(trial)
        proof=verify(source,trial,q);require(validate_editor_open_safety(trial).ok,'editor safety failed');require(sha(source)==q['sourceSha256'],'source changed')
        if not dry_run:os.link(trial,output)
        return dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',checks=proof,sourceUnchanged=True,native='NOT_CHECKED')
