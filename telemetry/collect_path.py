"""Native-rate raw collector with per-read timing and process/child CPU accounting."""
import argparse
import json
import math
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from network.experiment_config import route_spec


def root_qdisc(stdout):
    roots = [q for q in json.loads(stdout) if q.get('root')]
    if len(roots) != 1:
        raise ValueError('Expected one root qdisc')
    return roots[0]


def query_qdisc(interface, capacity_bps, runner=None, clock=None):
    runner = runner or subprocess.run
    clock = clock or time.monotonic
    record = dict(interface=interface, capacity_bps=capacity_bps, tc_start=clock())
    try:
        result = runner(['tc', '-j', '-s', 'qdisc', 'show', 'dev', interface],
                        capture_output=True, text=True, timeout=2)
        record.update(tc_exit=result.returncode, tc_stdout=result.stdout,
                      tc_stderr=result.stderr)
        if result.returncode == 0:
            try:
                record['root_qdisc'] = root_qdisc(result.stdout)
            except (ValueError, TypeError) as error:
                record['tc_error'] = str(error)
    except (subprocess.TimeoutExpired, OSError) as error:
        record['tc_error'] = str(error)
    record['tc_end'] = clock()
    return record


def query_qdiscs(interfaces, runner=None, clock=None):
    """One read-only dump per cycle; per-interface records share query bounds.

    Kernel dump entries are sequential, not an atomic simultaneous snapshot.
    Preserve the complete command output once, with filtered compatibility views.
    """
    runner = runner or subprocess.run
    clock = clock or time.monotonic
    command = ['tc', '-j', '-s', 'qdisc', 'show']
    batch = dict(command=command, tc_start=clock(), query_scope='all qdiscs in root namespace')
    items = None
    try:
        result = runner(command, capture_output=True, text=True, timeout=2)
        batch.update(tc_exit=result.returncode, tc_stdout=result.stdout, tc_stderr=result.stderr)
        if result.returncode == 0:
            items = json.loads(result.stdout)
            if not isinstance(items, list) or any(not isinstance(q, dict) for q in items):
                raise ValueError('Expected a JSON list of qdisc objects')
        else:
            batch['tc_error'] = 'Batch qdisc command failed'
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        batch['tc_error'] = str(error)
    batch['tc_end'] = clock()
    queues = {}
    for interface, capacity_bps in interfaces:
        record = dict(interface=interface, capacity_bps=capacity_bps,
                      tc_start=batch['tc_start'], tc_end=batch['tc_end'],
                      tc_exit=batch.get('tc_exit'), shared_batch=True)
        if batch.get('tc_error'):
            record['tc_error'] = batch['tc_error']
        else:
            selected = [q for q in items if q.get('dev') == interface]
            record['tc_stdout'] = json.dumps(selected)
            try:
                root = root_qdisc(record['tc_stdout'])
                if any(not isinstance(root.get(k), int) or root[k] < 0 for k in ['bytes', 'drops']):
                    raise ValueError('Missing or invalid root counters')
                record['root_qdisc'] = root
            except (ValueError, TypeError) as error:
                record['tc_error'] = str(error)
        queues[interface] = record
    return batch, queues


