"""Train only on registered training runs; select on whole-run validation data."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import shutil
import time

from build_trace_dataset import FEATURES
from fixed_trace_dataset import load_protocol,validate_selection
from tree_model import TreeModel,canonical_hash,f32
from tree_metrics import row_report,warning_report

PLAN=dict(id='cart-development-selection-v1',random_state=342,
    max_depth=[2,3,4],min_samples_leaf=[10,25],class_weight=[None,'balanced'],
    alarm_thresholds=[.35,.5,.65],sample_weight='Equal total weight per training run',
    selection='Maximize validation positive-class F1 averaged equally over ramp/bursty; tie: fewer nodes, larger min_samples_leaf, threshold closer to .5, unweighted classes',
    fit_partitions=['train'],selection_partitions=['validation'],test_partitions=[],
    warning_episode_cooldown_s=5.,warning_horizon_s=2.,
    note='Limited development search, not an untouched test estimate; never refit on validation after selection')


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_data(dataset,repo=None):
    dataset=Path(dataset);summary=read(dataset/'summary.json');protocol=load_protocol(dataset/'protocol.json')
    selection=read(dataset/'selection.json');validate_selection(selection,protocol)
    if not summary.get('complete_development') or summary['protocol']!=protocol:
        raise ValueError('Incomplete or mismatched development dataset')
    if summary.get('source_audit_policy',{}).get('id')!='measured-fixed-source-integrity-v1':
        raise ValueError('Source acceptance policy must be disclosed')
    if summary['feature_allowlist']!=FEATURES: raise ValueError('Feature allowlist differs')
    rows=[json.loads(s) for s in (dataset/'rows.jsonl').read_text().splitlines()]
    identities={x['folder']:(x['scenario'],x['seed'],x['split']) for x in selection['runs']}
    previous={};counts=Counter()
    for r in rows:
        if r['split'] not in ['train','validation'] or identities.get(r['run'])!=(r['scenario'],r['seed'],r['split']):
            raise ValueError('Unregistered/test identity in development rows')
        t=r['available']
        if not isinstance(t,(int,float)) or not math.isfinite(t) or t<=previous.get(r['run'],float('-inf')):
            raise ValueError('Rows must be strictly ordered within each run')
        previous[r['run']]=t
        if r['features'] is not None:
            if set(r['features'])!=set(FEATURES) or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in r['features'].values()):
                raise ValueError('Invalid/future feature input')
        if r['label'] is not None:
            if type(r['label']) is not int or r['label'] not in [0,1] or r['features'] is None or r['excluded_reason'] is not None:
                raise ValueError('Invalid eligible row')
            counts[r['run']]+=1
    if set(counts)!=set(identities): raise ValueError('Missing eligible registered run')
    if sum(counts.values())!=summary['total_eligible'] or sum(r['label']==1 for r in rows)!=summary['total_positive']:
        raise ValueError('Dataset counts differ from summary')
    for run in summary['runs']:
        if counts[run['run']]!=run['eligible']: raise ValueError('Run counts differ')
        if repo is not None:
            base=Path(repo).resolve()
            for relative,digest in run['raw_sha256'].items():
                path=(base/relative).resolve()
                if not path.is_relative_to(base) or sha(path)!=digest: raise ValueError('Raw input hash differs: '+relative)
    # Fingerprint actual CART input precision. Last-bit platform libm
    # differences in EWMA doubles do not change sklearn's float32 inputs.
    model_rows=[dict(r,features={k:f32(v) for k,v in r['features'].items()} if r['features'] is not None else None) for r in rows]
    fingerprint=canonical_hash(dict(protocol=protocol,rows=model_rows))
    return rows,summary,fingerprint


def training_weights(rows):
    counts=Counter(r['run'] for r in rows)
    return [len(rows)/(len(counts)*counts[r['run']]) for r in rows]


def fit_model(training,parameters):
    from sklearn.tree import DecisionTreeClassifier
    if not training or any(r['split']!='train' for r in training): raise ValueError('Fitting accepts training rows only')
    x=[[r['features'][name] for name in FEATURES] for r in training];y=[r['label'] for r in training]
    if set(y)!={0,1}: raise ValueError('Training requires both classes')
    tree=DecisionTreeClassifier(random_state=PLAN['random_state'],**parameters)
    tree.fit(x,y,sample_weight=training_weights(training));return tree


def export_model(tree,threshold,parameters,fingerprint,protocol):
    nodes=[];positive=list(tree.classes_).index(1)
    for i in range(tree.tree_.node_count):
        value=tree.tree_.value[i][0];leaf=tree.tree_.children_left[i]<0
        nodes.append(dict(feature=-1 if leaf else int(tree.tree_.feature[i]),
            threshold=float(tree.tree_.threshold[i]),left=int(tree.tree_.children_left[i]),
            right=int(tree.tree_.children_right[i]),p1=float(value[positive]/sum(value))))
    return dict(format='cmps342-cart-json-v1',features=FEATURES,alarm_threshold=threshold,nodes=nodes,
       parameters=parameters,plan=PLAN,dataset_fingerprint=fingerprint,
       acquisition_protocol_id=protocol['id'],label_config=protocol['label_config'],profile_id=protocol['profile_id'],
       feature_source_sha256=protocol['source_sha256']['build_trace_dataset.py'],
       note='Leaf frequency estimates, not calibrated probabilities. Selected using validation; no fresh test result or live ML action yet.')


def baseline(rows,name):
    values=[]
    for r in rows:
        f=r['features']
        values.append(float(bool(f and name=='past_trend' and f['utilization']>=.5
            and f['util_slope_2s']>0 and f['utilization']+2*f['util_slope_2s']>=.85)))
    return values


def review(model,rows,summary):
    probabilities=[model.probability(r['features']) if r['features'] is not None else 0. for r in rows]
    return dict(rows=row_report(rows,probabilities,model.threshold),
      warnings=warning_report(rows,probabilities,summary,model.threshold))


def train(dataset,repo,output):
    import numpy as np
    import sklearn
    from sklearn.tree import export_text
    rows,summary,fingerprint=load_data(dataset,repo)
    train_rows=[r for r in rows if r['split']=='train' and r['label'] is not None]
    validation=[r for r in rows if r['split']=='validation']
    output=Path(output).resolve()
    if output.is_relative_to(Path(repo).resolve()/'results/runs'): raise ValueError('Model output cannot overwrite raw evidence')
    output.mkdir(parents=True,exist_ok=False)
    # Persist the full plan before any development-data fit.
    (output/'training_plan.json').write_text(json.dumps(PLAN,indent=2)+'\n')
    candidates=[];best=None;best_key=None;best_tree=None
    for depth,leaf,weight in itertools.product(PLAN['max_depth'],PLAN['min_samples_leaf'],PLAN['class_weight']):
        parameters=dict(max_depth=depth,min_samples_leaf=leaf,class_weight=weight)
        tree=fit_model(train_rows,parameters)
        x=[[r['features'][f] for f in FEATURES] if r['features'] is not None else [0.]*len(FEATURES) for r in validation]
        probs=tree.predict_proba(x)[:,list(tree.classes_).index(1)].tolist()
        for threshold in PLAN['alarm_thresholds']:
            report=row_report(validation,probs,threshold)
            candidate=dict(parameters=parameters,threshold=threshold,node_count=int(tree.tree_.node_count),
                validation_scenario_macro_f1=report['scenario_macro_f1'],validation_rows=report)
            candidates.append(candidate)
            key=(report['scenario_macro_f1'],-tree.tree_.node_count,leaf,-abs(threshold-.5),weight is None)
            if best_key is None or key>best_key:
                best_key=key;best=candidate;best_tree=tree
    exported=export_model(best_tree,best['threshold'],best['parameters'],fingerprint,summary['protocol'])
    model=TreeModel(exported)
    # Verify float32 comparison parity on every available history, not just
    # the eligible training examples used to fit the model.
    usable=[r for r in rows if r['features'] is not None]
    x=[[r['features'][f] for f in FEATURES] for r in usable]
    reference=best_tree.predict_proba(x)[:,list(best_tree.classes_).index(1)]
    portable=np.array([model.probability(r['features']) for r in usable])
    if not np.allclose(reference,portable,rtol=0,atol=1e-12): raise RuntimeError('Export parity failed')
    if not np.array_equal(reference>=model.threshold,portable>=model.threshold): raise RuntimeError('Export alarm parity failed')
    summaries={split:[r for r in summary['runs'] if r['split']==split] for split in ['train','validation']}
    reports={split:review(model,[r for r in rows if r['split']==split],summaries[split]) for split in summaries}
    baselines={name:dict(rows=row_report(validation,baseline(validation,name),.5),
        warnings=warning_report(validation,baseline(validation,name),summaries['validation'],.5))
        for name in ['always_negative','past_trend']}
    timings=[]
    for r in usable[:1000]:
        start=time.perf_counter_ns();model.probability(r['features']);timings.append(time.perf_counter_ns()-start)
    timings.sort()
    report=dict(plan=PLAN,selected=best,candidates=candidates,dataset_fingerprint=fingerprint,
       data_counts={split:dict(runs=len(summaries[split]),eligible=sum(r['split']==split and r['label'] is not None for r in rows)) for split in summaries},
       metrics=reports,baselines=baselines,export_parity=dict(samples=len(usable),max_probability_error=float(max(abs(reference-portable))),alarm_decisions_identical=True),
       feature_importance=dict(zip(FEATURES,map(float,best_tree.feature_importances_))),
       environment=dict(python=platform.python_version(),sklearn=sklearn.__version__,numpy=np.__version__,platform=platform.platform()),
       runtime_offline_ns=dict(samples=len(timings),median=timings[len(timings)//2],p95=timings[round((len(timings)-1)*.95)]),
       input_hashes={name:sha(Path(dataset)/name) for name in ['rows.jsonl','summary.json','protocol.json','selection.json']},
       training_source_sha256={name:sha(Path(__file__).with_name(name)) for name in ['train_tree.py','tree_model.py','tree_metrics.py']},
       limitations=['Validation selection estimate, not untouched test generalization','Rows and events are clustered within only 16 schedules',
         'Whole-run warning replay has no network interventions; not a live QoS result','Pacing deviations retained under explicit measured-source amendment'])
    (output/'model.json').write_text(json.dumps(exported,indent=2)+'\n')
    (output/'training_report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'tree.txt').write_text(export_text(best_tree,feature_names=FEATURES)+'\n')
    for name in report['training_source_sha256']: shutil.copy2(Path(__file__).with_name(name),output/name)
    print(json.dumps(dict(selected=best,baselines={k:v['rows']['scenario_macro_f1'] for k,v in baselines.items()},
        export_parity=report['export_parity'],model= str(output/'model.json')),indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--repo',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();train(a.dataset,a.repo,a.output)
