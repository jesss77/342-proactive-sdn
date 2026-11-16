"""Guest fixed-primary development acquisition; no held-out collection or fitting."""
from datetime import datetime
import importlib
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from fixed_trace_dataset import load_protocol,development_plan,validate_selection,sha


def run(net,limit=2,resume=None,base=BASE,run_trial=None,inspect_trial=None):
    base=Path(base).resolve();protocol_path=base/'dataset_protocol.json'
    protocol=load_protocol(protocol_path);plan=development_plan(protocol)
    for name,digest in protocol['source_sha256'].items():
        if sha(base/name)!=digest: raise ValueError('Acquisition source changed: '+name)
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=len(plan):
        raise ValueError('Limit must be 1–16 new development runs')
    root=base/'results/runs'
    pipeline={name:sha(base/name) for name in ['run_dataset_batch.py','fixed_trace_dataset.py']}
    if resume is None:
        folder=root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-fixed-development-batch')
        folder.mkdir(parents=True)
        state=dict(protocol_id=protocol['id'],protocol_sha256=sha(protocol_path),plan=plan,
                   pipeline_sha256=pipeline,outcome='running',attempts=[],runs=[])
        (folder/'dataset_protocol.json').write_bytes(protocol_path.read_bytes())
        (folder/'run_dataset_batch.py').write_bytes(Path(__file__).read_bytes())
        (folder/'fixed_trace_dataset.py').write_bytes((base/'fixed_trace_dataset.py').read_bytes())
    else:
        folder=Path(resume).resolve()
        if folder.parent!=root.resolve(): raise ValueError('Resume must name a batch under this repository')
        state=json.loads((folder/'batch.json').read_text())
        if state['protocol_sha256']!=sha(protocol_path) or state['plan']!=plan: raise ValueError('Protocol changed since batch began')
        if state.get('pipeline_sha256')!=pipeline: raise ValueError('Dataset pipeline changed since batch began')
        if state['outcome'] not in ['paused','completed']: raise ValueError('Failed/interrupted batches need evidence review before resuming')
        if len(state['runs'])!=len(state['attempts']) or any(a['status']!='passed' for a in state['attempts']):
            raise ValueError('Batch has unresolved attempts')
        validate_selection(dict(protocol_id=protocol['id'],runs=state['runs']),protocol,allow_partial=True)
        if [{k:r[k] for k in ['split','scenario','seed']} for r in state['runs']]!=plan[:len(state['runs'])]:
            raise ValueError('Batch identities do not match the registered prefix')
    def save():
        (folder/'batch.json').write_text(json.dumps(state,indent=2)+'\n')
        (folder/'selection.json').write_text(json.dumps(dict(protocol_id=protocol['id'],runs=state['runs']),indent=2)+'\n')
    save();(root/'active-development-batch.txt').write_text(str(folder)+'\n')
    print('Development batch:',folder,flush=True)
    if run_trial is None or inspect_trial is None:
        import run_policy_experiment as runner
        runner=importlib.reload(runner)
        run_trial=runner.run;inspect_trial=runner.inspect_policy
    start=len(state['runs']);state['outcome']='running';save()
    try:
        for item in plan[start:start+limit]:
            attempt=dict(item,status='running');state['attempts'].append(attempt);save()
            before={p.name for p in root.glob('*-policy-fixed-*')}
            print('DATA ACQUISITION:',len(state['runs'])+1,'/',len(plan),item,flush=True)
            try:
                trial=Path(run_trial(net,policy='fixed',scenario=item['scenario'],requested_bps=protocol['scale_bps'],
                   duration=protocol['duration_s'],seed=item['seed']))
                attempt['folder']=trial.name;report=inspect_trial(trial)
                if report['screen_failures'] or report['applied_actions'] or report['denied_requests']:
                    raise RuntimeError('Fixed development trace failed quality/route screening')
                record=dict(item,folder=trial.name);state['runs'].append(record);attempt['status']='passed'
                print('DATA RESULT:',json.dumps(dict(record,receiver_mbps=report['receiver_mbps'],
                    udp_loss_percent=report['udp_loss_percent'],screen_failures=report['screen_failures'])),flush=True)
                save()
            except BaseException as e:
                attempt.update(status='failed',error=repr(e),
                    candidate_raw_folders=sorted({p.name for p in root.glob('*-policy-fixed-*')}-before))
                raise
        state['outcome']='completed' if len(state['runs'])==len(plan) else 'paused'
    except BaseException:
        state['outcome']='failed';save();raise
    finally: save()
    print('Batch:',state['outcome'],'| accepted',len(state['runs']),'/',len(plan),'|',folder,flush=True)
    print('Held-out seeds 31–33 were not acquired.',flush=True)
    return folder


if 'net' in globals():
    run(net,limit=globals().get('limit',2),resume=globals().get('resume'))
