"""Add supplemental modules without rewriting any original experiment source."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,sys

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def install(target):
    source=Path(__file__).resolve().parent;target=Path(target).resolve(strict=True)
    m=json.loads((source/'manifest.json').read_text())
    for name,digest in dict(m['unchanged_files'],**m['unchanged_testbed']).items():
        p=target/name
        if p.is_symlink() or sha(p)!=digest:raise ValueError('Frozen file differs; nothing installed: '+name)
    for name,digest in m['files'].items():
        if Path(name).name!=name:raise ValueError('Invalid payload name')
        payload=source/'payload'/name;p=target/name
        if payload.is_symlink() or sha(payload)!=digest:raise ValueError('Payload mismatch: '+name)
        if name.endswith('.py'):compile(payload.read_text(encoding='utf-8'),name,'exec')
        if p.is_symlink() or (p.exists() and (not p.is_file() or sha(p)!=digest)):
            raise ValueError('Existing supplemental file differs: '+name)
    installed=[]
    try:
        for name in m['files']:
            p=target/name
            if not p.exists():
                p.write_bytes((source/'payload'/name).read_bytes());installed.append(p)
                if hasattr(os,'chown'):os.chown(p,target.stat().st_uid,target.stat().st_gid)
        subprocess.run([sys.executable,'-m','unittest','-v',*m['test_modules']],cwd=target,check=True)
    except BaseException:
        for p in installed:p.unlink()
        raise
    receipt=target/'results/derived'/('supplement-install-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.json')
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(dict(manifest=m,tests='passed',original_files_rewritten=0),indent=2)+'\n')
    print('Supplement installed:',len(m['files']),'additive files. Original 61 files retained byte-for-byte.')
    print('Ready for first fixed-alternate ramp control, seed 41. No traffic started.')

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: install_supplement.py REPO')
    install(sys.argv[1])
