"""Read-only public package validation; --write-manifest is an explicit build step."""
from pathlib import Path
import argparse, ast, hashlib, json, re, zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/hancom-desktop'
SKIP = {'.git', '.verification', 'dist', '__pycache__'}
DENY = {'environment.json', 'installed-environment.json', 'reviewed-policy.txt',
        'reviewed-security-policy.txt', 'row-selection-qualification.json'}
PRIVATE_PATH = re.compile(r'[A-Za-z]:[/\\]+Users[/\\]+[^/\\\s]+', re.I)
TOKEN = re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{30,})\b')

def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and not SKIP.intersection(p.relative_to(root).parts)
                  and not any(part.startswith('.test-') for part in p.relative_to(root).parts))

def inventory():
    return {p.relative_to(PLUGIN).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files(PLUGIN) if p.name != 'PAYLOAD-SHA256.json'}

def verify():
    errors=[]
    for p in files(ROOT):
        rel=p.relative_to(ROOT).as_posix()
        if p.name in DENY or p.suffix.lower() in {'.dll', '.exe', '.pyc', '.pem'}:
            errors.append('Excluded private/runtime file: '+rel)
        if p.suffix == '.py':
            try: ast.parse(p.read_text(encoding='utf-8-sig'), filename=rel)
            except SyntaxError as e: errors.append('Python syntax: '+str(e))
        if p.suffix.lower() == '.ps1':
            raw=p.read_bytes()
            if any(byte >= 128 for byte in raw) and not raw.startswith(b'\xef\xbb\xbf'):
                errors.append('Non-ASCII PowerShell requires UTF-8 BOM for Windows PowerShell 5.1: '+rel)
        if p.suffix in {'.md','.py','.ps1','.json','.yaml','.txt'} or p.name in {'UPSTREAM-METADATA','PATCH.md'}:
            text=p.read_text(encoding='utf-8-sig')
            if PRIVATE_PATH.search(text) or TOKEN.search(text): errors.append('Private path/credential pattern: '+rel)
        if p.suffix == '.hwpx':
            with zipfile.ZipFile(p) as z:
                if z.testzip(): errors.append('Corrupt HWPX: '+rel)
                for name in z.namelist():
                    if name.endswith(('.xml','.hpf')):
                        text=z.read(name).decode('utf-8-sig')
                        if PRIVATE_PATH.search(text) or TOKEN.search(text): errors.append('Private HWPX metadata: '+rel+'/'+name)
    for name in ('hwpx','hwpx-windows-finalize','hancom-setup'):
        p=PLUGIN/'skills'/name/'SKILL.md';text=p.read_text(encoding='utf-8-sig')
        if not text.startswith('---\n') or f'name: {name}\n' not in text: errors.append('Invalid skill frontmatter: '+name)
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if '://' not in link and not (p.parent/link.split('#')[0]).is_file(): errors.append('Broken skill link: '+name+': '+link)
    marketplace=json.loads((ROOT/'.agents/plugins/marketplace.json').read_text(encoding='utf-8'))
    entry=marketplace['plugins'][0]
    if (ROOT/entry['source']['path']).resolve() != PLUGIN.resolve(): errors.append('Marketplace source mismatch')
    manifest=json.loads((PLUGIN/'PAYLOAD-SHA256.json').read_text(encoding='utf-8'))
    if manifest != inventory(): errors.append('Payload differs from complete file manifest')
    for p in (ROOT/'LICENSE', ROOT/'NOTICE', PLUGIN/'skills/hwpx/vendor/licenses/LICENSE', PLUGIN/'skills/hwpx/vendor/licenses/NOTICE'):
        if not p.is_file() or p.stat().st_size == 0: errors.append('Missing license/notice: '+str(p.relative_to(ROOT)))
    return {'status':'FAIL' if errors else 'PASS_PACKAGE_READ_ONLY', 'filesChecked':len(files(ROOT)),
            'payloadFiles':len(manifest), 'errors':errors, 'native':'NOT_CALLED', 'registryChanged':False}

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write-manifest',action='store_true');args=parser.parse_args()
    if args.write_manifest:
        (PLUGIN/'PAYLOAD-SHA256.json').write_text(json.dumps(inventory(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result=verify();print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(result['errors']))
