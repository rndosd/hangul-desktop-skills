"""Portable argv-based launcher in the current host-approved user context.
Never escapes sandbox, grants permission, registers a DLL or installs a service.
The calling host/user chooses the context; actual read-only preflight records
ordinary user/session/module binding, and each native worker separately proves
COM creation/RegisterModule. No retry or automatic elevation/fallback.
"""
import argparse,json,os,subprocess,sys,hashlib
from pathlib import Path
from classify_hancom_failure import classify
S=Path(__file__).resolve().parent
def require(ok,message):
 if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):
 with Path(p).open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def environment_map(mapping):
 result={}
 for key,value in mapping.items():
  name=key.upper();require(name not in result or result[name]==value,'AMBIGUOUS_CHILD_ENVIRONMENT:'+name);result[name]=value
 return result
def configuration_pair(skill_root=None, codex_root=None):
 root=Path(skill_root) if skill_root is not None else S.parent
 local=(root/'environment.json',root.parent/'hwpx/environment.json')
 # Never merge a partial candidate configuration with a global configuration.
 if any(p.exists() for p in local):
  require(all(p.is_file() for p in local),'incomplete local desktop configuration pair')
  return local
 home=Path(codex_root) if codex_root is not None else Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
 installed=(home/'skills/hwpx-windows-finalize/environment.json',home/'skills/hwpx/environment.json')
 require(all(p.is_file() for p in installed),'DESKTOP_NOT_CONFIGURED')
 return installed

def dependencies():
 config,sibling=configuration_pair();v=read(config)
 require(v.get('schema')=='hangul.desktop-environment.v1','invalid desktop schema')
 other=read(sibling)
 require(all(v.get(k)==other.get(k) for k in ['pythonPath','hancom','security']),'sibling desktop mismatch')
 sec=v.get('security',{});require(sec.get('status')=='reviewed_existing' and sec.get('reviewConfirmed') is True,'reviewed security module required')
 files={}
 for key,value in [('python',v.get('pythonPath')),('hwp',v.get('hancom',{}).get('path')),('dll',sec.get('dllPath')),('policy',sec.get('policyPath'))]:
  p=Path(value or '');require(p.is_absolute() and p.is_file(),'missing configured file:'+key);files[key]=dict(path=str(p),sha256=sha(p))
 require(files['dll']['sha256']==sec.get('sha256','').lower() and files['policy']['sha256']==sec.get('policySha256','').lower(),'security evidence hash changed')
 require(sys.version_info[:2]==(3,12),'Python 3.12 required by selected environment')
 require(Path(sys.executable).resolve()==Path(v['pythonPath']).resolve(),'selected desktop Python must launch this runner')
 ps=Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe';require(ps.is_file(),'Windows PowerShell missing')
 files['powershell']=dict(path=str(ps),sha256=sha(ps))
 for n in ['verify_hwpx_with_hancom.ps1','Hancom.OwnedExit.ps1','hancom_worker.ps1','Hancom.Environment.ps1','check_native_context.ps1','classify_hancom_failure.py']:
  require((S/n).is_file(),'missing selected candidate script:'+n);files[n]=dict(path=str(S/n),sha256=sha(S/n))
 return dict(config=dict(path=str(config),sha256=sha(config)),files=files,moduleName=sec['moduleName']),ps
