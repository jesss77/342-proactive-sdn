from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import json
import shutil
import subprocess
import time

base = Path('/home/jess/cmps342')
out = base / 'results' / datetime.now().strftime('P02-primary-3M-%Y%m%d-%H%M%S')
out.mkdir()
shutil.copy2(__file__, out / 'protocol.py')
(out / 'session.txt').write_text((base / 'results/active-session.txt').read_text())
clock = Path('/sys/devices/system/clocksource/clocksource0/current_clocksource')
meta = dict(started=datetime.now().astimezone().isoformat(), route='primary',
            requested_bps=3000000, payload_bytes=1200, requested_seconds=20,
            socket_buffers='default', clock_before=clock.read_text().strip())
(out / 'metadata.json').write_text(json.dumps(meta, indent=2))
print('Saving:', out, flush=True)
if meta['clock_before'] != 'kvm-clock':
    raise RuntimeError('Expected kvm-clock; traffic not started.')
h1, h2 = net.get('h1', 'h2')

def capture(node, command, name):
    stdout, stderr, status = node.pexec(command)
    (out / name).write_text(stdout)
    (out / (name + '.err')).write_text(stderr)
    if status:
        raise RuntimeError(f'{command} failed: {stderr}')

def snapshot(label):
    for host, interface in [('h1', 'h1-eth0'), ('s1', 's1-eth3'),
                            ('s2', 's2-eth2'), ('s4', 's4-eth1')]:
        capture(net[host], ['tc', '-s', 'qdisc', 'show', 'dev', interface],
                f'{label}-{interface}-queue.txt')
    capture(net['s2'], ['tc', '-s', 'class', 'show', 'dev', 's2-eth2'],
            f'{label}-bottleneck-class.txt')
    for host in [h1, h2]:
        capture(host, ['nstat', '-az', 'UdpInErrors', 'UdpRcvbufErrors',
                       'UdpSndbufErrors'], f'{label}-{host.name}-udp.txt')

processes = []
with ExitStack() as files:
    def launch(node, command, name):
        stdout = files.enter_context((out / (name + '.json')).open('w'))
        stderr = files.enter_context((out / (name + '.err')).open('w'))
        proc = node.popen(command, stdout=stdout, stderr=stderr)
        processes.append(proc)
        return proc

    try:
        stats_output = files.enter_context((out / 'vmstat.txt').open('w'))
        processes.append(subprocess.Popen(['vmstat', '-t', '1'],
                         stdout=stats_output, stderr=subprocess.STDOUT))
        snapshot('before')
        server = launch(h2, ['iperf3', '-s', '-1', '-B', h2.IP(),
                             '-p', '5201', '-J'], 'server')
        time.sleep(1)
        if server.poll() is not None:
            raise RuntimeError('Server exited; inspect server.err.')
        command = ['iperf3', '-c', h2.IP(), '-p', '5201', '-u',
                   '-b', '3M', '-l', '1200', '-t', '20', '-J']
        meta['client_command'] = command
        meta['client_started'] = datetime.now().astimezone().isoformat()
        started = time.monotonic()
        print('Starting h1 -> h2: 3 Mbit/s, 20 seconds...', flush=True)
        client = launch(h1, command, 'client')
        meta['client_exit'] = client.wait(timeout=40)
        meta['client_elapsed_s'] = time.monotonic() - started
        meta['client_finished'] = datetime.now().astimezone().isoformat()
        meta['server_exit'] = server.wait(timeout=10)
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        meta['clock_after'] = clock.read_text().strip()
        (out / 'metadata.json').write_text(json.dumps(meta, indent=2))
        snapshot('after')

data = json.loads((out / 'client.json').read_text())
if data.get('error') or meta['client_exit'] or meta['server_exit']:
    raise RuntimeError(f'Traffic did not complete normally: {data.get("error", meta)}')
for name in ['sum_sent', 'sum_received']:
    value = data['end'][name]
    print(f'{name}: {value["bits_per_second"]/1e6:.3f} Mbit/s; '
          f'{value["seconds"]:.3f} s')
received = data['end']['sum_received']
print(f'Loss: {received["lost_packets"]}/{received["packets"]} '
      f'({received["lost_percent"]:.3f}%); jitter: {received["jitter_ms"]:.3f} ms')
print('Process elapsed:', round(meta['client_elapsed_s'], 3), 's')
print('Intervals (seconds, Mbit/s):', [
    (round(i['sum']['seconds'], 3), round(i['sum']['bits_per_second']/1e6, 3))
    for i in data.get('intervals', [])])
print('Clock before/after:', meta['clock_before'], '/', meta['clock_after'])
print('Saved:', out)
