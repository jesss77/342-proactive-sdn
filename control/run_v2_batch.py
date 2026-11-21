"""Version 2 matched batch: 4 policies x 3 s3 background loads x 2 scenarios x 2 seeds."""
from datetime import datetime
import importlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

POLICIES = ['fixed', 'reactive', 'early_warning', 'ml']
SCENARIOS = ['ramp', 'bursty']
BG_LEVELS = [0, 4_000_000, 14_000_000]
SEEDS = [41, 42, 43]


def make_plan():
    rows = []
    block = 0
    for seed in SEEDS:
        for scenario in SCENARIOS:
            for bg_bps in BG_LEVELS:
                order = [POLICIES[(j + block) % 4] for j in [0, 1, 3, 2]]
                for pos, policy in enumerate(order):
                    rows.append(dict(
                        block=block, position=pos, policy=policy,
                        scenario=scenario, seed=seed, bg_bps=bg_bps,
                        requested_bps=11_500_000, duration=60,
                    ))
                block += 1
    return rows


def run(net, limit=12, warmup=True):
    import control.run_policy_experiment as runner
    runner = importlib.reload(runner)

    state_file = BASE / 'results/v2-batch.json'
    plan = make_plan()
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state['plan'] != plan:
            raise ValueError('Saved v2-batch.json plan differs; archive or remove it first')
    else:
        state = dict(
            experiment='v2-busy-alternate-admission',
            created=datetime.now().isoformat(),
            plan=plan,
            completed=[],
            failed=[],
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + '\n')

    done = len(state['completed'])
    if done == 0 and warmup:
        print('=== V2 WARM-UP RUN (discarded from batch stats) ===', flush=True)
        runner.run(net, policy='fixed', scenario='steady', requested_bps=3_000_000,
                   duration=15, seed=99, bg_bps=0)

    batch_slice = plan[done:done + limit]
    if not batch_slice:
        print(f'V2 batch already complete: {done}/{len(plan)} trials!', flush=True)
        return state_file

    for item in batch_slice:
        idx = len(state['completed']) + 1
        print(f'\n=== V2 TRIAL {idx}/{len(plan)}: {item} ===', flush=True)
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
                raise RuntimeError(
                    f"Quality screen failed: {report['screen_failures']} "
                    f"(failed_q={total_failed_q}, max_invalid={max_invalid})"
                )
            bg_sender_mbps = 0.0
            bg_loss_percent = 0.0
            if item['bg_bps'] > 0 and (folder / 'bg-sender.json').exists() and (folder / 'bg-receiver.json').exists():
                bgs = json.loads((folder / 'bg-sender.json').read_text())
                bgr = json.loads((folder / 'bg-receiver.json').read_text())
                bg_dur = (bgs['end_monotonic_ns'] - bgs['start_monotonic_ns']) / 1e9
                if bg_dur > 0 and bgs['sent_packets'] > 0:
                    bg_sender_mbps = 8 * bgs['sent_bytes'] / bg_dur / 1e6
                    bg_loss_percent = 100.0 * max(0, bgs['sent_packets'] - bgr['unique_packets']) / bgs['sent_packets']
            record = dict(
                **item,
                folder=folder.name,
                sender_mbps=report['sender_mbps'],
                receiver_mbps=report['receiver_mbps'],
                udp_loss_percent=report['udp_loss_percent'],
                rtt_p95_ms=report['rtt']['traffic_only']['milliseconds']['p95'],
                rtt_median_ms=report['rtt']['traffic_only']['milliseconds']['median'],
                s2_drops=report['queue_drop_deltas']['s2-eth2'],
                s3_drops=report['queue_drop_deltas']['s1-eth4'] + report['queue_drop_deltas']['s3-eth2'],
                actions=len(report['applied_actions']),
                denials=len(report['denied_requests']),
                switched_in_traffic=report['in_traffic_switch_verified'],
                bg_sender_mbps=round(bg_sender_mbps, 3),
                bg_loss_percent=round(bg_loss_percent, 4),
                collector_invalid_intervals=max_invalid,
                screen_failures=report['screen_failures'],
                collector_cpu=report['overhead']['collector_cpu_percent_one_core'],
                policy_cpu=report['overhead']['policy_cpu_percent_one_core']
                if 'policy_cpu_percent_one_core' in report['overhead']
                else report['overhead']['policy_thread_cpu_percent_one_core'],
            )
            state['completed'].append(record)
            state_file.write_text(json.dumps(state, indent=2) + '\n')
            print('V2 ACCEPTED:', json.dumps(record), flush=True)
        except BaseException as err:
            state['failed'].append(dict(**item, error=repr(err), at=datetime.now().isoformat()))
            state_file.write_text(json.dumps(state, indent=2) + '\n')
            print(f'V2 STOPPED ON ERROR at trial {idx}: {err}', flush=True)
            raise

    print(f'\nV2 PROGRESS: {len(state["completed"])}/{len(plan)} trials completed!', flush=True)
    return state_file


if 'net' in globals():
    run(net, limit=globals().get('limit', 12), warmup=globals().get('warmup', True))
