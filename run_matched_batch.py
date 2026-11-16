"""Registered paired networking evaluation; frozen v14 common policy loop."""
from datetime import datetime
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
POLICIES=['fixed','reactive','early_warning','ml']
SETTINGS=dict(id='four-policy-matched-v1',seeds=[41,42,43],
    scenarios=['steady','ramp','bursty'],policies=POLICIES,duration_s=60,
    scale_bps=dict(steady=3000000,ramp=11500000,bursty=11500000),
    interval_s=.25,coverage='all',max_successful_actions=1,
    profile_id='dual-forward-cburst16k-source250-v1',
    model_sha256='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595',
    threshold=.65,ordering='nine scenario/seed blocks; rotating scenarios and four Williams policy orders',
    source_discard_fraction_limit=.05,
    scope='One h1/h2 flow and its probes; no generated background. Steady 3M tests unnecessary actions; variable scenarios use unchanged 11.5M scale. No fitting or prediction-label construction on rerouted traces.')
COMMON_SOURCES=['run_policy_experiment.py','live_policy.py','routing_policy.py','routing_action.py',
    'operating_bounds.json','dual_path_profile.py','collect_path.py','run_continuous_trial.py',
    'continuous_udp.py','traffic_scenarios.py','build_trace_dataset.py','inspect_experiment.py',
    'topology.py','diamond_controller.py','experiment_config.py']
ML_SOURCES=['ml_trigger.py','tree_model.py','selected_tree.json']
EXTRA_SOURCES=['source_integrity.py','dataset_protocol.json','run_matched_batch.py']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def plan():
    rows=[];block=0
    for i,seed in enumerate(SETTINGS['seeds']):
        scenarios=SETTINGS['scenarios'][i:]+SETTINGS['scenarios'][:i]
        for scenario in scenarios:
            # Williams square balances positions and first-order carryover in
            # each group of four blocks. Nine blocks give position counts 2/3.
            order=[POLICIES[(j+block)%4] for j in [0,1,3,2]]
            for position,policy in enumerate(order):
                rows.append(dict(block=block,position=position,policy=policy,
                    scenario=scenario,seed=seed,requested_bps=SETTINGS['scale_bps'][scenario],
                    duration=SETTINGS['duration_s']))
            block+=1
    return rows

def load_protocol(base):
    base=Path(base);p=json.loads((base/'matched_protocol.json').read_text())
    if p.get('settings')!=SETTINGS or p.get('plan')!=plan():
        raise ValueError('Matched settings/plan differ from registration')
    names=COMMON_SOURCES+ML_SOURCES+EXTRA_SOURCES
    if set(p.get('source_sha256',{}))!=set(names):raise ValueError('Incomplete matched source pins')
    for name,digest in p['source_sha256'].items():
        if (base/name).is_symlink() or sha(base/name)!=digest:raise ValueError('Matched source changed: '+name)
    from ml_trigger import load_runtime_model
    model,context=load_runtime_model(base)
    if context['sha256']!=SETTINGS['model_sha256'] or model.threshold!=SETTINGS['threshold']:
        raise ValueError('Frozen matched model differs')
    return p

def child(root,name):
    if not isinstance(name,str) or not name or Path(name).name!=name or any(s in name for s in ['..','\\',':']):
        raise ValueError('Invalid raw folder identity')
    candidate=Path(root)/name
    if candidate.is_symlink():raise ValueError('Raw folder is a symlink')
    path=candidate.resolve()
    if path.parent!=Path(root).resolve():raise ValueError('Raw folder escaped repository')
    return path

def evidence_hashes(folder):
    folder=Path(folder);hashes={}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('Symlinks are not raw evidence')
        if p.is_file():hashes[p.relative_to(folder).as_posix()]=sha(p)
    if not hashes:raise ValueError('Missing raw evidence')
    return hashes

