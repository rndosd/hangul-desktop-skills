"""Install only into a newly created test CODEX_HOME; never register a module/COM.

Keep local receipts in ignored .verification for review. No downloads or DLL loads.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, uuid

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=ROOT/'plugins/hancom-desktop'

def run(script,args,success=True):
    cmd=['powershell.exe','-NoProfile','-File',str(script),*map(str,args)]
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8-sig',errors='replace',timeout=90)
    if (p.returncode==0) != success:
        raise RuntimeError(json.dumps({'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},ensure_ascii=False))
    return p

def json_prefix(text):
    decoder=json.JSONDecoder();return decoder.raw_decode(text.lstrip('\ufeff\r\n '))[0]

if __name__=='__main__':
    if os.name!='nt':raise SystemExit('Windows required; not run.')
    workspace=ROOT/'.verification'/('install-'+uuid.uuid4().hex);workspace.mkdir(parents=True)
    home=workspace/'한글 test home'
    installer=ROOT/'Install.ps1'
    args=['-CodexRoot',home,'-PythonPath',sys.executable]
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in PLUGIN.rglob('*') if p.is_file()}
    # CheckOnly must not bootstrap or create even the requested CODEX_HOME.
    p=run(installer,[*args,'-CheckOnly'])
    initial=json_prefix(p.stdout)
    assert not home.exists() and initial['security']['reviewConfirmed'] is False
    assert initial['registryChanges']==[] and initial['coreStatus']=='ready'
    p=run(PLUGIN/'Setup-OfficialModule.ps1',['-CodexRoot',home],False)
    assert 'AcceptGlobalFileAccess' in p.stderr and not home.exists()
    p=run(installer,[*args,'-NoDependencyInstall'])
    first=json_prefix(p.stdout)
    a=home/'skills/hwpx/environment.json';b=home/'skills/hwpx-windows-finalize/environment.json'
    config=json.loads(a.read_text(encoding='utf-8-sig'))
    assert config==json.loads(b.read_text(encoding='utf-8-sig'))
    assert config['codexRoot']==str(home) and config['security']['reviewConfirmed'] is False
    assert config['nativeStatus']=='blocked_security_module' and config['registryChanges']==[]
    marker=home/'skills/hwpx/keep-old.txt';marker.write_text('preserve backup')
    p=run(installer,[*args,'-NoDependencyInstall'])
    second=json_prefix(p.stdout)
    backup=Path(second['backupRoot'])/'hwpx/keep-old.txt'
    assert backup.read_text()=='preserve backup' and not marker.exists()
    # Invoke the plugin-cache launcher using the current test desktop config.
    env=dict(os.environ,CODEX_HOME=str(home))
    p=subprocess.run(['powershell.exe','-NoProfile','-File',str(PLUGIN/'skills/hwpx/scripts/Invoke-HangulTask.ps1'),'doctor'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8-sig',errors='replace',timeout=45)
    assert p.returncode==0,(p.stdout,p.stderr)
    doctor=json_prefix(p.stdout)
    assert doctor['configurationExists'] and doctor['securityModule']=='NOT_CHECKED'
    assert Path(doctor['configuration'])==a and Path(doctor['hwpxModule']).is_relative_to(PLUGIN/'skills/hwpx/vendor')
    # Transfer corruption must fail before installing into another home.
    damaged=workspace/'damaged-package';shutil.copytree(PLUGIN,damaged)
    (damaged/'requirements-core.txt').write_text('tampered')
    untouched=workspace/'must-not-create'
    p=run(damaged/'Install-HangulSkills.ps1',['-CodexRoot',untouched,'-CheckOnly'],False)
    assert 'Package hash mismatch' in p.stderr and not untouched.exists()
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in PLUGIN.rglob('*') if p.is_file()}
    result={'status':'PASS_ISOLATED_INSTALL','checks':['read-only no creation','no-consent stops before change','local configuration pair','unconfigured native remains blocked','reinstall backup','plugin cache uses current PC','corrupt transfer blocked','source package unchanged'],
            'python':sys.version.split()[0],'comCreated':'NOT_CALLED','securityModuleRegistered':'NOT_CALLED',
            'registryChanged':False,'networkUsed':False,'evidence':str(workspace)}
    (workspace/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
