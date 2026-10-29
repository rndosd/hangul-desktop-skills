"""Select the explicitly bundled candidate dependency before importing hwpx.

No runtime installation, monkey patch or global sys.path/environment change.
"""
from pathlib import Path
import sys
def activate():
 root=Path(__file__).resolve().parents[1]/'vendor'
 for name in ('hwpx', 'hwpx_automation'):
  if name in sys.modules:
   actual=Path(sys.modules[name].__file__).resolve()
   if not actual.is_relative_to(root):raise RuntimeError('shared runtime must be selected before importing '+name)
 if not (root/'hwpx/opc/xml_utils.py').is_file():raise RuntimeError('candidate dependency missing')
 if not (root/'hwpx_automation/office/agent/commands.py').is_file():raise RuntimeError('shared automation dependency missing')
 if str(root) not in sys.path:sys.path.insert(0,str(root))
 import hwpx
 if not Path(hwpx.__file__).resolve().is_relative_to(root):raise RuntimeError('wrong hwpx dependency selected')
 return Path(hwpx.__file__).resolve()

def identity():
 import hashlib
 actual=activate()
 import hwpx_automation
 engine=Path(hwpx_automation.__file__).resolve()
 root=actual.parent.parent
 if not engine.is_relative_to(root):raise RuntimeError('wrong shared automation dependency selected')
 files={'parser':actual.parent/'opc/xml_utils.py','run':actual.parent/'oxml/run.py','commands':engine.parent/'office/agent/commands.py'}
 return {'python':sys.executable,'core':str(actual),'automation':str(engine),'sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in files.items()}}

if __name__=='__main__':
 import runpy,json,hashlib
 actual=activate()
 if len(sys.argv)==1:
  parser=actual.parent/'opc/xml_utils.py';print(json.dumps(dict(module=str(actual),parser=str(parser),sha256=hashlib.sha256(parser.read_bytes()).hexdigest())))
 else:
  script=Path(sys.argv[1]).resolve(strict=True);sys.argv=sys.argv[1:];sys.path.insert(0,str(script.parent));runpy.run_path(str(script),run_name='__main__')
