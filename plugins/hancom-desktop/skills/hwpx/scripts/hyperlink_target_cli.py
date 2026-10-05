"""CLI for the explicit existing HTTPS web-field adapter."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import safe_hyperlink_target as editor

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('inspect');a.add_argument('source');a.add_argument('--ordinal',type=int,default=1);a.add_argument('--output',required=True)
    a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');a=p.parse_args()
    if a.command=='inspect':
        result=editor.inspect(a.source,a.ordinal)
        with Path(a.output).open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    else:result=editor.apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
