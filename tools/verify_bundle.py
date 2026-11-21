"""Verify current tracked publication bytes against the recreation manifest."""
import argparse,hashlib,json
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
def verify(root,manifest):
    root=Path(root).resolve();data=json.loads(Path(manifest).read_text(encoding='utf-8'));count=0
    for name,expected in data['files_sha256'].items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:raise ValueError('Unsafe manifest path')
        path=root.joinpath(*relative.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Manifest path escaped repository')
        with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=expected:raise ValueError('Published file differs: '+name)
        count+=1
    print(json.dumps(dict(files_verified=count,raw_and_frozen_hashes_checked=True)))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--manifest',type=Path,default=ROOT/'evidence/paper-evidence-publication-manifest.json')
    a=p.parse_args();verify(a.root,a.manifest)
