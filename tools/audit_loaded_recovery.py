"""Read-only audit of the full checkpoint after the loaded recovery failure."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse,hashlib,json,re,statistics,sys,tarfile
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_stopped_supplement import read,lines,sha,save,extract,intervals,actions,original_action_audit

def resources(path,native,tz):
    fields=None;rows=[]
    for line in Path(path).read_text().splitlines():
        p=line.split()
        if p[:3]==['r','b','swpd']:fields=p[:-1];continue
        if fields and len(p)==len(fields)+2 and re.fullmatch(r'\d{4}-\d\d-\d\d',p[-2]):
            stamp=datetime.fromisoformat(p[-2]+'T'+p[-1]).replace(tzinfo=tz).timestamp()
            row={name:float(x) for name,x in zip(fields,p[:-2])}
            row.update(source_s=stamp-native['start_wall_epoch_s'],epoch_s=stamp,local_time=p[-2]+' '+p[-1])
            rows.append(row)
    # The first vmstat data line describes averages since boot, not a one-second window.
    selected=[r for r in rows[1:] if 0<=r['source_s']<=60]
    return dict(rows=rows,traffic_rows=len(selected),
        mean_user_system_percent=statistics.mean(r['us']+r['sy'] for r in selected),
        max_user_system_percent=max(r['us']+r['sy'] for r in selected),
        zero_idle_windows=sum(r['id']==0 for r in selected),max_runnable=max(r['r'] for r in selected),
        max_swap_in=max(r['si'] for r in selected),max_swap_out=max(r['so'] for r in selected),
        scope='Guest one-second resource intervals; not precise host scheduling attribution')

def audit(repo,published,output,archive,original_archive):
    repo=Path(repo).resolve();published=Path(published).resolve();output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    if sha(archive)!='7ea47c86690aca1b8767577a0accaa9e16797d1c0e8115e0c5494350bfec64cc':raise ValueError('Full archive SHA differs')
    trusted=read(published/'evidence/recovery-install-manifest.json')
    pins=dict(trusted['unchanged_files'],**trusted['files'])
    for name,digest in pins.items():
        if sha(repo/name)!=digest:raise ValueError('Current frozen source changed: '+name)
    sys.path.insert(0,str(repo))
    import run_supplement_recovery as r
    import run_supplement_batch as initial
    from run_matched_batch import check_report,evidence_hashes,COMMON_SOURCES
    from run_policy_experiment import inspect_policy
    from inspect_experiment import queue_summary
    from source_integrity import source_integrity_audit
    from traffic_scenarios import continuous_schedule
    p,matched=r.load_protocol(repo);parent=r.verify_parent(repo,p)
    root=repo/'results/runs'
    registry=read(root/'supplement-recovery-registry-v1.json')
    batch=r.child(root,registry['batch']);state=read(batch/'batch.json')
    if (state['outcome']!='failed' or state['runs'] or len(state['attempts'])!=1
        or state['attempts'][0]['status']!='failed' or state['plan']!=r.plan()
        or state['protocol_sha256']!=sha(repo/'supplement_recovery_protocol.json')):raise ValueError('Recovery state differs')
    for name,digest in p['additional_source_sha256'].items():
        if sha(batch/name)!=digest:raise ValueError('Captured recovery source changed')
    if sha(batch/'supplement_recovery_protocol.json')!=state['protocol_sha256']:raise ValueError('Captured recovery registration changed')
    ready=state['readiness'][0];ready_folder=batch/ready['folder']
    if len(state['readiness'])!=1 or ready['status']!='passed' or evidence_hashes(ready_folder)!=ready['evidence_sha256']:
        raise ValueError('Readiness record changed')
    ready_meta=read(ready_folder/'readiness.json');ready_rows=lines(ready_folder/'samples.jsonl')
    ready_q={q:queue_summary(ready_rows,q) for q in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']}
    if ready_q!=ready_meta['report']['queues'] or ready_meta['report']['screen_failures']:raise ValueError('Readiness quality differs')
    ledger=read(root/'readiness-interruption-review-v1.json');review_folder=r.child(root,ledger['review'])
    review=read(review_folder/'review.json');interrupted=r.child(root,ledger['old_batch'])
    if (review['status']!='archived_pointers_raw_unchanged' or review['attempts'] or review['accepted']
        or evidence_hashes(interrupted)!=review['old_batch_files_sha256']
        or sha(review_folder/'registry-before.json')!=review['coordination_sha256']['registry']
        or sha(review_folder/'active-pointer-before.txt')!=review['coordination_sha256']['active_pointer']
        or review['review_helper_sha256']!=sha(published/'tools/review_interrupted_readiness.py')):
        raise ValueError('Interruption review/raw preservation differs')
    attempt=state['attempts'][0];item=r.plan()[0]
    if {k:attempt[k] for k in item}!=item:raise ValueError('Recovery cell differs')
    folder=r.child(root,attempt['folder']);meta=read(folder/'policy.json');trial=r.child(root,meta['trial'])
    trial_meta=read(trial/'metadata.json');native=read(trial/'sender-native.json');receiver=read(trial/'receiver-native.json')
    expected=continuous_schedule('bursty',11500000,60,44)
    if (meta['planned_segments']!=expected or trial_meta['traffic_plan']!=expected
        or trial_meta['seed']!=44 or trial_meta['scenario']!='bursty'
        or trial_meta['trial_context'].get('parent')!=folder.name):raise ValueError('Source schedule/context differs')
    for name in COMMON_SOURCES:
        if meta['source_sha256'][name]!=matched['source_sha256'][name] or sha(folder/name)!=matched['source_sha256'][name]:
            raise ValueError('Captured common source differs')
    report=inspect_policy(folder)
    saved_review=next((batch/'reviews').glob('*.json'))
    if read(saved_review)!=report:raise ValueError('Independent failed inspection differs from guest review')
    if report['screen_failures']!=['udp_error','collector_quality']:raise ValueError('Failed screens differ')
    try:check_report(repo,folder,item,matched,report,source_integrity_audit)
    except ValueError as error:rejection=str(error)
    else:raise ValueError('Failed recovery unexpectedly passed')
    source_audit=source_integrity_audit(trial)
    start=native['start_monotonic_ns']/1e9;finish=native['end_monotonic_ns']/1e9
    raw=lines(folder/'samples.jsonl');queues={q:intervals(raw,q,start,finish) for q in ready_q}
    for q,info in queues.items():
        if len(info['invalid_intervals'])!=report['collector']['qdiscs'][q]['invalid_intervals'] or len(info['failed_queries'])!=report['collector']['qdiscs'][q]['failed_queries']:
            raise ValueError('Independent interval classification differs')
    events=actions(folder,start);decisions=lines(folder/'decisions.jsonl')
    resource=resources(trial/'vmstat.txt',native,datetime.fromisoformat(trial_meta['started']).tzinfo)
    # Compare the authoritative archive, not a checkout that acquired local bytecode.
    if sha(original_archive)!='e8f2e4e4294d35918c8b0d2e37fa79e92366732a19b0a12daad6f7c2a521b8e3':raise ValueError('Original archive SHA differs')
    original_files=[];appended_logs=[]
    allowed_append={'results/runs/session-20261114-235538-primary-continuous/controller.log',
        'results/runs/session-20261114-235538-primary-continuous/mininet.log'}
    with tarfile.open(original_archive) as tf:
        for member in tf:
            if not member.isfile():continue
            rel=Path(member.name).relative_to('342-proactive-sdn');original_files.append(rel.as_posix())
            old=tf.extractfile(member).read();new=(repo/rel).read_bytes()
            if old==new:continue
            if rel.as_posix() not in allowed_append or not new.startswith(old):raise ValueError('Original evidence changed: '+rel.as_posix())
            appended_logs.append(dict(path=rel.as_posix(),original_bytes=len(old),current_bytes=len(new),original_prefix_sha256=hashlib.sha256(old).hexdigest(),append_only=True))
    if len(original_files)!=9818 or len(appended_logs)!=2:raise ValueError('Unexpected original archive comparison counts')
    original_actions=original_action_audit(repo)
    proof=dict(archive_sha256=sha(archive),archive_bytes=Path(archive).stat().st_size,
        current_regular_files=sum(path.is_file() for path in repo.rglob('*')),frozen_source_files_verified=len(pins),
        original_checkpoint_files_byte_identical=len(original_files)-len(appended_logs),appended_session_logs=appended_logs,
        original_checkpoint_files_preserved=len(original_files),parent=parent,interruption_review_verified=True,
        recovery=dict(batch=batch.name,outcome=state['outcome'],accepted=0,attempted=1,complete_blocks=0),
        readiness=dict(folder=ready_folder.relative_to(repo).as_posix(),reported=ready_meta,independent_queue_summary=ready_q),
        failed=dict(folder=folder.name,trial=trial.name,report=report,source_audit=source_audit,
            queues=queues,actions=events,rejection=rejection,raw_evidence_sha256=evidence_hashes(folder),
            trial_evidence_sha256=evidence_hashes(trial),resources=resource,
            decision_statuses=dict(Counter(d.get('status') for d in decisions)),
            denied_reasons=dict(Counter((d.get('action')or{}).get('rejection') for d in decisions if (d.get('action')or{}).get('applied') is False)),
            packet_accounting=dict(sent=native['sent_packets'],unique_received=receiver['unique_packets'],
                missing=native['sent_packets']-receiver['unique_packets'],root_drops=report['queue_drop_deltas'],udp_errors=report['trial']['udp_error_deltas'],
                scope='Root drops include probes/control; UDP receive-buffer and input-error counters overlap. No unsupported cross-layer sum.')),
        original_action_audit=original_actions,source_or_quality_settings_changed=False)
    save(output/'audit.json',proof)
    one=queues['s2-eth2'];print(json.dumps(dict(output=str(output),regular_files=proof['current_regular_files'],
        original_files_unchanged=proof['original_checkpoint_files_byte_identical'],appended_session_logs=appended_logs,frozen_sources_verified=len(pins),failed_screens=report['screen_failures'],
        udp_errors=report['trial']['udp_error_deltas'],packet_accounting=proof['failed']['packet_accounting'],
        source_pacing_discard_percent=source_audit['discard_percent'],source_max_pacer_gap_s=native['max_pacer_gap_s'],
        bad_intervals_one_representative_queue=one,actions=events,denials=proof['failed']['denied_reasons'],
        resource_summary={k:v for k,v in resource.items() if k!='rows'}),indent=2))
    return proof

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    paths=parser.add_mutually_exclusive_group(required=True)
    paths.add_argument('--repo',type=Path,help='Existing safely extracted guest repository')
    paths.add_argument('--extract',type=Path,help='New directory for safe extraction')
    parser.add_argument('--published',type=Path,default=root)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path,default=root/'evidence/raw/342-sdn-checkpoint-20261120-223910.tar.gz')
    parser.add_argument('--original-archive',type=Path,default=root/'evidence/raw/342-sdn-checkpoint-20261116-214839.tar.gz')
    args=parser.parse_args()
    if args.extract:
        extract(args.archive,args.extract,'7ea47c86690aca1b8767577a0accaa9e16797d1c0e8115e0c5494350bfec64cc')
        args.repo=args.extract/'342-proactive-sdn'
    audit(args.repo,args.published,args.output,args.archive,args.original_archive)
