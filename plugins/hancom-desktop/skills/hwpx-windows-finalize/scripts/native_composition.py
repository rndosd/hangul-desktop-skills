"""A bounded plan for appending already prepared HWPX blocks via InsertFile."""
import hashlib
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

SCHEMA = 'hwpx.native-compose.v1'

def require(value, message):
    if not value: raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def page_profile(data):
    # Read only the prepared block's page geometry; never rewrite source XML.
    with ZipFile(BytesIO(data)) as package:
        sections=[n for n in package.namelist() if n.startswith('Contents/section') and n.endswith('.xml')]
        require(len(sections)==1, 'compose supports prepared single-section blocks')
        root=ElementTree.fromstring(package.read(sections[0]))
    pages=root.findall('.//{http://www.hancom.co.kr/hwpml/2011/paragraph}pagePr')
    require(len(pages)==1, 'one explicit page geometry required in prepared block')
    return tuple((element.tag,tuple(sorted(element.attrib.items()))) for element in pages[0].iter())

def validate(plan, source=None):
    require(isinstance(plan, dict) and set(plan) == {'schema', 'base', 'blocks'}, 'compose requires schema, base and blocks')
    require(plan['schema'] == SCHEMA, 'unsupported composition schema')
    require(isinstance(plan['blocks'], list) and 1 <= len(plan['blocks']) <= 20, 'compose requires 1..20 appended blocks')
    profiles={}
    def ref(value, block=False):
        keys={'path','sha256','join'} if block else {'path','sha256'}
        require(isinstance(value,dict) and set(value)==keys, 'explicit path/hash and block join required')
        require(isinstance(value['path'],str) and Path(value['path']).is_absolute(), 'absolute input path required')
        path=Path(value['path']).resolve(strict=True)
        require(path.is_file() and path.suffix.lower()=='.hwpx', 'existing HWPX block required')
        expected=value['sha256']
        require(isinstance(expected,str) and len(expected)==64 and all(x in '0123456789abcdefABCDEF' for x in expected), 'sha256 must contain 64 hex characters')
        data=path.read_bytes()
        require(hashlib.sha256(data).hexdigest()==expected.lower(), 'composition input changed: '+str(path))
        profiles[str(path)]=page_profile(data)
        result=dict(path=str(path),sha256=expected.lower())
        if block:
            require(value['join'] in ('none','paragraph','page','section'), 'join must be none, paragraph, page or section')
            result['join']=value['join']
        return result
    result=dict(schema=SCHEMA,base=ref(plan['base']),blocks=[ref(x,True) for x in plan['blocks']])
    if source is not None:require(Path(source).resolve()==Path(result['base']['path']), 'composition base must match source')
    current=profiles[result['base']['path']]
    for block in result['blocks']:
        if block['join']=='section':
            require(profiles[block['path']]==current, 'SECTION_LAYOUT_UNSUPPORTED: InsertFile cannot guarantee changed paper/margins; prepare a common layout or use the explicit native page-layout workflow')
    return result

def inputs(plan):
    return {p['path']:p['sha256'] for p in [plan['base'],*plan['blocks']]}

def check_inputs(plan):
    result=[]
    for path,expected in inputs(plan).items():
        try: actual=sha(path);error=None
        except OSError as exc: actual=None;error=str(exc)
        result.append(dict(path=path,expected=expected,actual=actual,unchanged=actual==expected,error=error))
    return result
