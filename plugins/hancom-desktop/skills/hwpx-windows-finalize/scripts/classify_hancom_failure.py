"""Read-only failure stage classification. Never launches, registers or repairs."""
import argparse,json
from pathlib import Path
def classify(v):
 error=str(v.get('error',''))+' '+str(v.get('stderr',''))+' '+str(v.get('stdout',''))
 low=error.lower()
 evidence={k:v.get(k,'NOT_RECORDED') for k in ['status','comCreated','registerModuleCalled','securityModuleRegistered','firstOpen','saveAs','reopen','pdfExport']}
 if 'process_conflict' in low or 'lock_conflict' in low:
  stage='PRE_COM_CONFLICT';action='Wait for the existing user session or automation owner; do not kill user Hwp or reinstall DLL.'
 elif 'dictionary' in low and 'path' in low and 'Start-Process' in error:
  stage='CONTROLLER_PROCESS_LAUNCH';action='Check inherited child environment name collisions. Explicit environment serialization is a scoped candidate; preserve original failure and verify it. No COM/module failure inferred.'
 elif v.get('comCreated') is False:
  stage='COM_ACTIVATION';action='Record HRESULT and same-time DCOM events. Compare the same worker in an authorized ordinary logged-in user context once. No security registration conclusion before RegisterModule.'
 elif v.get('comCreated') is True and v.get('registerModuleCalled') is True and v.get('securityModuleRegistered') is False:
  stage='SECURITY_MODULE_REGISTRATION';action='Read selected reviewed module name/DLL/architecture and actual user context; do not open a document or auto-register/replace a DLL.'
 elif v.get('comCreated') is True and v.get('securityModuleRegistered') is True:
  if v.get('firstOpen') is False:stage='DOCUMENT_OPEN';action='Diagnose the exact file and receipt; do not reinstall a working security module.'
  elif v.get('mode')=='SaveAs' and v.get('saveAs') is False:stage='DOCUMENT_SAVE';action='Preserve the candidate and inspect output access/file errors.'
  elif v.get('reopen') is False:stage='DOCUMENT_REOPEN';action='Inspect the saved file and same-object Clear/Open steps.'
  elif v.get('pdfExport') is False and v.get('status')!='PASS_FULL':stage='PDF_EXPORT';action='Inspect the requested PDF output and native export error.'
  elif v.get('status')=='PASS_FULL':stage='NATIVE_STEPS_PASSED';action='Perform exact-file content and visual review; COM success is not strict preservation acceptance.'
  else:stage='POST_NATIVE_OR_CLEANUP';action='Inspect remaining process/source hash and cleanup receipt.'
 else:stage='UNDETERMINED';action='Preserve logs; missing fields are not false results. Do not repeat or change settings without a cause.'
 return dict(stage=stage,evidence=evidence,nextAction=action,settingsChanged=False,automaticRepair=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',required=True);a=p.parse_args()
 result=classify(json.loads(Path(a.input).read_text(encoding='utf-8-sig')))
 with Path(a.output).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps(result,ensure_ascii=False))
