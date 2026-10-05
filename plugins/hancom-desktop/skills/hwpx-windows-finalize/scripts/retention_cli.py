"""Explicit source/tool-bound inspect and apply; no native or security changes."""
from pathlib import Path
import argparse,json,sys
import retain_unused_paragraph_style as para
import retain_unused_character_style as char
import hancom_completion_gate as gate
S=Path(__file__).resolve().parent
def refs():
    return [gate.ref(S/n) for n in ['retention_cli.py','retain_unused_paragraph_style.py','retain_unused_character_style.py']]+[gate.ref(S.parent.parent/'hwpx/scripts'/n) for n in ['safe_edit.py','candidate_runtime.py','namespace_literal_guard.py']]+[gate.ref(S.parent.parent/'hwpx/vendor/hwpx'/n) for n in ['document.py','oxml/header_part.py']]
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('inspect');a.add_argument('source');a.add_argument('--kind',choices=['paragraph','character'],required=True);a.add_argument('--id',action='append',required=True);a.add_argument('--output',required=True)
    a=sub.add_parser('apply');a.add_argument('source');a.add_argument('--plan',required=True);a.add_argument('--output',required=True);a.add_argument('--receipt',required=True)
    a=p.parse_args()
    try:
        if a.command=='inspect':
            module=para if a.kind=='paragraph' else char
            v=dict(schema='hwpx.explicit-unused-definition-retention.v1',kind=a.kind,source=gate.ref(a.source),binding=module.inspect(a.source,a.id),tools=refs(),native='NOT_CALLED',declaredChange='Only named header styles for explicitly selected unused definitions; old definitions and all body/assets exact.')
            gate.write_new(Path(a.output),v)
        else:
            q=json.loads(Path(a.plan).read_text(encoding='utf-8-sig'))
            para.need(set(q)=={'schema','kind','source','binding','tools','native','declaredChange'} and q['schema']=='hwpx.explicit-unused-definition-retention.v1' and q['kind'] in ['paragraph','character'],'invalid retention plan')
            para.need(q['tools']==refs() and q['source']==gate.ref(a.source),'source or tool binding changed')
            for x in q['tools']:gate.verify_ref(x)
            out=Path(a.output).absolute();receipt=Path(a.receipt).absolute()
            para.need(not receipt.exists() and receipt.parent.is_dir() and receipt!=out and receipt not in [Path(a.source).resolve(),Path(a.plan).resolve()],'new distinct receipt required before mutation')
            module=para if q['kind']=='paragraph' else char
            v=module.apply(a.source,out,q['binding']);v.update(plan=gate.ref(a.plan),tools=q['tools'],native='NOT_CALLED',savedRoundtrip='NOT_CHECKED',visual='NOT_REVIEWED',publication=False)
            gate.write_new(receipt,v)
        print(json.dumps(v,ensure_ascii=False));return 0
    except (ValueError,KeyError,OSError,gate.GateError) as ex:
        print(json.dumps(dict(status='BLOCKED_NO_RETRY',error=str(ex),native='NOT_CALLED'),ensure_ascii=False));return 3
if __name__=='__main__':raise SystemExit(main())
