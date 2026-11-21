"""Read-only block review of the registered bursty follow-up; issue exact-state receipt."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import csv
import json
import sys

sys.dont_write_bytecode = True
from audit_stopped_supplement import read, lines, sha, save, extract, intervals, actions, original_action_audit
from audit_loaded_recovery import resources


def require(ok, message):
    if not ok:
        raise ValueError(message)


def audit(repo,published,output,archive,expected):
    repo=Path(repo).resolve(); published=Path(published).resolve(); output=Path(output).resolve()
    require(not output.is_relative_to(repo), 'Audit output must be outside raw evidence')
    output.mkdir(parents=True,exist_ok=False)
    require(len(expected)==64 and sha(archive)==expected, 'Checkpoint checksum differs')
    manifest=read(published/'evidence/bursty-followup-install-manifest.json')
    pins=dict(manifest['unchanged_files'],**manifest['files'])
    require(len(pins)==85, 'Installed source/artifact count differs')
    for name,digest in pins.items():
        require(sha(repo/name)==digest, 'Installed frozen file changed: '+name)
    sys.path.insert(0,str(repo))
    import run_bursty_followup as f
    from run_matched_batch import load_protocol,check_report,child,evidence_hashes
    from run_policy_experiment import inspect_policy
    from source_integrity import source_integrity_audit
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    from continuous_udp import canonical_summaries
    from traffic_scenarios import continuous_schedule
    from build_trace_dataset import intervals as feature_intervals,detect_events

    p=f.load_protocol(repo);parent=f.verify_parent(repo,p)
    root=repo/'results/runs';batch=child(root,read(root/f.REGISTRY)['batch']);state=read(batch/'batch.json')
    f.validate_resume(repo,batch,state,p)
    count=len(state['runs'])
    require(count in [4,8,12,16] and state['outcome']==('completed' if count==16 else 'paused'),
            'Incomplete or failed block cannot authorize continuation')
    require(len(state['readiness'])==count//4 and len(state['independent_reviews'])==count//4-1,
            'Readiness/independent review gate count differs')
    readiness=[]
    for i,r in enumerate(state['readiness']):
        saved=batch/r['folder'];ready=read(saved/'readiness.json')
        independent={q:queue_summary(lines(saved/'samples.jsonl'),q) for q in QUEUES}
        env=read(batch/('environment-'+str(i))/'environment.json')
        require(env['cpu_count']==1 and env['clocksource']=='tsc', 'Environment differs')
        require(ready['outcome']=='passed' and ready['no_traffic_generated'] is True
                and not ready['report']['screen_failures'] and independent==ready['report']['queues']
                and 57<=ready['report']['elapsed_s']<=66 and all(not q['invalid_intervals']
                and not q['failed_queries'] and q['interval_count']>=215 for q in independent.values()),
                'Readiness quality replay differs')
        readiness.append(dict(block=i,environment=env,report=ready))
    matched=load_protocol(repo);results=[];rows=[];fixed_events={}
    # Original/common inspectors assess network validity, not whether a policy won.
    for item,record,attempt in zip(f.plan()[:count],state['runs'],state['attempts']):
        require({k:attempt[k] for k in item}==item, 'Attempt identity differs')
        folder=child(root,record['folder']);trial=child(root,record['trial'])
        report=inspect_policy(folder)
        require(report==read(batch/attempt['review']), 'Guest policy review replay differs')
        replay_record=check_report(repo,folder,item,matched,report,source_integrity_audit)
        require(replay_record==record, 'Common quality/accounting record differs')
        sender=read(trial/'sender-native.json');receiver=read(trial/'receiver-native.json')
        client,server=canonical_summaries(sender,receiver)
        require(client==read(trial/'client.json') and server==read(trial/'server.json'), 'Native summaries differ')
        meta=read(trial/'metadata.json')
        require(meta['traffic_plan']==continuous_schedule('bursty',11500000,60,item['seed']), 'Source schedule differs')
        start=sender['start_monotonic_ns']/1e9;finish=sender['end_monotonic_ns']/1e9
        raw=lines(folder/'samples.jsonl')
        collector={q:intervals(raw,q,start,finish) for q in QUEUES}
        require(all(not v['failed_queries'] and not v['invalid_intervals'] for v in collector.values()),
                'Independent collector interval classification failed')
        require(all(v==0 for host in report['trial']['udp_error_deltas'].values() for v in host.values()),
                'Endpoint UDP error appeared')
        decisions=lines(folder/'decisions.jsonl');events=actions(folder,start)
        require(len(events)==len(report['applied_actions']), 'Applied action audit differs')
        if item['policy']=='fixed':
            fixed_events[item['seed']]=[dict(e,onset_since_source_s=e['onset']-start,
                confirmation_since_source_s=e['confirmed_available']-start)
                for e in detect_events(feature_intervals(raw,start,finish),.85,1.)]
        first_ready=next((dict(d,source_s=d['decision_at']-start) for d in decisions if d.get('status')=='ready'),None)
        resource=resources(trial/'vmstat.txt',sender,datetime.fromisoformat(meta['started']).tzinfo)
        stats=report['collector']['stats'];q=next(iter(report['collector']['qdiscs'].values()))
        result=dict(identity=item,folder=folder.name,trial=trial.name,report=report,
            source_audit=source_integrity_audit(trial),independent_collector=collector,actions=events,
            decision_statuses=dict(Counter(d.get('status') for d in decisions)),first_ready_decision=first_ready,
            resources=resource,raw_policy_sha256=evidence_hashes(folder),raw_trial_sha256=evidence_hashes(trial))
        results.append(result)
        rows.append(dict(seed=item['seed'],policy=item['policy'],sender_mbps=report['sender_mbps'],
            receiver_mbps=report['receiver_mbps'],udp_loss_percent=report['udp_loss_percent'],
            source_discard_percent=result['source_audit']['discard_percent'],max_pacer_gap_ms=1000*sender['max_pacer_gap_s'],
            bottleneck_drops=report['trial']['queue_drop_deltas']['s2-eth2'],
            traffic_probe_rtt_median_ms=report['rtt']['traffic_only']['milliseconds']['median'],
            traffic_probe_rtt_p95_ms=report['rtt']['traffic_only']['milliseconds']['p95'],
            actions=len(events),denials=len(report['denied_requests']),
            action_program_start_source_s=events[0]['program_start_s'] if events else None,
            action_decision_source_s=events[0]['decision_s'] if events else None,
            program_start_measurement_age_ms=1000*events[0]['program_start_measurement_age_s'] if events else None,
            full_decision_to_readback_ms=1000*events[0]['full_decision_to_readback_s'] if events else None,
            model_inference_calls=(report['inference'] or {}).get('calls'),
            first_ready_utilization=(first_ready or {}).get('features',{}).get('utilization'),
            collector_cpu_percent_one_core=report['overhead']['collector_cpu_percent_one_core'],
            policy_cpu_percent_one_core=report['overhead']['policy_thread_cpu_percent_one_core'],
            query_max_ms=1000*q['query_duration_s']['max'],query_p95_ms=1000*q['query_duration_s']['p95'],
            guest_mean_cpu_percent=resource['mean_user_system_percent']))
    # Verify there are no extra/hidden runs under reserved seeds outside the ledger.
    owned={r[k] for r in state['runs'] for k in ['folder','trial']}
    observed=set()
    for folder in root.iterdir():
        if not folder.is_dir():continue
        for name in ['policy.json','metadata.json','control.json','component.json']:
            path=folder/name
            if path.is_file() and read(path).get('seed') in f.SETTINGS['seeds']:
                require(folder.name in owned, 'Unregistered reserved-seed acquisition: '+folder.name)
                observed.add(folder.name)
    require(observed==owned, 'Registered reserved-seed folders missing')
    original=original_action_audit(repo)
    f.validate_resume(repo,batch,state,p)
    proof=dict(checkpoint_sha256=expected,archive_bytes=Path(archive).stat().st_size,
        batch=batch.name,batch_sha256=sha(batch/'batch.json'),outcome=state['outcome'],
        installed_source_artifact_pins_verified=85,parent=parent,guest_reviews_exactly_reproduced=count,
        accepted_cells=count,all_outcomes_retained=True,readiness=readiness,results=results,summary=rows,
        fixed_reference_events=fixed_events,original_action_audit=original,raw_unchanged_after_review=True,
        interpretation='Post-failure four-seed follow-up, kept separate from original benchmark and stopped cohorts. One-way actions, no required benefit. Fixed-reference event timing is descriptive alignment across separate matched runs, not prediction labels on intervened traces.')
    save(output/'audit.json',proof)
    with (output/'results.csv').open('x',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    if count<16:
        receipt=dict(kind='independent_bursty_followup_block_review',batch=batch.name,
            accepted_cells=count,batch_sha256=proof['batch_sha256'],quality_passed=True,all_outcomes_retained=True,
            checkpoint_sha256=expected,audit_sha256=sha(output/'audit.json'),protocol_sha256=sha(repo/f.PROTOCOL))
        save(output/'review-receipt.json',receipt)
        f.check_block_review(output/'review-receipt.json',batch,state)
    print(json.dumps(dict(accepted_cells=count,guest_reviews_reproduced=count,source_pins_verified=85,
        receipt=str(output/'review-receipt.json') if count<16 else None,
        batch_sha256=proof['batch_sha256'],rows=rows,fixed_reference_events=fixed_events),indent=2))
    return proof


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    where=parser.add_mutually_exclusive_group(required=True)
    where.add_argument('--repo',type=Path);where.add_argument('--extract',type=Path)
    parser.add_argument('--published',type=Path,default=root)
    parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    if a.extract:
        extract(a.archive,a.extract,a.expected_sha256);a.repo=a.extract/'342-proactive-sdn'
    audit(a.repo,a.published,a.output,a.archive,a.expected_sha256)
