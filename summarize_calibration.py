"""Reproduce the six-run primary calibration table from raw files, without editing them."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
from inspect_experiment import inspect_trial

RUNS = [
    '20261114-183628-914080-primary-3000000bps',
    '20261114-183704-705722-primary-3000000bps',
    '20261114-183740-583006-primary-3000000bps',
    '20261114-180445-932256-primary-12000000bps',
    '20261114-180904-299142-primary-12000000bps',
    '20261114-180940-146123-primary-12000000bps']


def summarize(root, output):
    root, output = Path(root), Path(output)
    rows, provenance = [], {}
    for name in RUNS:
        report = inspect_trial(root / name)
        if report['screen_failures']:
            raise ValueError(f'{name}: {report["screen_failures"]}')
        sender, receiver = report['sender'], report['receiver']
        sent = sender['bytes'] // 1200
        received = receiver['bytes'] // 1200
        missing = sent-received
        if missing != report['queue_drop_deltas']['s2-eth2']:
            raise ValueError('Packet accounting does not match: ' + name)
        source_queue = (root / name / 'before-h1-eth0-queue.txt').read_text()
        bottleneck = (root / name / 'before-bottleneck-class.txt').read_text()
        if 'limit 250' not in source_queue or 'cburst 16Kb' not in bottleneck:
            raise ValueError('Unexpected calibration profile: ' + name)
        rows.append(dict(run=name, offered_mbps=report['requested_bps']/1e6,
                         sender_mbps=sender['bits_per_second']/1e6,
                         receiver_mbps=receiver['bits_per_second']/1e6,
                         sent_datagrams=sent, received_datagrams=received,
                         missing_datagrams=missing, sender_based_loss_percent=100*missing/sent,
                         receiver_sequence_loss_percent=receiver['lost_percent'],
                         bottleneck_drops=report['queue_drop_deltas']['s2-eth2'],
                         jitter_ms=receiver['jitter_ms']))
        provenance[name] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                            for f in (root / name).iterdir() if f.is_file()}
    groups = {}
    for rate in [3, 12]:
        subset = [r for r in rows if r['offered_mbps'] == rate]
        groups[rate] = dict(n=len(subset))
        for key in ['receiver_mbps', 'sender_based_loss_percent']:
            values = [r[key] for r in subset]
            groups[rate][key] = dict(mean=statistics.mean(values),
                                     sample_sd=statistics.stdev(values),
                                     min=min(values), max=max(values))
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'runs.csv').open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(groups=groups, comparison='Fixed primary calibration; no routing intervention',
                   profile='one-vCPU; forward cburst 16384; h1 queue 250; bottleneck queue 50',
                   loss_definition='100*(sender payload bytes-receiver payload bytes)/sender payload bytes',
                   uncertainty='Three runs per condition; SD is descriptive, not a guarantee of capacity')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
    (output / 'source-sha256.json').write_text(json.dumps(provenance, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', default='results/runs')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    summarize(args.runs, args.output)
