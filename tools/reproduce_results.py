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

def run(output,checkpoint,figures=False,refit=False,plot_python=None,training_python=None):
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
    def logged(command,name):
        with (output/(name+'.log')).open('w',encoding='utf-8') as f:
            subprocess.run(command,check=True,stdout=f,stderr=subprocess.STDOUT)
    logged([sys.executable,str(ROOT/'tools/p01_accounting.py'),'--repo',str(repo),'--output',str(output/'p01-accounting.json')],'p01-accounting')
    logged([sys.executable,str(ROOT/'tools/calibration_controls.py'),'--repo',str(repo),'--output',str(output/'calibration')],'calibration')
    logged([sys.executable,str(repo/'audit_event_targets.py'),'--repo',str(repo),'--output',str(output/'target-audit')],'target-audit')
    development_batch=repo/'results/runs/20261115-194521-170669-fixed-development-batch'
    logged([sys.executable,str(repo/'fixed_trace_dataset.py'),'--repo',str(repo),'--selection',str(development_batch/'selection.json'),
        '--protocol',str(repo/'dataset_protocol.json'),'--output',str(output/'development')],'development')
    development=json.loads((output/'development/summary.json').read_text())
    if [development[k] for k in ['total_eligible','total_positive','total_observed_events']]!=[1594,559,79]:
        raise ValueError('Development counts differ')
    logged([sys.executable,str(repo/'review_tree.py'),'--dataset',str(output/'development'),'--model',str(ROOT/'selected_tree.json'),
        '--output',str(output/'development-review')],'development-review')
    review=json.loads((output/'development-review/review.json').read_text())
    training=json.loads((ROOT/'results/model-development-v1/training_report.json').read_text())
    if review['dataset_fingerprint']!=training['dataset_fingerprint'] or review['metrics']!=training['metrics']:
        raise ValueError('Frozen development review differs')
    subprocess.run([sys.executable,str(ROOT/'tools/analyze_matched.py'),'--repo',str(repo),'--output',str(output/'networking')],check=True)
    actual=json.loads((output/'networking/matched-report.json').read_text())
    expected=json.loads((ROOT/'results/matched-v1/matched-report.json').read_text())
    if actual!=expected:raise ValueError('Reproduced networking report differs')
    logged([sys.executable,str(ROOT/'tools/summarize_matched.py'),'--repo',str(repo),'--networking',str(output/'networking'),
        '--output',str(output/'analysis')],'analysis')
    details=json.loads((output/'analysis/analysis-details.json').read_text())
    expected_details=json.loads((ROOT/'results/matched-v1/analysis-details.json').read_text())
    if {k:v for k,v in details.items() if k!='raw_archive'}!={k:v for k,v in expected_details.items() if k!='raw_archive'}:
        raise ValueError('Paired/quality analysis differs')
    logged([sys.executable,str(ROOT/'tools/additional_metrics.py'),'--report',str(output/'networking/matched-report.json'),
        '--output',str(output/'analysis/ADDITIONAL_METRICS.md')],'additional-metrics')
    for name in ['INTERPRETATION.md','ADDITIONAL_METRICS.md']:
        if (output/'analysis'/name).read_text(encoding='utf-8')!=(ROOT/'results/matched-v1'/name).read_text(encoding='utf-8'):
            raise ValueError('Rebuilt summary differs: '+name)
    pointer=repo/'results/runs/active-heldout-batch.txt'
    batch=repo/'results/runs'/Path(pointer.read_text().strip()).name
    log=output/'heldout-reproduction.log'
    with log.open('w',encoding='utf-8') as f:
        subprocess.run([sys.executable,str(repo/'heldout_dataset.py'),'--repo',str(repo),'--batch',str(batch),'--output',str(output/'prediction')],check=True,stdout=f)
    actual_prediction=json.loads((output/'prediction/test_report.json').read_text())
    expected_prediction=json.loads((ROOT/'results/matched-v1/prediction-reference.json').read_text())
    if actual_prediction!=expected_prediction:raise ValueError('Reproduced prediction report differs')
    logged([sys.executable,str(ROOT/'tools/latency_supplement.py'),'--repo',str(repo),'--networking',str(output/'networking'),
        '--output',str(output/'latency')],'latency')
    if json.loads((output/'latency/latency-supplement.json').read_text())!=json.loads((ROOT/'results/matched-v1/latency-supplement.json').read_text()):
        raise ValueError('Received-reply latency supplement differs')
    if figures:
        logged([str(plot_python or sys.executable),str(ROOT/'tools/plot_matched.py'),'--report',str(output/'networking/matched-report.json'),
            '--output',str(output/'plots')],'plots')
        manifest=json.loads((output/'plots/figures/manifest.json').read_text())
        if len(manifest['figures'])!=8 or any((output/'plots'/p).stat().st_size<1000 for p in manifest['figures']):
            raise ValueError('Figure set incomplete')
    if refit:
        logged([str(training_python or sys.executable),str(repo/'train_tree.py'),'--dataset',str(output/'development'),
            '--repo',str(repo),'--output',str(output/'training-replay')],'training-replay')
        if json.loads((output/'training-replay/model.json').read_text())!=json.loads((ROOT/'selected_tree.json').read_text()):
            raise ValueError('Training replay does not reproduce the frozen tree')
    receipt=dict(checkpoint_sha256=EXPECTED,raw_files=files,matched_trials=36,heldout_trials=6,
        networking_report_exact_match=True,prediction_report_exact_match=True,
        development_traces=16,development_rows=1594,development_review_exact_match=True,
        calibration_controls=12,event_target_audit_rebuilt=True,latency_trials_exact_match=36,
        paired_quality_and_additional_tables_match=True,
        figures_regenerated=8 if figures else 0,training_replay_model_equal=bool(refit),
        published_source_pins_match=True,traffic_started=False,forwarding_changed=False,model_fitted=bool(refit),
        frozen_model_overwritten=False)
    (output/'reproduction.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,default=ROOT/'evidence/raw/342-sdn-checkpoint-20261116-214839.tar.gz')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--figures',action='store_true',help='Regenerate four PNG/SVG figure sets with optional plot dependencies')
    p.add_argument('--refit',action='store_true',help='Replay original train/validation search into a separate output; never changes frozen model')
    p.add_argument('--plot-python',type=Path,help='Optional interpreter with requirements-analysis.txt')
    p.add_argument('--training-python',type=Path,help='Optional interpreter with requirements-ml.txt')
    a=p.parse_args();run(a.output,a.checkpoint,a.figures,a.refit,a.plot_python,a.training_python)
