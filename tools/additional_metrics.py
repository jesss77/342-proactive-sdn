from pathlib import Path
import csv,hashlib,json,statistics,zipfile

import argparse
p=argparse.ArgumentParser(description='Rebuild achieved-source, CPU, queue and action tables')
p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();out=args.output.resolve()
if out.exists() or out.is_relative_to(args.report.resolve().parent):raise ValueError('Use a new table output outside preserved inputs')
out.parent.mkdir(parents=True,exist_ok=True)
d=json.loads(args.report.read_text(encoding='utf-8'));rows=d['rows']
def stats(values):
    values=[v for v in values if v is not None]
    return 'n/a' if not values else f'{statistics.mean(values):.3f} [{min(values):.3f}, {max(values):.3f}]'
metrics=['# Additional matched metrics','',
    'Each bracket gives the observed three-seed range, not a confidence interval. CPU components use recorded windows and are not total system cost. Inference is included in policy CPU. Loaded probe loss covers the complete loaded-probe window; traffic-only probe loss remains uncomputed.','',
    '## Source and probe observations','',
    '| Scenario | Policy | Achieved sender Mbit/s mean [range] | Loaded probe loss % mean [range] | Pacing discard % mean [range] |',
    '| --- | --- | --- | --- | --- |']
groups=[]
for scenario in ['steady','ramp','bursty']:
    for policy in ['fixed','reactive','early_warning','ml']:
        selected=[r for r in rows if (r['scenario'],r['policy'])==(scenario,policy)]
        groups.append((scenario,policy,selected))
        metrics.append(f"| {scenario} | {policy} | {stats([r['sender_mbps'] for r in selected])} | {stats([r['loaded_probe_loss_percent'] for r in selected])} | {stats([r['source_discard_percent'] for r in selected])} |")
metrics+=['','## Computation costs','',
    '| Scenario | Policy | Collector CPU % one core mean [range] | Policy CPU % one core mean [range] | ML within-run p95 wall µs mean [range] |',
    '| --- | --- | --- | --- | --- |']
for scenario,policy,selected in groups:
    metrics.append(f"| {scenario} | {policy} | {stats([r['collector_cpu_percent_one_core'] for r in selected])} | {stats([r['policy_cpu_percent_one_core'] for r in selected])} | {stats([r['inference_wall_p95_us'] for r in selected])} |")
metrics+=['','## Queue localization','',
    'Sampled maxima are not packet-level maxima. Drop deltas include probes/control packets; they are separate from UDP sequence loss.',
    '', '| Scenario | Policy | Primary sampled max queue packets mean [range] | Primary bottleneck drop total | Alternate drop total |',
    '| --- | --- | --- | --- | --- |']
for scenario,policy,selected in groups:
    metrics.append(f"| {scenario} | {policy} | {stats([r['sampled_queue_max_packets']['s2-eth2'] for r in selected])} | {sum(r['queue_drops']['s2-eth2'] for r in selected)} | {sum(r['queue_drops']['s1-eth4']+r['queue_drops']['s3-eth2'] for r in selected)} |")
metrics+=['','## Individual applied actions','',
    'Source elapsed is measured from each run’s own source start. It is not event lead time or packet interruption. No-action runs are retained in trials.csv.',
    '', '| Scenario | Policy | Seed | Switch source elapsed s | Command/readback ms | Denials before applied switch |',
    '| --- | --- | --- | --- | --- | --- |']
for r in rows:
    if r['actions']:metrics.append(f"| {r['scenario']} | {r['policy']} | {r['seed']} | {r['switch_source_elapsed_s']:.3f} | {r['command_readback_ms']:.3f} | {r['denials']} |")
out.write_text('\n'.join(metrics)+'\n',encoding='utf-8')
