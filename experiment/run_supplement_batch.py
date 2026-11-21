"""Additive, preregistered controls then new-seed bursty blocks; no model changes."""
from datetime import datetime,timezone
import importlib,json,shutil
from pathlib import Path
from run_matched_batch import (load_protocol as load_matched,sha,write,child,
    evidence_hashes,check_report,POLICIES)

BASE=Path(__file__).resolve().parent
SETTINGS=dict(id='advisor-supplement-v1',controls_seeds=[41,42,43],
    bursty_seeds=[44,45,46],duration_s=60,requested_scale_bps=11500000,
    interval_s=.25,model_sha256='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595',
    policy_order='three successive Williams orders continuing original block numbering at nine',
    scope='Supplement to original 36; controls answer fixed-alternate asymmetry. New bursty blocks assess run variability. All outcomes retained; no parameter fitting or benefit gate.')

def plan():
    rows=[]
    for seed in SETTINGS['controls_seeds']:
        for scenario in ['ramp','bursty']:
            rows.append(dict(stage='controls',policy='fixed_alternate',scenario=scenario,seed=seed,
                requested_bps=11500000,duration=60))
    for i,seed in enumerate(SETTINGS['bursty_seeds']):
        for position,policy in enumerate([POLICIES[(j+9+i)%4] for j in [0,1,3,2]]):
            rows.append(dict(stage='bursty',block=9+i,position=position,policy=policy,
                scenario='bursty',seed=seed,requested_bps=11500000,duration=60))
    return rows

def load_protocol(base):
    base=Path(base);matched=load_matched(base)
    p=json.loads((base/'supplement_protocol.json').read_text())
    if p.get('settings')!=SETTINGS or p.get('plan')!=plan():raise ValueError('Supplement registration differs')
    if p.get('matched_protocol_sha256')!=sha(base/'matched_protocol.json'):raise ValueError('Frozen matched registration differs')
    expected={'run_schedule_path_control.py','run_supplement_batch.py','test_supplement.py','run_path_control.py'}
    if set(p.get('additional_source_sha256',{}))!=expected:raise ValueError('Supplement source pins incomplete')
    for name,digest in p['additional_source_sha256'].items():
        if (base/name).is_symlink() or sha(base/name)!=digest:raise ValueError('Supplement source changed: '+name)
    return p,matched

def control_record(base,folder,item,report):
    root=Path(base)/'results/runs';folder=child(root,Path(folder).name)
    m=json.loads((folder/'control.json').read_text());trial=child(root,m['trial'])
    if (report['outcome']!='completed' or report['control_screen_failures']
        or m['route']!='alternate' or any(m[k]!=item[k] for k in ['scenario','seed','duration'])
        or m['requested_scale_bps']!=item['requested_bps']):raise ValueError('Supplement control quality or identity failed')
    t=report['trial']
    return dict(item,folder=folder.name,trial=trial.name,
        policy_evidence_sha256=evidence_hashes(folder),trial_evidence_sha256=evidence_hashes(trial),
        sender_mbps=t['sender']['bits_per_second']/1e6,receiver_mbps=t['receiver']['bits_per_second']/1e6,
        udp_loss_percent=t['receiver']['lost_percent'],actions=1,denials=0,
        source_discard_percent=report['source_audit']['discard_percent'])

def validate_resume(base,folder,state,p):
    root=Path(base)/'results/runs';registered=plan()
    if (state.get('outcome') not in ['paused','completed']
        or state.get('protocol_sha256')!=sha(Path(base)/'supplement_protocol.json')
        or state.get('plan')!=registered or len(state['attempts'])!=len(state['runs'])
        or any(a['status']!='passed' for a in state['attempts'])
        or any({k:r[k] for k in item}!=item for r,item in zip(state['runs'],registered))):
        raise ValueError('Failed/interrupted/changed supplement requires evidence review')
    if len(state['runs'])>len(registered):raise ValueError('Too many supplemental runs')
    if sha(folder/'supplement_protocol.json')!=state['protocol_sha256']:raise ValueError('Captured registration changed')
    for name,digest in p['additional_source_sha256'].items():
        if sha(folder/name)!=digest:raise ValueError('Captured source changed')
    for record in state['runs']:
        for key,hkey in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:
            if evidence_hashes(child(root,record[key]))!=record[hkey]:raise ValueError('Accepted evidence changed')

