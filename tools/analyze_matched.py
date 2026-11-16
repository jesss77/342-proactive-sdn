"""Offline matched networking review; never changes VM source, model or raw data."""
import argparse
import csv
import importlib
import json
import math
from pathlib import Path
import statistics
import sys

POLICIES=['fixed','reactive','early_warning','ml']
SCENARIOS=['steady','ramp','bursty']
METRICS=['sender_mbps','receiver_mbps','udp_loss_percent','traffic_reply_median_ms',
    'traffic_reply_p95_ms','loaded_probe_loss_percent','actions','denials',
    'collector_cpu_percent_one_core','policy_cpu_percent_one_core',
    'source_discard_percent','switch_source_elapsed_s','command_readback_ms']

def stats(values):
    values=[v for v in values if isinstance(v,(int,float)) and math.isfinite(v)]
    return dict(n=len(values),mean=statistics.mean(values),min=min(values),max=max(values),
        sample_sd=statistics.stdev(values) if len(values)>1 else None) if values else dict(n=0,mean=None,min=None,max=None,sample_sd=None)

def summarize(rows):
    grouped=[];paired=[]
    for scenario in SCENARIOS:
        selected=[r for r in rows if r['scenario']==scenario]
        for policy in POLICIES:
            group=[r for r in selected if r['policy']==policy]
            grouped.append(dict(scenario=scenario,policy=policy,runs=len(group),
                metrics={key:stats([r.get(key) for r in group]) for key in METRICS}))
        fixed={r['seed']:r for r in selected if r['policy']=='fixed'}
        for policy in POLICIES[1:]:
            group=[r for r in selected if r['policy']==policy]
            differences={}
            for key in METRICS:
                differences[key]=stats([r[key]-fixed[r['seed']][key] for r in group
                    if r['seed'] in fixed and r.get(key) is not None and fixed[r['seed']].get(key) is not None])
            paired.append(dict(scenario=scenario,policy=policy,reference='fixed',
                direction='policy minus fixed; loss changes are percentage points, RTT changes milliseconds',metrics=differences))
    return dict(grouped=grouped,paired=paired,
        interpretation='Descriptive means, observed ranges and sample standard deviations over three seeds. Rows/windows are not independent trials. No confidence or superiority claim from these summaries alone.')

def metric_row(repo,item,report,record):
    native=json.loads((repo/'results/runs'/record['trial']/'sender-native.json').read_text())
    actions=report['applied_actions'];action=actions[0] if actions else None
    inf=report.get('inference') or {};wall=inf.get('wall') or {}
    rtt=report['rtt']['traffic_only']['milliseconds'];overhead=report['overhead']
    return dict(policy=item['policy'],scenario=item['scenario'],seed=item['seed'],folder=record['folder'],trial=record['trial'],
        sender_mbps=report['sender_mbps'],receiver_mbps=report['receiver_mbps'],udp_loss_percent=report['udp_loss_percent'],
        traffic_reply_median_ms=rtt['median'],traffic_reply_p95_ms=rtt['p95'],
        loaded_probe_loss_percent=report['rtt']['loaded']['loss_percent'],
        traffic_window_probe_loss_percent=report['rtt']['traffic_only']['loss_percent'],
        actions=len(actions),denials=len(report['denied_requests']),
        switch_source_elapsed_s=action['started']-native['start_monotonic_ns']/1e9 if action else None,
        command_readback_ms=1000*action['command_and_readback_elapsed_s'] if action else None,
        collector_cpu_percent_one_core=overhead['collector_cpu_percent_one_core'],
        policy_cpu_percent_one_core=overhead['policy_thread_cpu_percent_one_core'],
        inference_cpu_percent_one_core=overhead.get('inference_cpu_percent_one_core',0.),
        inference_calls=inf.get('calls',0),inference_wall_median_us=wall.get('median_ns')/1000 if wall.get('median_ns') is not None else None,
        inference_wall_p95_us=wall.get('p95_ns')/1000 if wall.get('p95_ns') is not None else None,
        source_discard_percent=record['source_discard_percent'],
        source_max_pacer_gap_ms=1000*native['max_pacer_gap_s'],
        queue_drops=report['queue_drop_deltas'],
        sampled_queue_max_packets={dev:q['max_queue_packets'] for dev,q in report['collector']['qdiscs'].items()})

