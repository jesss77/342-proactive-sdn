"""Three registered frozen-ML ramp runs: capture off, on, off; one per call."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import gzip
import importlib
import json
import os
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from run_matched_batch import sha, write, child, evidence_hashes, check_report
from packet_activation import ClockProbe, Capture, INTERFACES, clock_bounds, analyze_capture, require

PROTOCOL = 'activation_protocol.json'
REGISTRY = 'activation-pilot-registry-v1.json'
OWN = ['packet_activation.py', 'run_activation_pilot.py', 'test_activation_pilot.py', 'ACTIVATION_PILOT.md']
SETTINGS = dict(id='selected-udp-activation-pilot-v1', policy='ml', scenario='ramp', seed=1,
    requested_bps=11500000, duration_s=60, tcpdump_version='4.99.4', libpcap_version='1.10.4',
    parent_batch='20261120-232315-489421-loaded-component-diagnostics',
    parent_checkpoint_sha256='b851a04ab1762953dea2b36ae64268373bc961b4cef6ce490d56ee70b25f4005',
    capture_interfaces=INTERFACES, direction='out', snaplen=128, capture_buffer_kib=4096,
    timestamp_type='host', timestamp_precision='nano', clock_sample_period_s=.5,
    max_observed_clock_envelope_ns=10000000,
    rule='Exactly off/on/off once, one step per explicit call. Stop on any execution/network/capture/timing quality failure. No retries, resets or replacements. No-action is retained.',
    scope='First identified UDP observed arriving on alternate selected-switch egress, not switch hardware activation, application delivery or counterfactual onset. Fixed-order overhead bracket is descriptive, not causal.')


def plan():
    return [dict(step='before', capture=False), dict(step='capture', capture=True), dict(step='after', capture=False)]


def load_protocol(base):
    import run_loaded_diagnostics as d
    base = Path(base).resolve(); d.load_protocol(base)
    p = json.loads((base / PROTOCOL).read_text())
    require(p['settings'] == SETTINGS and p['plan'] == plan(), 'Activation registration differs')
    require(len(p['frozen_source_sha256']) == 76 and set(p['additional_source_sha256']) == set(OWN),
            'Activation source pins incomplete')
    for name, digest in dict(p['frozen_source_sha256'], **p['additional_source_sha256']).items():
        require(Path(name).name == name and not (base/name).is_symlink() and sha(base/name) == digest,
                'Activation/frozen source changed: ' + name)
    return p


def verify_parent(base, p):
    import run_loaded_diagnostics as d
    base = Path(base).resolve(); prior = d.load_protocol(base); d.verify_prior(base, prior)
    for name, digest in p['parent_evidence_sha256'].items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in name and ':' not in name,
                'Unsafe parent evidence path')
        path = base.joinpath(*rel.parts)
        require(not path.is_symlink() and path.resolve().is_relative_to(base) and sha(path) == digest,
                'Parent diagnostic evidence changed: ' + name)
    root = base/'results/runs'
    require(json.loads((root/d.REGISTRY).read_text())['batch'] == SETTINGS['parent_batch'], 'Different diagnostic parent')
    folder = root/SETTINGS['parent_batch']; state = json.loads((folder/'batch.json').read_text())
    d.validate_state(base, folder, state)
    require(state['outcome'] == 'completed' and len(state['attempts']) == 4, 'Completed diagnostic ladder required')
    return dict(parent=folder.name, files_verified=len(p['parent_evidence_sha256']), original_edited=False)


def preflight(folder):
    from run_loaded_diagnostics import environment
    environment(folder)
    require(os.name == 'posix' and hasattr(os, 'wait4') and os.geteuid() == 0,
            'Existing root Mininet Linux session required')
    result = subprocess.run(['tcpdump', '--version'], capture_output=True, text=True, timeout=5)
    version = result.stdout+result.stderr
    write(Path(folder)/'tcpdump-version.json', dict(exit=result.returncode, text=version))
    require(result.returncode == 0 and 'tcpdump version 4.99.4' in version and 'libpcap version 1.10.4' in version,
            'Capture software differs from registered capability')
    for dev in INTERFACES:
        r = subprocess.run(['tcpdump','-n','-p','-i',dev,'-J'], capture_output=True, text=True, timeout=5)
        text = r.stdout+r.stderr
        write(Path(folder)/(dev+'-timestamp-types.json'),dict(exit=r.returncode,text=text))
        import re
        require(r.returncode == 0 and re.search(r'^\s*host\s+\(', text, re.M), 'Host timestamp type unavailable: '+dev)


def execute_step(net, base, item, folder, run_fn=None, probe_factory=ClockProbe, capture_factory=Capture):
    if run_fn is None:
        import run_policy_experiment as runner
        runner = importlib.reload(runner)
        require(runner.BASE.resolve() == Path(base).resolve(), 'Runner belongs to another repository')
        run_fn = runner.run
    probe = probe_factory(Path(folder)/'clock-map.jsonl')
    captures = [capture_factory(folder,d) for d in INTERFACES] if item['capture'] else []
    summaries = {}; cleanup = []; result = None; error = None; clock_usage = None
    try:
        probe.start()
        for c in captures:
            c.start()
        result = run_fn(net, policy='ml', scenario='ramp', requested_bps=11500000, duration=60, seed=1)
        for c in captures:
            require(c.proc.poll() is None, 'Capture exited during policy run')
    except BaseException as e:
        error = repr(e)
    finally:
        for c in captures:
            try:
                summaries[c.interface] = c.stop()
            except BaseException as e:
                cleanup.append(c.interface+': '+repr(e))
        try:
            clock_usage = probe.stop()
        except BaseException as e:
            cleanup.append('clock probe: '+repr(e))
        write(Path(folder)/'capture-processes.json', summaries)
        write(Path(folder)/'execution.json',dict(error=error,cleanup_errors=cleanup,
            returned_policy_folder=Path(result).name if result else None,clock_probe=clock_usage))
    if error or cleanup:
        raise RuntimeError('Activation execution/cleanup failed: '+str(error or cleanup))
    return Path(result)


def inspect_step(base, folder, raw, item):
    from run_policy_experiment import inspect_policy
    from run_matched_batch import load_protocol as matched
    from source_integrity import source_integrity_audit
    base, folder, raw = Path(base), Path(folder), Path(raw)
    network = inspect_policy(raw)
    # Keep the exact network report even when its frozen quality checks reject it.
    with (folder/'network-review.json').open('x') as f:
        json.dump(network,f,indent=2)
    record = check_report(base,raw,dict(policy='ml',scenario='ramp',seed=1,requested_bps=11500000,duration=60),
                          matched(base),network,source_integrity_audit)
    trial = child(base/'results/runs',record['trial'])
    sender = json.loads((trial/'sender-native.json').read_text()); receiver = json.loads((trial/'receiver-native.json').read_text())
    meta = json.loads((trial/'metadata.json').read_text())
    clocks = [json.loads(s) for s in (folder/'clock-map.jsonl').read_text().splitlines()]
    bounds = clock_bounds(clocks,sender['start_monotonic_ns'],sender['end_monotonic_ns'])
    decisions = [json.loads(s) for s in (raw/'decisions.jsonl').read_text().splitlines()]
    applied = [dict(d['action'],decision_at=d['decision_at']) for d in decisions if (d.get('action') or {}).get('applied')]
    require(len(applied) == len(network['applied_actions']) <= 1, 'Decision/action identity differs')
    capture = None
    if item['capture']:
        capture = analyze_capture(folder,sender,receiver,meta['udp_port'],bounds,applied[0] if applied else None)
        records = capture.pop('records')
        with gzip.open(folder/'identified-packets.jsonl.gz','wt',encoding='utf-8') as f:
            for dev, packets in records.items():
                for packet in packets:
                    f.write(json.dumps(dict(interface=dev,**packet))+'\n')
    else:
        require(not list(folder.glob('*.pcap')), 'Unexpected capture in off control')
    source = source_integrity_audit(trial)
    return dict(step=item['step'],capture_enabled=item['capture'],outcome='completed',screen_failures=[],
        network=network,source_audit=source,clock_mapping=bounds,capture=capture,
        clock_probe_usage=json.loads((folder/'execution.json').read_text())['clock_probe'],
        sender_mbps=network['sender_mbps'],receiver_mbps=network['receiver_mbps'],
        udp_loss_percent=network['udp_loss_percent'],actions=applied,
        denial_reasons=dict(Counter(a['rejection'] for a in network['denied_requests'])),
        source_max_pacer_gap_s=sender['max_pacer_gap_s'],policy_record=record,
        timing_scope='Observed packet at alternate selected-switch egress; clock-pair envelope and software timestamp limitations apply. No predicted/prevented onset reconstructed.')


def validate_state(base, folder, state):
    require(state['outcome'] in ['paused','completed'] and state['plan'] == plan()
        and state['protocol_sha256'] == sha(Path(base)/PROTOCOL)
        and len(state['attempts']) <= 3
        and [a['step'] for a in state['attempts']] == [p['step'] for p in plan()[:len(state['attempts'])]]
        and all(a['status'] == 'passed' for a in state['attempts']), 'Failed/partial/changed activation pilot cannot retry')
    require(sha(Path(folder)/PROTOCOL) == state['protocol_sha256'], 'Captured activation protocol changed')
    for name, digest in state['captured_source_sha256'].items():
        require(sha(Path(folder)/name) == digest, 'Captured source changed')
    if state['attempts']:
        require(evidence_hashes(Path(folder)/'readiness') == state['readiness_sha256'], 'Readiness evidence changed')
    for a in state['attempts']:
        for key in ['policy','trial']:
            require(evidence_hashes(child(Path(base)/'results/runs',a[key])) == a[key+'_sha256'], 'Policy/source raw changed')
        require(evidence_hashes(Path(folder)/a['step']) == a['step_sha256'], 'Pilot step evidence changed')


def run(net,step='before',base=BASE,executor=None,inspector=inspect_step,environment_check=preflight,readiness_check=None):
    base = Path(base).resolve(); p = load_protocol(base); parent = verify_parent(base,p)
    root = base/'results/runs'; registry = root/REGISTRY
    if registry.exists():
        folder = child(root,json.loads(registry.read_text())['batch']); state = json.loads((folder/'batch.json').read_text())
        validate_state(base,folder,state)
    else:
        require(step == 'before', 'Start at before; no skipped controls')
        folder = root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-packet-activation-pilot'); folder.mkdir()
        pins = dict(p['frozen_source_sha256'],**p['additional_source_sha256'])
        for name in [*pins,PROTOCOL]:
            shutil.copy2(base/name,folder/name)
        state = dict(outcome='paused',plan=plan(),attempts=[],parent=parent,protocol_sha256=sha(base/PROTOCOL),
                     captured_source_sha256=pins,created=datetime.now(timezone.utc).isoformat())
        write(folder/'batch.json',state)
        with registry.open('x') as f:
            json.dump(dict(batch=folder.name),f)
    require(len(state['attempts']) < 3, 'Activation pilot already complete; no repeat')
    item = plan()[len(state['attempts'])]
    require(step == item['step'], 'Next registered activation step is '+item['step'])
    state['outcome'] = 'running'; write(folder/'batch.json',state)
    before = {d.name for d in root.iterdir() if d.is_dir()}; entry = None
    try:
        out = folder/step; out.mkdir(); env = out/'environment'; env.mkdir()
        environment_check(env)
        if not state['attempts']:
            from run_supplement_recovery import readiness
            (readiness_check or readiness)(net,base,folder/'readiness')
            state['readiness_sha256'] = evidence_hashes(folder/'readiness'); write(folder/'batch.json',state)
        entry = dict(item,status='running'); state['attempts'].append(entry); write(folder/'batch.json',state)
        print('ACTIVATION PILOT:',step,'| capture',item['capture'],'| one frozen ML ramp',flush=True)
        raw = (executor or execute_step)(net,base,item,out)
        raw = child(root,Path(raw).name); entry['policy'] = raw.name
        trial = child(root,json.loads((raw/'policy.json').read_text())['trial']); entry['trial'] = trial.name
        report = inspector(base,out,raw,item)
        with (out/'review.json').open('x') as f:
            json.dump(report,f,indent=2)
        require(report['outcome'] == 'completed' and not report['screen_failures'], 'Activation quality failed')
        entry.update(status='passed',policy_sha256=evidence_hashes(raw),trial_sha256=evidence_hashes(trial),step_sha256=evidence_hashes(out))
        state['outcome'] = 'completed' if len(state['attempts']) == 3 else 'paused'
        print('ACTIVATION REVIEW:',json.dumps({k:report[k] for k in ['step','capture_enabled','sender_mbps','receiver_mbps','udp_loss_percent','clock_mapping','capture']}),flush=True)
    except BaseException as error:
        state.update(outcome='failed',error=repr(error))
        if entry is not None:
            entry.update(status='failed',error=repr(error))
        state['new_raw_folders'] = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name not in before)
        raise
    finally:
        write(folder/'batch.json',state); print('ACTIVATION STATE:',state['outcome'],'|',folder,flush=True)
    return folder


if 'net' in globals():
    run(net,step=globals().get('step','before'))
elif __name__ == '__main__':
    raise SystemExit('Use the existing Mininet CLI; see ACTIVATION_PILOT.md')
