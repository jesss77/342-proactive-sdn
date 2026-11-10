"""Run from the Mininet CLI with a live `net`; see SETUP.md."""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import signal
import subprocess
import time


def run(net, base):
    base = Path(base).resolve()
    out = base / 'results/runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f-primary-3M')
    out.mkdir(parents=True)
    clock = Path('/sys/devices/system/clocksource/clocksource0/current_clocksource')

    def read_clock():
        return clock.read_text().strip() if clock.exists() else 'unavailable'

    def git(*args):
        result = subprocess.run(['git', '-C', str(base), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    meta = dict(started=datetime.now().astimezone().isoformat(), route='primary',
                requested_bps=3000000, payload_bytes=1200, requested_seconds=20,
                socket_buffers='default', clock_before=read_clock(),
                git_commit=git('rev-parse', 'HEAD'), git_status=git('status', '--porcelain'),
                validity='pending_review', outcome='running', commands={}, exits={},
                capture_status={}, source_sha256={})
    for name in ['topology.py', 'diamond_controller.py', 'requirements.txt', 'run_primary_trial.py']:
        source = base / name
        shutil.copy2(source, out / name)
        meta['source_sha256'][name] = hashlib.sha256(source.read_bytes()).hexdigest()

    def save():
        (out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')

    save()
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
        for node, interface in [('h1', 'h1-eth0'), ('s1', 's1-eth3'),
                                ('s2', 's2-eth2'), ('s4', 's4-eth1')]:
            capture(net[node], ['tc', '-s', 'qdisc', 'show', 'dev', interface],
                    f'{label}-{interface}-queue.txt')
        capture(net['s2'], ['tc', '-s', 'class', 'show', 'dev', 's2-eth2'],
                f'{label}-bottleneck-class.txt')
        for host in [h1, h2]:
            capture(host, ['nstat', '-az', 'UdpInErrors', 'UdpRcvbufErrors',
                           'UdpSndbufErrors'], f'{label}-{host.name}-udp.txt')

    processes = {}
    started = None
    with ExitStack() as files:
        def launch(node, command, name):
            meta['commands'][name] = command
            stdout = files.enter_context((out / (name + '.json')).open('w'))
            stderr = files.enter_context((out / (name + '.err')).open('w'))
            processes[name] = node.popen(command, stdout=stdout, stderr=stderr)
            return processes[name]

        try:
            stats = files.enter_context((out / 'vmstat.txt').open('w'))
            processes['vmstat'] = subprocess.Popen(['vmstat', '-t', '1'], stdout=stats,
                                                   stderr=subprocess.STDOUT)
            snapshot('before')
            server = launch(h2, ['iperf3', '-s', '-1', '-B', h2.IP(), '-p', '5201', '-J'], 'server')
            time.sleep(1)
            if server.poll() is not None:
                raise RuntimeError('Server exited before traffic; inspect server.err.')
            command = ['iperf3', '-c', h2.IP(), '-p', '5201', '-u', '-b', '3M',
                       '-l', '1200', '-t', '20', '-J']
            meta['client_started'] = datetime.now().astimezone().isoformat()
            started = time.monotonic()
            client = launch(h1, command, 'client')
            save()
            meta['exits']['client'] = client.wait(timeout=40)
            meta['client_elapsed_s'] = time.monotonic() - started
            meta['exits']['server'] = server.wait(timeout=10)
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
            # Interrupt both endpoints first so iperf3 can flush partial output.
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
            except Exception as error:
                meta['snapshot_error'] = str(error)
                meta['validity'] = 'invalid'
            save()

    if meta['outcome'] == 'completed':
        try:
            for name in ['client', 'server']:
                data = json.loads((out / (name + '.json')).read_text())
                if data.get('error') or not data.get('end'):
                    raise ValueError(f'{name} lacks a successful final result')
                if name == 'client':
                    received = data['end']['sum_received']
                    print(f'Receiver: {received["bits_per_second"] / 1e6:.3f} Mbit/s; '
                          f'loss {received["lost_percent"]:.3f}%')
        except (ValueError, KeyError) as error:
            meta.update(outcome='incomplete_output', validity='invalid', error=str(error))
    save()
    print('Outcome:', meta['outcome'], '| Validity:', meta['validity'])
    print('Saved:', out)
    return out


if 'net' in globals():
    run(net, Path(__file__).resolve().parent)
elif __name__ == '__main__':
    raise SystemExit('Run this from the Mininet CLI as shown in SETUP.md.')
