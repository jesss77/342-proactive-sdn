"""Run inside the Mininet CLI; route must match the already running controller."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from experiment_config import calibrated_profile, route_spec, verify_route
from run_primary_trial import run as traffic_trial
from traffic_scenarios import schedule
from traffic_scenarios import continuous_schedule
from run_continuous_trial import run as continuous_trial


def stop(proc):
    if proc is None:
        return None
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait(timeout=3)


def interface_counts():
    result = {}
    for name in ['s1-eth3', 's1-eth4', 's2-eth2', 's3-eth2', 's4-eth3', 's4-eth4']:
        folder = Path('/sys/class/net') / name / 'statistics'
        try:
            result[name] = {key: int((folder / key).read_text())
                            for key in ['tx_bytes', 'tx_packets', 'rx_bytes', 'rx_packets']}
        except (OSError, ValueError) as error:
            result[name] = dict(error=str(error))
    return result


def run_experiment(net, route='primary', requested_bps=3_000_000,
                   interval=0.25, duration=20, scenario='steady', seed=1, engine='iperf'):
    spec = route_spec(route)
    if interval not in [0.1, 0.25, 0.5]:
        raise ValueError('Use one native interval: 0.1, 0.25 or 0.5 seconds')
    if os.cpu_count() != 1:
        raise RuntimeError('This calibration profile requires the recorded one-vCPU guest')
    if engine not in ['iperf', 'continuous']:
        raise ValueError('engine must be iperf or continuous')
    segments = (continuous_schedule if engine == 'continuous' else schedule)(
        scenario, requested_bps, duration, seed)
    folder = BASE / 'results/runs' / (
        datetime.now().strftime('%Y%m%d-%H%M%S-%f') +
        f'-experiment-{route}-{engine}-{scenario}-{round(interval*1000)}ms')
    folder.mkdir(parents=True)
    meta = dict(started=datetime.now(timezone.utc).isoformat(), route=route,
                policy='fixed', interventions=False, interval_s=interval,
                scenario=scenario, seed=seed, planned_segments=segments, traffic_engine=engine,
                segment_mode=('one persistent UDP flow; continuous sequence across schedule'
                              if engine == 'continuous' else 'independent iperf endpoints; startup gaps recorded'),
                payload_bytes=1200, vm_cpus=os.cpu_count(), platform=platform.uname()._asdict(),
                outcome='running', validity='pending_review', trials=[], source_sha256={})
    def save():
        (folder / 'experiment.json').write_text(json.dumps(meta, indent=2) + '\n')
    for name in ['topology.py', 'diamond_controller.py', 'requirements.txt',
                 'run_experiment.py', 'experiment_config.py', 'run_primary_trial.py',
                 'collect_path.py', 'traffic_scenarios.py', 'inspect_experiment.py',
                 'continuous_udp.py', 'run_continuous_trial.py']:
        source = BASE / name
        shutil.copy2(source, folder / name)
        meta['source_sha256'][name] = hashlib.sha256(source.read_bytes()).hexdigest()
    save()
    print('Experiment folder:', folder, flush=True)
    try:
        meta['forwarding_before'] = verify_route(net, route, folder)
        with calibrated_profile(net, route, folder) as profile:
            meta['profile'] = profile
            out, err, code = net['h1'].pexec(
                ['ping', '-n', '-D', '-c', '10', '-i', '0.2', '-w', '5', net['h2'].IP()])
            (folder / 'ping-idle.txt').write_text(out + err)
            meta['idle_ping_exit'] = code
            if code:
                raise RuntimeError('Idle ping failed; inspect ping-idle.txt')
            meta['counters_before'] = interface_counts()
            collector = ping = None
            with ExitStack() as files:
                try:
                    log = files.enter_context((folder / 'collector.log').open('w'))
                    collector = subprocess.Popen(
                        ['/usr/bin/python3', str(BASE / 'collect_path.py'),
                         str(folder / 'samples.jsonl'), '--route', route,
                         '--interval', str(interval), '--duration',
                         str(sum(s['requested_seconds'] + 15 for s in segments) + 20)],
                        stdout=log, stderr=subprocess.STDOUT)
                    time.sleep(2)
                    if collector.poll() is not None:
                        raise RuntimeError('Collector exited before traffic')
                    ping_out = files.enter_context((folder / 'ping-loaded.txt').open('w'))
                    ping = net['h1'].popen(
                        ['ping', '-n', '-D', '-i', '0.2', net['h2'].IP()],
                        stdout=ping_out, stderr=subprocess.STDOUT)
                    meta['probe'] = dict(command=['ping', '-n', '-D', '-i', '0.2', net['h2'].IP()],
                                         started_monotonic=time.monotonic())
                    save()
                    work = ([(dict(segment=0, requested_seconds=sum(
                        s['requested_seconds'] for s in segments), requested_bps=requested_bps))]
                        if engine == 'continuous' else segments)
                    for segment in work:
                        print('Segment:', segment, flush=True)
                        timing = dict(segment=segment['segment'],
                                      call_start_monotonic=time.monotonic())
                        if engine == 'continuous':
                            trial = continuous_trial(net, BASE, requested_bps, route,
                                segment['requested_seconds'], plan=segments, seed=seed, scenario=scenario)
                        else:
                            trial = traffic_trial(net, BASE, segment['requested_bps'], route,
                                                  segment['requested_seconds'])
                        timing.update(call_end_monotonic=time.monotonic(), run=trial.name)
                        meta['trials'].append(timing)
                        (trial / 'experiment-reference.json').write_text(json.dumps(dict(
                            experiment=str(folder), profile=profile, route=route,
                            scenario=scenario, seed=seed, interval_s=interval,
                            segment=segment, traffic_engine=engine,
                            continuous_schedule=segments if engine == 'continuous' else None), indent=2))
                        save()
                        trial_meta = json.loads((trial / 'metadata.json').read_text())
                        if trial_meta['outcome'] != 'completed':
                            raise RuntimeError('Traffic trial failed: ' + trial.name)
                        if collector.poll() is not None or ping.poll() is not None:
                            raise RuntimeError('Collector or RTT probe exited during traffic')
                    time.sleep(2)
                finally:
                    meta['ping_exit'] = stop(ping)
                    meta['collector_exit'] = stop(collector)
                    meta['counters_after'] = interface_counts()
                    save()
            if meta['collector_exit'] != 0:
                raise RuntimeError('Collector did not exit cleanly')
        meta['forwarding_after'] = verify_route(net, route, folder, 'after')
        meta['outcome'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        meta.update(outcome='error', validity='invalid', error=str(error) or type(error).__name__)
    finally:
        meta['finished'] = datetime.now(timezone.utc).isoformat()
        save()
    print('Experiment outcome:', meta['outcome'], '| validity:', meta['validity'], flush=True)
    print('Saved:', folder, flush=True)
    return folder


if 'net' in globals():
    run_experiment(net, route=globals().get('route', 'primary'),
                   requested_bps=globals().get('requested_bps', 3_000_000),
                   interval=globals().get('interval', 0.25),
                   duration=globals().get('duration', 20),
                   scenario=globals().get('scenario', 'steady'), seed=globals().get('seed', 1),
                   engine=globals().get('engine', 'iperf'))
elif __name__ == '__main__':
    raise SystemExit('Load this file from the Mininet CLI with net and __file__ supplied.')