def run(net,stage='controls',limit=1,resume=None,base=BASE,status_path=None,
        control_runner=None,control_inspector=None,policy_runner=None,policy_inspector=None):
    base=Path(base).resolve();root=base/'results/runs';p,matched=load_protocol(base)
    if stage not in ['controls','bursty'] or type(limit) is not int or not 1<=limit<=12:raise ValueError('Invalid stage/limit')
    if control_runner is None or control_inspector is None:
        import run_schedule_path_control as control
        control=importlib.reload(control);control_runner=control.run;control_inspector=control.inspect_control
    if policy_runner is None or policy_inspector is None:
        import run_policy_experiment as policy
        policy=importlib.reload(policy);policy_runner=policy.run;policy_inspector=policy.inspect_policy
    from source_integrity import source_integrity_audit
    registry=root/'supplement-registry-v1.json';registered=plan()
    if resume is None:
        if registry.exists():raise ValueError('Supplement already registered; resume instead')
        if stage!='controls':raise ValueError('Complete alternate controls first')
        if any(root.glob('*-policy-*-bursty-seed4[456]')) or any(root.glob('*-schedule-path-control-*')):
            raise ValueError('Supplement identities already exist; review before collection')
        folder=root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-advisor-supplement')
        folder.mkdir(parents=True)
        state=dict(role='supplement_not_original_benchmark',registered_at=datetime.now(timezone.utc).isoformat(),
            protocol_sha256=sha(base/'supplement_protocol.json'),plan=registered,outcome='paused',attempts=[],runs=[])
        for name in ['supplement_protocol.json','matched_protocol.json',*p['additional_source_sha256']]:shutil.copy2(base/name,folder/name)
        with registry.open('x') as f:json.dump(dict(batch=folder.name),f)
    else:
        folder=child(root,Path(resume).name)
        if not registry.exists() or json.loads(registry.read_text()).get('batch')!=folder.name:raise ValueError('Unregistered resume')
        state=json.loads((folder/'batch.json').read_text());validate_resume(base,folder,state,p)
    count=len(state['runs'])
    if stage=='bursty' and count<6:raise ValueError('Complete and review all six alternate controls first')
    if stage=='controls' and count>=6:raise ValueError('Controls completed; explicitly select bursty stage')
    def save():
        write(folder/'batch.json',state)
        if status_path:write(status_path,dict(batch=str(folder),outcome=state['outcome'],
            accepted=len(state['runs']),attempts=len(state['attempts']),last_attempt=state['attempts'][-1] if state['attempts'] else None,
            results=[{k:v for k,v in r.items() if not k.endswith('_sha256')} for r in state['runs']]))
    (root/'active-supplement-batch.txt').write_text(str(folder)+'\n')
    state['outcome']='running';save()
    try:
        for item in registered[count:min(count+limit,6 if stage=='controls' else 18)]:
            load_protocol(base);attempt=dict(item,status='running');state['attempts'].append(attempt);save()
            before={r.name for r in root.iterdir() if r.is_dir()}
            print('SUPPLEMENT:',len(state['runs'])+1,'/18',item,flush=True)
            try:
                if stage=='controls':
                    raw=Path(control_runner(net,scenario=item['scenario'],seed=item['seed']))
                    attempt['folder']=raw.name;report=control_inspector(raw)
                    record=control_record(base,raw,item,report)
                else:
                    raw=Path(policy_runner(net,policy=item['policy'],scenario=item['scenario'],seed=item['seed'],
                        duration=item['duration'],requested_bps=item['requested_bps']))
                    attempt['folder']=raw.name;report=policy_inspector(raw)
                    record=check_report(base,raw,item,matched,report,source_integrity_audit)
                load_protocol(base)
                reviews=folder/'reviews';reviews.mkdir(exist_ok=True)
                write(reviews/(f'{len(state["runs"]):02d}-'+raw.name+'.json'),report)
                state['runs'].append(record);attempt['status']='passed';save()
                print('SUPPLEMENT RESULT:',json.dumps({k:v for k,v in record.items() if not k.endswith('_sha256')}),flush=True)
            except BaseException as e:
                attempt.update(status='failed',error=repr(e),candidate_raw_folders=sorted({r.name for r in root.iterdir() if r.is_dir()}-before));raise
        state['outcome']='completed' if len(state['runs'])==18 else 'paused'
    except BaseException:
        state['outcome']='failed';save();raise
    finally:save()
    print('Supplement:',state['outcome'],'| accepted',len(state['runs']),'/18 |',folder,flush=True)
    return folder

if 'net' in globals():
    run(net,stage=globals().get('stage','controls'),limit=globals().get('limit',1),resume=globals().get('resume'),status_path=globals().get('status_path'))