def run(source,mode,output,pdf,run_dir,context,timeout=120,preflight_only=False):
 require(context in ['ordinary-shell','host-approved'],'explicit host/user execution context required')
 require(mode in ['OpenOnly','SaveAs'] and type(timeout) is int and 10<=timeout<=300,'invalid native mode/timeout')
 source=Path(source).resolve(strict=True);r=Path(run_dir).absolute()
 require(source.suffix.lower()=='.hwpx' and source.is_file(),'existing HWPX required');require(not r.exists() and r.parent.is_dir(),'new run in existing folder required')
 dst=Path(output).absolute() if output else None;pdf_path=Path(pdf).absolute() if pdf else None
 require((mode=='SaveAs')==bool(dst),'SaveAs output required; OpenOnly output forbidden')
 paths=[source,r]
 for p,ext in [(dst,'.hwpx'),(pdf_path,'.pdf')]:
  if p:require(p.suffix.lower()==ext and not p.exists() and p.parent.is_dir(),'new artifact in existing parent required');paths.append(p.resolve())
 require(len(set(paths))==len(paths),'paths must be distinct')
 meta,ps=dependencies();env=environment_map(os.environ);r.mkdir();before=sha(source)
 write(r/'request.json',dict(source=str(source),sourceSha256=before,mode=mode,output=str(dst) if dst else None,pdf=str(pdf_path) if pdf_path else None,requestedContext=context,contextIsHostChoiceNotSandboxDetection=True,dependencies=meta))
 argv=[str(ps),'-NoProfile','-STA','-File',str(S/'check_native_context.ps1'),'-OutputPath',str(r/'context.json')]
 p=subprocess.run(argv,env=env,capture_output=True,text=True,encoding='utf-8-sig',errors='replace',timeout=30)
 write(r/'preflight-command.json',dict(argv=argv,exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 if p.returncode!=0:
  result=dict(status='BLOCKED_PREFLIGHT',comCreated='NOT_CALLED',securityModuleRegistered='NOT_CALLED',context=read(r/'context.json') if (r/'context.json').exists() else None)
 elif preflight_only:result=dict(status='PASS_PREFLIGHT_NATIVE_NOT_CALLED',comCreated='NOT_CALLED',securityModuleRegistered='NOT_CALLED')
 else:
  argv=[str(ps),'-NoProfile','-File',str(S/'verify_hwpx_with_hancom.ps1'),'-CandidatePath',str(source),'-Mode',mode,'-RunDirectory',str(r/'native'),'-TimeoutSeconds',str(timeout)]
  if dst:argv+=['-OutputPath',str(dst)]
  if pdf_path:argv+=['-PdfPath',str(pdf_path)]
  try:
   p=subprocess.run(argv,env=env,capture_output=True,text=True,encoding='utf-8-sig',errors='replace',timeout=timeout+30)
   command=dict(argv=argv,exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr);write(r/'controller-command.json',command)
   receipt=read(r/'native/receipt.json') if (r/'native/receipt.json').exists() else command
   result=dict(status='PASS_NATIVE' if p.returncode==0 and receipt.get('status')=='PASS_FULL' else 'BLOCKED_NATIVE',classification=classify(receipt),comCreated=receipt.get('comCreated','NOT_RECORDED'),securityModuleRegistered=receipt.get('securityModuleRegistered','NOT_RECORDED'),receiptPath=str(r/'native/receipt.json'))
  except subprocess.TimeoutExpired as e:result=dict(status='BLOCKED_CONTROLLER_TIMEOUT',comCreated='NOT_RECORDED',securityModuleRegistered='NOT_RECORDED',error='Owned controller timeout; preserve artifacts, inspect remaining process, do not auto-retry or kill Hwp.')
 result.update(sourceUnchanged=sha(source)==before,settingsChanged=False,automaticRetry=False,fullDocumentAcceptance='NOT_CHECKED')
 if not result['sourceUnchanged']:result['status']='FAIL_SOURCE_CHANGED'
 write(r/'runner-result.json',result);return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--mode',choices=['OpenOnly','SaveAs'],default='OpenOnly');p.add_argument('--output');p.add_argument('--pdf');p.add_argument('--run',required=True);p.add_argument('--context',choices=['ordinary-shell','host-approved'],required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('--preflight-only',action='store_true');v=p.parse_args()
 try:result=run(v.source,v.mode,v.output,v.pdf,v.run,v.context,v.timeout,v.preflight_only)
 except (ValueError,OSError,KeyError,subprocess.TimeoutExpired) as e:result=dict(status='BLOCKED_LAUNCHER',error=str(e),comCreated='NOT_CALLED_OR_NOT_RECORDED',settingsChanged=False)
 print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['status'].startswith('PASS') else 3)
