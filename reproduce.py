"""Rebuild the frozen experiment results from compact, byte-verified inputs. No traffic by default."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify():
    manifest=read(ROOT/'MANIFEST.json')
    for name,digest in manifest['files_sha256'].items():
        rel=PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:raise ValueError('Unsafe manifest path')
        if sha(ROOT/name)!=digest:raise ValueError('Repository file differs: '+name)
    print('Verified',len(manifest['files_sha256']),'repository files.',flush=True)
def materialize(output):
    meta=read(ROOT/'data/manifest.json');bundle=ROOT/'data/inputs.zip'
    if sha(bundle)!=meta['archive_sha256']:raise ValueError('Input archive digest differs')
    for name,digest in meta['frozen_source_files'].items():
        if PurePosixPath(name).name!=name or '\\' in name or ':' in name:raise ValueError('Unsafe source path')
        if sha(ROOT/'experiment'/name)!=digest:raise ValueError('Frozen experiment file differs: '+name)
    output.mkdir(parents=True,exist_ok=False)
    lab=output/'inputs/lab';pub=output/'inputs/publication'
    for dest in [lab,pub]:
        dest.mkdir(parents=True)
        for p in (ROOT/'experiment').iterdir():
            if p.is_file():shutil.copy2(p,dest/p.name)
    with zipfile.ZipFile(bundle) as z:
        index=json.loads(z.read('index.json'));assert len(index['files'])==meta['logical_files']
        for name,digest in index['files'].items():
            rel=PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts or len(rel.parts)<2 or rel.parts[0] not in ['lab','publication'] or '\\' in name or ':' in name:raise ValueError('Unsafe input path')
            dest=output/'inputs'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            data=z.read('objects/'+digest)
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Input object digest differs')
            if dest.exists() and dest.read_bytes()!=data:raise ValueError('Frozen source differs')
            dest.write_bytes(data)
    return lab,pub
def run(output,lab,pub,figures=False,refit=False):
    output=Path(output).resolve();lab=Path(lab).resolve();pub=Path(pub).resolve()
    output.mkdir(parents=True,exist_ok=True);analysis=ROOT/'analysis';env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    def logged(name,command):
        print('Rebuilding:',name,flush=True)
        with (output/(name+'.log')).open('w',encoding='utf-8') as f:
            subprocess.run([sys.executable,*map(str,command)],check=True,env=env,stdout=f,stderr=subprocess.STDOUT)
    def script(name,args):return [analysis/name,*args]
    logged('calibration',script('calibration_controls.py',['--repo',lab,'--output',output/'calibration']))
    logged('event-targets',[lab/'audit_event_targets.py','--repo',lab,'--output',output/'event-targets'])
    logged('development',[lab/'fixed_trace_dataset.py','--repo',lab,'--selection',lab/'results/runs/20261115-194521-170669-fixed-development-batch/selection.json','--protocol',lab/'dataset_protocol.json','--output',output/'development'])
    counts=read(output/'development/summary.json');assert [counts[k] for k in ['total_eligible','total_positive','total_observed_events']]==[1594,559,79]
    logged('model-review',[lab/'review_tree.py','--dataset',output/'development','--model',lab/'selected_tree.json','--output',output/'model-review'])
    actual=read(output/'model-review/review.json');expected=read(pub/'results/model-development-v1/training_report.json')
    assert actual['dataset_fingerprint']==expected['dataset_fingerprint'] and actual['metrics']==expected['metrics']
    logged('matched',script('analyze_matched.py',['--repo',lab,'--output',output/'matched']))
    assert read(output/'matched/matched-report.json')==read(pub/'results/matched-v1/matched-report.json')
    logged('paired-results',script('summarize_matched.py',['--repo',lab,'--networking',output/'matched','--output',output/'paired']))
    actual=read(output/'paired/analysis-details.json');expected=read(pub/'results/matched-v1/analysis-details.json')
    assert {k:v for k,v in actual.items() if k!='raw_archive'}=={k:v for k,v in expected.items() if k!='raw_archive'}
    logged('rtt',script('latency_supplement.py',['--repo',lab,'--networking',output/'matched','--output',output/'rtt']))
    assert read(output/'rtt/latency-supplement.json')==read(pub/'results/matched-v1/latency-supplement.json')
    batch=lab/'results/runs'/Path((lab/'results/runs/active-heldout-batch.txt').read_text().strip()).name
    logged('heldout',[lab/'heldout_dataset.py','--repo',lab,'--batch',batch,'--output',output/'heldout'])
    assert read(output/'heldout/test_report.json')==read(pub/'results/matched-v1/prediction-reference.json')
    logged('supplement-cases',script('replay_cases.py',['--repo',lab,'--published',pub,'--output',output/'supplement']))
    for stage in ['components','activation','followup']:
        logged(stage,script('replay_audit.py',[stage,'--repo',lab,'--published',pub,'--output',output/stage]))
    logged('paper-tables',script('consolidate_paper_evidence.py',['--repo',lab,'--published',pub,'--output',output/'tables']))
    actual=read(output/'tables/paper-evidence.json');expected=read(ROOT/'results/tables/paper-evidence.json')
    # Relative path separators are platform-specific; all scientific outputs must match.
    actual['inputs_sha256']={k.replace('\\','/'):v for k,v in actual['inputs_sha256'].items()}
    expected['inputs_sha256']={k.replace('\\','/'):v for k,v in expected['inputs_sha256'].items()}
    assert actual==expected,'Consolidated evidence differs'
    if figures:
        logged('paper-figures',script('plot_paper_evidence.py',['--repo',lab,'--analysis',output/'tables','--output',output/'figures']))
        logged('time-traces',script('build_time_traces.py',['--repo',lab,'--report',output/'matched/matched-report.json','--output',output/'time-traces','--plots']))
    paper_args=['--repo',ROOT,'--lab',lab,'--evidence',output/'tables/paper-evidence.json','--output',output/'paper']
    if figures:paper_args+=['--figures','--v1-figures',output/'figures']
    logged('final-paper-assets',script('build_paper_assets.py',paper_args))
    from importlib.util import spec_from_file_location,module_from_spec
    spec=spec_from_file_location('paper_assets',analysis/'build_paper_assets.py');paper=module_from_spec(spec);spec.loader.exec_module(paper)
    paper.compare_tables(read(output/'paper/table-data.json'),read(ROOT/'results/paper/table-data.json'))
    import csv
    for name in ['paired-differences.csv','captured-source.csv','captured-queues.csv','forwarding-timing.csv','topology.csv']:
        with (output/'paper/plot-data'/name).open(newline='') as a,(ROOT/'results/paper/plot-data'/name).open(newline='') as b:
            assert list(csv.DictReader(a))==list(csv.DictReader(b)),'Paper plot values differ: '+name
    if refit:
        logged('training-replay',[lab/'train_tree.py','--dataset',output/'development','--repo',lab,'--output',output/'training'])
        assert read(output/'training/model.json')==read(lab/'selected_tree.json')
    receipt=dict(original_matched_trials=36,development_runs=16,heldout_runs=6,
       primary_and_alternate_calibration_reproduced=True,supplemental_controls_and_failed_outcomes_reproduced=True,
       component_diagnostics_reproduced=4,activation_steps_reproduced=3,followup_attempts_reproduced=7,
       heldout_predictions_exact=True,matched_report_exact=True,consolidated_evidence_exact=True,
       raw_quality_rules_changed=False,traffic_started=False,model_refitted=refit,
       source_checkpoint_comparisons='Historical receipts retained; obsolete full-backup comparisons are not rerun.',figures_regenerated=figures,
       final_paper_tables_exact=True,final_paper_plot_values_exact=True,v2_summary_arithmetic_reproduced=True,v2_raw_logs_available=False)
    (output/'reproduction.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--figures',action='store_true');p.add_argument('--refit',action='store_true');p.add_argument('--verify',action='store_true',help='Verify repository bytes without rebuilding')
    # Developer-only readset collection is intentionally absent from the public interface.
    a=p.parse_args();verify()
    if not a.output:
        if not a.verify:p.error('--output is required for a rebuild')
        sys.exit(0)
    lab,pub=materialize(a.output);run(a.output,lab,pub,a.figures,a.refit)
