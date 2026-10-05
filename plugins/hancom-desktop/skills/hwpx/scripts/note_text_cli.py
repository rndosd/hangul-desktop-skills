"""CLI for the source-bound note run editor; select bundled runtime first."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import safe_note_text as editor

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('inspect');p.add_argument('source');p.add_argument('--kind',choices=['footNote','endNote'],required=True);p.add_argument('--ordinal',type=int,default=1);p.add_argument('--output',required=True)
    p=sub.add_parser('apply');p.add_argument('source');p.add_argument('output');p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if args.command=='inspect':
        result=editor.inspect(args.source,args.kind,args.ordinal)
        with Path(args.output).open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    else:
        req=json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
        result=editor.apply(args.source,args.output,req,args.dry_run)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