def check_report(base,folder,item,protocol,report,auditor):
    root=Path(base)/'results/runs';folder=child(root,Path(folder).name)
    m=json.loads((folder/'policy.json').read_text())
    from traffic_scenarios import continuous_schedule
    expected=continuous_schedule(item['scenario'],item['requested_bps'],item['duration'],item['seed'])
    if (m.get('outcome')!='completed' or report.get('outcome')!='completed'
        or any(m.get(k)!=item[k] for k in ['policy','scenario','seed'])
        or m.get('duration')!=item['duration'] or m.get('requested_scale_bps')!=item['requested_bps']
        or m.get('planned_segments')!=expected or m.get('profile',{}).get('id')!=SETTINGS['profile_id']):
        raise ValueError('Trial identity/schedule/profile differs from registered cell')
    names=COMMON_SOURCES+(ML_SOURCES if item['policy']=='ml' else [])
    for name in names:
        if m['source_sha256'].get(name)!=protocol['source_sha256'][name] or sha(folder/name)!=protocol['source_sha256'][name]:
            raise ValueError('Captured trial source differs: '+name)
    if (report['screen_failures'] or report['restoration']['failures']
        or not report['route_restoration']['verified'] or report['route_restoration']['failures']):
        raise ValueError('Matched trial quality/restoration failed')
    applied=report['applied_actions']
    if len(applied)>1 or (item['policy']=='fixed' and (applied or report['denied_requests'])):
        raise ValueError('Policy violated action budget/fixed routing')
    # No-action/denied-action and steady-load switches remain valid outcomes.
    # A claimed action must have the common inspector's in-traffic path proof.
    if applied and not report['in_traffic_switch_verified']:raise ValueError('Claimed action lacks in-traffic path proof')
    if item['policy']=='ml' and ((report.get('model') or {}).get('sha256')!=SETTINGS['model_sha256']
        or (report.get('model') or {}).get('threshold')!=SETTINGS['threshold']
        or not (report.get('inference') or {}).get('calls')):
        raise ValueError('ML inference/model binding missing')
    trial=child(root,m['trial'])
    if report['trial']['run']!=trial.name:raise ValueError('Trial reference differs')
    native_meta=json.loads((trial/'metadata.json').read_text())
    if (native_meta.get('traffic_plan')!=expected or native_meta.get('seed')!=item['seed']
        or native_meta.get('scenario')!=item['scenario']
        or any(native_meta.get('trial_context',{}).get(k)!=v for k,v in
            dict(kind='policy_experiment',policy=item['policy'],parent=folder.name).items())):
        raise ValueError('Source schedule/identity/parent differs from registered cell')
    audit=auditor(trial)
    return dict(item,folder=folder.name,trial=trial.name,
        policy_evidence_sha256=evidence_hashes(folder),trial_evidence_sha256=evidence_hashes(trial),
        receiver_mbps=report['receiver_mbps'],sender_mbps=report['sender_mbps'],
        udp_loss_percent=report['udp_loss_percent'],actions=len(applied),denials=len(report['denied_requests']),
        source_discard_percent=audit['discard_percent'],
        source_audit_scope='Sender integrity only; dynamic routing quality is checked by the common inspector')

def pilot_gate(base,protocol,inspect_trial):
    root=Path(base)/'results/runs'
    for folder in sorted(root.glob('*-policy-ml-ramp-seed1'),reverse=True):
        try:
            m=json.loads((folder/'policy.json').read_text())
            if m.get('source_sha256')!={n:protocol['source_sha256'][n] for n in COMMON_SOURCES+ML_SOURCES}:continue
            report=inspect_trial(folder)
            item=dict(policy='ml',scenario='ramp',seed=1,requested_bps=11500000,duration=60)
            from source_integrity import source_integrity_audit
            record=check_report(base,folder,item,protocol,report,source_integrity_audit)
            if report['in_traffic_switch_verified'] and record['actions']==1:return dict(folder=folder.name,model_sha256=SETTINGS['model_sha256'])
        except (OSError,ValueError,KeyError):continue
    raise ValueError('Accepted live ML seed-1 pilot under this exact common source is required')

