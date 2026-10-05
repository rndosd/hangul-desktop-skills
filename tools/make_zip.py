"""Build from reviewed Git files, excluding local evidence and machine settings."""
from pathlib import Path
import hashlib, subprocess, sys, zipfile

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    subprocess.run([sys.executable,'-B',str(ROOT/'tools/verify_release.py')],cwd=ROOT,check=True)
    tracked=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8').split('\0')
    target=ROOT/'dist/hangul-desktop-skills-0.1.0-beta.1.zip';target.parent.mkdir(exist_ok=True)
    if target.exists():raise FileExistsError('Review existing archive; no overwrite')
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for relative in sorted(filter(None,tracked)):
            p=ROOT/relative
            if not p.is_file():raise FileNotFoundError(relative)
            z.write(p,'hangul-desktop-skills/'+relative)
    print(str(target));print('SHA256 '+hashlib.sha256(target.read_bytes()).hexdigest())
