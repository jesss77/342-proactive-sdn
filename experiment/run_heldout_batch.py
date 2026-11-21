"""Six registered fresh fixed-primary traces; pin model before any acquisition."""
from datetime import datetime
import importlib
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
# The Mininet interpreter survives source updates. Bind the current offline
# reader and audit, rather than a previously cached zero-discard pilot reader.
import fixed_trace_dataset as fixed_data
fixed_data=importlib.reload(fixed_data)
import source_integrity as source_audit
source_audit=importlib.reload(source_audit)
import heldout_dataset as heldout
heldout=importlib.reload(heldout)
from fixed_trace_dataset import load_protocol,sha
from source_integrity import source_integrity_audit
from heldout_dataset import FROZEN_MODEL_SHA,test_plan,frozen_model,guest_reproduction

PIPELINE=['run_heldout_batch.py','heldout_dataset.py','source_integrity.py','fixed_trace_dataset.py',
          'tree_model.py','tree_metrics.py','train_tree.py']


def run(net,limit=6,resume=None,base=BASE,run_trial=None,inspect_trial=None,source_auditor=source_integrity_audit):
    base=Path(base).resolve();root=base/'results/runs'
    protocol_path=base/'dataset_protocol.json';protocol=load_protocol(protocol_path)
    model=frozen_model(base/'selected_tree.json',protocol);reproduction=guest_reproduction(base,model)
    for name,digest in protocol['source_sha256'].items():
        if sha(base/name)!=digest: raise ValueError('Acquisition source changed: '+name)
    if type(limit) is not int or not 1<=limit<=6: raise ValueError('Fresh-test limit must be 1–6')
    plan=test_plan(protocol);pipeline={name:sha(base/name) for name in PIPELINE}
    registry=root/('heldout-registry-'+FROZEN_MODEL_SHA[:12]+'.json')
    if resume is None:
        if registry.exists(): raise ValueError('A fresh-test batch is already registered for this model; inspect/resume it instead of reacquiring')
        if any(list(root.glob(f'*-policy-fixed-*-seed{seed}')) for seed in protocol['partitions']['test']):
            raise ValueError('Reserved test identities already exist; evidence review required')
        folder=root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-frozen-heldout-batch')
        folder.mkdir(parents=True)
        state=dict(role='heldout_test',protocol_id=protocol['id'],protocol_sha256=sha(protocol_path),
            model_sha256=FROZEN_MODEL_SHA,guest_development_reproduction=reproduction,
            plan=plan,pipeline_sha256=pipeline,outcome='running',attempts=[],runs=[])
        with registry.open('x') as f: json.dump(dict(model_sha256=FROZEN_MODEL_SHA,batch=str(folder)),f,indent=2)
        for name in PIPELINE: (folder/name).write_bytes((base/name).read_bytes())
        (folder/'dataset_protocol.json').write_bytes(protocol_path.read_bytes())
        (folder/'frozen_model.json').write_bytes((base/'selected_tree.json').read_bytes())
    else:
        folder=Path(resume).resolve()
        if folder.parent!=root.resolve() or not registry.exists() or Path(json.loads(registry.read_text())['batch']).resolve()!=folder:
            raise ValueError('Resume does not match the registered fresh-test batch')
        state=json.loads((folder/'batch.json').read_text())
        if (state.get('outcome') not in ['paused','completed'] or state['model_sha256']!=FROZEN_MODEL_SHA
            or state['protocol_sha256']!=sha(protocol_path) or state['pipeline_sha256']!=pipeline
            or state['plan']!=plan or len(state['attempts'])!=len(state['runs'])
            or any(a['status']!='passed' for a in state['attempts'])
            or [{k:r[k] for k in ['split','scenario','seed']} for r in state['runs']]!=plan[:len(state['runs'])]):
            raise ValueError('Failed, changed or unresolved fresh-test batch requires evidence review')
        if sha(folder/'frozen_model.json')!=FROZEN_MODEL_SHA: raise ValueError('Frozen batch model changed')
    def save():
        (folder/'batch.json').write_text(json.dumps(state,indent=2)+'\n')
        (folder/'selection.json').write_text(json.dumps(dict(role='heldout_test',protocol_id=protocol['id'],
            model_sha256=FROZEN_MODEL_SHA,runs=state['runs']),indent=2)+'\n')
    save();(root/'active-heldout-batch.txt').write_text(str(folder)+'\n')
    print('Frozen held-out batch:',folder,'| model:',FROZEN_MODEL_SHA,flush=True)
    if run_trial is None or inspect_trial is None:
        import run_policy_experiment as runner
        runner=importlib.reload(runner);run_trial=runner.run;inspect_trial=runner.inspect_policy
    start=len(state['runs']);state['outcome']='running';save()
    try:
        for item in plan[start:start+limit]:
            attempt=dict(item,status='running');state['attempts'].append(attempt);save()
            before={p.name for p in root.glob('*-policy-fixed-*')}
            print('HELDOUT ACQUISITION:',len(state['runs'])+1,'/ 6',item,flush=True)
            try:
                if sha(base/'selected_tree.json')!=FROZEN_MODEL_SHA: raise RuntimeError('Frozen model changed during collection')
                folder_run=Path(run_trial(net,policy='fixed',scenario=item['scenario'],requested_bps=protocol['scale_bps'],
                    duration=protocol['duration_s'],seed=item['seed']))
                attempt['folder']=folder_run.name;report=inspect_trial(folder_run)
                if report['screen_failures'] or report['applied_actions'] or report['denied_requests']:
                    raise RuntimeError('Fresh-test acquisition/route screen failed')
                audit=source_auditor(root/report['trial']['run'])
                if sha(base/'selected_tree.json')!=FROZEN_MODEL_SHA: raise RuntimeError('Frozen model changed during collection')
                state['runs'].append(dict(item,folder=folder_run.name));attempt['status']='passed'
                attempt['source_discard_percent']=audit['discard_percent']
                print('HELDOUT RESULT:',json.dumps(dict(item,folder=folder_run.name,receiver_mbps=report['receiver_mbps'],
                    udp_loss_percent=report['udp_loss_percent'],source_discard_percent=audit['discard_percent'],screen_failures=[])),flush=True)
                save()
            except BaseException as e:
                attempt.update(status='failed',error=repr(e),candidate_raw_folders=sorted({p.name for p in root.glob('*-policy-fixed-*')}-before))
                raise
        state['outcome']='completed' if len(state['runs'])==6 else 'paused'
    except BaseException:
        state['outcome']='failed';save();raise
    finally: save()
    print('Held-out batch:',state['outcome'],'| accepted',len(state['runs']),'/ 6 |',folder,flush=True)
    print('No model fitting, threshold changes or ML rerouting performed.',flush=True)
    return folder


if 'net' in globals(): run(net,limit=globals().get('limit',6),resume=globals().get('resume'))
