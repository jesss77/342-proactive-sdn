"""Explicit fresh-test gate/evaluation; never fits or changes the frozen tree."""
import argparse
import csv
import json
from pathlib import Path

from build_trace_dataset import FEATURES
from fixed_trace_dataset import load_protocol,load_fixed_trace,read,sha
from source_integrity import AUDIT_POLICY
from train_tree import review,baseline
from tree_metrics import row_report,warning_report
from tree_model import TreeModel,canonical_hash,f32

FROZEN_MODEL_SHA='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595'


def test_plan(protocol):
    return [dict(split='test',scenario=scenario,seed=seed)
      for i,seed in enumerate(protocol['partitions']['test'])
      for scenario in (protocol['scenarios'] if i%2==0 else list(reversed(protocol['scenarios'])))]


def frozen_model(path,protocol):
    if sha(path)!=FROZEN_MODEL_SHA: raise ValueError('Frozen model bytes changed; held-out gate refused')
    model=TreeModel.load(path);m=model.model
    if (m.get('acquisition_protocol_id')!=protocol['id'] or m.get('profile_id')!=protocol['profile_id']
        or m.get('label_config')!=protocol['label_config']
        or m.get('feature_source_sha256')!=protocol['source_sha256']['build_trace_dataset.py']):
        raise ValueError('Frozen model/protocol context differs')
    return model


def guest_reproduction(base,model):
    expected=dict(n=599,tp=170,fp=35,fn=37,tn=357)
    for path in sorted((Path(base)/'results/derived').glob('tree-review-*/review.json'),reverse=True):
        r=read(path)
        if (r.get('dataset_fingerprint')==model.model['dataset_fingerprint']
            and r.get('model_parameters')==model.model['parameters'] and r.get('alarm_threshold')==model.threshold):
            counts=r.get('metrics',{}).get('validation',{}).get('rows',{}).get('pooled',{})
            if all(counts.get(k)==v for k,v in expected.items()):
                return dict(path=str(path.relative_to(base)),sha256=sha(path))
    raise ValueError('Matching guest frozen-model development reproduction is required before fresh test acquisition')


def validate_test_selection(selection,protocol):
    if selection.get('role')!='heldout_test' or selection.get('model_sha256')!=FROZEN_MODEL_SHA or selection.get('protocol_id')!=protocol['id']:
        raise ValueError('Invalid frozen-test selection header')
    plan=test_plan(protocol);runs=selection['runs'];identities=[];folders=set()
    for r in runs:
        identity={k:r[k] for k in ['split','scenario','seed']}
        if identity not in plan or identity in identities: raise ValueError('Unregistered/duplicate held-out identity')
        name=r['folder']
        if not isinstance(name,str) or Path(name).name!=name or '/' in name or '\\' in name or name in folders:
            raise ValueError('Invalid/duplicate held-out folder')
        identities.append(identity);folders.add(name)
    if len(identities)!=len(plan): raise ValueError('All six fresh test identities are required before evaluation')
    return runs


def evaluate(repo,batch,output):
    repo=Path(repo).resolve();batch=Path(batch).resolve();output=Path(output).resolve()
    if batch.parent!=(repo/'results/runs').resolve(): raise ValueError('Batch must belong to this repository')
    if output.is_relative_to(repo/'results/runs'): raise ValueError('Test derivatives cannot overwrite raw evidence')
    state=read(batch/'batch.json');protocol=load_protocol(batch/'dataset_protocol.json')
    model=frozen_model(batch/'frozen_model.json',protocol)
    if (state.get('outcome')!='completed' or state.get('model_sha256')!=FROZEN_MODEL_SHA
        or state.get('protocol_sha256')!=sha(batch/'dataset_protocol.json')
        or len(state['attempts'])!=6 or any(a['status']!='passed' for a in state['attempts'])):
        raise ValueError('Fresh-test batch is incomplete or has unresolved attempts')
    for name,digest in state['pipeline_sha256'].items():
        if sha(batch/name)!=digest: raise ValueError('Held-out pipeline snapshot changed: '+name)
        if name in ['heldout_dataset.py','source_integrity.py','fixed_trace_dataset.py','tree_model.py','tree_metrics.py','train_tree.py'] and sha(repo/name)!=digest:
            raise ValueError('Evaluation code changed after held-out acquisition began: '+name)
    selection=read(batch/'selection.json');selected=validate_test_selection(selection,protocol)
    if selected!=state['runs']: raise ValueError('Batch and test selection disagree')
    rows=[];summaries=[]
    for item in selected:
        labeled,summary=load_fixed_trace(repo,item['folder'],protocol)
        if (summary['scenario'],summary['seed'])!=(item['scenario'],item['seed']): raise ValueError('Test identity mismatch')
        summary['split']='test';summaries.append(summary)
        rows.extend(dict(run=item['folder'],split='test',scenario=item['scenario'],seed=item['seed'],**r) for r in labeled)
    metrics=review(model,rows,summaries)
    baselines={name:dict(rows=row_report(rows,baseline(rows,name),.5),
        warnings=warning_report(rows,baseline(rows,name),summaries,.5)) for name in ['always_negative','past_trend']}
    model_rows=[dict(r,features={k:f32(v) for k,v in r['features'].items()} if r['features'] is not None else None) for r in rows]
    summary=dict(protocol=protocol,feature_allowlist=FEATURES,complete_development=False,complete_heldout=True,
        source_audit_policy=AUDIT_POLICY,model_sha256=FROZEN_MODEL_SHA,
        frozen_training_dataset_fingerprint=model.model['dataset_fingerprint'],
        test_dataset_fingerprint=canonical_hash(dict(protocol=protocol,rows=model_rows)),runs=summaries,
        total_eligible=sum(s['eligible'] for s in summaries),total_positive=sum(s['positive'] for s in summaries),
        total_observed_events=sum(e['onset_observed'] for s in summaries for e in s['events']))
    report=dict(model_sha256=FROZEN_MODEL_SHA,parameters=model.model['parameters'],threshold=model.threshold,
        metrics=metrics,baselines=baselines,counts={k:summary[k] for k in ['total_eligible','total_positive','total_observed_events']},
        fitting_performed=False,threshold_changed=False,
        interpretation='Fresh fixed-primary prediction test of the pinned model. No ML rerouting, networking gain or universal congestion-truth claim.')
    output.mkdir(parents=True,exist_ok=False)
    for name,obj in [('summary.json',summary),('test_report.json',report),('selection.json',selection),('protocol.json',protocol)]:
        (output/name).write_text(json.dumps(obj,indent=2)+'\n')
    with (output/'rows.jsonl').open('x') as f:
        for r in rows: f.write(json.dumps(r)+'\n')
    columns=['run','scenario','seed','split','available','label','excluded_reason','lead_to_onset_s']+FEATURES
    with (output/'dataset.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for r in rows: w.writerow({**{k:r[k] for k in columns if k in r},**(r['features'] or {})})
    print('HELDOUT TEST:',json.dumps(dict(report= str(output/'test_report.json'),counts=report['counts'],
        rows=metrics['rows'],warning_summary=[{k:r[k] for k in ['scenario','events','scorable_events','true_warnings','false_warnings','late_warnings','censored_warnings','median_lead_s']}
        for r in metrics['warnings']['by_run']]),indent=2),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--batch',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();evaluate(a.repo,a.batch,a.output)
