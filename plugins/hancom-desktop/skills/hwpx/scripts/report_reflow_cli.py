"""Thin entry point for the separately qualified bounded reflow adapter."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import safe_report_reflow as editor

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('inspect-flow');a.add_argument('source');a.add_argument('--index',type=int,required=True)
 a=sub.add_parser('inspect-toc');a.add_argument('source')
 a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');a=p.parse_args()
 if a.command=='inspect-flow':result=editor.flow_binding(a.source,a.index)
 elif a.command=='inspect-toc':result=editor.toc_bindings(a.source)
 else:result=editor.apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run)
 print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
