"""Fixed-alternate control runs: h1->h2 permanently on s3 alongside h3->h4 background."""
from contextlib import ExitStack
from datetime import datetime
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from network.dual_path_profile import dual_profile, LINKS
from telemetry.inspect_experiment import inspect_trial, ping_statistics
import traffic.run_continuous_trial as recorder
from traffic.traffic_scenarios import continuous_schedule


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


def run_one(net, scenario='ramp', seed=41, bg_bps=14_000_000, duration=60, requested_bps=11_500_000):
    folder = BASE / 'results/runs' / (
        datetime.now().strftime('%Y%m%d-%H%M%S-%f') + f'-fixed-alternate-{scenario}-bg{bg_bps//1_000_000}m-seed{seed}'
    )
    folder.mkdir(parents=True)
    plan = continuous_schedule(scenario, requested_bps, duration, seed)
    bg_server = bg_client = ping = None

    with dual_profile(net, folder):
        with ExitStack() as files:
            try:
                pinglog = files.enter_context((folder / 'ping-loaded.txt').open('w'))
                ping = net['h1'].popen(['ping', '-n', '-D', '-i', '.2', net['h2'].IP()],
                                       stdout=pinglog, stderr=subprocess.STDOUT)
                if bg_bps > 0:
                    bg_plan = dict(run_id=uuid.uuid4().hex,
                                   segments=[dict(segment=0, requested_bps=bg_bps, requested_seconds=duration + 15)])
                    (folder / 'bg-plan.json').write_text(json.dumps(bg_plan, indent=2))
                    bg_srv_log = files.enter_context((folder / 'bg-server.log').open('w'))
                    bg_cli_log = files.enter_context((folder / 'bg-client.log').open('w'))
                    udp_cmd = ['nice', '-n', '19', sys.executable, str(BASE / 'traffic/continuous_udp.py')]
                    bg_server = net['h4'].popen(
                        udp_cmd + ['receive', '--plan', str(folder / 'bg-plan.json'), '--host', net['h4'].IP(),
                                   '--port', '5203', '--payload-bytes', '1470', '--tick', '0.01',
                                   '--output', str(folder / 'bg-receiver.json'),
                                   '--samples', str(folder / 'bg-receiver.jsonl'),
                                   '--ready', str(folder / 'bg-ready.json'), '--max-duration', str(duration + 30)],
                        stdout=bg_srv_log, stderr=subprocess.STDOUT)
                    deadline = time.monotonic() + 5
                    while not (folder / 'bg-ready.json').exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    bg_client = net['h3'].popen(
                        udp_cmd + ['send', '--plan', str(folder / 'bg-plan.json'), '--host', net['h4'].IP(),
                                   '--port', '5203', '--payload-bytes', '1470', '--tick', '0.01',
                                   '--output', str(folder / 'bg-sender.json'),
                                   '--samples', str(folder / 'bg-sender.jsonl')],
                        stdout=bg_cli_log, stderr=subprocess.STDOUT)
                    time.sleep(1.0)

                trial = Path(recorder.run(
                    net, BASE, requested_bps, 'alternate', duration,
                    plan=plan, seed=seed, scenario=scenario, capture_links=LINKS,
                ))
                time.sleep(1.0)
            finally:
                stop(ping)
                stop(bg_client)
                time.sleep(0.3)
                stop(bg_server)

    t = inspect_trial(trial, dynamic=False)
    native = json.loads((trial / 'sender-native.json').read_text())
    windows = [(native['start_wall_epoch_s'], native['end_wall_epoch_s'])]
    rtt = ping_statistics((folder / 'ping-loaded.txt').read_text(), windows)

    bg_sender_mbps = bg_receiver_mbps = bg_loss_percent = 0.0
    if bg_bps > 0 and (folder / 'bg-sender.json').exists() and (folder / 'bg-receiver.json').exists():
        bgs = json.loads((folder / 'bg-sender.json').read_text())
        bgr = json.loads((folder / 'bg-receiver.json').read_text())
        bg_dur = (bgs['end_monotonic_ns'] - bgs['start_monotonic_ns']) / 1e9
        if bg_dur > 0 and bgs['sent_packets'] > 0:
            bg_sender_mbps = 8 * bgs['sent_bytes'] / bg_dur / 1e6
            bg_receiver_mbps = 8 * bgr['unique_bytes'] / bg_dur / 1e6
            bg_loss_percent = 100.0 * max(0, bgs['sent_packets'] - bgr['unique_packets']) / bgs['sent_packets']

    record = dict(
        policy='fixed_alternate', scenario=scenario, seed=seed, bg_bps=bg_bps,
        folder=folder.name, trial=trial.name,
        h1_sender_mbps=round(t['sender']['bits_per_second'] / 1e6, 3),
        h1_receiver_mbps=round(t['receiver']['bits_per_second'] / 1e6, 3),
        h1_loss_percent=round(t['receiver']['lost_percent'], 3),
        rtt_p95_ms=rtt['milliseconds']['p95'],
        s1_eth4_drops=t['queue_drop_deltas'].get('s1-eth4', 0),
        s3_eth2_drops=t['queue_drop_deltas'].get('s3-eth2', 0),
        bg_sender_mbps=round(bg_sender_mbps, 3),
        bg_receiver_mbps=round(bg_receiver_mbps, 3),
        bg_loss_percent=round(bg_loss_percent, 3),
        screen_failures=t['screen_failures'],
    )
    print('FIXED-ALTERNATE RESULT:', json.dumps(record), flush=True)
    return record


def run(net):
    results = [
        run_one(net, scenario='ramp', seed=41, bg_bps=14_000_000),
        run_one(net, scenario='bursty', seed=41, bg_bps=14_000_000),
    ]
    out_dir = BASE / 'results/v2-report'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'fixed_alternate_control.json').write_text(json.dumps(results, indent=2) + '\n')

    lines = [
        '# Fixed-Alternate Control Check (`h1 -> h2` permanently on `s3`, `s3 BG = 14 Mbit/s`)',
        '',
        '| Scenario | Seed | `h1->h2` Goodput (Mbit/s) | `h1->h2` Loss (%) | RTT `p95` (ms) | `s1-eth4` Drops | `s3-eth2` Drops | `h3->h4` BG Goodput (Mbit/s) | `h3->h4` BG Loss (%) |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for r in results:
        lines.append(
            f"| {r['scenario']} | {r['seed']} | {r['h1_receiver_mbps']:.3f} | {r['h1_loss_percent']:.3f} | "
            f"{r['rtt_p95_ms']} | {r['s1_eth4_drops']} | {r['s3_eth2_drops']} | "
            f"{r['bg_receiver_mbps']:.3f} | {r['bg_loss_percent']:.3f} |"
        )
    md = '\n'.join(lines) + '\n'
    (out_dir / 'FIXED_ALTERNATE_CONTROL.md').write_text(md)
    print('\n' + md, flush=True)


if 'net' in globals():
    run(net)
