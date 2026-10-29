"""Compose prepared blocks, save/reopen and export PDF in one owned native job."""
import argparse, json
from run_native_job import run, read

def compose(request, output, pdf, run_dir, context, timeout=120):
    return run(request['base']['path'],'SaveAs',output,pdf,run_dir,context,timeout,composition=request)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--pdf',required=True)
    parser.add_argument('--run',required=True)
    parser.add_argument('--context',choices=['ordinary-shell','host-approved'],required=True)
    parser.add_argument('--timeout',type=int,default=120)
    a=parser.parse_args()
    try:result=compose(read(a.request),a.output,a.pdf,a.run,a.context,a.timeout)
    except (ValueError,OSError,KeyError,TypeError) as error:result=dict(status='BLOCKED_INPUT',reason=str(error),automaticRetry=False)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASS_NATIVE' else 3

if __name__=='__main__':raise SystemExit(main())
