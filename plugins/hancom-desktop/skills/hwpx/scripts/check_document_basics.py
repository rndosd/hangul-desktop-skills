"""Read-only native-number hierarchy and manual-prefix check; not a grammar/layout validator."""
from pathlib import Path
import argparse,collections,json,re,zipfile,xml.etree.ElementTree as E
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}';H='{http://www.hancom.co.kr/hwpml/2011/head}'
def check(path,required_levels=()):
    levels=collections.Counter();failures=[]
    with zipfile.ZipFile(path) as z:
        h=E.fromstring(z.read('Contents/header.xml'));shapes={n.get('id'):n for n in h.iter(H+'paraPr')}
        for name in sorted(n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n)):
            root=E.fromstring(z.read(name))
            for index,p in enumerate(list(root)):
                text=''.join(n.text or '' for n in p.iter(P+'t'))
                # Only top-level paragraphs. Existing tables are not flattened
                # into parent text and counted again as manual list items.
                if p.find('.//'+P+'tbl') is not None:continue
                if text and re.match(r'^[ \t\u3000]',text):failures.append(dict(code='MANUAL_LEADING_WHITESPACE',section=name,paragraph=index))
                if re.match(r'^(?:\d{1,2}\.|[가-하][.)]|\d{1,2}\))\s',text):failures.append(dict(code='LITERAL_ITEM_PREFIX',section=name,paragraph=index))
                shape=shapes.get(p.get('paraPrIDRef'));head=shape.find(H+'heading') if shape is not None else None
                if head is not None and head.get('type')=='NUMBER':levels[int(head.get('level'))+1]+=1
    for level in required_levels:
        if not levels.get(level):failures.append(dict(code='REQUIRED_NATIVE_LEVEL_MISSING',level=level))
    return dict(status='FAIL' if failures else 'PASS_STRUCTURE',native_number_levels=dict(levels),failures=failures,scope='선언된 실제 번호 수준·선행 공백·문자 번호 검사. 의미·맞춤법·줄 정렬·겹침은 별도 검토.')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path);p.add_argument('--required-levels',default='');p.add_argument('--output',type=Path);a=p.parse_args()
    result=check(a.path,[int(n) for n in a.required_levels.split(',') if n]);s=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:
        with a.output.open('x',encoding='utf8') as f:f.write(s)
    print(s);raise SystemExit(1 if result['status']=='FAIL' else 0)
