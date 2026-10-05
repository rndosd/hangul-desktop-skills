"""Explicit selected-table flow binding; preserve original and write a new copy."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json,hashlib
import safe_expanded_table_flow as editor
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
 a=s.add_parser('inspect');a.add_argument('source');a.add_argument('--table',type=int,required=True);a.add_argument('--header-rows',type=int,nargs='+',required=True);a.add_argument('--caption')
 a=s.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');a=p.parse_args()
 if a.command=='inspect':
  data=Path(a.source).read_bytes();result=dict(sourceSha256=hashlib.sha256(data).hexdigest(),binding=editor.binding(data,a.table,a.header_rows,a.caption))
 else:result=editor.apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