def analyze(repo,batch,output):
    repo=Path(repo).resolve();output=Path(output).resolve()
    if output.is_relative_to(repo):raise ValueError('Analysis output must be outside the preserved checkpoint')
    if output.exists():raise ValueError('Use a new output directory; previous derivatives are preserved')
    sys.path.insert(0,str(repo))
    matched=importlib.import_module('run_matched_batch');runner=importlib.import_module('run_policy_experiment')
    from source_integrity import source_integrity_audit
    protocol=matched.load_protocol(repo)
    if batch is None:batch=repo/'results/runs'/Path((repo/'results/runs/active-matched-batch.txt').read_text().strip()).name
    batch=Path(batch).resolve()
    if batch.parent!=(repo/'results/runs').resolve():raise ValueError('Batch is not part of the supplied checkpoint')
    state=json.loads((batch/'batch.json').read_text());plan=matched.plan()
    if (state.get('outcome')!='completed' or state.get('plan')!=plan or len(state['runs'])!=36
        or len(state['attempts'])!=36 or any(a['status']!='passed' for a in state['attempts'])
        or [{k:r[k] for k in plan[0]} for r in state['runs']]!=plan):
        raise ValueError('A complete, registered 36-trial batch without unresolved attempts is required')
    if state['protocol_sha256']!=matched.sha(batch/'matched_protocol.json') or matched.sha(batch/'matched_protocol.json')!=matched.sha(repo/'matched_protocol.json'):
        raise ValueError('Captured protocol differs')
    for name,digest in protocol['source_sha256'].items():
        if matched.sha(batch/name)!=digest:raise ValueError('Captured batch source differs: '+name)
    rows=[];reviews={}
    for item,record in zip(plan,state['runs']):
        folder=matched.child(repo/'results/runs',record['folder'])
        report=runner.inspect_policy(folder)
        checked=matched.check_report(repo,folder,item,protocol,report,source_integrity_audit)
        if checked!=record:raise ValueError('Saved acceptance evidence differs from recomputed evidence: '+folder.name)
        rows.append(metric_row(repo,item,report,record));reviews[folder.name]=report
    result=dict(protocol=protocol,complete=True,trials=36,model_refit=False,threshold_changed=False,
        summary=summarize(rows),rows=rows,
        scope='Single selected pair; one successful switch per trial; synthetic scenarios and one VM. Received-probe RTT is separate from loaded-probe loss; traffic-window loss remains uncomputed. Inference CPU is already included in policy CPU. Command/readback time is not packet interruption.')
    output.mkdir(parents=True)
    (output/'matched-report.json').write_text(json.dumps(result,indent=2)+'\n')
    fields=[k for k in rows[0] if k not in ['queue_drops','sampled_queue_max_packets']]
    with (output/'trials.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({k:r[k] for k in fields} for r in rows)
    review_dir=output/'reviews';review_dir.mkdir()
    for name,report in reviews.items():(review_dir/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    lines=['# Matched networking evaluation','',result['scope'],'',result['summary']['interpretation'],'',
        '| Scenario | Policy | Goodput mean [range] Mbit/s | UDP loss mean [range] % | Reply RTT p95 mean [range] ms | Actions across 3 runs |',
        '| --- | --- | --- | --- | --- | --- |']
    def cell(s):return 'unavailable' if not s['n'] else f"{s['mean']:.3f} [{s['min']:.3f}, {s['max']:.3f}]"
    for group in result['summary']['grouped']:
        m=group['metrics'];lines.append(f"| {group['scenario']} | {group['policy']} | {cell(m['receiver_mbps'])} | {cell(m['udp_loss_percent'])} | {cell(m['traffic_reply_p95_ms'])} | {sum(r['actions'] for r in rows if r['scenario']==group['scenario'] and r['policy']==group['policy'])} |")
    (output/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--batch');p.add_argument('--output',required=True)
    a=p.parse_args();result=analyze(a.repo,a.batch,a.output)
    print(json.dumps(dict(trials=result['trials'],output=str(Path(a.output).resolve()),fitting=False)))
