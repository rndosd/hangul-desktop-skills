from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import semantic_table_binding as b
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--request',required=True);a=p.parse_args();q=json.loads(Path(a.request).read_text(encoding='utf-8-sig'))
 if not isinstance(q,dict)or q.get('schema')!='hwpx.semantic-table-binding.v1'or set(q)-{'schema','headers','key','sourceSha256'}:raise ValueError('unsupported binding request')
 result=b.bind(a.source,q['headers'],q.get('key'),q.get('sourceSha256'));result.update(nativeCalls=0,documentPublished=False);print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
