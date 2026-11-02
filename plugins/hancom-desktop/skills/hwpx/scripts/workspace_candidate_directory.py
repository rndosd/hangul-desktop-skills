"""Inherit an authorized parent ACL; clean up only the one owned candidate."""
from contextlib import contextmanager
from pathlib import Path
import os
import uuid

# Windows without long paths stops at 259 characters. A folder must leave room for the files
# written inside, the longest being a writer's temporary 'tmpXXXXXXXX.hwpx.tmp'; a nested
# candidate folder is checked in turn.
FOLDER_LIMIT=259-len('\\tmpXXXXXXXX.hwpx.tmp')

def long_paths_enabled():
    if os.name!='nt':return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            return winreg.QueryValueEx(key,'LongPathsEnabled')[0]==1
    except OSError:
        return False

@contextmanager
def workspace_candidate_directory(*, prefix, dir):
    parent=Path(dir).resolve(strict=True)
    if not parent.is_dir():raise ValueError('existing output directory required')
    if not isinstance(prefix,str) or not prefix or any(c in prefix for c in '/\\:'):
        raise ValueError('simple prefix required')
    for _ in range(8):
        folder=parent/('.'+prefix+uuid.uuid4().hex[:8])  # short: nested folders add up
        if len(str(folder))>FOLDER_LIMIT and not long_paths_enabled():
            raise ValueError(f'PATH_TOO_LONG: 작업 폴더 경로가 {len(str(folder))}자라 Windows 경로 한도(260자)를 넘습니다. '
                             '경로가 짧은 폴더에 출력하세요.')
        try:folder.mkdir();break
        except FileExistsError:continue
    else:raise FileExistsError('no free candidate folder name')
    candidate=folder/'candidate.hwpx'
    try:yield str(folder)
    finally:
        # No chmod, ACL change, broad enumeration or recursive deletion.
        candidate.unlink(missing_ok=True)
        folder.rmdir()
