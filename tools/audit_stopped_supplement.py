"""Independently audit the stopped supplement and retain quality-failure details."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,shutil,sys,tarfile
sys.dont_write_bytecode=True

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def lines(path):return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def extract(archive,destination,expected):
    if sha(archive)!=expected:raise ValueError('Archive digest differs')
    destination.mkdir(parents=True,exist_ok=False);seen=set();count=total=0
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar:
            p=PurePosixPath(m.name)
            if (p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='342-proactive-sdn'
                or '\\' in m.name or ':' in m.name or not(m.isfile() or m.isdir()) or p in seen):
                raise ValueError('Unsafe/duplicate archive member')
            seen.add(p);target=destination.joinpath(*p.parts)
            if not target.resolve().is_relative_to(destination.resolve()):raise ValueError('Archive escape')
            if m.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(m) as source,target.open('xb') as out:shutil.copyfileobj(source,out)
                if target.stat().st_size!=m.size:raise ValueError('Member size mismatch')
                count+=1;total+=m.size
    return dict(files=count,bytes=total)

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

def audit(archive,expected,raw_destination,output,published,original_repo=None):
    archive=Path(archive);raw_destination=Path(raw_destination).resolve();output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    if not raw_destination.exists():extracted=extract(archive,raw_destination,expected)
    else:
        if sha(archive)!=expected:raise ValueError('Archive digest differs')
        extracted=dict(files=sum(p.is_file() for p in raw_destination.rglob('*')),bytes=sum(p.stat().st_size for p in raw_destination.rglob('*') if p.is_file()))
    repo=raw_destination/'342-proactive-sdn';manifest=read(repo/'supplement-export-manifest.json')
    for name,digest in manifest['files_sha256'].items():
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:raise ValueError('Unsafe manifest path')
        if sha(repo.joinpath(*p.parts))!=digest:raise ValueError('Export member digest differs: '+name)
    if len(manifest['files_sha256'])!=828 or extracted['files']!=829:raise ValueError('Unexpected export count')
    trusted=read(Path(published)/'evidence/supplement-install-manifest.json')
    trusted_pins=dict(trusted['unchanged_files'],**trusted['unchanged_testbed'],**trusted['files'])
    if set(manifest['source_status'])!=set(trusted_pins):raise ValueError('Source set differs')
    for name,digest in trusted_pins.items():
        if manifest['source_status'][name]!={'expected_sha256':digest,'actual_sha256':digest} or sha(repo/name)!=digest:
            raise ValueError('Frozen source differs: '+name)
    sys.path.insert(0,str(repo))
    import run_supplement_batch as supplement
    from source_integrity import source_integrity_audit
    from run_matched_batch import check_report,child,evidence_hashes
    from run_schedule_path_control import inspect_control
    from run_policy_experiment import inspect_policy
    p,matched=supplement.load_protocol(repo);root=repo/'results/runs'
    batch=child(root,manifest['batch']);state=read(batch/'batch.json');registered=supplement.plan()
    if state['outcome']!='failed' or len(state['runs'])!=7 or len(state['attempts'])!=8:raise ValueError('Stopped batch identity differs')
    if state['protocol_sha256']!=sha(repo/'supplement_protocol.json') or state['plan']!=registered:raise ValueError('Registered protocol/plan differs')
    if [a['status'] for a in state['attempts']]!=['passed']*7+['failed']:raise ValueError('Attempt state differs')
    reports=[]
    for index,record in enumerate(state['runs']):
        item=registered[index]
        if {k:record[k] for k in item}!=item:raise ValueError('Accepted cell order differs')
        folder=child(root,record['folder'])
        for key,hkey in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:
            if evidence_hashes(child(root,record[key]))!=record[hkey]:raise ValueError('Accepted evidence differs')
        report=inspect_control(folder) if item['stage']=='controls' else inspect_policy(folder)
        check=supplement.control_record(repo,folder,item,report) if item['stage']=='controls' else check_report(repo,folder,item,matched,report,source_integrity_audit)
        if check!=record:raise ValueError('Independent accepted record differs: '+folder.name)
        reports.append(dict(identity=item,status='accepted',folder=folder.name,trial=record['trial'],report=report))
    failed=state['attempts'][-1];item=registered[7]
    if {k:failed[k] for k in item}!=item:raise ValueError('Failed cell order differs')
    folder=child(root,failed['folder']);report=inspect_policy(folder);trial=read(folder/'policy.json')['trial']
    if report['screen_failures']!=['collector_quality']:raise ValueError('Failed screen differs')
    try:check_report(repo,folder,item,matched,report,source_integrity_audit)
    except ValueError as e:rejection=str(e)
    else:raise ValueError('Failed cell unexpectedly passed')
    reports.append(dict(identity=item,status='failed',folder=folder.name,trial=trial,report=report,rejection=rejection,
        source_audit=source_integrity_audit(root/trial)))
    diagnostics=[]
    for record in reports:
        folder=root/record['folder'];trial=root/record['trial'];native=read(trial/'sender-native.json')
        start=native['start_monotonic_ns']/1e9;finish=native['end_monotonic_ns']/1e9
        raw=lines(folder/'samples.jsonl');queues={q:intervals(raw,q,start,finish) for q in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']}
        for q,d in queues.items():
            expected_q=record['report']['collector']['qdiscs'][q]
            if len(d['invalid_intervals'])!=expected_q['invalid_intervals'] or len(d['failed_queries'])!=expected_q['failed_queries']:
                raise ValueError('Independent interval diagnosis disagrees with frozen inspector')
        diagnostics.append(dict(identity=record['identity'],status=record['status'],folder=record['folder'],trial=record['trial'],
            native_clock=dict(start_monotonic_s=start,start_epoch_s=native['start_wall_epoch_s'],duration_s=finish-start),
            queues=queues,actions=actions(folder,start) if (folder/'decisions.jsonl').exists() else []))
    for name,digest in manifest['files_sha256'].items():
        if sha(repo/name)!=digest:raise ValueError('Audit changed original extracted evidence')
    summary=dict(archive_sha256=expected,archive_bytes=archive.stat().st_size,extracted=extracted,
        export_files_verified=828,frozen_sources_verified=len(trusted_pins),accepted_records_exactly_reproduced=7,
        controls=6,accepted_bursty=1,failed_bursty=1,complete_extra_policy_blocks=0,model_sha256=sha(repo/'selected_tree.json'),
        raw_changed=False,failed_folder=folder.name,reports=reports,diagnostics=diagnostics)
    if original_repo:summary['original_action_audit']=original_action_audit(original_repo)
    save(output/'audit.json',summary)
    failed_diag=diagnostics[-1]
    print(json.dumps(dict(output=str(output),files_verified=828,accepted_reproduced=7,
        failed_screen=reports[-1]['report']['screen_failures'],failed_diagnostics=failed_diag),indent=2))
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--extract',required=True);p.add_argument('--output',required=True);p.add_argument('--published',required=True)
    p.add_argument('--original-repo')
    a=p.parse_args();audit(a.archive,a.sha256,a.extract,a.output,a.published,a.original_repo)
