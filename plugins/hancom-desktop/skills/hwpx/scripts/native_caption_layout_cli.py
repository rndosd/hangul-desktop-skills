"""CLI for explicit exclusive-style caption grouping and spacing."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import safe_native_caption_layout as editor
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('inspect');a.add_argument('source');a.add_argument('--table',required=True,type=int);a.add_argument('--caption',required=True);a.add_argument('--output',required=True)
    a=s.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');a=p.parse_args()
    if a.command=='inspect':
        result=editor.inspect(a.source,a.table,a.caption)
        with Path(a.output).open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    else:result=editor.apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
