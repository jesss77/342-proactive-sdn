"""Native steady-load interval calibration; burst resolution remains a separate test."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import importlib
import json
import shutil
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from run_experiment import run_experiment
import inspect_experiment as inspection


def interval_order(repetitions=3):
    if not isinstance(repetitions, int) or not 1 <= repetitions <= 3:
        raise ValueError('Use one exploratory block or up to three repeated blocks')
    intervals = [.5, .25, .1]
    return [dict(repetition=r+1, interval_s=interval)
            for r in range(repetitions)
            for interval in intervals[r:] + intervals[:r]]


def run_sweep(net, route='alternate', requested_bps=12_000_000,
              repetitions=3, duration=20, seed=1):
    # A running Mininet shell may have imported the previous inspector version.
    importlib.reload(inspection)
    plan = interval_order(repetitions)
    folder = BASE / 'results/runs' / (
        datetime.now().strftime('%Y%m%d-%H%M%S-%f') + f'-interval-sweep-{route}')
    folder.mkdir(parents=True)
    metadata = dict(started=datetime.now(timezone.utc).isoformat(), route=route,
                    requested_bps=requested_bps, duration_s=duration, seed=seed,
                    scenario='steady', plan=plan, experiments=[], outcome='running',
                    limitation='Steady-load timing/overhead test; does not validate missed-burst detection.')
    for name in ['run_interval_sweep.py', 'collect_path.py', 'inspect_experiment.py']:
        shutil.copy2(BASE / name, folder / name)
    metadata['source_sha256'] = {
        name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
        for name in ['run_interval_sweep.py', 'collect_path.py', 'inspect_experiment.py']}
    def save():
        (folder / 'sweep.json').write_text(json.dumps(metadata, indent=2) + '\n')
    save()
    print('Sweep folder:', folder, flush=True)
    columns = ['repetition', 'interval_ms', 'experiment', 'receiver_mbps',
               'udp_loss_percent', 'trial_screen_failures', 'idle_rtt_median_ms',
               'loaded_rtt_median_ms', 'collector_cpu_percent_one_core',
               'queries_failed', 'intervals_flagged', 'restoration_failures']
    try:
        with (folder / 'summary.csv').open('x', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=columns)
            writer.writeheader()
            for index, item in enumerate(plan):
                print(f"Sweep {index+1}/{len(plan)}: {item}", flush=True)
                experiment = run_experiment(net, route=route, requested_bps=requested_bps,
                    interval=item['interval_s'], duration=duration, scenario='steady', seed=seed)
                metadata['experiments'].append(dict(item, folder=experiment.name))
                save()
                raw = json.loads((experiment / 'experiment.json').read_text())
                if raw['outcome'] != 'completed':
                    raise RuntimeError('Experiment failed; sweep stopped: ' + experiment.name)
                report = inspection.inspect_experiment(experiment)
                (folder / (experiment.name + '-inspection.json')).write_text(
                    json.dumps(report, indent=2) + '\n')
                trial = report['trials'][0]
                collector = report['collector']
                usage = (collector.get('process_overhead') or {}).get('cpu_percent_one_core')
                queues = collector['qdiscs']
                idle = report['rtt']['idle']['milliseconds'] or {}
                loaded = report['rtt']['loaded']['traffic_only']['milliseconds'] or {}
                summary = dict(repetition=item['repetition'], interval_ms=item['interval_s']*1000,
                    experiment=experiment.name, receiver_mbps=trial['receiver']['bits_per_second']/1e6,
                    udp_loss_percent=trial['receiver']['lost_percent'],
                    trial_screen_failures=';'.join(trial['screen_failures']),
                    idle_rtt_median_ms=idle.get('median'), loaded_rtt_median_ms=loaded.get('median'),
                    collector_cpu_percent_one_core=sum(usage.values()) if usage is not None else None,
                    queries_failed=sum(q['failed_queries'] for q in queues.values()),
                    intervals_flagged=sum(q['invalid_intervals'] for q in queues.values()),
                    restoration_failures=len(report['restoration']['failures']))
                writer.writerow(summary)
                csv_file.flush()
                print('SWEEP RESULT:', json.dumps(summary), flush=True)
                if report['restoration']['failures']:
                    raise RuntimeError('Restoration failed; sweep stopped')
        metadata['outcome'] = 'completed'
    except BaseException as error:
        metadata.update(outcome='incomplete', error=str(error) or type(error).__name__)
        raise
    finally:
        metadata['finished'] = datetime.now(timezone.utc).isoformat()
        save()
        print('Sweep records:', folder, flush=True)
    return folder


if 'net' in globals():
    run_sweep(net, route=globals().get('route', 'alternate'),
              requested_bps=globals().get('requested_bps', 12_000_000),
              repetitions=globals().get('repetitions', 3),
              duration=globals().get('duration', 20), seed=globals().get('seed', 1))
elif __name__ == '__main__':
    raise SystemExit('Load this script from Mininet with net and __file__ supplied.')
