"""Pure payload planning; no XML edits, COM or automatic duplicate removal."""
from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import paragraph_run_payload as m

def main():
 p=argparse.ArgumentParser();p.add_argument('--request',required=True);a=p.parse_args();q=json.loads(Path(a.request).read_text(encoding='utf-8-sig'))
 if not isinstance(q,dict) or q.get('schema')!='hwpx.paragraph-payload.v1' or set(q)-{'schema','runs','span','text','segments'}:raise ValueError('unsupported payload request')
 runs=m.plan(q['runs'],q['span'],q['text'],q.get('segments'))
 print(json.dumps(dict(schema='hwpx.paragraph-payload-result.v1',runs=runs,intendedText=q['text'],payloadExact=True,nativeCalls=0,documentPublished=False),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