def run(net,limit=4,resume=None,base=BASE,run_trial=None,inspect_trial=None,source_auditor=None,pilot_checker=pilot_gate):
    base=Path(base).resolve();root=base/'results/runs'
    p=load_protocol(base);registered=plan()
    if type(limit) is not int or not 1<=limit<=36:raise ValueError('Limit must be 1–36 new trials')
    if run_trial is None or inspect_trial is None:
        import run_policy_experiment as runner
        runner=importlib.reload(runner);run_trial=runner.run;inspect_trial=runner.inspect_policy
    if source_auditor is None:
        from source_integrity import source_integrity_audit
        source_auditor=source_integrity_audit
    gate=pilot_checker(base,p,inspect_trial)
    registry=root/'matched-registry-v1.json';root.mkdir(parents=True,exist_ok=True)
    if resume is None:
        if registry.exists():raise ValueError('Matched batch already registered; inspect/resume it instead of reacquiring')
        if any(root.glob('*-policy-*-seed4[123]')):raise ValueError('Matched identities already exist; review evidence before collection')
        folder=root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-matched-policy-batch')
        folder.mkdir()
        state=dict(role='matched_networking_evaluation',protocol_sha256=sha(base/'matched_protocol.json'),
            plan=registered,model_sha256=SETTINGS['model_sha256'],pilot=gate,
            outcome='running',attempts=[],runs=[])
        with registry.open('x') as f:json.dump(dict(batch=folder.name),f)
        for name in ['matched_protocol.json',*p['source_sha256']]:shutil.copy2(base/name,folder/name)
    else:
        resume=Path(resume).resolve()
        if resume.parent!=root:raise ValueError('Resume must be inside this repository')
        folder=child(root,resume.name)
        if not registry.exists() or json.loads(registry.read_text()).get('batch')!=folder.name:raise ValueError('Unregistered resume')
        state=json.loads((folder/'batch.json').read_text())
        if (state.get('outcome') not in ['paused','completed']
            or state['protocol_sha256']!=sha(base/'matched_protocol.json') or state['plan']!=registered
            or len(state['attempts'])!=len(state['runs']) or any(a['status']!='passed' for a in state['attempts'])
            or [{k:r[k] for k in registered[0]} for r in state['runs']]!=registered[:len(state['runs'])]):
            raise ValueError('Failed/interrupted/changed matched batch requires evidence review')
        if sha(folder/'matched_protocol.json')!=sha(base/'matched_protocol.json'):raise ValueError('Captured protocol changed')
        for name,digest in p['source_sha256'].items():
            if sha(folder/name)!=digest:raise ValueError('Captured batch source changed')
        for record in state['runs']:
            for key,hkey in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:
                if evidence_hashes(child(root,record[key]))!=record[hkey]:raise ValueError('Accepted raw evidence changed')
    def save():write(folder/'batch.json',state)
    save();(root/'active-matched-batch.txt').write_text(str(folder)+'\n')
    print('Matched batch:',folder,flush=True)
    count=len(state['runs']);state['outcome']='running';save()
    try:
        for item in registered[count:count+limit]:
            load_protocol(base)
            attempt=dict(item,status='running');state['attempts'].append(attempt);save()
            before={r.name for r in root.iterdir() if r.is_dir()}
            print('MATCHED ACQUISITION:',len(state['runs'])+1,'/ 36',item,flush=True)
            try:
                raw=Path(run_trial(net,policy=item['policy'],scenario=item['scenario'],seed=item['seed'],
                    duration=item['duration'],requested_bps=item['requested_bps']))
                attempt['folder']=raw.name
                if raw.resolve().parent!=root:raise ValueError('Runner returned a foreign raw folder')
                report=inspect_trial(raw)
                record=check_report(base,raw,item,p,report,source_auditor)
                load_protocol(base)
                reviews=folder/'reviews';reviews.mkdir(exist_ok=True)
                write(reviews/(f'{len(state["runs"]):02d}-'+raw.name+'.json'),report)
                state['runs'].append(record);attempt['status']='passed';save()
                print('MATCHED RESULT:',json.dumps({k:record[k] for k in [*item,'folder','receiver_mbps','sender_mbps','udp_loss_percent','actions','denials','source_discard_percent']}),flush=True)
            except BaseException as e:
                attempt.update(status='failed',error=repr(e),candidate_raw_folders=sorted({r.name for r in root.iterdir() if r.is_dir()}-before))
                raise
        state['outcome']='completed' if len(state['runs'])==36 else 'paused'
    except BaseException:
        state['outcome']='failed';save();raise
    finally:save()
    print('Matched batch:',state['outcome'],'| accepted',len(state['runs']),'/ 36 |',folder,flush=True)
    print('All outcomes retained. No model fitting, threshold changes or QoS benefit requirement.',flush=True)
    return folder

if 'net' in globals():run(net,limit=globals().get('limit',4),resume=globals().get('resume'))
