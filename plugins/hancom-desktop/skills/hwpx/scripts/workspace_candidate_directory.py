"""Inherit an authorized parent ACL; clean up only the one owned candidate."""
from contextlib import contextmanager
from pathlib import Path
import uuid

@contextmanager
def workspace_candidate_directory(*, prefix, dir):
    parent=Path(dir).resolve(strict=True)
    if not parent.is_dir():raise ValueError('existing output directory required')
    if not isinstance(prefix,str) or not prefix or any(c in prefix for c in '/\\:'):
        raise ValueError('simple prefix required')
    folder=parent/('.'+prefix+uuid.uuid4().hex)
    folder.mkdir()
    candidate=folder/'candidate.hwpx'
    try:yield str(folder)
    finally:
        # No chmod, ACL change, broad enumeration or recursive deletion.
        candidate.unlink(missing_ok=True)
        folder.rmdir()
