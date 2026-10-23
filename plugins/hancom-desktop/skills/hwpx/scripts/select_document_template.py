"""Select and copy an existing source form. Never create a blank document."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inventory(skill_root):
 root=Path(skill_root)/'assets/document-templates'
 return root,json.loads((root/'catalog.json').read_text(encoding='utf-8'))

def select(skill_root,kind=None,output=None,template_id=None,user_source=None):
 root,data=inventory(skill_root)
 if user_source:
  source=Path(user_source).resolve(strict=True)
  if source.suffix.lower() not in ('.hwpx','.hwp'):raise ValueError('사용자 서식은 HWPX 또는 HWP 원본이어야 합니다.')
  entry=dict(id='user-source',label='사용자 제공 서식',source=str(source),sha256=digest(source),selection='user_source_first',limitations=['사용자가 형식으로 지정한 서식인지 내용 참고 자료인지 먼저 구분합니다.'])
 else:
  chosen=template_id or data['defaults'].get(kind)
  matches=[r for r in data['templates'] if r['id']==chosen]
  if len(matches)!=1:raise ValueError('네 갈래 목적 또는 목록의 원본 id를 선택하세요.')
  entry=dict(matches[0])
  if entry.get('status')!='active_source':raise ValueError('선택할 수 없는 원본 상태입니다.')
  source=(root/entry['path']).resolve(strict=True)
  if not source.is_relative_to(root.resolve()):raise ValueError('보관 폴더 밖 경로입니다.')
  if digest(source)!=entry['sha256']:raise ValueError('보관 원본 해시가 목록과 다릅니다.')
  entry.update(source=str(source),selection='existing_source',preview=str(root/entry['preview']) if entry.get('preview') else None)
 entry['source_sha256']=digest(source)
 entry['native']='NEW_CONTENT_NOT_CHECKED'
 if source.suffix.lower()=='.hwp':entry['conversion_note']='HWPX API 편집이 필요하면 구형 HWP 변환 안내에 따라 HWPX 사본으로 변환합니다. 확장자만 바꾸지 않습니다.'
 if output is not None:
  output=Path(output).absolute()
  if output.suffix.lower()!=source.suffix.lower():raise ValueError('원본과 같은 확장자로 복사해야 합니다. 형식 변환은 별도 수행하세요.')
  if not output.parent.is_dir() or output.is_symlink() or output.resolve()==source:raise ValueError('원본과 다른 새 출력 경로와 기존 부모 폴더가 필요합니다.')
  with output.open('xb') as f:f.write(source.read_bytes())
  if digest(output)!=entry['source_sha256']:raise IOError('원본과 사본 해시가 다릅니다.')
  entry['output']=str(output)
 return entry

def main():
 p=argparse.ArgumentParser(description=__doc__)
 choice=p.add_mutually_exclusive_group()
 choice.add_argument('--kind',choices=['plan','report','notice','meeting','review','result','long_report','agenda','budget','settlement'])
 choice.add_argument('--id',dest='template_id')
 choice.add_argument('--source',type=Path)
 p.add_argument('--list',action='store_true');p.add_argument('--all',action='store_true');p.add_argument('--output',type=Path)
 a=p.parse_args();skill_root=Path(__file__).resolve().parents[1]
 if a.list or a.all:
  if a.output or a.kind or a.template_id or a.source:p.error('목록 조회와 복사를 함께 수행하지 않습니다.')
  _,data=inventory(skill_root)
  result=data if a.all else {'groups':[{'id':g['id'],'title':g['title'],'examples':g['examples'],'default':data['defaults'][g['id']]} for g in data['groups']],'policy':data['policy']}
 else:
  if not any([a.kind,a.template_id,a.source]):p.error('--kind, --id, --source 또는 --list가 필요합니다.')
  result=select(skill_root,a.kind,a.output,a.template_id,a.source)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
