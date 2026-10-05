# SPDX-License-Identifier: Apache-2.0
"""Bounded character-spacing/ratio candidates with exact format preservation."""
import copy
import argparse
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile
from importlib.metadata import version
from lxml import etree as ET

from hwpx import HwpxDocument
from hwpx.oxml import HwpxOxmlParagraph
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_edit import candidates, digest, local, parse, snapshot, source_path
from namespace_literal_guard import preserve_namespace_literals

SCHEMA='hwpx.bounded-character-format.v1'


def first_difference(a,b,path=()):
    if a==b:return None
    if isinstance(a,dict) and isinstance(b,dict):
        for key in sorted(set(a)|set(b)):
            if key not in a or key not in b:return {'path':path+(key,),'reason':'member mismatch'}
            result=first_difference(a[key],b[key],path+(key,))
            if result:return result
    if isinstance(a,(tuple,list)) and isinstance(b,(tuple,list)):
        if len(a)!=len(b):return {'path':path,'expected_length':len(a),'actual_length':len(b)}
        for i,(left,right) in enumerate(zip(a,b)):
            result=first_difference(left,right,path+(i,))
            if result:return result
    return {'path':path,'expected':repr(a)[:350],'actual':repr(b)[:350]}


def shape(node):
    return node.tag,tuple(sorted(node.attrib.items())),node.text or '',node.tail or '',tuple(shape(c) for c in node)


def character_semantics(node):
    # Only new style clones: API may reorder flags and omit inactive NONE
    # markers. Existing style definitions remain exact in the package snapshot.
    children=[c for c in node if not (local(c)=='underline' and c.get('type')=='NONE')
              and not (local(c)=='strikeout' and c.get('shape')=='NONE')]
    return node.tag,tuple(sorted(node.attrib.items())),node.text or '',node.tail or '',tuple(sorted((shape(c) for c in children),key=repr))


def uniform_value(node,name):
    child=next((n for n in node if local(n)==name),None)
    if child is None or not child.attrib:
        raise ValueError('missing '+name+' language channels')
    values={int(v) for v in child.attrib.values()}
    if len(values)!=1:
        raise ValueError('language-specific '+name+' requires a different explicit contract')
    return values.pop()


