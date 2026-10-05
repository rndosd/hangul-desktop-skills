"""Bound source/table identity, preserve original, publish a new file only."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import safe_mixed_table_structure as editor
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
 a=s.add_parser('inspect');a.add_argument('source');a.add_argument('--table',type=int,required=True)
 a=s.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');a=p.parse_args()
 result=editor.inspect(a.source,a.table) if a.command=='inspect' else editor.apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
