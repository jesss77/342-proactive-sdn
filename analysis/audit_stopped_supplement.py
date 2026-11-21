"""Independently audit the stopped supplement and retain quality-failure details."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,shutil,sys,tarfile
sys.dont_write_bytecode=True

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def lines(path):return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def intervals(raw,queue,start,finish):
    from inspect_experiment import queue_rows
    previous=None;bad=[];failed=[]
    for index,row in enumerate(queue_rows(raw,queue)):
        root=row.get('root_qdisc')
        if row.get('tc_exit')!=0 or row.get('tc_error') or not root:
            failed.append(dict(queue=queue,index=index,sample=row.get('sample'),exit=row.get('tc_exit'),error=row.get('tc_error')))
            previous=None;continue
        now=(row['tc_start']+row['tc_end'])/2
        if previous is not None:
            before,t0=previous;dt=now-t0;reasons=[];requested=row['requested_interval']
            if dt<=0:reasons.append('nonpositive_elapsed')
            if min(root['bytes']-before['root_qdisc']['bytes'],root['drops']-before['root_qdisc']['drops'])<0:reasons.append('counter_reset')
            if dt>2*requested:reasons.append('elapsed_over_two_intervals')
            if row['tc_end']-row['tc_start']>requested:reasons.append('current_query_over_interval')
            if before['tc_end']-before['tc_start']>before['requested_interval']:reasons.append('previous_query_over_interval')
            if row.get('skipped_before_sample',0):reasons.append('skipped_poll_deadline')
            if reasons:
                bad.append(dict(queue=queue,index=index,sample=row.get('sample'),utc=row.get('utc'),reasons=reasons,
                    start_s=t0-start,end_s=now-start,read_finished_s=row['tc_end']-start,actual_dt_s=dt,
                    current_query_s=row['tc_end']-row['tc_start'],previous_query_s=before['tc_end']-before['tc_start'],
                    skipped=row.get('skipped_before_sample',0),overlaps_source=before['tc_start']<finish and row['tc_end']>start))
        previous=row,now
    return dict(invalid_intervals=bad,failed_queries=failed)

def actions(folder,start):
    decisions=lines(folder/'decisions.jsonl');logs=lines(folder/'action.jsonl');result=[]
    for d in decisions:
        a=d.get('action') or {}
        if not a.get('applied'):continue
        observed=a['admission']['observed_at'];begin=a['started'];end=a['verified_finished']
        verify=[r for r in logs if r.get('event')=='command' and r.get('label')=='readback_primary'
            and d['decision_at']<=r['started']<=begin and r['finished']<=begin]
        install=[r for r in logs if r.get('event')=='command' and r.get('label')=='apply_alternate'
            and begin<=r['started']<=end]
        result.append(dict(reason=d['reason'],observed_s=observed-start,decision_s=d['decision_at']-start,
            decision_age_s=d['decision_at']-observed,program_start_s=begin-start,readback_finished_s=end-start,
            program_start_measurement_age_s=begin-observed,readback_finish_measurement_age_s=end-observed,
            full_decision_to_readback_s=end-d['decision_at'],program_and_readback_s=end-begin,
            primary_verification=[dict(node=r['node'],started_s=r['started']-start,finished_s=r['finished']-start,
                elapsed_s=r['elapsed_s']) for r in verify],
            first_install_command_age_s=min((r['started']-observed for r in install),default=None),
            meaning='First install command start and flow readback are not first selected UDP packet activation times'))
    return result

def original_action_audit(repo):
    from run_matched_batch import evidence_hashes,load_protocol
    repo=Path(repo);p=load_protocol(repo)
    root=repo/'results/runs';batch=root/'20261116-191234-565387-matched-policy-batch'
    state=read(batch/'batch.json')
    if state['outcome']!='completed' or len(state['runs'])!=36:raise ValueError('Original benchmark incomplete')
    result=[]
    for record in state['runs']:
        for key,hkey in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:
            if evidence_hashes(root/record[key])!=record[hkey]:raise ValueError('Original benchmark raw hash changed')
        native=read(root/record['trial']/'sender-native.json')
        for a in actions(root/record['folder'],native['start_monotonic_ns']/1e9):
            result.append(dict(policy=record['policy'],scenario=record['scenario'],seed=record['seed'],folder=record['folder'],**a))
    return dict(scope='All 36 original trials; all raw record hashes rechecked. Nineteen applied actions; no packet activation measurement.',
        rows=result,max_program_start_measurement_age_s=max(a['program_start_measurement_age_s'] for a in result),
        max_full_decision_to_readback_s=max(a['full_decision_to_readback_s'] for a in result))