@preserve_namespace_literals
def apply_format(source,output,plan,*,dry_run=False):
    source=source_path(source);output=Path(output).absolute();before=digest(source)
    if source==output.resolve() or output.exists() or output.is_symlink() or output.suffix.lower()!='.hwpx' or not output.parent.is_dir():
        raise ValueError('output must be a new HWPX path')
    if version('python-hwpx')!='6.3.0' or not validate_editor_open_safety(source).ok:
        raise ValueError('unsupported runtime or invalid source')
    if not isinstance(plan,dict) or set(plan)!={'schema','source_sha256','targets'} or plan['schema']!=SCHEMA or plan['source_sha256']!=before:
        raise ValueError('invalid/stale format plan')
    if not isinstance(plan['targets'],list) or not 1<=len(plan['targets'])<=20:
        raise ValueError('format plan requires 1..20 explicit paragraphs')
    with ZipFile(source) as z:header=parse(z.read('Contents/header.xml'))
    old_styles={n.get('id'):n for n in header.iter() if local(n)=='charPr'}
    expected_header=parse(ET.tostring(header.getroottree()))
    expected_chars=next(n for n in expected_header.iter() if local(n)=='charProperties')
    expected_styles={n.get('id'):n for n in expected_chars if local(n)=='charPr'}
    attrs={};changed=set();seen=set();results=[];new_expectations={}
    with tempfile.TemporaryDirectory(prefix='hwpx-format-',dir=output.parent) as tmp:
        candidate=Path(tmp)/'candidate.hwpx';doc=HwpxDocument.open(source)
        try:
            section_map={s.part_name:s for s in doc.sections}
            for target in plan['targets']:
                if set(target)!={'part','paragraph_path','expected_text','letter_spacing','ratio','reason'} or not target['reason']:
                    raise ValueError('explicit target, expected text, spacing, ratio and reason required')
                key=(target['part'],tuple(target['paragraph_path']))
                if key in seen:raise ValueError('duplicate format paragraph')
                seen.add(key)
                options=[c for c in candidates(source,target['expected_text'],before) if c['part']==target['part'] and tuple(c['paragraph_path'])==key[1]]
                if len(options)!=1 or not options[0]['supported'] or options[0]['_paragraph_text']!=target['expected_text']:
                    raise ValueError('format target missing/unsupported/mismatched')
                view=options[0];section=section_map[target['part']];node=section.element
                for i in key[1]:node=node[i]
                paragraph=HwpxOxmlParagraph(node,section)
                for info in view['_runs']:
                    if not info['text']:continue
                    old=old_styles[info['char_pr']];old_spacing=uniform_value(old,'spacing');old_ratio=uniform_value(old,'ratio')
                    spacing,ratio=target['letter_spacing'],target['ratio']
                    if type(spacing)is not int or type(ratio)is not int or abs(spacing-old_spacing)>5 or abs(ratio-old_ratio)>5 or not -10<=spacing<=10 or not 95<=ratio<=105:
                        raise ValueError('bounded format limits exceeded')
                    if spacing==old_spacing and ratio==old_ratio:continue
                    run=next(r for r in paragraph.runs if r.element is node[info['path'][0]])
                    # Only requested language-channel spacing/ratio changes.
                    # ensure_run also rewrites inactive decoration children and
                    # can append NONE underline out of native order. Clone via
                    # the public bounded header API so every other node stays
                    # exact, including inactive underline/strikeout and order.
                    wanted=copy.deepcopy(old)
                    for tag,value in [('spacing',spacing),('ratio',ratio)]:
                        child=next(n for n in wanted if local(n)==tag)
                        for channel in child.attrib:child.set(channel,str(value))
                    def without_id(n):
                        clone=copy.deepcopy(n);clone.attrib.pop('id',None)
                        return shape(clone)
                    def modify_channels(n):
                        for tag,value in [('spacing',spacing),('ratio',ratio)]:
                            child=next(n for n in n if local(n)==tag)
                            for channel in child.attrib:child.set(channel,str(value))
                    new_style=doc.parts.headers[0].ensure_char_property(
                        base_char_pr_id=info['char_pr'],
                        predicate=lambda n,w=wanted:without_id(n)==without_id(w),
                        modifier=modify_channels)
                    new_id=new_style.get('id')
                    expected=copy.deepcopy(old);expected.set('id',str(new_id))
                    for tag,value in [('spacing',spacing),('ratio',ratio)]:
                        child=next(n for n in expected if local(n)==tag)
                        for channel in child.attrib:child.set(channel,str(value))
                    if str(new_id) in expected_styles:
                        if shape(expected_styles[str(new_id)])!=shape(expected):
                            raise ValueError('public style deduplication changed unrelated format')
                    else:
                        expected_chars.append(expected);expected_styles[str(new_id)]=expected
                        new_expectations[str(new_id)]=expected
                    run.char_pr_id_ref=new_id
                    if run.replace_text(info['text'],info['text'],count=1)!=1:
                        raise ValueError('public layout-cache invalidation failed')
                    attrs[(key[0],key[1]+(info['path'][0],))]={'charPrIDRef':str(new_id)}
                    changed.add(key)
                    results.append({'part':key[0],'paragraph_path':key[1],'before_char_pr':info['char_pr'],
                                    'after_char_pr':new_id,'before_spacing':old_spacing,'after_spacing':spacing,
                                    'before_ratio':old_ratio,'after_ratio':ratio,'font_height_preserved':old.get('height'),'reason':target['reason']})
            if not results:raise ValueError('format plan makes no changes')
            expected_chars.set('itemCnt',str(len(expected_styles)))
            expected=snapshot(source,changed_paragraphs=changed,attribute_overrides=attrs,xml_roots={'Contents/header.xml':expected_header})
            doc.save_to_path(candidate)
        finally:doc.close()
        # Verify complete meaning of each new definition against the original
        # clone plus only approved spacing/ratio, including exact child order.
        with ZipFile(candidate) as z:actual_header=parse(z.read('Contents/header.xml'))
        actual_styles={n.get('id'):n for n in actual_header.iter() if local(n)=='charPr'}
        for ident,expected_style in new_expectations.items():
            actual_style=actual_styles.get(ident)
            if actual_style is None or shape(expected_style)!=shape(actual_style):
                raise ValueError('new style changes unrequested character semantics; no output published')
            position=list(expected_chars).index(expected_style)
            expected_chars.remove(expected_style);expected_chars.insert(position,copy.deepcopy(actual_style))
        expected=snapshot(source,changed_paragraphs=changed,attribute_overrides=attrs,xml_roots={'Contents/header.xml':expected_header})
        reopened=HwpxDocument.open(candidate);reopened.close()
        actual=snapshot(candidate,changed_paragraphs=changed)
        if not validate_editor_open_safety(candidate).ok or actual!=expected:
            raise ValueError('format/text/non-target preservation mismatch; no output published: '+json.dumps(first_difference(expected,actual),ensure_ascii=False))
        if digest(source)!=before:raise ValueError('source changed; no output published')
        after=digest(candidate)
        if not dry_run:os.link(candidate,output)
    return {'schema':'hwpx.bounded-character-format-receipt.v1','status':'PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',
            'source_sha256':before,'output_sha256':after,'published':not dry_run,'changes':results,
            'font_size_reduced':False,'all_unrequested_format_and_text_preserved':True,
            'native_open':'not_checked','native_render':'not_checked','visual_review':'not_performed',
            'necessity_and_readability':'native_review_required','completion':'format_candidate_native_pending'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('output');parser.add_argument('--plan',required=True);parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:
        print(json.dumps(apply_format(args.source,args.output,json.loads(Path(args.plan).read_text(encoding='utf-8-sig')),dry_run=args.dry_run),ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc),'native_render':'not_checked'},ensure_ascii=False));raise SystemExit(2)
