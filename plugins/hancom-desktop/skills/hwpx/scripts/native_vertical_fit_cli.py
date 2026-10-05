from candidate_runtime import activate
activate()
from pathlib import Path
import sys,json,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'hwpx-windows-finalize/scripts'))
import native_vertical_fit as fit
import safe_native_vertical_margins as edit
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
 a=s.add_parser('inspect');a.add_argument('source');a.add_argument('--policy',required=True)
 a=s.add_parser('dry-run');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True)
 a=s.add_parser('run');a.add_argument('source');a.add_argument('output');a.add_argument('--policy',required=True)
 a=p.parse_args()
 q=json.loads(Path(a.request if a.command=='dry-run' else a.policy).read_text(encoding='utf-8-sig'))
 if a.command=='inspect':b=fit.policy(a.source,q);result=dict(binding=b,grid=list(fit.grid(b,q)),native='NOT_CALLED')
 elif a.command=='dry-run':result=edit.apply(a.source,a.output,q,True)
 else:result=fit.run(a.source,a.output,q)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
