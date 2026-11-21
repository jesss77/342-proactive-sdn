"""Version 2 low-load steady control: 4 policies x 3 seeds at 3 Mbit/s (s3 BG = 4 Mbit/s)."""
from datetime import datetime
import importlib
import json
from pathlib import Path
import statistics
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

POLICIES = ['fixed', 'reactive', 'early_warning', 'ml']
SEEDS = [41, 42, 43]


def make_plan():
    rows = []
    for b_idx, seed in enumerate(SEEDS):
        order = [POLICIES[(j + b_idx) % 4] for j in [0, 1, 3, 2]]
        for pos, policy in enumerate(order):
            rows.append(dict(
                block=b_idx, position=pos, policy=policy,
                scenario='steady', seed=seed, bg_bps=4_000_000,
                requested_bps=3_000_000, duration=60,
            ))
    return rows


def run(net):
    import control.run_policy_experiment as runner
    runner = importlib.reload(runner)

    state_file = BASE / 'results/v2-steady-control.json'
    plan = make_plan()
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state['plan'] != plan:
            raise ValueError('Saved v2-steady-control.json plan differs')
    else:
        state = dict(
            experiment='v2-steady-low-load-control',
            created=datetime.now().isoformat(),
            plan=plan,
            completed=[],
            failed=[],
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + '\n')

    for item in plan[len(state['completed']):]:
        idx = len(state['completed']) + 1
        print(f'\n=== V2 STEADY {idx}/{len(plan)}: {item} ===', flush=True)
        try:
            folder = Path(runner.run(
                net,
                policy=item['policy'],
                scenario=item['scenario'],
                requested_bps=item['requested_bps'],
                duration=item['duration'],
                seed=item['seed'],
                bg_bps=item['bg_bps'],
            ))
            report = runner.inspect_policy(folder)
            qdiscs = report['collector']['qdiscs']
            max_invalid = max(q['invalid_intervals'] for q in qdiscs.values())
            total_failed_q = sum(q['failed_queries'] for q in qdiscs.values())
            hard_failures = [
                f for f in report['screen_failures']
                if not (f == 'collector_quality' and total_failed_q == 0 and max_invalid <= 3)
            ]
            if hard_failures:
                raise RuntimeError(f"Quality screen failed: {report['screen_failures']}")
            bg_loss = 0.0
            if (folder / 'bg-sender.json').exists() and (folder / 'bg-receiver.json').exists():
                bgs = json.loads((folder / 'bg-sender.json').read_text())
                bgr = json.loads((folder / 'bg-receiver.json').read_text())
                if bgs['sent_packets'] > 0:
                    bg_loss = 100.0 * max(0, bgs['sent_packets'] - bgr['unique_packets']) / bgs['sent_packets']
            record = dict(
                **item,
                folder=folder.name,
                receiver_mbps=round(report['receiver_mbps'], 3),
                udp_loss_percent=round(report['udp_loss_percent'], 4),
                rtt_p95_ms=report['rtt']['traffic_only']['milliseconds']['p95'],
                actions=len(report['applied_actions']),
                denials=len(report['denied_requests']),
                switched_in_traffic=report['in_traffic_switch_verified'],
                bg_loss_percent=round(bg_loss, 4),
                screen_failures=report['screen_failures'],
            )
            state['completed'].append(record)
            state_file.write_text(json.dumps(state, indent=2) + '\n')
            print('STEADY ACCEPTED:', json.dumps(record), flush=True)
        except BaseException as err:
            state['failed'].append(dict(**item, error=repr(err), at=datetime.now().isoformat()))
            state_file.write_text(json.dumps(state, indent=2) + '\n')
            print(f'STEADY STOPPED ON ERROR at trial {idx}: {err}', flush=True)
            raise

    out_dir = BASE / 'results/v2-report'
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = state['completed']
    lines = [
        '# Version 2 Low-Load Control (`steady 3 Mbit/s`, `s3 BG = 4 Mbit/s`, Seeds 41–43)',
        '',
        '| Policy | Goodput mean (Mbit/s) | UDP Loss mean (%) | RTT `p95` mean (ms) | Unnecessary Switches | Denials | BG Loss (%) |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for pol in POLICIES:
        g = [r for r in rows if r['policy'] == pol]
        lines.append(
            f"| {pol} | {statistics.mean(r['receiver_mbps'] for r in g):.3f} | "
            f"{statistics.mean(r['udp_loss_percent'] for r in g):.3f} | "
            f"{statistics.mean(r['rtt_p95_ms'] for r in g):.1f} | "
            f"{sum(r['actions'] for r in g)}/{len(g)} | {sum(r['denials'] for r in g)} | "
            f"{statistics.mean(r['bg_loss_percent'] for r in g):.3f} |"
        )
    md = '\n'.join(lines) + '\n'
    (out_dir / 'V2_STEADY_CONTROL.md').write_text(md)
    print('\n' + md, flush=True)


if 'net' in globals():
    run(net)
