"""Reproduce saved results without traffic, forwarding changes or model fitting."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import subprocess
import sys
import tarfile

EXPECTED='e8f2e4e4294d35918c8b0d2e37fa79e92366732a19b0a12daad6f7c2a521b8e3'
ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run(output,checkpoint):
    output=Path(output).resolve();checkpoint=Path(checkpoint).resolve()
    if sha(checkpoint)!=EXPECTED:raise ValueError('Checkpoint digest differs')
    output.mkdir(parents=True,exist_ok=False)
    raw=output/'checkpoint';raw.mkdir();seen=set();files=0
    with tarfile.open(checkpoint,'r:gz') as archive:
        for member in archive:
            p=PurePosixPath(member.name)
            if (p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='342-proactive-sdn'
                or '\\' in member.name or ':' in member.name or not(member.isfile() or member.isdir()) or p in seen):
                raise ValueError('Unsupported or unsafe archive entry')
            seen.add(p);target=raw.joinpath(*p.parts)
            if not target.resolve().is_relative_to(raw.resolve()):raise ValueError('Archive path escapes destination')
            if member.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
                if target.stat().st_size!=member.size:raise ValueError('Extracted size differs')
                files+=1
    if files!=9818:raise ValueError('Checkpoint file count differs')
    repo=raw/'342-proactive-sdn'
    protocol=json.loads((repo/'matched_protocol.json').read_text())
    for name,digest in protocol['source_sha256'].items():
        if sha(repo/name)!=digest or sha(ROOT/name)!=digest:raise ValueError('Published or checkpoint source pin differs: '+name)
    subprocess.run([sys.executable,str(ROOT/'tools/analyze_matched.py'),'--repo',str(repo),'--output',str(output/'networking')],check=True)
    actual=json.loads((output/'networking/matched-report.json').read_text())
    expected=json.loads((ROOT/'results/matched-v1/matched-report.json').read_text())
    if actual!=expected:raise ValueError('Reproduced networking report differs')
    pointer=repo/'results/runs/active-heldout-batch.txt'
    batch=repo/'results/runs'/Path(pointer.read_text().strip()).name
    log=output/'heldout-reproduction.log'
    with log.open('w',encoding='utf-8') as f:
        subprocess.run([sys.executable,str(repo/'heldout_dataset.py'),'--repo',str(repo),'--batch',str(batch),'--output',str(output/'prediction')],check=True,stdout=f)
    actual_prediction=json.loads((output/'prediction/test_report.json').read_text())
    expected_prediction=json.loads((ROOT/'results/matched-v1/prediction-reference.json').read_text())
    if actual_prediction!=expected_prediction:raise ValueError('Reproduced prediction report differs')
    receipt=dict(checkpoint_sha256=EXPECTED,raw_files=files,matched_trials=36,heldout_trials=6,
        networking_report_exact_match=True,prediction_report_exact_match=True,
        published_source_pins_match=True,traffic_started=False,forwarding_changed=False,model_fitted=False)
    (output/'reproduction.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,default=ROOT/'evidence/raw/342-sdn-checkpoint-20261116-214839.tar.gz')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.output,a.checkpoint)
