"""Replay scientific inspections from verified curated inputs; no full-backup comparison."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import csv
import gzip
import json
import re
import shutil
import sys
import tarfile

sys.dont_write_bytecode = True
from audit_stopped_supplement import read, lines, sha, save, intervals, actions, original_action_audit
from audit_loaded_recovery import resources

ARCHIVE_SHA = '7d4c4fdcabe24b952e69fd0a078382ffbd34f0416a78ae45edd41fb958267c16'
PREVIOUS_SHA = 'b851a04ab1762953dea2b36ae64268373bc961b4cef6ce490d56ee70b25f4005'
PROTOCOL_SHA = '48d4c2ddade50ee3266c1bfa811b3c2f8cff622fffa63dcb11678b4ec312f237'


def require(ok, message):
    if not ok:
        raise ValueError(message)




def audit(repo, published, output):
    repo = Path(repo).resolve(); published = Path(published).resolve(); output = Path(output).resolve()
    require(not output.is_relative_to(repo), 'Derived audit must be outside raw extraction')
    output.mkdir(parents=True, exist_ok=False)
    trusted = read(published/'evidence/activation-install-manifest.json')
    pins = dict(trusted['unchanged_files'], **trusted['files'])
    require(len(pins) == 81, 'Installed pin set differs')
    for name, digest in pins.items():
        require(sha(repo/name) == digest, 'Installed frozen file differs: '+name)
    require(sha(repo/'activation_protocol.json') == PROTOCOL_SHA, 'Protocol differs')
    sys.path.insert(0, str(repo))
    import run_activation_pilot as pilot
    from run_matched_batch import child, evidence_hashes
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    from continuous_udp import canonical_summaries
    from traffic_scenarios import continuous_schedule

    p = pilot.load_protocol(repo); parent = pilot.verify_parent(repo, p)
    root = repo/'results/runs'; batch = child(root, read(root/pilot.REGISTRY)['batch'])
    state = read(batch/'batch.json'); pilot.validate_state(repo, batch, state)
    require(state['outcome'] == 'completed' and len(state['attempts']) == 3, 'Pilot incomplete')
    require(state['captured_source_sha256'] == dict(p['frozen_source_sha256'], **p['additional_source_sha256']),
            'Captured source set differs')
    ready = read(batch/'readiness/readiness.json')
    ready_queues = {q:queue_summary(lines(batch/'readiness/samples.jsonl'), q) for q in QUEUES}
    require(ready['outcome'] == 'passed' and ready['no_traffic_generated'] is True
            and not ready['report']['screen_failures'] and ready_queues == ready['report']['queues'], 'Readiness replay differs')
    require(57 <= ready['report']['elapsed_s'] <= 66 and all(not x['failed_queries']
            and not x['invalid_intervals'] and x['interval_count'] >= 215 for x in ready_queues.values()),
            'Readiness coverage/quality failed')
    ledger = read(root/'activation-interruption-review-v1.json')
    amendment = child(root, ledger['review']); review = read(amendment/'review.json')
    cancelled = child(root, ledger['old_batch']); cancelled_state = read(cancelled/'batch.json')
    require(ledger['status'] == 'committed' and review['status'] == 'archived_registry_raw_unchanged'
            and ledger['zero_traffic_attempts'] is True and review['traffic_attempts'] == 0
            and not review['source_model_quality_or_plan_changed']
            and review['completed_partial_samples'] == 204, 'Cancellation review differs')
    require(evidence_hashes(cancelled) == review['old_batch_files_sha256']
            and (cancelled/'batch.json').read_bytes() == (amendment/'batch-before.json').read_bytes()
            and sha(amendment/'registry-before.json') == review['registry_sha256']
            and read(amendment/'registry-before.json')['batch'] == cancelled.name,
            'Cancelled batch or archived registry differs')
    require(cancelled_state['outcome'] == 'failed' and cancelled_state['error'] == 'KeyboardInterrupt()'
            and not cancelled_state['attempts'] and not cancelled_state['new_raw_folders'], 'Cancellation had acquisition')
    partial = [json.loads(x) for x in (cancelled/'readiness/samples.jsonl').read_text().splitlines(keepends=True)
               if x.endswith('\n') and x.strip()]
    partial_queues = {q:queue_summary(partial,q) for q in QUEUES}
    require(len(partial) == 204 and partial_queues == review['partial_queue_summary']
            and all(not x['failed_queries'] and not x['invalid_intervals'] for x in partial_queues.values()),
            'Cancelled partial quality replay differs')
    require(review['review_helper_sha256'] == sha(published/'tools/review_activation_interruption.py'),
            'Cancellation helper differs from published reviewed version')

    results = []; table = []
    expected = continuous_schedule('ramp', 11500000, 60, 1)
    for item, record in zip(pilot.plan(), state['attempts']):
        require({k:record[k] for k in item} == item and record['status'] == 'passed', 'Step identity differs')
        raw = child(root, record['policy']); trial = child(root, record['trial']); saved = batch/item['step']
        # inspect_step writes network and decoded-packet derivatives. Replay only
        # copied instrumentation inputs in a new derived directory, never raw.
        replay = output/'replay'/item['step']; replay.mkdir(parents=True)
        for name in ['execution.json','clock-map.jsonl','capture-processes.json']:
            shutil.copy2(saved/name, replay/name)
        if item['capture']:
            for dev in ['s1-eth3','s1-eth4']:
                for suffix in ['.pcap','.tcpdump.log']:
                    shutil.copy2(saved/(dev+suffix), replay/(dev+suffix))
        report = pilot.inspect_step(repo, replay, raw, item)
        require(report == read(saved/'review.json'), 'Guest review replay differs: '+item['step'])
        require(read(replay/'network-review.json') == read(saved/'network-review.json'), 'Network review differs')
        if item['capture']:
            with gzip.open(saved/'identified-packets.jsonl.gz','rt',encoding='utf-8') as f:
                old = [json.loads(x) for x in f]
            with gzip.open(replay/'identified-packets.jsonl.gz','rt',encoding='utf-8') as f:
                new = [json.loads(x) for x in f]
            require(old == new and len(new) == report['capture']['captured_union_datagrams'],
                    'Decoded packet identities differ')
        env = read(saved/'environment/environment.json')
        require(env['cpu_count'] == 1 and env['clocksource'] == 'tsc', 'Recorded environment differs')
        version = read(saved/'environment/tcpdump-version.json')
        require(version['exit'] == 0 and 'tcpdump version 4.99.4' in version['text']
                and 'libpcap version 1.10.4' in version['text'], 'Capture version differs')
        sender = read(trial/'sender-native.json'); receiver = read(trial/'receiver-native.json')
        client, server = canonical_summaries(sender, receiver)
        require(client == read(trial/'client.json') and server == read(trial/'server.json'), 'Endpoint summary differs')
        meta = read(trial/'metadata.json')
        require(meta['traffic_plan'] == expected and meta['seed'] == 1 and meta['scenario'] == 'ramp', 'Workload differs')
        start = sender['start_monotonic_ns']/1e9; finish = sender['end_monotonic_ns']/1e9
        independent = {q:intervals(lines(raw/'samples.jsonl'),q,start,finish) for q in QUEUES}
        require(all(not v['invalid_intervals'] and not v['failed_queries'] for v in independent.values()),
                'Independent collector classification failed')
        network = report['network']; queues = network['collector']['qdiscs']; first_q = next(iter(queues.values()))
        require(not network['screen_failures'] and all(v == 0 for h in network['trial']['udp_error_deltas'].values()
                for v in h.values()), 'Network/endpoint quality failed')
        events = actions(raw,start)
        require(len(events) == len(report['actions']), 'Action count differs')
        resource = resources(trial/'vmstat.txt', sender, datetime.fromisoformat(meta['started']).tzinfo)
        capture = report['capture']; processes = read(saved/'capture-processes.json')
        capture_cpu = sum(x['cpu_seconds'] for x in processes.values())
        result = dict(step=item['step'], policy=raw.name, trial=trial.name, report=report,
            environment=env, actions=events, independent_collector=independent, resources=resource,
            sender_packets=sender['sent_packets'], received_packets=receiver['unique_packets'],
            capture_child_cpu_seconds=capture_cpu, raw_policy_sha256=evidence_hashes(raw),
            raw_trial_sha256=evidence_hashes(trial), instrumentation_sha256=evidence_hashes(saved))
        results.append(result)
        timing = capture['timing'] if capture else None
        table.append(dict(step=item['step'], sender_mbps=report['sender_mbps'], receiver_mbps=report['receiver_mbps'],
            udp_loss_percent=report['udp_loss_percent'], sent_packets=sender['sent_packets'],
            source_discard_percent=report['source_audit']['discard_percent'],
            max_pacer_gap_ms=1000*report['source_max_pacer_gap_s'],
            collector_cpu_percent_one_core=network['overhead']['collector_cpu_percent_one_core'],
            policy_cpu_percent_one_core=network['overhead']['policy_thread_cpu_percent_one_core'],
            clock_probe_cpu_seconds=report['clock_probe_usage']['cpu_seconds'], capture_child_cpu_seconds=capture_cpu,
            guest_mean_cpu_percent=resource['mean_user_system_percent'], query_max_ms=1000*first_q['query_duration_s']['max'],
            query_p95_ms=1000*first_q['query_duration_s']['p95'], clock_observed_envelope_ns=report['clock_mapping']['observed_envelope_ns'],
            traffic_probe_rtt_median_ms=network['rtt']['traffic_only']['milliseconds']['median'],
            traffic_probe_rtt_p95_ms=network['rtt']['traffic_only']['milliseconds']['p95'],
            applied_actions=len(events), denied_requests=sum(report['denial_reasons'].values()),
            full_decision_to_readback_ms=1000*events[0]['full_decision_to_readback_s'] if events else None,
            programming_to_readback_ms=1000*events[0]['program_and_readback_s'] if events else None,
            first_alternate_after_decision_low_ms=1000*timing['first_alternate_after_decision_s'][0] if timing else None,
            first_alternate_after_decision_high_ms=1000*timing['first_alternate_after_decision_s'][1] if timing else None))
    previous = dict(scope="Historical backup-to-backup comparison retained in the saved audit; curated replay verifies only retained inputs")
    original = original_action_audit(repo)
    pilot.validate_state(repo,batch,state)  # Prove replay left raw hashes intact.
    require(evidence_hashes(cancelled) == review['old_batch_files_sha256'], 'Replay changed cancelled batch')
    private = [x.relative_to(repo).as_posix() for x in repo.rglob('*') if x.is_file()
               and (x.suffix.lower() in ['.pdf','.docx','.pem','.key','.env']
                    or any(word in x.name.lower() for word in ['credential','password','token','email']))]
    require(not private, 'Potential private attachments require review')
    proof = dict(source_checkpoint_sha256=ARCHIVE_SHA, input_scope="Curated byte-verified inputs; no full VM backup replay",
        regular_files=sum(x.is_file() for x in repo.rglob('*')), installed_source_artifact_pins_verified=81,
        protocol_sha256=PROTOCOL_SHA, batch=batch.name, outcome='completed', guest_reviews_exactly_reproduced=3,
        parent=parent, cancellation_review=review, readiness=ready, prior_checkpoint_comparison=previous,
        original_action_audit=original, steps=results, summary=table, raw_unchanged_after_replay=True,
        interpretation='One fixed-order off/on/off frozen-ML ramp pilot. Software selected-egress packet observation with observed clock envelope; not atomic installation, receiver delivery, prevented onset, a causal overhead bound or an ML efficacy repetition.')
    save(output/'audit.json',proof)
    with (output/'activation-results.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=table[0]); w.writeheader(); w.writerows(table)
    print(json.dumps(dict(output=str(output), files=proof['regular_files'], source_pins=81,
        guest_reviews_reproduced=3, previous=previous, rows=table,
        capture_timing=results[1]['report']['capture']['timing']),indent=2))
    return proof
