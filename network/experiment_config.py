"""Route definitions and the explicitly recorded calibration revision."""
from contextlib import contextmanager
from pathlib import Path
import json
import re

PROFILE = 'forward-cburst16k-source250-v1'
ROUTES = {
    'primary': dict(uplink=3, switch='s2', upstream='s1-eth3',
                    egress='s2-eth2', ingress='s4-eth3', capacity_bps=10_000_000,
                    capacity_limited_interfaces=['s2-eth2'],
                    links=[('h1', 'h1-eth0', 100), ('s1', 's1-eth3', 100),
                           ('s2', 's2-eth2', 10), ('s4', 's4-eth1', 100)]),
    'alternate': dict(uplink=4, switch='s3', upstream='s1-eth4',
                      egress='s3-eth2', ingress='s4-eth4', capacity_bps=20_000_000,
                      capacity_limited_interfaces=['s1-eth4', 's3-eth2'],
                      links=[('h1', 'h1-eth0', 100), ('s1', 's1-eth4', 20),
                             ('s3', 's3-eth2', 20), ('s4', 's4-eth1', 100)])
}


def route_spec(route):
    if route not in ROUTES:
        raise ValueError('route must be primary or alternate')
    return ROUTES[route]


def validate_flow(text, destination, port):
    """Require exactly one destination rule with the requested numeric output."""
    lines = [line for line in text.splitlines()
             if ('dl_dst=' + destination) in line and 'actions=' in line]
    if len(lines) != 1 or not re.search(
            r'actions=output:' + str(port) + r'\s*$', lines[0]):
        raise RuntimeError(f'Forwarding mismatch for {destination}: expected output {port}')


def verify_route(net, route, folder, phase='before'):
    spec = route_spec(route)
    proof = {}
    for switch, destination in [('s1', '00:00:00:00:00:02'),
                                 ('s4', '00:00:00:00:00:01')]:
        command = ['ovs-ofctl', '-O', 'OpenFlow13', '--no-names', 'dump-flows', switch]
        out, err, code = net[switch].pexec(command)
        Path(folder, f'{phase}-{switch}-flows.txt').write_text(out + err)
        if code:
            raise RuntimeError(err)
        if any(int(value) > 100 for value in re.findall(r'priority=(\d+)', out)):
            raise RuntimeError('Unexpected higher-priority routing overlay; passive route is not established')
        validate_flow(out, destination, spec['uplink'])
        proof[switch] = dict(destination=destination, output_port=spec['uplink'])
    return proof


@contextmanager
def calibrated_profile(net, route, folder):
    """Apply only from the known original profile and always attempt restoration."""
    folder = Path(folder)
    spec = route_spec(route)
    commands = []
    def execute(node, args, label):
        out, err, code = net[node].pexec(args)
        commands.append(dict(label=label, node=node, command=args,
                             stdout=out, stderr=err, exit=code))
        (folder / 'profile-commands.json').write_text(json.dumps(commands, indent=2))
        if code:
            raise RuntimeError(f'{node}: {err}')
        return out

    # Refuse to overwrite a different calibration or an unshaped topology.
    for node, interface, rate in spec['links']:
        text = execute(node, ['tc', '-s', 'class', 'show', 'dev', interface], 'preflight')
        if not all(part in text for part in
                   [f'rate {rate}Mbit', f'ceil {rate}Mbit', 'burst 15Kb', 'cburst 1600b']):
            raise RuntimeError(f'{interface}: expected original rate/ceil/cburst; inspect profile log')
        queue_text = execute(node, ['tc', '-s', 'qdisc', 'show', 'dev', interface], 'preflight-queue')
        if not re.search(r'netem.*limit 50\b.*delay 1ms', queue_text):
            raise RuntimeError(f'{interface}: expected original netem limit 50 and delay 1ms')
    source_text = next(c['stdout'] for c in commands
                       if c['label'] == 'preflight-queue' and c['node'] == 'h1')
    if not re.search(r'netem.*limit 50\b.*delay 1ms', source_text):
        raise RuntimeError('Expected original source netem limit 50, delay 1ms')

    def change_class(node, interface, rate, cburst, label):
        execute(node, ['tc', 'class', 'change', 'dev', interface, 'parent', '5:',
                       'classid', '5:1', 'htb', 'rate', f'{rate}mbit',
                       'ceil', f'{rate}mbit', 'burst', '15360',
                       'cburst', str(cburst)], label)
    def change_source(limit, label):
        execute('h1', ['tc', 'qdisc', 'change', 'dev', 'h1-eth0', 'parent', '5:1',
                       'handle', '10:', 'netem', 'delay', '1ms', 'limit', str(limit)], label)
    touched = []
    source_touched = False
    try:
        for link in spec['links']:
            change_class(*link, 16384, 'apply')
            touched.append(link)
        change_source(250, 'apply-source')
        source_touched = True
        for node, interface, _rate in spec['links']:
            execute(node, ['tc', '-s', 'class', 'show', 'dev', interface], 'active-class')
            execute(node, ['tc', '-s', 'qdisc', 'show', 'dev', interface], 'active-queue')
        yield dict(id=PROFILE, route=route, cburst_bytes=16384, burst_bytes=15360,
                   source_queue_packets=250, bottleneck_queue_packets=50,
                   delay_ms=1, forward_links=spec['links'])
    finally:
        failures = []
        if source_touched:
            try:
                change_source(50, 'restore-source')
            except Exception as error:
                failures.append(str(error))
        for link in reversed(touched):
            try:
                change_class(*link, 1600, 'restore')
            except Exception as error:
                failures.append(str(error))
        (folder / 'restoration.json').write_text(json.dumps(dict(failures=failures), indent=2))
        if failures:
            raise RuntimeError('Profile restoration failed: ' + '; '.join(failures))
