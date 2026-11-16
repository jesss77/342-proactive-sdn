"""Record one persistent scheduled UDP flow inside the existing Mininet net."""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import signal
import subprocess
import time
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent))
from experiment_config import route_spec, verify_route
from continuous_udp import Schedule, canonical_summaries


def wait_for_client(client, timeout, abort_event=None, clock=time.monotonic):
    if abort_event is None:
        return client.wait(timeout=timeout)
    deadline=clock()+timeout
    while True:
        if abort_event.is_set(): raise RuntimeError('Trial cancelled by policy controller')
        remaining=deadline-clock()
        if remaining<=0: raise subprocess.TimeoutExpired('continuous sender', timeout)
        try: return client.wait(timeout=min(.2,remaining))
        except subprocess.TimeoutExpired: pass


def run(net, base, requested_bps=3000000, route='primary', duration=20, plan=None, seed=1, scenario='steady', udp_port=5202, route_verifier=None, trial_context=None, capture_links=None, on_created=None, abort_event=None):
    if route_verifier is not None and (trial_context or {}).get('route_verification') != 'owned_hostpair':
        raise ValueError('Custom route verification requires explicit owned-hostpair context')
    proof = route_verifier or verify_route
    spec = route_spec(route)
    segments = plan or [dict(segment=0, requested_bps=requested_bps, requested_seconds=duration)]
    scheduled = Schedule(segments)
    duration = scheduled.duration
    requested_bps = round(scheduled.bits[-1]/duration)
    if requested_bps <= 0 or duration <= 0:
        raise ValueError('Rate and duration must be positive')
    base = Path(base).resolve()
    out = base / 'results/runs' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + f'-{route}-continuous-{scenario}-{requested_bps}bps')
    out.mkdir(parents=True)
    clock = Path('/sys/devices/system/clocksource/clocksource0/current_clocksource')

    def read_clock():
        return clock.read_text().strip() if clock.exists() else 'unavailable'

    def git(*args):
        result = subprocess.run(['git', '-C', str(base), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    meta = dict(started=datetime.now().astimezone().isoformat(), route=route,
                requested_bps=requested_bps, payload_bytes=1200, requested_seconds=duration,
                traffic_engine='continuous-udp-v1', scenario=scenario, seed=seed,
                traffic_plan=segments, run_id=uuid.uuid4().hex,
                receive_drain_seconds=.5,
                socket_buffers='default', clock_before=read_clock(),
                git_commit=git('rev-parse', 'HEAD'), git_status=git('status', '--porcelain'),
                validity='pending_review', outcome='running', commands={}, exits={},
                capture_status={}, source_sha256={}, trial_context=trial_context, capture_links=capture_links)
    for name in ['topology.py', 'diamond_controller.py', 'requirements.txt', 'run_continuous_trial.py', 'experiment_config.py', 'continuous_udp.py', 'traffic_scenarios.py']:
        source = base / name
        shutil.copy2(source, out / name)
        meta['source_sha256'][name] = hashlib.sha256(source.read_bytes()).hexdigest()

    def save():
        (out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')

    (out / 'traffic-plan.json').write_text(json.dumps(dict(run_id=meta['run_id'], segments=segments), indent=2))
    save()
    if on_created is not None: on_created(out)
    print('Saving:', out, flush=True)
    h1, h2 = net.get('h1', 'h2')

    def capture(node, command, name):
        stdout, stderr, status = node.pexec(command)
        (out / name).write_text(stdout)
        (out / (name + '.err')).write_text(stderr)
        meta['capture_status'][name] = status
        if status:
            raise RuntimeError(f'{command} failed: {stderr}')

    def snapshot(label):
        for node, interface, _rate in (capture_links or spec['links']):
            capture(net[node], ['tc', '-s', 'qdisc', 'show', 'dev', interface],
                    f'{label}-{interface}-queue.txt')
        capture(net[spec['switch']], ['tc', '-s', 'class', 'show', 'dev', spec['egress']],
                f'{label}-bottleneck-class.txt')
        for host in [h1, h2]:
            capture(host, ['nstat', '-az', 'UdpInErrors', 'UdpRcvbufErrors',
                           'UdpSndbufErrors'], f'{label}-{host.name}-udp.txt')

    processes = {}
    started = None
    with ExitStack() as files:
        def launch(node, command, name):
            meta['commands'][name] = command
            stdout = files.enter_context((out / (name + '-process.log')).open('w'))
            stderr = files.enter_context((out / (name + '.err')).open('w'))
            processes[name] = node.popen(command, stdout=stdout, stderr=stderr)
            return processes[name]

        try:
            meta['forwarding_before'] = proof(net, route, out)
            stats = files.enter_context((out / 'vmstat.txt').open('w'))
            processes['vmstat'] = subprocess.Popen(['vmstat', '-t', '1'], stdout=stats,
                                                   stderr=subprocess.STDOUT)
            snapshot('before')
            common = [sys.executable, str(base / 'continuous_udp.py')]
            common_args = ['--plan', str(out / 'traffic-plan.json'), '--port', str(udp_port)]
            server = launch(h2, common + ['receive'] + common_args + [
                '--host', h2.IP(), '--output', str(out / 'receiver-native.json'),
                '--samples', str(out / 'receiver-samples.jsonl'),
                '--ready', str(out / 'receiver-ready.json'),
                '--max-duration', str(duration+30)], 'server')
            ready_deadline = time.monotonic()+5
            while not (out / 'receiver-ready.json').exists():
                if abort_event is not None and abort_event.is_set():
                    raise RuntimeError('Trial cancelled by policy controller')
                if server.poll() is not None or time.monotonic() > ready_deadline:
                    raise RuntimeError('Receiver did not become ready; inspect server.err')
                time.sleep(.02)
            ready = json.loads((out / 'receiver-ready.json').read_text())
            meta['udp_port'] = ready['address'][1]
            sender_args = ['--plan', str(out / 'traffic-plan.json'), '--port', str(meta['udp_port'])]
            command = common + ['send'] + sender_args + [
                '--host', h2.IP(), '--output', str(out / 'sender-native.json'),
                '--samples', str(out / 'sender-samples.jsonl')]
            meta['client_started'] = datetime.now().astimezone().isoformat()
            started = time.monotonic()
            client = launch(h1, command, 'client')
            save()
            meta['exits']['client'] = wait_for_client(client, duration+20, abort_event)
            meta['client_elapsed_s'] = time.monotonic() - started
            meta['client_finished'] = datetime.now().astimezone().isoformat()
            time.sleep(meta['receive_drain_seconds'])
            if server.poll() is not None:
                raise RuntimeError('Receiver exited before planned shutdown')
            server.send_signal(signal.SIGINT)
            meta['exits']['server'] = server.wait(timeout=5)
            if meta['exits']['client'] or meta['exits']['server']:
                raise RuntimeError('Nonzero endpoint exit; inspect outputs.')
            meta['outcome'] = 'completed'
        except (Exception, KeyboardInterrupt) as error:
            meta['outcome'] = 'timeout' if isinstance(error, subprocess.TimeoutExpired) else 'error'
            meta['error'] = str(error) or type(error).__name__
            meta['validity'] = 'invalid'
            if started is not None:
                meta['client_elapsed_s'] = time.monotonic() - started
        finally:
            # Stop both endpoints and preserve their native summaries on failure.
            for proc in processes.values():
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
            for name, proc in processes.items():
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                meta['exits'][name] = proc.returncode
            meta['clock_after'] = read_clock()
            meta['finished'] = datetime.now().astimezone().isoformat()
            save()
            try:
                snapshot('after')
                meta['forwarding_after'] = proof(net, route, out, 'after')
            except Exception as error:
                meta['snapshot_error'] = str(error)
                meta['validity'] = 'invalid'
            save()

    if meta['outcome'] == 'completed':
        try:
            sender = json.loads((out / 'sender-native.json').read_text())
            receiver = json.loads((out / 'receiver-native.json').read_text())
            meta['traffic_started_epoch_s'] = sender['start_wall_epoch_s']
            meta['traffic_finished_epoch_s'] = sender['end_wall_epoch_s']
            client_json, server_json = canonical_summaries(sender, receiver)
            for name, data in [('client', client_json), ('server', server_json)]:
                with (out / (name + '.json')).open('x') as target:
                    json.dump(data, target, indent=2)
            meta['pacer'] = {key: sender[key] for key in [
                'discarded_budget_bits', 'planned_bits', 'skipped_ticks', 'max_pacer_gap_s', 'send_errors']}
            for name in ['client', 'server']:
                data = json.loads((out / (name + '.json')).read_text())
                if data.get('error') or not data.get('end'):
                    raise ValueError(f'{name} lacks a successful final result')
                if name == 'server':
                    received = data['end']['sum_received']
                    print(f'Receiver: {received["bits_per_second"] / 1e6:.3f} Mbit/s; '
                          f'loss {received["lost_percent"]:.3f}%')
        except (OSError, ValueError, KeyError) as error:
            meta.update(outcome='incomplete_output', validity='invalid', error=str(error))
    save()
    print('Outcome:', meta['outcome'], '| Validity:', meta['validity'])
    print('Saved:', out)
    return out


if 'net' in globals():
    run(net, Path(__file__).resolve().parent)
elif __name__ == '__main__':
    raise SystemExit('Run this from the Mininet CLI as shown in SETUP.md.')