def collect(output, route='primary', interval=0.25, duration=60, coverage='route'):
    if coverage not in ['route', 'all']:
        raise ValueError('coverage must be route or all')
    spec = route_spec(route)
    qdisc_specs = ([(name, rate*1_000_000) for _node, name, rate in spec['links'][1:3]]
                   if coverage == 'route' else [('s1-eth3',100_000_000),('s2-eth2',10_000_000),
                                                ('s1-eth4',20_000_000),('s3-eth2',20_000_000)])
    schema = 5 if coverage == 'route' else 6
    if not math.isfinite(interval) or not math.isfinite(duration) or min(interval, duration) <= 0:
        raise ValueError('Positive finite interval and duration required')
    if Path(output).exists() or Path(str(output) + '.stats.json').exists():
        raise FileExistsError('Refusing to overwrite collector data or statistics')
    try:
        import resource
        def cpu():
            own = resource.getrusage(resource.RUSAGE_SELF)
            child = resource.getrusage(resource.RUSAGE_CHILDREN)
            return dict(self_s=own.ru_utime + own.ru_stime,
                        children_s=child.ru_utime + child.ru_stime)
    except ImportError:
        def cpu():
            return {}
    stopped = False
    def stop(_signal, _frame):
        nonlocal stopped
        stopped = True
    original_handlers = {s: signal.signal(s, stop) for s in [signal.SIGTERM, signal.SIGINT]}
    interfaces = sorted(set([spec['upstream'], spec['egress'], spec['ingress'],
                             's1-eth3', 's1-eth4', 's4-eth3', 's4-eth4']))
    interfaces = sorted(set(interfaces) | {name for name, _rate in qdisc_specs})
    start = deadline = time.monotonic()
    before_cpu = cpu()
    sequence = skipped = 0
    try:
        with Path(output).open('x') as f:
            while not stopped and time.monotonic() - start < duration:
                time.sleep(max(0, deadline - time.monotonic()))
                if stopped or time.monotonic() - start >= duration:
                    break
                row = dict(schema_version=schema, coverage=coverage, sample=sequence, utc=datetime.now(timezone.utc).isoformat(),
                           route=route, capacity_bps=spec['capacity_bps'], egress=spec['egress'],
                           monotonic_start=time.monotonic(), scheduled=deadline,
                           requested_interval=interval, skipped_before_sample=skipped,
                           interfaces={})
                for name in interfaces:
                    folder = Path('/sys/class/net') / name / 'statistics'
                    before = time.monotonic()
                    record = {}
                    try:
                        record.update({key: int((folder / key).read_text()) for key in
                                       ['tx_bytes', 'rx_bytes', 'tx_packets', 'rx_packets']})
                    except (OSError, ValueError) as error:
                        record['error'] = str(error)
                    record.update(read_start=before, read_end=time.monotonic())
                    row['interfaces'][name] = record
                # Always query both inter-switch forward interfaces, including
                # the first limiting queue on the alternate route.
                row['tc_batch'], row['qdiscs'] = query_qdiscs(qdisc_specs)
                # Retain the original egress fields so old analysis callers work.
                row.update({key: value for key, value in row['qdiscs'][spec['egress']].items()
                            if key not in ['interface', 'capacity_bps']})
                row['monotonic_end'] = time.monotonic()
                f.write(json.dumps(row) + '\n')
                f.flush()
                sequence += 1
                deadline += interval
                skipped = 0
                if deadline < time.monotonic():
                    skipped = int((time.monotonic() - deadline) / interval) + 1
                    deadline += skipped * interval
    finally:
        for s, handler in original_handlers.items():
            signal.signal(s, handler)
        elapsed = time.monotonic() - start
        after_cpu = cpu()
        usage = {key: after_cpu[key] - value for key, value in before_cpu.items()}
        Path(str(output) + '.stats.json').write_text(json.dumps(dict(
            route=route, schema_version=schema, coverage=coverage, backend='one-tc-json-dump-per-cycle',
            tc_processes_per_sample=1, interval_s=interval, samples=sequence, elapsed_s=elapsed,
            queried_qdiscs=[name for name, _rate in qdisc_specs],
            cpu_seconds=usage, cpu_percent_one_core={
                key: 100 * value / elapsed for key, value in usage.items()},
            stopped_by_signal=stopped), indent=2))
    print('Saved', sequence, 'samples to', output, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output')
    p.add_argument('--route', choices=['primary', 'alternate'], default='primary')
    p.add_argument('--interval', type=float, default=0.25)
    p.add_argument('--duration', type=float, default=60)
    p.add_argument('--coverage', choices=['route','all'], default='route')
    args = p.parse_args()
    collect(args.output, args.route, args.interval, args.duration, args.coverage)
