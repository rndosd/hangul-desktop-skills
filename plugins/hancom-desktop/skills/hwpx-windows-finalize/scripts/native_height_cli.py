from pathlib import Path
import argparse,json,sys
import native_measured_table_height as height
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
 a=s.add_parser('inspect');a.add_argument('source');a.add_argument('--table-id',action='append',required=True);a.add_argument('--output',required=True)
 a=s.add_parser('run');a.add_argument('source');a.add_argument('--table-id',action='append',required=True);a.add_argument('--work',required=True);a.add_argument('--context',choices=['ordinary-shell','host-approved'],required=True)
 a=p.parse_args()
 try:
  if a.command=='inspect':v=height.inspect(a.source,a.table_id);height.write(a.output,v)
  else:v=height.run(a.source,a.work,a.table_id,a.context)
  print(json.dumps(v,ensure_ascii=False));return 3 if v.get('status','').startswith('BLOCKED') else 0
 except (ValueError,KeyError,OSError,height.gate.GateError) as ex:print(json.dumps(dict(status='BLOCKED',error=str(ex),native='NOT_CALLED_OR_PRESERVED_JOB'),ensure_ascii=False));return 3
if __name__=='__main__':raise SystemExit(main())
