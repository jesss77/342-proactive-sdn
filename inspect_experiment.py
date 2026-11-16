"""Read-only route-aware assessment; write derivatives outside raw run directories."""
import argparse
import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from experiment_config import route_spec


def percentiles(values):
    if not values:
        return None
    ordered = sorted(values)
    return {key: ordered[round((len(ordered)-1)*fraction)]
            for key, fraction in [('min', 0), ('median', .5), ('p95', .95), ('max', 1)]}


def counter_delta(before, after, pattern):
    a, b = re.search(pattern, before), re.search(pattern, after)
    if not a or not b:
        raise ValueError('Counter missing from snapshot')
    delta = int(b[1]) - int(a[1])
    if delta < 0:
        raise ValueError('Counter reset')
    return delta


def inspect_trial(path, dynamic=False):
    path = Path(path)
    meta = json.loads((path / 'metadata.json').read_text())
    context = meta.get('trial_context') or {}
    if dynamic and not context.get('dynamic_routing'):
        raise ValueError('Dynamic screening requires explicit policy-trial context')
    if context.get('dynamic_routing') and not dynamic:
        raise ValueError('Use the policy inspector for a dynamically routed trial')
    spec = route_spec(meta['route'])
    sender_json = json.loads((path / 'client.json').read_text())
    receiver_json = json.loads((path / 'server.json').read_text())
    sender = sender_json.get('end', {}).get('sum_sent')
    receiver = receiver_json.get('end', {}).get('sum_received')
    failures = []
    if meta['outcome'] != 'completed' or sender_json.get('error') or receiver_json.get('error'):
        failures.append('endpoint_outcome')
    if not sender or not receiver:
        raise ValueError('Missing successful endpoint summaries')
    if any(meta['exits'].get(name) != 0 for name in ['client', 'server']):
        failures.append('endpoint_exit')
    if meta.get('snapshot_error') or any(meta.get('capture_status', {}).values()):
        failures.append('snapshot_error')
    if meta.get('clock_before') != meta.get('clock_after'):
        failures.append('clock_changed')
    target, duration = meta['requested_bps'], meta['requested_seconds']
    mixed = meta.get('traffic_engine') == 'continuous-udp-v1' and meta.get('scenario') != 'steady'
    if abs(sender['bits_per_second']/target - 1) > .05:
        failures.append('achieved_sender_rate')
    for name, value in [('sender', sender), ('receiver', receiver)]:
        if abs(value['seconds']/duration - 1) > .05:
            failures.append(name + '_duration')
    if abs(meta.get('client_elapsed_s', math.inf)/duration - 1) > .05:
        failures.append('process_elapsed')
    drops = {}
    for _node, interface, _rate in (meta.get('capture_links') if dynamic else spec['links']):
        drops[interface] = counter_delta(
            (path / f'before-{interface}-queue.txt').read_text(),
            (path / f'after-{interface}-queue.txt').read_text(), r'dropped (\d+)')
    # The alternate has two equally limiting 20 Mbit/s links. Both are valid
    # overload drop locations; the 100 Mbit/s access interfaces are not.
    allowed = ['s2-eth2','s1-eth4','s3-eth2'] if dynamic else spec['capacity_limited_interfaces']
    if any(value for interface, value in drops.items() if interface not in allowed):
        failures.append('access_link_drop')
    errors = {}
    for host in ['h1', 'h2']:
        snapshots = [{key: int(value) for key, value in re.findall(
            r'^(Udp\w+)\s+(\d+)', (path / f'{phase}-{host}-udp.txt').read_text(), re.M)}
                     for phase in ['before', 'after']]
        errors[host] = {key: snapshots[1][key]-snapshots[0][key]
                        for key in ['UdpInErrors', 'UdpRcvbufErrors', 'UdpSndbufErrors']}
    if any(value for counts in errors.values() for value in counts.values()):
        failures.append('udp_error')
    low_load = not mixed and target <= .8 * spec['capacity_bps']
    if low_load and (receiver['lost_percent'] > .1 or
                     abs(receiver['bits_per_second']/target - 1) > .05 or any(drops.values())):
        failures.append('below_capacity_delivery')
    if not dynamic and not mixed and target > spec['capacity_bps'] and not any(
            drops[interface] > 0 for interface in spec['capacity_limited_interfaces']):
        failures.append('overload_not_established')
    times = re.findall(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',
                       (path / 'vmstat.txt').read_text())
    from datetime import datetime
    gaps = [(datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds()
            for a, b in zip(times, times[1:])]
    if not gaps or max(gaps) > 2:
        failures.append('resource_sampling_gap')
    pacer = meta.get('pacer')
    if pacer and pacer['planned_bits'] > 0 and pacer['discarded_budget_bits']/pacer['planned_bits'] > .05:
        failures.append('source_pacing_budget_discarded')
    return dict(run=path.name, route=meta['route'], requested_bps=target,
                sender=sender, receiver=receiver, queue_drop_deltas=drops,
                udp_error_deltas=errors, screen_failures=failures,
                max_resource_gap_s=max(gaps, default=None),
                traffic_engine=meta.get('traffic_engine', 'iperf'),
                scenario=meta.get('scenario', 'steady'), pacer=pacer,
                mixed_schedule_note=('Whole-run average is not a congestion label; inspect per-window data.'
                                     if mixed else None),
                sender_based_missing_datagrams=(sender['bytes']-receiver['bytes'])/meta['payload_bytes'],
                accounting_note='Queue counters include RTT probes and control packets; keep sequence loss separately.')


def sample_intervals(rows):
    """Use query midpoints, actual dt and counter deltas; retain reset/gap flags."""
    previous = None
    for row in rows:
        root = row.get('root_qdisc')
        if row.get('tc_exit') != 0 or row.get('tc_error') or not root:
            previous = None
            continue
        now = (row['tc_start'] + row['tc_end']) / 2
        if previous is not None:
            before, prior_time = previous
            dt = now-prior_time
            byte_delta = root['bytes']-before['root_qdisc']['bytes']
            drop_delta = root['drops']-before['root_qdisc']['drops']
            reset = min(byte_delta, drop_delta) < 0
            valid = (dt > 0 and not reset and dt <= 2 * row['requested_interval']
                     and row['tc_end']-row['tc_start'] <= row['requested_interval']
                     and before['tc_end']-before['tc_start'] <= before['requested_interval']
                     and not row.get('skipped_before_sample', 0))
            yield dict(utc=row['utc'], monotonic=now, actual_dt_s=dt,
                       query_duration_s=row['tc_end']-row['tc_start'],
                       sampling_valid=valid, counter_reset=reset,
                       qdisc_departure_bps=8*byte_delta/dt if dt > 0 and not reset else None,
                       utilization=8*byte_delta/dt/row['capacity_bps'] if dt > 0 and not reset else None,
                       drops_delta=drop_delta, backlog_bytes=root.get('backlog'),
                       queue_packets=root.get('qlen'), skipped=row.get('skipped_before_sample', 0))
        previous = row, now


def queue_rows(rows, interface):
    """Each queue has its own query clock, capacity and failure continuity."""
    for row in rows:
        if 'qdiscs' in row:
            query = row['qdiscs'].get(interface, dict(tc_error='queue not queried'))
            yield dict(row, **query)
        elif row.get('egress') == interface:
            yield row


def queue_summary(rows, interface):
    selected = list(queue_rows(rows, interface))
    intervals = list(sample_intervals(selected))
    roots = [row['root_qdisc'] for row in selected
             if row.get('tc_exit') == 0 and not row.get('tc_error') and row.get('root_qdisc')]
    return dict(samples=len(selected), failed_queries=sum(
        row.get('tc_exit') != 0 or bool(row.get('tc_error')) for row in selected),
        actual_interval_s=percentiles([row['actual_dt_s'] for row in intervals]),
        query_duration_s=percentiles([row['tc_end']-row['tc_start'] for row in selected
                                     if 'tc_start' in row and 'tc_end' in row]),
        invalid_intervals=sum(not row['sampling_valid'] for row in intervals),
        interval_count=len(intervals),
        max_queue_packets=max((q.get('qlen', 0) for q in roots), default=None),
        max_backlog_bytes=max((q.get('backlog', 0) for q in roots), default=None),
        sampled_drop_delta=sum(row['drops_delta'] for row in intervals
                               if not row['counter_reset']),
        departure_bps=percentiles([row['qdisc_departure_bps'] for row in intervals
                                  if row['sampling_valid']]),
        rate_note='Counter-derived departures; utilization uses configured class rate, not calibrated payload service.')


def ping_statistics(text, windows=None):
    """Keep full-probe loss separate from replies inside actual traffic windows."""
    values, censored = [], 0
    for line in text.splitlines():
        stamp = re.search(r'^\[([\d.]+)\]', line)
        if windows is not None and (not stamp or not any(
                start <= float(stamp[1]) <= end for start, end in windows)):
            continue
        value = re.search(r'time([=<])([\d.]+)\s*ms', line)
        if value:
            if value[1] == '<':
                censored += 1
            else:
                values.append(float(value[2]))
    loss = re.search(r'([\d.]+)% packet loss', text) if windows is None else None
    return dict(replies=len(values)+censored, milliseconds=percentiles(values),
                loss_percent=float(loss[1]) if loss else None,
                censored_below_1ms=censored)


def inspect_experiment(folder, csv_output=None):
    folder = Path(folder).resolve()
    meta = json.loads((folder / 'experiment.json').read_text())
    root = folder.parent
    trials = [inspect_trial(root / item['run']) for item in meta['trials']]
    rows = [json.loads(line) for line in (folder / 'samples.jsonl').read_text().splitlines()]
    intervals = list(sample_intervals(rows))
    collector = dict(samples=len(rows), failed_queries=sum(
        row.get('tc_exit') != 0 or bool(row.get('tc_error')) for row in rows),
        actual_interval_s=percentiles([r['actual_dt_s'] for r in intervals]),
        query_duration_s=percentiles([r['tc_end']-r['tc_start'] for r in rows]),
        invalid_intervals=sum(not r['sampling_valid'] for r in intervals))
    stats = folder / 'samples.jsonl.stats.json'
    collector['process_overhead'] = json.loads(stats.read_text()) if stats.exists() else None
    spec = route_spec(meta['route'])
    collector['qdiscs'] = {interface: queue_summary(rows, interface)
                           for _node, interface, _rate in spec['links'][1:3]}
    collector['collection_duration_s'] = percentiles([
        row['monotonic_end']-row['monotonic_start'] for row in rows])
    windows = []
    for item in meta['trials']:
        trial_meta = json.loads((root / item['run'] / 'metadata.json').read_text())
        if trial_meta.get('traffic_started_epoch_s') and trial_meta.get('traffic_finished_epoch_s'):
            windows.append((trial_meta['traffic_started_epoch_s'], trial_meta['traffic_finished_epoch_s']))
        elif trial_meta.get('client_started') and trial_meta.get('client_finished'):
            windows.append(tuple(datetime.fromisoformat(trial_meta[key]).timestamp()
                                 for key in ['client_started', 'client_finished']))
    rtt = {}
    for phase in ['idle', 'loaded']:
        text = (folder / f'ping-{phase}.txt').read_text()
        rtt[phase] = ping_statistics(text)
        if phase == 'loaded':
            rtt[phase]['traffic_only'] = ping_statistics(text, windows)
            rtt[phase]['traffic_windows_epoch_s'] = windows
    counters = {}
    for interface, after in meta.get('counters_after', {}).items():
        before = meta.get('counters_before', {}).get(interface, {})
        if 'error' not in before and 'error' not in after and before:
            counters[interface] = {key: after[key]-before[key] for key in before}
    restoration = json.loads((folder / 'restoration.json').read_text())
    report = dict(experiment=folder.name, route=meta['route'], outcome=meta['outcome'],
                  profile=meta.get('profile'), scenario=meta['scenario'], seed=meta['seed'],
                  trials=trials, collector=collector, rtt=rtt,
                  route_counter_deltas=counters, restoration=restoration,
                  assessment='Screening only; guest route/counter/RTT review required. Raw data preserved.')
    if csv_output and intervals:
        with Path(csv_output).open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(intervals[0]))
            writer.writeheader()
            writer.writerows(intervals)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder')
    parser.add_argument('--csv', help='New derived CSV path; existing files are not overwritten')
    args = parser.parse_args()
    print(json.dumps(inspect_experiment(args.folder, args.csv), indent=2))
