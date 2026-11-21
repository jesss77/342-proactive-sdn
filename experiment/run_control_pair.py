"""Compare one steady iperf reference and continuous-source control on the same route."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib
import json
import shutil
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def run_pair(net, route='alternate', requested_bps=3_000_000, duration=20, interval=.25):
    for name in ['traffic_scenarios', 'continuous_udp', 'run_continuous_trial',
                 'inspect_experiment', 'run_experiment']:
        importlib.reload(importlib.import_module(name))
    from run_experiment import run_experiment
    from inspect_experiment import inspect_experiment
    folder = BASE / 'results/runs' / (
        datetime.now().strftime('%Y%m%d-%H%M%S-%f') + f'-source-control-pair-{route}')
    folder.mkdir(parents=True)
    shutil.copy2(BASE / 'run_control_pair.py', folder)
    meta = dict(started=datetime.now(timezone.utc).isoformat(), route=route,
                requested_bps=requested_bps, duration_s=duration, interval_s=interval,
                scenario='steady', seed=1, engines=['iperf', 'continuous'],
                experiments=[], outcome='running', validity='pending_review',
                script_sha256=hashlib.sha256((folder / 'run_control_pair.py').read_bytes()).hexdigest(),
                scope='One exploratory source-validation pair; no routing or ML benefit.')
    def save():
        (folder / 'control-pair.json').write_text(json.dumps(meta, indent=2)+'\n')
    save()
    try:
        for engine in meta['engines']:
            print('Source control:', engine, flush=True)
            experiment = run_experiment(net, route=route, requested_bps=requested_bps,
                duration=duration, interval=interval, scenario='steady', seed=1, engine=engine)
            meta['experiments'].append(dict(engine=engine, folder=experiment.name))
            save()
            raw = json.loads((experiment / 'experiment.json').read_text())
            if raw['outcome'] != 'completed':
                raise RuntimeError('Source control failed; inspect ' + experiment.name)
            report = inspect_experiment(experiment)
            (folder / f'{engine}-inspection.json').write_text(json.dumps(report, indent=2)+'\n')
            trial = report['trials'][0]
            print('CONTROL RESULT:', json.dumps(dict(engine=engine, experiment=experiment.name,
                sender_mbps=trial['sender']['bits_per_second']/1e6,
                receiver_mbps=trial['receiver']['bits_per_second']/1e6,
                udp_loss_percent=trial['receiver']['lost_percent'],
                queue_drops=trial['queue_drop_deltas'], udp_errors=trial['udp_error_deltas'],
                pacer=trial.get('pacer'), screen_failures=trial['screen_failures'],
                rtt=report['rtt'], collector=report['collector'],
                restoration=report['restoration'])), flush=True)
            if report['restoration']['failures']:
                raise RuntimeError('Profile restoration failed; stopped control pair')
        meta['outcome'] = 'completed'
    except BaseException as error:
        meta.update(outcome='incomplete', error=str(error) or type(error).__name__)
        raise
    finally:
        meta['finished'] = datetime.now(timezone.utc).isoformat()
        save()
        print('Control-pair records:', folder, flush=True)
    return folder


if 'net' in globals():
    run_pair(net, route=globals().get('route', 'alternate'),
             requested_bps=globals().get('requested_bps', 3_000_000),
             duration=globals().get('duration', 20), interval=globals().get('interval', .25))
elif __name__ == '__main__':
    raise SystemExit('Load from Mininet with net and __file__ supplied.')
