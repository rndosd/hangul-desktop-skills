"""Select the explicitly bundled candidate dependency before importing hwpx.

No runtime installation, monkey patch or global sys.path/environment change.
"""
from pathlib import Path
import sys
def activate():
 root=Path(__file__).resolve().parents[1]/'vendor'
 if 'hwpx' in sys.modules:
  actual=Path(sys.modules['hwpx'].__file__).resolve()
  if not actual.is_relative_to(root):raise RuntimeError('candidate runtime must be selected before importing hwpx')
 if not (root/'hwpx/opc/xml_utils.py').is_file():raise RuntimeError('candidate dependency missing')
 sys.path.insert(0,str(root))
 import hwpx
 if not Path(hwpx.__file__).resolve().is_relative_to(root):raise RuntimeError('wrong hwpx dependency selected')
 return Path(hwpx.__file__).resolve()

if __name__=='__main__':
 import runpy,json,hashlib
 actual=activate()
 if len(sys.argv)==1:
  parser=actual.parent/'opc/xml_utils.py';print(json.dumps(dict(module=str(actual),parser=str(parser),sha256=hashlib.sha256(parser.read_bytes()).hexdigest())))
 else:
  script=Path(sys.argv[1]).resolve(strict=True);sys.argv=sys.argv[1:];sys.path.insert(0,str(script.parent));runpy.run_path(str(script),run_name='__main__')
