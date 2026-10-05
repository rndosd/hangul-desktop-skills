from candidate_runtime import activate
activate()
from pathlib import Path
import argparse,json
import safe_native_report_spacing as editor
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('inspect');a.add_argument('source');a.add_argument('--headings-file',required=True);a.add_argument('--output',required=True)
    a=s.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');a=p.parse_args()
    if a.command=='inspect':
        texts=json.loads(Path(a.headings_file).read_text(encoding='utf-8-sig'));v=dict(sourceSha256=editor.sha(a.source),binding=editor.inspect(a.source,texts))
        with Path(a.output).open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
    else:v=editor.apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run)
    print(json.dumps(v,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
