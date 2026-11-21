"""Audit the stopped follow-up without changing its failed state or issuing a resume receipt."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import csv
import json
import sys

sys.dont_write_bytecode=True
from audit_stopped_supplement import read,lines,sha,save,extract,intervals,actions,original_action_audit
from audit_loaded_recovery import resources

ARCHIVE_SHA='a4c9f96e7a5029d7a28d2abf1ef86e7a62c84722e23eb0c585e286ab4f78c64d'


def require(ok,message):
    if not ok:raise ValueError(message)


def audit(repo,published,output,archive):
    repo=Path(repo).resolve();published=Path(published).resolve();output=Path(output).resolve()
    require(not output.is_relative_to(repo),'Derived audit must stay outside raw extraction')
    output.mkdir(parents=True,exist_ok=False)
    require(sha(archive)==ARCHIVE_SHA,'Final checkpoint checksum differs')
    manifest=read(published/'evidence/bursty-followup-install-manifest.json')
    pins=dict(manifest['unchanged_files'],**manifest['files'])
    require(len(pins)==85,'Installed pin count differs')
    for name,digest in pins.items():require(sha(repo/name)==digest,'Installed frozen file changed: '+name)
    testbed={name:sha(published/name) for name in ['topology.py','diamond_controller.py']}
    for name,digest in testbed.items():require(sha(repo/name)==digest,'Original topology/controller changed: '+name)
    sys.path.insert(0,str(repo))
    import run_bursty_followup as f
    from run_matched_batch import load_protocol,check_report,child,evidence_hashes,COMMON_SOURCES,ML_SOURCES
    from run_policy_experiment import inspect_policy
    from source_integrity import source_integrity_audit
    from continuous_udp import canonical_summaries
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    from traffic_scenarios import continuous_schedule

    p=f.load_protocol(repo);parent=f.verify_parent(repo,p);matched=load_protocol(repo)
    root=repo/'results/runs';batch=child(root,read(root/f.REGISTRY)['batch']);state=read(batch/'batch.json')
    original_hashes=evidence_hashes(batch)
    require(state['outcome']=='failed' and len(state['attempts'])==7 and len(state['runs'])==6
            and state['plan']==f.plan() and [x['status'] for x in state['attempts']]==['passed']*6+['failed']
            and state['protocol_sha256']==sha(repo/f.PROTOCOL)==sha(batch/f.PROTOCOL),
            'Stopped follow-up state differs')
    require('Matched trial quality/restoration failed' in state['error'],'Unexpected stopped error')
    for name,digest in dict(p['frozen_source_sha256'],**p['additional_source_sha256']).items():
        require(sha(batch/name)==digest,'Captured source changed: '+name)
    # Bind the previous independent block review without editing mutable batch.json.
    previous=read(published/'results/bursty-followup-v1/seed51/audit.json')
    receipt=read(published/'results/bursty-followup-v1/seed51/review-receipt.json')
    require(previous['batch']==batch.name and receipt['accepted_cells']==4
            and receipt['batch_sha256']==previous['batch_sha256']
            and receipt['audit_sha256']==sha(published/'results/bursty-followup-v1/seed51/audit.json')
            and len(state['independent_reviews'])==1,'Seed51 independent gate differs')
    binding=state['independent_reviews'][0]
    require(binding['sha256']==sha(published/'results/bursty-followup-v1/seed51/review-receipt.json')
            and binding['checkpoint_sha256']==receipt['checkpoint_sha256'] and binding['accepted_cells']==4,
            'Recorded seed51 receipt binding differs')
    for old_result,record in zip(previous['results'],state['runs'][:4]):
        require(record['folder']==old_result['folder'] and record['trial']==old_result['trial']
                and evidence_hashes(root/record['folder'])==old_result['raw_policy_sha256']
                and evidence_hashes(root/record['trial'])==old_result['raw_trial_sha256'],
                'Previously reviewed seed51 evidence changed')
    require(len(state['readiness'])==2,'Expected two readiness checks')
    readiness=[]
    for index,record in enumerate(state['readiness']):
        saved=batch/record['folder'];meta=read(saved/'readiness.json')
        queues={q:queue_summary(lines(saved/'samples.jsonl'),q) for q in QUEUES}
        env=read(batch/('environment-'+str(index))/'environment.json')
        require(record['status']=='passed' and evidence_hashes(saved)==record['evidence_sha256']
                and meta['outcome']=='passed' and meta['no_traffic_generated'] is True
                and not meta['report']['screen_failures'] and queues==meta['report']['queues']
                and 57<=meta['report']['elapsed_s']<=66 and env['cpu_count']==1 and env['clocksource']=='tsc',
                'Readiness/environment evidence differs')
        require(all(not q['failed_queries'] and not q['invalid_intervals'] and q['interval_count']>=215
                    for q in queues.values()),'Readiness quality replay failed')
        readiness.append(dict(block=index,environment=env,report=meta))
    attempts=[];table=[]
    for index,(item,a) in enumerate(zip(f.plan()[:7],state['attempts'])):
        require({k:a[k] for k in item}==item,'Attempt identity/order differs')
        folder=child(root,a['folder']);trial=child(root,a['trial'])
        meta=read(folder/'policy.json');native_meta=read(trial/'metadata.json')
        expected=continuous_schedule('bursty',11500000,60,item['seed'])
        require(all(meta[k]==item[k] for k in ['policy','scenario','seed','duration'])
                and meta['requested_scale_bps']==11500000 and meta['planned_segments']==expected
                and native_meta['traffic_plan']==expected and meta['trial']==trial.name,
                'Source/policy identity differs')
        for name in COMMON_SOURCES+(ML_SOURCES if item['policy']=='ml' else []):
            require(meta['source_sha256'][name]==matched['source_sha256'][name]
                    and sha(folder/name)==matched['source_sha256'][name],'Captured trial source changed')
        require(sha(batch/a['review'])==a['review_sha256'],'Saved review changed')
        report=inspect_policy(folder);require(report==read(batch/a['review']),'Guest review does not reproduce')
        sender=read(trial/'sender-native.json');receiver=read(trial/'receiver-native.json')
        client,server=canonical_summaries(sender,receiver)
        require(client==read(trial/'client.json') and server==read(trial/'server.json'),'Native summaries differ')
        source=source_integrity_audit(trial)
        start=sender['start_monotonic_ns']/1e9;finish=sender['end_monotonic_ns']/1e9
        raw=lines(folder/'samples.jsonl');qdiscs=report['collector']['qdiscs']
        independent={q:intervals(raw,q,start,finish) for q in QUEUES}
        for q,info in independent.items():
            require(len(info['invalid_intervals'])==qdiscs[q]['invalid_intervals']
                    and len(info['failed_queries'])==qdiscs[q]['failed_queries'],'Independent collector audit differs')
        require(not report['restoration']['failures'] and report['route_restoration']['verified']
                and not report['route_restoration']['failures'],'Restoration failed')
        rejection=None
        if index<6:
            require(check_report(repo,folder,item,matched,report,source_integrity_audit)==state['runs'][index],
                    'Accepted common quality/accounting record differs')
        else:
            require(report['screen_failures']==['collector_quality'],'Unexpected failure screen')
            try:check_report(repo,folder,item,matched,report,source_integrity_audit)
            except ValueError as error:rejection=str(error)
            require(rejection=='Matched trial quality/restoration failed','Common rejection no longer reproduces')
        decisions=lines(folder/'decisions.jsonl');events=actions(folder,start)
        denied=dict(Counter((d.get('action') or {}).get('rejection') for d in decisions
                           if (d.get('action') or {}).get('applied') is False))
        resource=resources(trial/'vmstat.txt',sender,datetime.fromisoformat(native_meta['started']).tzinfo)
        result=dict(identity=item,status=a['status'],folder=folder.name,trial=trial.name,report=report,
            source_audit=source,independent_collector=independent,actions=events,denied_reasons=denied,
            resources=resource,decision_statuses=dict(Counter(d.get('status') for d in decisions)),
            rejection=rejection,raw_policy_sha256=evidence_hashes(folder),raw_trial_sha256=evidence_hashes(trial),
            packet_accounting=dict(sent=sender['sent_packets'],unique_received=receiver['unique_packets'],
                missing=sender['sent_packets']-receiver['unique_packets'],root_drops=report['queue_drop_deltas'],
                udp_errors=report['trial']['udp_error_deltas'],scope='Sequence loss, root drops and endpoint counters remain separate.'))
        attempts.append(result);one=next(iter(qdiscs.values()))
        table.append(dict(seed=item['seed'],policy=item['policy'],status=a['status'],sender_mbps=report['sender_mbps'],
            receiver_mbps=report['receiver_mbps'],udp_loss_percent=report['udp_loss_percent'],screen_failures=';'.join(report['screen_failures']),
            actions=len(events),denials=len(report['denied_requests']),denial_reasons=json.dumps(denied,sort_keys=True),
            source_discard_percent=source['discard_percent'],max_pacer_gap_ms=1000*sender['max_pacer_gap_s'],
            failed_queries_per_queue=one['failed_queries'],invalid_intervals_per_queue=one['invalid_intervals'],
            query_max_ms=1000*one['query_duration_s']['max'],collector_cpu_percent_one_core=report['overhead']['collector_cpu_percent_one_core'],
            guest_mean_cpu_percent=resource['mean_user_system_percent']))
    owned={a[k] for a in state['attempts'] for k in ['folder','trial']};observed=set()
    for folder in root.iterdir():
        if not folder.is_dir():continue
        for name in ['policy.json','metadata.json','control.json','component.json']:
            path=folder/name
            if path.is_file() and read(path).get('seed') in f.SETTINGS['seeds']:
                require(folder.name in owned,'Unregistered reserved-seed trial');observed.add(folder.name)
    require(observed==owned and set(state['new_raw_folders'])==
            {a[k] for a in state['attempts'][4:] for k in ['folder','trial']},'Missing/hidden attempt reference')
    try:f.validate_resume(repo,batch,state,p)
    except ValueError as error:resume_rejection=str(error)
    else:raise ValueError('Failed batch unexpectedly resumable')
    original=original_action_audit(repo)
    require(evidence_hashes(batch)==original_hashes,'Audit changed failed batch')
    failed_raw=lines(root/attempts[-1]['folder']/'samples.jsonl')
    source_start=read(root/attempts[-1]['trial']/'sender-native.json')['start_monotonic_ns']/1e9
    invalid_samples={x['sample'] for x in attempts[-1]['independent_collector']['s2-eth2']['invalid_intervals']}
    poll_cycles=[dict(sample=r['sample'],source_start_s=r['monotonic_start']-source_start,
        cycle_ms=1000*(r['monotonic_end']-r['monotonic_start']),
        start_lateness_ms=1000*(r['monotonic_start']-r['scheduled']),
        completion_minus_next_deadline_ms=1000*(r['monotonic_end']-r['scheduled']-r['requested_interval']),
        tc_query_ms=1000*(r['tc_end']-r['tc_start']),skipped_before_sample=r.get('skipped_before_sample',0))
        for r in failed_raw if r['sample'] in invalid_samples or r['sample']+1 in invalid_samples]
    private=[x.relative_to(repo).as_posix() for x in repo.rglob('*') if x.is_file()
             and (x.suffix.lower() in ['.pdf','.docx','.pem','.key','.env']
                  or any(word in x.name.lower() for word in ['password','credential','email']))]
    require(not private,'Potential private attachment/key files need review')
    proof=dict(archive_sha256=ARCHIVE_SHA,archive_bytes=Path(archive).stat().st_size,
        regular_files=sum(x.is_file() for x in repo.rglob('*')),installed_source_artifact_pins_verified=85,
        unchanged_original_testbed_sha256=testbed,failed_poll_cycles=poll_cycles,
        batch=batch.name,batch_outcome='failed',scheduled=16,attempted=7,quality_valid_individual_trials=6,
        failed_trials=1,unattempted=9,complete_four_policy_blocks=1,complete_seeds=[51],incomplete_seeds=[52],
        unattempted_seeds=[53,54],parent=parent,readiness=readiness,guest_reviews_exactly_reproduced=7,
        previous_seed51_unchanged=True,attempts=attempts,summary=table,original_action_audit=original,
        resume_rejection=resume_rejection,raw_unchanged_after_audit=True,new_acquisition_closed=True,
        source_model_or_quality_rule_changed=False,
        interpretation='Only seed51 is a complete additional matched block; seed52 is partial. Do not pool partial/quality-invalid data into four-policy means. Preserve original benchmark, all adverse/no-action outcomes, failure and attrition. No retry/replacement or causal host/root-cause fix claim.')
    save(output/'audit.json',proof)
    with (output/'attempts.csv').open('x',newline='',encoding='utf-8') as file:
        w=csv.DictWriter(file,fieldnames=table[0]);w.writeheader();w.writerows(table)
    print(json.dumps(dict(output=str(output),scheduled=16,attempted=7,valid=6,failed=1,unattempted=9,
        complete_blocks=1,source_pins=85,guest_reviews_reproduced=7,rows=table,
        failed_collector=attempts[-1]['independent_collector']['s2-eth2'],
        failed_poll_cycles=poll_cycles,
        failed_resources={k:v for k,v in attempts[-1]['resources'].items() if k!='rows'},
        seed52_denials=[x['denied_reasons'] for x in attempts[4:]],
        seed52_early_warning_action=attempts[5]['actions']),indent=2))
    return proof


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
    where=p.add_mutually_exclusive_group(required=True);where.add_argument('--repo',type=Path);where.add_argument('--extract',type=Path)
    p.add_argument('--published',type=Path,default=root);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--archive',type=Path,default=root/'evidence/raw/342-sdn-checkpoint-20261121-164948.tar.gz')
    a=p.parse_args()
    if a.extract:extract(a.archive,a.extract,ARCHIVE_SHA);a.repo=a.extract/'342-proactive-sdn'
    audit(a.repo,a.published,a.output,a.archive)
