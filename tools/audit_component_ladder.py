"""Reproduce the four-case component diagnostic from its exact raw checkpoint."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import csv
import json
import sys
import tarfile

sys.dont_write_bytecode = True
from audit_stopped_supplement import read, lines, sha, save, extract, intervals, actions, original_action_audit
from audit_loaded_recovery import resources

ARCHIVE_SHA = 'b851a04ab1762953dea2b36ae64268373bc961b4cef6ce490d56ee70b25f4005'
PREVIOUS_SHA = '7ea47c86690aca1b8767577a0accaa9e16797d1c0e8115e0c5494350bfec64cc'
PROTOCOL_SHA = 'aa193d5c1d2d02a2955a0f3680276149c8f4d8b491c1353ee63c0aae30ebae1b'
SESSION_LOGS = {'results/runs/session-20261114-235538-primary-continuous/controller.log',
                'results/runs/session-20261114-235538-primary-continuous/mininet.log'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare_previous(repo, archive):
    require(sha(archive) == PREVIOUS_SHA, 'Previous archive digest differs')
    count = identical = 0
    appended = []
    with tarfile.open(archive) as tf:
        for member in tf:
            if not member.isfile():
                continue
            rel = Path(member.name).relative_to('342-proactive-sdn')
            before = tf.extractfile(member).read()
            after = (repo / rel).read_bytes()
            count += 1
            if before == after:
                identical += 1
            else:
                require(rel.as_posix() in SESSION_LOGS and after.startswith(before),
                        'Historical contents changed: ' + rel.as_posix())
                appended.append(dict(path=rel.as_posix(), previous_bytes=len(before),
                                     current_bytes=len(after), append_only=True))
    require(count == 10720, 'Previous checkpoint member count differs')
    return dict(previous_regular_files=count, byte_identical=identical,
                appended_session_logs=appended, previous_contents_preserved=True)


def audit(repo, published, output, archive, previous_archive):
    repo = Path(repo).resolve(); published = Path(published).resolve(); output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    require(sha(archive) == ARCHIVE_SHA, 'Component checkpoint digest differs')
    trusted = read(published / 'evidence/loaded-diagnostics-install-manifest.json')
    pins = dict(trusted['unchanged_files'], **trusted['files'])
    require(len(pins) == 76, 'Installed source/artifact set differs')
    for name, digest in pins.items():
        require(sha(repo / name) == digest, 'Installed file changed: ' + name)
    require(sha(repo / 'loaded_diagnostics_protocol.json') == PROTOCOL_SHA, 'Protocol digest differs')
    sys.path.insert(0, str(repo))
    import run_loaded_diagnostics as d
    from run_matched_batch import check_report, load_protocol, child, evidence_hashes
    from run_policy_experiment import inspect_policy
    from source_integrity import source_integrity_audit
    from continuous_udp import canonical_summaries
    from traffic_scenarios import continuous_schedule
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    p = d.load_protocol(repo)
    prior = d.verify_prior(repo, p)
    root = repo / 'results/runs'
    batch = child(root, read(root / d.REGISTRY)['batch'])
    state = read(batch / 'batch.json')
    d.validate_state(repo, batch, state)
    require(state['outcome'] == 'completed' and len(state['attempts']) == 4, 'Ladder incomplete')
    require(state['captured_source_sha256'] == dict(p['frozen_source_sha256'], **p['additional_source_sha256']),
            'Captured source pin set differs')
    ready = read(batch / 'readiness/readiness.json')
    ready_queues = {q: queue_summary(lines(batch / 'readiness/samples.jsonl'), q) for q in QUEUES}
    require(ready['outcome'] == 'passed' and ready.get('no_traffic_generated') is True,
            'Readiness outcome/scope differs')
    require(ready_queues == ready['report']['queues'] and not ready['report']['screen_failures'],
            'Readiness inspection differs')
    require(57 <= ready['report']['elapsed_s'] <= 66 and all(
        not q['failed_queries'] and not q['invalid_intervals'] and q['interval_count'] >= 215
        for q in ready_queues.values()), 'Readiness duration/coverage/quality differs')
    matched = load_protocol(repo)
    expected = continuous_schedule('bursty', 11500000, 60, 44)
    results = []
    for item, record in zip(d.plan(), state['attempts']):
        require({k: record[k] for k in item} == item and record['status'] == 'passed', 'Diagnostic identity differs')
        folder = child(root, record['folder']); trial = child(root, record['trial'])
        environment = read(batch / record['environment'] / 'environment.json')
        require(environment['cpu_count'] == 1 and environment['clocksource'] == 'tsc'
                and environment['host_conditions'] == d.SETTINGS['host_conditions'], 'Recorded environment differs')
        if item['policy'] is None:
            report = d.inspect_component(folder)
            meta = read(folder / 'component.json')
            trial_report = report['trial_report']
            collector = report['collector']
        else:
            report = inspect_policy(folder)
            check_report(repo, folder, dict(policy=item['policy'], scenario='bursty', seed=44,
                requested_bps=11500000, duration=60), matched, report, source_integrity_audit)
            meta = read(folder / 'policy.json')
            trial_report = report['trial']
            collector = dict(applicable=True, queues=report['collector']['qdiscs'], stats=report['collector']['stats'])
        require(meta['trial'] == trial.name, 'Diagnostic trial reference differs')
        require(report == read(batch / record['review']), 'Independent inspection differs from guest: ' + item['case'])
        require(not report['screen_failures'] and report['outcome'] == 'completed', 'Diagnostic quality failed')
        native_meta = read(trial / 'metadata.json')
        require(native_meta['traffic_plan'] == expected and native_meta['seed'] == 44
                and native_meta['scenario'] == 'bursty', 'Native workload differs')
        sender = read(trial / 'sender-native.json'); receiver = read(trial / 'receiver-native.json')
        client, server = canonical_summaries(sender, receiver)
        require(client == read(trial / 'client.json') and server == read(trial / 'server.json'),
                'Native endpoint summaries do not reproduce')
        require(all(v == 0 for host in trial_report['udp_error_deltas'].values() for v in host.values()),
                'Endpoint error appeared')
        source = source_integrity_audit(trial)
        start = sender['start_monotonic_ns'] / 1e9; finish = sender['end_monotonic_ns'] / 1e9
        if collector['applicable']:
            raw = lines(folder / 'samples.jsonl')
            independent = {q: intervals(raw, q, start, finish) for q in QUEUES}
            require(all(not v['invalid_intervals'] and not v['failed_queries'] for v in independent.values()),
                    'Independent collector classification failed')
        else:
            require(not (folder / 'samples.jsonl').exists() and meta['collector_exit'] is None,
                    'Continuous collector unexpectedly present')
            independent = None
        events = actions(folder, start) if item['policy'] else []
        if item['policy']:
            require(len(events) == len(report['applied_actions']), 'Applied action audit differs')
        denial_reasons = dict(Counter((r.get('action') or {}).get('rejection') for r in
            (lines(folder / 'decisions.jsonl') if item['policy'] else [])
            if (r.get('action') or {}).get('applied') is False))
        resource = resources(trial / 'vmstat.txt', sender, datetime.fromisoformat(native_meta['started']).tzinfo)
        results.append(dict(case=item['case'], folder=folder.name, trial=trial.name,
            report=report, environment=environment, source_audit=source, collector=collector,
            independent_collector_intervals=independent, actions=events, denial_reasons=denial_reasons,
            resources=resource, packet_accounting=dict(sent=sender['sent_packets'], unique_received=receiver['unique_packets'],
                missing=sender['sent_packets']-receiver['unique_packets'], root_drops=trial_report['queue_drop_deltas'],
                udp_errors=trial_report['udp_error_deltas'], scope='Separate sequence, root-drop and endpoint counters; no cross-layer sum.'),
            max_pacer_gap_s=sender['max_pacer_gap_s'], policy_raw_sha256=evidence_hashes(folder),
            trial_raw_sha256=evidence_hashes(trial)))
    previous = compare_previous(repo, previous_archive)
    original = original_action_audit(repo)
    private_files = [path.relative_to(repo).as_posix() for path in repo.rglob('*') if path.is_file()
                     and (path.suffix.lower() in ['.pdf', '.docx', '.pem', '.key', '.env']
                          or any(x in path.name.lower() for x in ['credential', 'password', 'token', 'email']))]
    require(not private_files, 'Potential private attachment/key files require review')
    proof = dict(archive_sha256=ARCHIVE_SHA, archive_bytes=Path(archive).stat().st_size,
        regular_files=sum(path.is_file() for path in repo.rglob('*')), installed_source_artifact_pins_verified=76,
        protocol_sha256=PROTOCOL_SHA, prior_evidence=prior, prior_checkpoint_comparison=previous,
        batch=batch.name, outcome='completed', guest_reviews_exactly_reproduced=4,
        readiness=ready, cases=results, original_action_audit=original,
        acquisition_code_model_or_threshold_changed=False,
        interpretation='Four bounded diagnostic windows passed; earlier fault not reproduced, root cause unresolved. Fixed order, one run per component and concurrent host work preclude a causal/efficacy estimate. No pooling with original or failed supplemental runs.')
    save(output / 'audit.json', proof)
    table = []
    for case in results:
        r = case['report']; c = case['collector']; native = case['packet_accounting']
        first_queue = next(iter(c['queues'].values())) if c['applicable'] else None
        table.append(dict(case=case['case'], folder=case['folder'], trial=case['trial'],
            sender_mbps=r['sender_mbps'], receiver_mbps=r['receiver_mbps'], udp_loss_percent=r['udp_loss_percent'],
            sent=native['sent'], received=native['unique_received'], missing=native['missing'],
            bottleneck_drops=native['root_drops']['s2-eth2'],
            source_discard_percent=case['source_audit']['discard_percent'], max_pacer_gap_ms=1000*case['max_pacer_gap_s'],
            collector_applicable=c['applicable'], collector_cpu_percent_one_core=sum(c['stats']['cpu_percent_one_core'].values()) if c['applicable'] else None,
            query_median_ms=1000*first_queue['query_duration_s']['median'] if first_queue else None,
            query_max_ms=1000*first_queue['query_duration_s']['max'] if first_queue else None,
            invalid_intervals_per_queue=first_queue['invalid_intervals'] if first_queue else None,
            failed_queries_per_queue=first_queue['failed_queries'] if first_queue else None,
            applied_actions=len(case['actions']), denied_requests=sum(case['denial_reasons'].values()),
            guest_mean_cpu_percent=case['resources']['mean_user_system_percent']))
    with (output / 'component-results.csv').open('x', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=table[0]); w.writeheader(); w.writerows(table)
    print(json.dumps(dict(output=str(output), regular_files=proof['regular_files'], source_pins=76,
        guest_reviews_reproduced=4, previous_checkpoint_preservation=previous, rows=table,
        reactive_action_timing=results[-1]['actions'], reactive_denials=results[-1]['denial_reasons']), indent=2))
    return proof


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument('--repo', type=Path)
    where.add_argument('--extract', type=Path)
    parser.add_argument('--published', type=Path, default=root)
    parser.add_argument('--archive', type=Path, default=root/'evidence/raw/342-sdn-checkpoint-20261120-234612.tar.gz')
    parser.add_argument('--previous-archive', type=Path, default=root/'evidence/raw/342-sdn-checkpoint-20261120-223910.tar.gz')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.extract:
        extract(args.archive, args.extract, ARCHIVE_SHA)
        args.repo = args.extract / '342-proactive-sdn'
    audit(args.repo, args.published, args.output, args.archive, args.previous_archive)
