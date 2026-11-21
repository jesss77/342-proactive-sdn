"""Bounded component-isolation diagnostic; never resets the failed study."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from run_matched_batch import sha, write, child, evidence_hashes

SETTINGS = dict(
    id='loaded-component-isolation-v1', scenario='bursty', seed=44,
    requested_scale_bps=11500000, duration_s=60, interval_s=.25,
    coverage='all', clocksource='tsc', cpu_count=1,
    profile_id='dual-forward-cburst16k-source250-v1',
    host_conditions='Plugged in; other work remains running, as reported by Jess. Not an otherwise-idle host.',
    recovery_batch='20261120-220211-529321-bursty-supplement-recovery',
    checkpoint_sha256='7ea47c86690aca1b8767577a0accaa9e16797d1c0e8115e0c5494350bfec64cc',
    rule='One case per explicit call, in order, once each. Stop on any execution, quality, identity or restoration failure. No retry/reset/replacement.',
    interpretation='Diagnostic component ladder, not a paired policy-benefit study or proof of root cause. Fixed order and concurrent host work limit causal attribution.')
OWN_SOURCES = ['run_loaded_diagnostics.py', 'test_loaded_diagnostics.py', 'LOADED_DIAGNOSTICS.md']
PROTOCOL = 'loaded_diagnostics_protocol.json'
REGISTRY = 'loaded-diagnostics-registry-v1.json'


def plan():
    return [dict(case=name, collector=name != 'source_receiver',
                 policy={'fixed_loop': 'fixed', 'reactive_loop': 'reactive'}.get(name))
            for name in ['source_receiver', 'collector', 'fixed_loop', 'reactive_loop']]


def load_protocol(base):
    from run_supplement_recovery import load_protocol as frozen
    base = Path(base).resolve()
    frozen(base)
    p = json.loads((base / PROTOCOL).read_text())
    if p.get('settings') != SETTINGS or p.get('plan') != plan():
        raise ValueError('Diagnostic registration changed')
    if set(p.get('additional_source_sha256', {})) != set(OWN_SOURCES):
        raise ValueError('Diagnostic source pins incomplete')
    if len(p.get('frozen_source_sha256', {})) != 72:
        raise ValueError('Frozen source pins incomplete')
    for name, digest in dict(p['frozen_source_sha256'], **p['additional_source_sha256']).items():
        if Path(name).name != name or (base / name).is_symlink() or sha(base / name) != digest:
            raise ValueError('Diagnostic/frozen source changed: ' + name)
    return p


def verify_prior(base, protocol):
    from run_supplement_recovery import load_protocol as frozen, verify_parent
    base = Path(base).resolve()
    prior, _ = frozen(base)
    verify_parent(base, prior)  # Preserve all 828 initial supplement files.
    for name, digest in protocol['prior_evidence_sha256'].items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe prior evidence path')
        path = base.joinpath(*rel.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(base) or sha(path) != digest:
            raise ValueError('Prior evidence changed: ' + name)
    state = json.loads((base / 'results/runs' / SETTINGS['recovery_batch'] / 'batch.json').read_text())
    if state['outcome'] != 'failed' or state['runs'] or len(state['attempts']) != 1:
        raise ValueError('Expected preserved failed recovery state')
    return dict(pinned_files=len(protocol['prior_evidence_sha256']), prior_outcome='failed', prior_edited=False)


def environment(folder):
    clock = Path('/sys/devices/system/clocksource/clocksource0/current_clocksource').read_text().strip()
    info = dict(timestamp=datetime.now(timezone.utc).isoformat(), cpu_count=os.cpu_count(),
                clocksource=clock, kernel=platform.release(), python=sys.version,
                loadavg=list(os.getloadavg()), host_conditions=SETTINGS['host_conditions'])
    info['meminfo'] = Path('/proc/meminfo').read_text()
    for name, args in [('ovs', ['ovs-vsctl', '--version']), ('tc', ['tc', '-V']),
                       ('vmstat', ['vmstat', '-V'])]:
        r = subprocess.run(args, capture_output=True, text=True, timeout=5)
        info[name] = dict(exit=r.returncode, stdout=r.stdout, stderr=r.stderr)
        if r.returncode:
            write(Path(folder) / 'environment.json', info)
            raise ValueError('Environment version check failed: ' + name)
    write(Path(folder) / 'environment.json', info)
    if info['cpu_count'] != 1 or clock != SETTINGS['clocksource']:
        raise ValueError('One-vCPU/tsc diagnostic protocol required; do not change settings to bypass')
    return info


def component_run(net, base, case, folder, clock=time.monotonic, sleep=time.sleep):
    """Same source/profile/probes/resource log, with only the collector added."""
    import run_continuous_trial as recorder
    recorder = importlib.reload(recorder)
    from dual_path_profile import dual_profile, LINKS, QUEUES
    from routing_action import RoutingAction
    from run_experiment import stop, interface_counts
    from traffic_scenarios import continuous_schedule
    base, folder = Path(base), Path(folder)
    if case not in ['source_receiver', 'collector']:
        raise ValueError('Unknown component case')
    meta = dict(case=case, collector_enabled=case == 'collector', policy_loop_enabled=False,
                scenario='bursty', seed=44, requested_scale_bps=11500000, duration=60,
                outcome='running', source_sha256={})
    actor = collector = ping = None
    def save():
        write(folder / 'component.json', meta)
    def created(trial):
        meta['trial'] = Path(trial).name
        save()
    def proof(_net, route, out, phase='before'):
        if route != 'primary' or actor.route != 'primary':
            raise RuntimeError('Component diagnostic must stay on primary')
        for switch, text in actor.verify('primary').items():
            (Path(out) / f'{phase}-{switch}-flows.txt').write_text(text)
        return dict(mode='owned_hostpair', selected_route='primary')
    protocol = load_protocol(base)
    for name, digest in protocol['frozen_source_sha256'].items():
        shutil.copy2(base / name, folder / name)
        meta['source_sha256'][name] = digest
    save()
    try:
        actor = RoutingAction(lambda n, args: net[n].pexec(args), folder / 'action.jsonl', clock=clock)
        with dual_profile(net, folder) as profile:
            meta['profile'] = profile
            before = interface_counts(); t0 = clock(); sleep(1)
            after = interface_counts(); elapsed = clock() - t0
            if not .9 <= elapsed <= 2:
                raise RuntimeError('Idle counter timing failed')
            if any(not 0 <= 8 * (after[d]['tx_bytes'] - before[d]['tx_bytes']) / elapsed <= 100000 for d in QUEUES):
                raise RuntimeError('Diagnostic requires idle testbed')
            out, err, code = net['h1'].pexec(['ping', '-n', '-D', '-c', '10', '-i', '.2', '-w', '5', net['h2'].IP()])
            (folder / 'ping-idle.txt').write_text(out + err)
            if code:
                raise RuntimeError('Idle probe failed')
            meta['counters_before'] = interface_counts(); save()
            with ExitStack() as files:
                try:
                    if case == 'collector':
                        log = files.enter_context((folder / 'collector.log').open('x'))
                        collector = subprocess.Popen(['/usr/bin/python3', str(base / 'collect_path.py'),
                            str(folder / 'samples.jsonl'), '--route', 'primary', '--coverage', 'all',
                            '--interval', '.25', '--duration', '100'], stdout=log, stderr=subprocess.STDOUT)
                    sleep(2)  # Same warm-up in both component cases.
                    if collector is not None and collector.poll() is not None:
                        raise RuntimeError('Collector exited before traffic')
                    pinglog = files.enter_context((folder / 'ping-loaded.txt').open('x'))
                    ping = net['h1'].popen(['ping', '-n', '-D', '-i', '.2', net['h2'].IP()],
                                            stdout=pinglog, stderr=subprocess.STDOUT)
                    trial = recorder.run(net, base, 11500000, 'primary', 60,
                        plan=continuous_schedule('bursty', 11500000, 60, 44), seed=44, scenario='bursty',
                        route_verifier=proof, capture_links=LINKS, on_created=created,
                        trial_context=dict(route_verification='owned_hostpair', kind='loaded_component_diagnostic',
                                           case=case, parent=folder.name, diagnostic_only=True))
                    created(trial)
                    if json.loads((trial / 'metadata.json').read_text())['outcome'] != 'completed':
                        raise RuntimeError('Diagnostic traffic failed; raw source retained')
                    if ping.poll() is not None or (collector is not None and collector.poll() is not None):
                        raise RuntimeError('Probe/collector exited during source')
                    sleep(2)
                finally:
                    meta['ping_exit'] = stop(ping)
                    meta['collector_exit'] = stop(collector) if collector is not None else None
                    meta['counters_after'] = interface_counts(); save()
            if collector is not None and meta['collector_exit'] != 0:
                raise RuntimeError('Collector shutdown failed')
            proof(net, 'primary', folder, 'selected')
            actor.close(); meta['route_restoration'] = dict(verified=True, failures=[])
        meta['outcome'] = 'completed'
    except BaseException as error:
        meta.update(outcome='error', error=repr(error))
        raise
    finally:
        if actor is not None:
            try:
                actor.close(); meta['route_restoration'] = dict(verified=True, failures=[])
            except BaseException as error:
                meta.update(outcome='error', route_restoration=dict(verified=False, failures=[repr(error)]))
        save()
    return folder


def inspect_component(folder):
    from inspect_experiment import inspect_trial, queue_summary, ping_statistics
    from dual_path_profile import QUEUES
    from source_integrity import source_integrity_audit
    from traffic_scenarios import continuous_schedule
    folder = Path(folder)
    m = json.loads((folder / 'component.json').read_text())
    base = folder.parent.parent.parent
    p = load_protocol(base)
    trial = child(base / 'results/runs', m['trial'])
    t = inspect_trial(trial)
    failures = list(t['screen_failures'])
    native = json.loads((trial / 'metadata.json').read_text())
    expected = continuous_schedule('bursty', 11500000, 60, 44)
    if (m['outcome'] != 'completed' or native['traffic_plan'] != expected or native['seed'] != 44
        or native['scenario'] != 'bursty' or native['trial_context'].get('parent') != folder.name
        or native['trial_context'].get('case') != m['case'] or m['profile']['id'] != SETTINGS['profile_id']):
        failures.append('identity_schedule_profile')
    for name, digest in p['frozen_source_sha256'].items():
        if m['source_sha256'].get(name) != digest or sha(folder / name) != digest:
            failures.append('captured_source:' + name)
    restoration = json.loads((folder / 'restoration.json').read_text())
    if restoration['failures'] or not m['route_restoration']['verified'] or m['route_restoration']['failures']:
        failures.append('restoration')
    deltas = {d: m['counters_after'][d]['tx_bytes'] - m['counters_before'][d]['tx_bytes'] for d in QUEUES}
    if any(deltas[d] < 100000 for d in ['s1-eth3', 's2-eth2']):
        failures.append('primary_path_not_demonstrated')
    if any(deltas[d] != 0 for d in ['s1-eth4', 's3-eth2']):
        failures.append('unexpected_alternate_activity')
    collector = dict(applicable=m['collector_enabled'], reason='Intentionally absent in source/receiver diagnostic')
    if m['collector_enabled']:
        rows = [json.loads(line) for line in (folder / 'samples.jsonl').read_text().splitlines()]
        stats = json.loads((folder / 'samples.jsonl.stats.json').read_text())
        queues = {q: queue_summary(rows, q) for q in QUEUES}
        collector = dict(applicable=True, queues=queues, stats=stats)
        if (stats.get('schema_version') != 6 or stats.get('coverage') != 'all'
            or set(stats.get('queried_qdiscs', [])) != set(QUEUES) or not rows
            or any(q['failed_queries'] or q['invalid_intervals'] or q['interval_count'] < 215 for q in queues.values())):
            failures.append('collector_quality')
    elif (folder / 'samples.jsonl').exists():
        failures.append('unexpected_collector')
    audit = source_integrity_audit(trial)
    sender = json.loads((trial / 'sender-native.json').read_text())
    return dict(case=m['case'], outcome=m['outcome'], trial=trial.name, screen_failures=failures,
        sender_mbps=t['sender']['bits_per_second']/1e6, receiver_mbps=t['receiver']['bits_per_second']/1e6,
        udp_loss_percent=t['receiver']['lost_percent'], trial_report=t, source_audit=audit,
        max_pacer_gap_s=sender['max_pacer_gap_s'], collector=collector,
        rtt=ping_statistics((folder / 'ping-loaded.txt').read_text(), [(sender['start_wall_epoch_s'], sender['end_wall_epoch_s'])]),
        route_tx_bytes=deltas, restoration=restoration, route_restoration=m['route_restoration'],
        interpretation='Primary overload loss is an outcome, not an automatic quality rejection. No policy-benefit or precise activation claim.')


def validate_state(base, folder, state):
    if (state['protocol_sha256'] != sha(Path(base) / PROTOCOL) or state['plan'] != plan()
        or state['outcome'] not in ['paused', 'completed'] or len(state['attempts']) > 4
        or [r['case'] for r in state['attempts']] != [r['case'] for r in plan()[:len(state['attempts'])]]
        or any(a['status'] != 'passed' for a in state['attempts'])):
        raise ValueError('Failed/partial/changed diagnostic cannot resume or retry')
    if sha(Path(folder) / PROTOCOL) != state['protocol_sha256']:
        raise ValueError('Captured diagnostic registration changed')
    for name, digest in state['captured_source_sha256'].items():
        if sha(Path(folder) / name) != digest:
            raise ValueError('Captured diagnostic source changed')
    if state['attempts']:
        for name, digest in state['readiness_files_sha256'].items():
            if sha(Path(folder) / 'readiness' / name) != digest:
                raise ValueError('Readiness evidence changed')
    for record in state['attempts']:
        if evidence_hashes(Path(folder) / record['environment']) != record['environment_sha256']:
            raise ValueError('Environment record changed')
        for key in ['folder', 'trial']:
            if evidence_hashes(child(Path(base) / 'results/runs', record[key])) != record[key + '_sha256']:
                raise ValueError('Diagnostic raw evidence changed')
        if sha(Path(folder) / record['review']) != record['review_sha256']:
            raise ValueError('Diagnostic review changed')


def run(net, case='source_receiver', base=BASE, executor=None, inspector=None,
        readiness_check=None, environment_check=environment):
    base = Path(base).resolve()
    p = load_protocol(base)
    prior = verify_prior(base, p)
    root = base / 'results/runs'
    root.mkdir(parents=True, exist_ok=True)
    registry = root / REGISTRY
    if registry.exists():
        folder = child(root, json.loads(registry.read_text())['batch'])
        state = json.loads((folder / 'batch.json').read_text())
        validate_state(base, folder, state)
    else:
        if case != 'source_receiver':
            raise ValueError('Start at source_receiver; no skipped components')
        folder = root / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-loaded-component-diagnostics')
        folder.mkdir()
        captured = dict(p['frozen_source_sha256'], **p['additional_source_sha256'])
        for name in [*captured, PROTOCOL]:
            shutil.copy2(base / name, folder / name)
        state = dict(outcome='paused', plan=plan(), attempts=[], prior=prior,
            protocol_sha256=sha(base / PROTOCOL), captured_source_sha256=captured,
            host_conditions=SETTINGS['host_conditions'], created=datetime.now(timezone.utc).isoformat())
        write(folder / 'batch.json', state)
        with registry.open('x') as f:
            json.dump(dict(batch=folder.name), f)
    if len(state['attempts']) == 4:
        raise ValueError('Diagnostic ladder already complete; no repeated acquisition')
    item = plan()[len(state['attempts'])]
    if case != item['case']:
        raise ValueError('Next registered case is ' + item['case'])
    def save():
        write(folder / 'batch.json', state)
    state['outcome'] = 'running'; save()
    entry = None
    before = {d.name for d in root.iterdir() if d.is_dir()}
    try:
        env = folder / ('environment-' + case)
        env.mkdir()
        environment_check(env)
        if not state['attempts']:
            from run_supplement_recovery import readiness
            (readiness_check or readiness)(net, base, folder / 'readiness')
            state['readiness_files_sha256'] = evidence_hashes(folder / 'readiness'); save()
        entry = dict(item, status='running', environment=env.name, environment_sha256=evidence_hashes(env))
        state['attempts'].append(entry); save()
        print('COMPONENT DIAGNOSTIC:', case, '| one registered 60-second trial', flush=True)
        if executor is not None:
            raw = executor(net, base, item, folder)
        elif item['policy'] is not None:
            import run_policy_experiment as runner
            runner = importlib.reload(runner)
            if runner.BASE.resolve() != base:
                raise ValueError('Policy runner belongs to a different repository')
            raw = runner.run(net, policy=item['policy'], scenario='bursty', requested_bps=11500000, duration=60, seed=44)
        else:
            raw = root / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-component-' + case + '-seed44')
            raw.mkdir()
            component_run(net, base, case, raw)
        raw = child(root, Path(raw).name)
        validator = None
        if inspector is not None:
            report = inspector(raw)
        elif item['policy'] is not None:
            from run_matched_batch import check_report, load_protocol as matched
            from source_integrity import source_integrity_audit
            report = runner.inspect_policy(raw)
            validator = lambda: check_report(base, raw, dict(policy=item['policy'], scenario='bursty', seed=44,
                requested_bps=11500000, duration=60), matched(base), report, source_integrity_audit)
        else:
            report = inspect_component(raw)
        entry['folder'] = raw.name
        meta = json.loads((raw / ('policy.json' if item['policy'] else 'component.json')).read_text())
        trial = child(root, meta['trial'])
        entry['trial'] = trial.name
        review = folder / ('review-' + case + '.json')
        with review.open('x') as f:
            json.dump(report, f, indent=2)
        entry.update(review=review.name, review_sha256=sha(review), folder_sha256=evidence_hashes(raw), trial_sha256=evidence_hashes(trial))
        if validator is not None:
            validator()
        if (report['outcome'] != 'completed' or report['screen_failures']
            or report['restoration']['failures'] or not report['route_restoration']['verified']
            or report['route_restoration']['failures']):
            raise ValueError('Component diagnostic quality/restoration failed; no automatic retry')
        entry['status'] = 'passed'
        state['outcome'] = 'completed' if len(state['attempts']) == 4 else 'paused'
        print('DIAGNOSTIC RESULT:', json.dumps({k: report[k] for k in ['outcome', 'screen_failures', 'sender_mbps', 'receiver_mbps', 'udp_loss_percent']}), flush=True)
    except BaseException as error:
        state.update(outcome='failed', error=repr(error))
        if entry is not None:
            entry.update(status='failed', error=repr(error))
        state['new_raw_folders'] = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name not in before)
        # Preserve returned/partially created policy and source references on all failures.
        raise
    finally:
        save()
        print('DIAGNOSTIC STATE:', state['outcome'], '|', folder, flush=True)
    return folder


if 'net' in globals():
    run(net, case=globals().get('case', 'source_receiver'))
elif __name__ == '__main__':
    raise SystemExit('Run within the existing Mininet CLI; see LOADED_DIAGNOSTICS.md')
