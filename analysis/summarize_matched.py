from pathlib import Path
import collections,json,statistics,sys
import argparse
p=argparse.ArgumentParser(description='Rebuild paired contrasts, quality summaries and interpretation from saved evidence')
p.add_argument('--repo',type=Path,required=True);p.add_argument('--networking',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();repo=args.repo.resolve();out=args.output.resolve()
if out.is_relative_to(repo) or out.is_relative_to(args.networking.resolve()):raise ValueError('Write summaries outside preserved inputs')
out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze_matched import stats,summarize
data=json.loads((args.networking/'matched-report.json').read_text(encoding='utf-8'));rows=data['rows']

scenarios=['steady','ramp','bursty'];contrasts=[]
for scenario in scenarios:
    for reference in ['reactive','early_warning']:
        diffs=[]
        for seed in [41,42,43]:
            ml=next(r for r in rows if (r['scenario'],r['policy'],r['seed'])==(scenario,'ml',seed))
            other=next(r for r in rows if (r['scenario'],r['policy'],r['seed'])==(scenario,reference,seed))
            diffs.append(dict(seed=seed,goodput_mbps=ml['receiver_mbps']-other['receiver_mbps'],
                udp_loss_percentage_points=ml['udp_loss_percent']-other['udp_loss_percent'],
                traffic_reply_p95_ms=ml['traffic_reply_p95_ms']-other['traffic_reply_p95_ms']))
        contrasts.append(dict(scenario=scenario,policy='ml',reference=reference,direction='ML minus reference',
            by_seed=diffs,summary={key:stats([x[key] for x in diffs]) for key in ['goodput_mbps','udp_loss_percentage_points','traffic_reply_p95_ms']}))
denials=[];quality=[];unnecessary=[];actions=[];all_udp_errors=[];queue_totals=collections.Counter()
for row in rows:
    report=json.loads((args.networking/'reviews'/(row['folder']+'.json')).read_text())
    queue_totals.update(report['queue_drop_deltas'])
    for host,errors in report['trial']['udp_error_deltas'].items():
        for kind,value in errors.items():all_udp_errors.append(value)
    stats_q=report['collector']['qdiscs']
    quality.append(dict(folder=row['folder'],screen_failures=report['screen_failures'],
        failed_queries=sum(q['failed_queries'] for q in stats_q.values()),
        invalid_intervals=sum(q['invalid_intervals'] for q in stats_q.values()),
        max_actual_interval_s=max(q['actual_interval_s']['max'] for q in stats_q.values()),
        max_query_duration_s=max(q['query_duration_s']['max'] for q in stats_q.values()),
        profile_restoration_failures=report['restoration']['failures'],route_restored=report['route_restoration']['verified']))
    if report['denied_requests']:
        denials.append(dict(scenario=row['scenario'],seed=row['seed'],policy=row['policy'],
            switch_source_elapsed_s=row['switch_source_elapsed_s'],udp_loss_percent=row['udp_loss_percent'],
            rejections=dict(collections.Counter(a['rejection'] for a in report['denied_requests']))))
    decisions=[json.loads(s) for s in (repo/'results/runs'/row['folder']/'decisions.jsonl').read_text().splitlines()]
    applied=[d for d in decisions if d.get('action',{}).get('applied')]
    for decision in applied:
        record=dict(scenario=row['scenario'],seed=row['seed'],policy=row['policy'],
            switch_source_elapsed_s=row['switch_source_elapsed_s'],command_readback_ms=row['command_readback_ms'],
            probability=decision.get('model_probability'),feature_utilization=decision['features']['utilization'],
            sample_age_s=decision['sample_age_s'],reason=decision['reason'])
        actions.append(record)
        if row['scenario']=='steady':
            unnecessary.append(dict(record,features=decision['features'],interpretation='Low-load action; no sustained high-utilization need demonstrated. Preserve as an unnecessary reroute, not a prevented-congestion success.'))
assert len(quality)==36 and all(not q['screen_failures'] and not q['failed_queries'] and not q['invalid_intervals'] and q['route_restored'] and not q['profile_restoration_failures'] for q in quality)
assert max(all_udp_errors)==0
source_comparability=[]
for scenario in scenarios:
    for seed in [41,42,43]:
        group=[r for r in rows if (r['scenario'],r['seed'])==(scenario,seed)]
        rates=[r['sender_mbps'] for r in group]
        source_comparability.append(dict(scenario=scenario,seed=seed,min_sender_mbps=min(rates),max_sender_mbps=max(rates),
            spread_mbps=max(rates)-min(rates),spread_percent_of_min=100*(max(rates)-min(rates))/min(rates)))
info=dict(verified_trials=36,raw_archive=dict(source_checkpoint_sha256='e8f2e4e4294d35918c8b0d2e37fa79e92366732a19b0a12daad6f7c2a521b8e3',input_package='data/inputs.zip',verification='Curated input bytes/source pins checked; no full historical checkpoint comparison is rerun'),
    direct_ml_contrasts=contrasts,denial_cases=denials,unnecessary_low_load_actions=unnecessary,
    applied_action_count=len(actions),actions=actions,quality=quality,all_udp_error_deltas_zero=True,
    queue_drops_summed_by_interface=dict(queue_totals),source_comparability=source_comparability,
    source_discard_percent=stats([r['source_discard_percent'] for r in rows]),
    command_readback_ms=stats([r['command_readback_ms'] for r in rows]),
    policy_cpu_percent_one_core=stats([r['policy_cpu_percent_one_core'] for r in rows]),
    collector_cpu_percent_one_core=stats([r['collector_cpu_percent_one_core'] for r in rows]),
    inference_p95_wall_us=stats([r['inference_wall_p95_us'] for r in rows if r['policy']=='ml']),
    interpretation='Earlier-trigger rerouting improved this constrained benchmark, but ML does not show an overall advantage over the simpler early-warning comparator. Keep seed-specific behavior, current-load admission denials, source differences and low-load cost explicit.')
(out/'analysis-details.json').write_text(json.dumps(info,indent=2)+'\n')

lines=['# Interpretation of the complete matched benchmark','',
'All 36 trials were independently rechecked against the registered plan, frozen source/model hashes, preserved raw hashes, source integrity and quality/restoration screens. There were no failed queries, invalid sampled intervals, UDP endpoint errors or restoration failures in the accepted set. This is a single-VM, single-flow synthetic benchmark with three seeds per cell and one possible successful switch per trial.','',
'## Delivery and policy comparison','',
'Ramp loss averaged 9.740577% for fixed, 0.001947% reactive, 0% early warning and 0% ML. Receiver goodput averaged 7.510254, 8.319361, 8.328790 and 8.328941 Mbit/s respectively. Both early methods switched earlier than reactive on every ramp seed, but their delivery outcomes were essentially tied.','',
'Bursty loss averaged 18.681719% fixed, 5.591034% reactive, 0.012666% early warning and 0.194688% ML. Both early modes improved delivery over fixed and reactive in each seed, but ML did not beat simple early warning consistently. ML had zero loss in burst seeds 41/42 and 0.584064% in seed 43; early warning retained small losses of 0.006525%â€“0.015846%. Mean goodput was 7.521430 Mbit/s for ML versus 7.537009 for early warning. Report direct paired differences and the three-seed spread, not a universal or statistically established ranking.','',
'## Mechanism and adverse outcomes','',
'Reactive encountered four insufficient-headroom denials in burst seed 41 and forty in seed 42. The latter did not switch until 47.610659 seconds and lost 15.030369% of UDP datagrams. These are real outcomes of the same current-load/headroom guard: a late trigger can reach admission when the observed flow is too large. Do not remove the guard, retune after evaluation, or omit these trials.','',
'In steady seed 41, ML switched after roughly '+f"{unnecessary[0]['switch_source_elapsed_s']:.3f}"+' seconds with utilization 0.283581, no queue/backlog/drop signal, and predicted probability 0.890385 above threshold 0.65. This is an unnecessary low-load action. ML took no action in the other two steady seeds, while fixed/reactive/early warning took none in all three. All steady runs delivered with zero UDP loss. One action is not evidence of a prevented event when there was no sustained load increase.','',
'## Prediction, lead time and latency','',
'Keep the separate untouched prediction test beside networking results: row F1 0.956522 for ramps and 0.811111 for bursty traffic; advance warnings reached 2/3 ramp and 9/25 scorable burst events (26 observed). Twenty-four false episodes included twenty late warnings; five tail episodes were censored. High row F1 alone does not establish actionable prediction.','',
'Nineteen matched actions were applied. CLI command/readback elapsed ranged from '+f"{info['command_readback_ms']['min']:.3f} to {info['command_readback_ms']['max']:.3f}"+' ms. This includes local command/readback overhead, not packet disruption or exact rule-activation time. Successful held-out warning-run median leads ranged approximately 0.995â€“1.999 seconds. They are from separate fixed traces and cannot be treated as paired proof of time available for a matched intervention. Full packet-level activation/disruption measurement remains outside this benchmark.','',
'## Measurement and source limits','',
'Mean receiver goodput is over each whole traffic schedule. Reply RTT statistics describe received probes, with loaded-probe loss reported separately; traffic-window probe loss is uncomputed. Queue occupancy is sampled at 250 ms, so sampled maxima are not packet-level maxima. Queue drops include probes/control packets and must not be equated exactly to UDP sequence loss.','',
'Pacing-budget discard reached '+f"{info['source_discard_percent']['max']:.6f}"+'% of planned bits, below the unchanged 5% acquisition limit. Sender-rate spread within a matched cell reached '+f"{max(x['spread_percent_of_min'] for x in source_comparability):.6f}"+'%; equal plans do not guarantee identical packet timing. Disclose achieved rates, source diagnostics and CPU variation. One-vCPU wall time and sequential execution remain sources of variation despite the rotated order.','',
'Inference CPU is a subset of policy-thread CPU and is not added again. The one-way/single-action cap makes most of a rerouted run stay on the alternate path; these results do not establish repeated recovery behavior, fairness with other flows, arbitrary cross-traffic, link failure handling, maximum throughput or deployment readiness.','',
'## Supported conclusion','',
'The shared implementation is operational and earlier triggering improves delivery against fixed/reactive baselines in this tested setup. A simple trend rule already captures most of that benefit. These data do not establish added value from the learned tree, and reveal an unnecessary low-load ML action. The contribution should emphasize the controlled comparison, observed limitations and cost measurements rather than claim general ML superiority.']
(out/'INTERPRETATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(trials=36,actions=len(actions),denial_cases=denials,
    unnecessary_low_load_actions=len(unnecessary),source_discard_max_percent=info['source_discard_percent']['max'],
    command_readback_ms=info['command_readback_ms']),indent=2))
