from pathlib import Path
import copy,json,sys,uuid

INSTALLED=Path.home()/'.codex/skills/hwpx'
sys.path.append(str(INSTALLED/'scripts'))
from candidate_runtime import activate
activate()
import safe_body_structure as body
from hangul_task import batch
from hwpx_automation.office.agent import HwpxAgentDocument
from lxml import etree as E

def snapshot(node):
 return [node.tag,sorted(node.attrib.items()),node.text or '',node.tail or '',[snapshot(n) for n in node]]

def main():
 source=Path(sys.argv[1]).resolve(strict=True)
 evidence=Path(sys.argv[2]).resolve()/('run-'+uuid.uuid4().hex)
 evidence.mkdir(parents=True)
 def write(name,value):
  (evidence/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
 before=source.read_bytes()
 inspection=body.inspect(source);write('inspect.json',inspection)
 paragraphs=inspection['paragraphs']
 edits=[]
 for index,replacement in [(1,' 활동 개요'),(5,' 운영 방향')]:
  record=paragraphs[index]
  assert not record['plain'] and not record['richTemplate']
  assert record['controls']==['rect']
  assert not record['cloneEligibility']['eligible'] and 'cannot be cloned' in record['cloneEligibility']['reason']
  candidate=record['directRunTextEdit']
  assert candidate['status']=='candidate' and candidate['preservationVerificationRequired']
  assert candidate['runs']==[{'index':0,'text':record['binding']['text'],'charPrIDRef':'54'}]
  edits.append((index,replacement))
 parts,roots,defs=body.package(before)
 p=roots['Contents/section0.xml'][1]
 for tag in ['ctrl','mysteryControl']:
  unknown=copy.deepcopy(p)
  E.SubElement(unknown.find(body.P+'run'),body.P+tag)
  assert body.direct_run_text_candidate(unknown)['status']=='unsupported'
 mixed=copy.deepcopy(p)
 E.SubElement(mixed.find(body.P+'run').find(body.P+'t'),body.P+'lineBreak')
 assert body.direct_run_text_candidate(mixed)['status']=='unsupported'
 unknown_rect=copy.deepcopy(p)
 E.SubElement(unknown_rect.find('.//'+body.P+'rect'),body.P+'mysteryControl')
 assert body.direct_run_text_candidate(unknown_rect)['status']=='unsupported'
 field_source=INSTALLED/'assets/document-templates/reusable-blocks/budget-form.hwpx'
 field_inspection=body.inspect(field_source)
 write('real-field-inspect.json',field_inspection)
 assert any('fieldBegin' in r['controls'] for r in field_inspection['paragraphs'])
 assert all(r['directRunTextEdit']['status']=='unsupported' and r['directRunTextEdit']['route'] is None and not r['directRunTextEdit']['runs'] for r in field_inspection['paragraphs'])
 request=dict(schema=body.RICH_SCHEMA,sourceSha256=inspection['sourceSha256'],editableReason='Verify controlled heading remains outside body edits',protectedSpans=[],operations=[dict(op='replace_runs',target=paragraphs[1]['binding'],runs=[' 활동 개요'])])
 try:body.checked(before,request)
 except ValueError as error:assert 'unsupported run target' in str(error)
 else:raise AssertionError('body apply must reject the controlled heading')
 target=evidence/'heading-edited.hwpx'
 with HwpxAgentDocument.open(source) as doc:
  commands=[]
  for index,replacement in edits:
   path=f'/section[1]/paragraph[{index+1}]/run[1]'
   found=[r for r in doc.records if r.path==path and r.kind=='run']
   assert len(found)==1 and found[0].summary['text']==paragraphs[index]['binding']['text']
   commands.append(dict(commandId=f'heading-{index}',op='set',path=path,properties=dict(text=replacement)))
  request=dict(schemaVersion='hwpx.agent-batch/v1',input=dict(filename=str(source)),output=dict(filename=str(target),overwrite=False),expectedRevision=doc.revision,commands=commands,quality='transparent',verificationRequirements=['package','reopen','openSafety','semanticDiff','bytePreservation'])
 for mode in ['dry','commit']:
  req=dict(request,dryRun=mode=='dry',idempotencyKey=f'{evidence.name}-{mode}')
  write(mode+'-request.json',req)
  result=batch(req);write(mode+'-result.json',result)
  assert result['ok'],result
 after,actual_roots,_=body.package(target.read_bytes())
 assert source.read_bytes()==before
 assert set(parts)==set(after)
 assert all(parts[n]==after[n] for n in parts if n!='Contents/section0.xml')
 expected=copy.deepcopy(roots['Contents/section0.xml'])
 for index,replacement in edits:
  expected[index].find(body.P+'run').find(body.P+'t').text=replacement
  for cache in expected[index].findall(body.P+'linesegarray'):expected[index].remove(cache)
 assert snapshot(expected)==snapshot(actual_roots['Contents/section0.xml'])
 assert [snapshot(n) for n in roots['Contents/section0.xml'].iter(body.P+'rect')]==[snapshot(n) for n in actual_roots['Contents/section0.xml'].iter(body.P+'rect')]
 report=dict(status='PASS',source=str(source),sourceSha256=body.digest(before),candidate=str(target),candidateSha256=body.sha(target),headingTextEdits=2,rectanglesAndAllUneditedSubtreesEqual=True,nonTargetPackageMembersByteExact=True,bodyApplyStillRejectsControlledHeading=True,unknownAndMixedInlineCandidatesBlocked=True,realFieldSource=str(field_source),realFieldSourceSha256=body.sha(field_source),realFieldNoFallback=True,native='NOT_CHECKED')
 write('summary.json',report)
 print(json.dumps(dict(status='PASS',evidence=str(evidence)),ensure_ascii=False))

if __name__=='__main__':main()
