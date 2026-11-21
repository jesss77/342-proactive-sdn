"""Consolidate frozen outcomes, warning denominators and exclusions without fitting or traffic."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse,csv,hashlib,json,statistics,sys
sys.dont_write_bytecode=True

MODEL_SHA='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595'

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def table(path,rows):
    with Path(path).open('x',newline='',encoding='utf-8') as file:
        w=csv.DictWriter(file,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

def run(repo,published,out):
    repo=Path(repo).resolve();pub=Path(published).resolve();out=Path(out).resolve()
    assert not out.is_relative_to(repo/'results/runs');out.mkdir(parents=True,exist_ok=False)
    assert sha(pub/'selected_tree.json')==MODEL_SHA
    sys.path.insert(0,str(pub))
    from tree_model import TreeModel
    from tree_metrics import row_report,warning_report
    from train_tree import baseline
    from build_trace_dataset import covers
    model=TreeModel.load(pub/'selected_tree.json')
    base=repo/'results/derived'
    paths={'development':base/'development-v1-audited-20261115-210839',
           'test':base/'heldout-v1-20261115-220914'}
    inputs={};datasets={};exclusions=[];event_association=[]
    for phase,path in paths.items():
        summary=read(path/'summary.json');rows=[json.loads(x) for x in (path/'rows.jsonl').read_text().splitlines()]
        inputs[str(path.relative_to(repo)/'summary.json')]=sha(path/'summary.json')
        inputs[str(path.relative_to(repo)/'rows.jsonl')]=sha(path/'rows.jsonl')
        for s in summary['runs']:
            for name,digest in s['raw_sha256'].items():assert sha(repo/name)==digest,name
            group=[r for r in rows if r['run']==s['run']];counts=Counter(r['excluded_reason'] or 'eligible' for r in group)
            assert len(group)==s['rows'] and counts['eligible']==s['eligible']
            exclusions.append(dict(phase=phase,split=s['split'],scenario=s['scenario'],seed=s['seed'],run=s['run'],
                rows=len(group),eligible=s['eligible'],positive=s['positive'],negative=s['negative'],
                incomplete_past_history=counts['incomplete_past_history'],event_already_started=counts['event_already_started'],
                incomplete_or_invalid_future=counts['incomplete_or_invalid_future'],invalid_sample=counts['invalid_sample'],
                covered_source_seconds=sum(r['t1']-r['t0'] for r in group),
                feature_available_rows=sum(r['features'] is not None for r in group)))
            events=[e for e in s['events'] if e['onset_observed']]
            event_association.append(dict(phase=phase,split=s['split'],scenario=s['scenario'],seed=s['seed'],
                observed_events=len(events),events_with_root_drops=sum(e['root_drops']>0 for e in events),
                event_root_drops=sum(e['root_drops'] for e in events),
                feature_available_interval_root_drops=sum(r['features']['drops_per_s']*(r['t1']-r['t0']) for r in group if r['features'] is not None),
                minimum_event_peak_queue=min((e['peak_queue_packets'] for e in events),default=None),
                maximum_event_peak_queue=max((e['peak_queue_packets'] for e in events),default=None)))
        datasets[phase]=(rows,summary)
    test_rows,test_summary=datasets['test'];saved=read(paths['test']/'test_report.json')
    probabilities=[model.probability(r['features']) if r['features'] is not None else 0 for r in test_rows]
    assert row_report(test_rows,probabilities,model.threshold)==saved['metrics']['rows']
    assert warning_report(test_rows,probabilities,test_summary['runs'],model.threshold)==saved['metrics']['warnings']
    warning_runs=[];prediction=[]
    for name,values,threshold in [('ML',probabilities,model.threshold),('trend',baseline(test_rows,'past_trend'),.5),
                                  ('always_negative',baseline(test_rows,'always_negative'),.5)]:
        rr=row_report(test_rows,values,threshold);wr=warning_report(test_rows,values,test_summary['runs'],threshold)
        if name!='ML':
            key='past_trend' if name=='trend' else 'always_negative'
            assert rr==saved['baselines'][key]['rows'] and wr==saved['baselines'][key]['warnings']
        for scenario,metrics in rr['by_scenario'].items():prediction.append(dict(method=name,scenario=scenario,**metrics))
        for summary,w in zip(test_summary['runs'],wr['by_run']):
            group=[r for r in test_rows if r['run']==summary['run']]
            support=[dict(t0=r['t0'],t1=r['t1'],valid=r.get('excluded_reason')!='invalid_sample') for r in group]
            # Duration-weighted discrete prediction opportunities; no imputation
            # or pretence that an endpoint decision occupies its whole prior bin.
            scorable=sum(r['t1']-r['t0'] for r in group if r['features'] is not None
                         and covers(support,r['available'],r['available']+3.75))
            covered=sum(r['t1']-r['t0'] for r in group)
            unmatched=[a for a in w['alarms'] if a['event'] is None]
            late_unmatched=sum(a['late'] for a in unmatched)
            warning_runs.append(dict(method=name,scenario=summary['scenario'],seed=summary['seed'],run=summary['run'],
                events=w['events'],scorable_events=w['scorable_events'],true_advance_episodes=w['true_warnings'],
                unmatched_episodes=len(unmatched),late_unmatched_episodes=late_unmatched,
                other_unmatched_episodes=len(unmatched)-late_unmatched,censored_episodes=w['censored_warnings'],
                missed_scorable_events=w['scorable_events']-w['true_warnings'],covered_source_seconds=covered,
                scorable_opportunity_seconds=scorable,unmatched_per_covered_minute=60*len(unmatched)/covered,
                unmatched_per_scorable_minute=60*len(unmatched)/scorable,
                lead_at_least_0_5s=sum(x>=.5 for x in w['lead_s']),lead_at_least_1s=sum(x>=1 for x in w['lead_s']),
                lead_s=w['lead_s']))
            assert abs(w['false_warnings_per_minute']-60*len(unmatched)/covered)<1e-10
    warning_groups=[]
    for method in ['ML','trend','always_negative']:
        for scenario in ['ramp','bursty']:
            g=[r for r in warning_runs if (r['method'],r['scenario'])==(method,scenario)]
            add=['events','scorable_events','true_advance_episodes','unmatched_episodes','late_unmatched_episodes',
                 'other_unmatched_episodes','censored_episodes','missed_scorable_events','covered_source_seconds',
                 'scorable_opportunity_seconds','lead_at_least_0_5s','lead_at_least_1s']
            result=dict(method=method,scenario=scenario,independent_runs=len(g),**{k:sum(x[k] for x in g) for k in add})
            result['unmatched_per_covered_minute']=60*result['unmatched_episodes']/result['covered_source_seconds']
            result['unmatched_per_scorable_minute']=60*result['unmatched_episodes']/result['scorable_opportunity_seconds']
            result['other_unmatched_per_scorable_minute']=60*result['other_unmatched_episodes']/result['scorable_opportunity_seconds']
            result['event_recall_scorable']=result['true_advance_episodes']/result['scorable_events']
            leads=[x for r in g for x in r['lead_s']]
            result['lead_median_s']=statistics.median(leads) if leads else None
            result['lead_min_s']=min(leads) if leads else None;result['lead_max_s']=max(leads) if leads else None
            warning_groups.append(result)
    matched=read(pub/'results/matched-v1/matched-report.json');rows=matched['rows'];paired=[];aggregates=[]
    for scenario in ['steady','ramp','bursty']:
        for policy in ['fixed','reactive','early_warning','ml']:
            g=[r for r in rows if (r['scenario'],r['policy'])==(scenario,policy)]
            assert len(g)==3
            for metric in ['receiver_mbps','udp_loss_percent','traffic_reply_p95_ms','collector_cpu_percent_one_core','policy_cpu_percent_one_core']:
                values=[r[metric] for r in g]
                aggregates.append(dict(scenario=scenario,policy=policy,metric=metric,n=3,mean=statistics.mean(values),
                    sd=statistics.stdev(values),min=min(values),max=max(values)))
        for seed in [41,42,43]:
            ml=next(r for r in rows if (r['scenario'],r['policy'],r['seed'])==(scenario,'ml',seed))
            trend=next(r for r in rows if (r['scenario'],r['policy'],r['seed'])==(scenario,'early_warning',seed))
            paired.append(dict(cohort='original',scenario=scenario,seed=seed,
                delta_receiver_mbps=ml['receiver_mbps']-trend['receiver_mbps'],delta_loss_pp=ml['udp_loss_percent']-trend['udp_loss_percent'],
                delta_rtt_p95_ms=ml['traffic_reply_p95_ms']-trend['traffic_reply_p95_ms'],ml_actions=ml['actions'],trend_actions=trend['actions']))
    followup=read(pub/'results/bursty-followup-v1/closed-audit.json')
    extra={r['policy']:r for r in followup['summary'] if r['seed']==51};ml=extra['ml'];trend=extra['early_warning']
    detailed={r['identity']['policy']:r['report'] for r in followup['attempts'] if r['identity']['seed']==51}
    paired.append(dict(cohort='separate_followup',scenario='bursty',seed=51,
        delta_receiver_mbps=ml['receiver_mbps']-trend['receiver_mbps'],delta_loss_pp=ml['udp_loss_percent']-trend['udp_loss_percent'],
        delta_rtt_p95_ms=detailed['ml']['rtt']['traffic_only']['milliseconds']['p95']-detailed['early_warning']['rtt']['traffic_only']['milliseconds']['p95'],
        ml_actions=ml['actions'],trend_actions=trend['actions']))
    exclusion_groups=[]
    for split in ['train','validation','test']:
        g=[r for r in exclusions if r['split']==split]
        fields=['rows','eligible','positive','negative','incomplete_past_history','event_already_started',
                'incomplete_or_invalid_future','invalid_sample','feature_available_rows','covered_source_seconds']
        total=dict(split=split,independent_runs=len(g),**{k:sum(x[k] for x in g) for k in fields})
        assert total['rows']==total['eligible']+sum(total[k] for k in ['incomplete_past_history','event_already_started','incomplete_or_invalid_future','invalid_sample'])
        exclusion_groups.append(total)
    original_actions=followup['original_action_audit']['rows']
    control=dict(applied_actions=len(original_actions),
        full_decision_to_readback_ms={name:fn([1000*a['full_decision_to_readback_s'] for a in original_actions])
                                      for name,fn in [('min',min),('median',statistics.median),('max',max)]},
        programming_to_readback_ms={name:fn([1000*a['program_and_readback_s'] for a in original_actions])
                                   for name,fn in [('min',min),('median',statistics.median),('max',max)]})
    controls=[r for r in read(pub/'results/supplement-diagnostics-v1/audit.json')['reports'] if r['identity']['stage']=='controls']
    assert len(controls)==6
    from run_path_control import inspect_control
    calibration=[]
    for path in sorted((repo/'results/runs').glob('*-path-control-alternate-*bps')):
        if not path.name.endswith(('12000000bps','16000000bps')):continue
        r=inspect_control(path);assert not r['control_screen_failures']
        calibration.append(dict(folder=path.name,requested_bps=r['trial']['requested_bps'],
            sender_mbps=r['trial']['sender']['bits_per_second']/1e6,
            receiver_mbps=r['trial']['receiver']['bits_per_second']/1e6,udp_loss_percent=r['trial']['receiver']['lost_percent']))
    assert len(calibration)==6
    report=dict(model_sha256=MODEL_SHA,fitting_performed=False,threshold_changed=False,inputs_sha256=inputs,
        exclusion_by_run=exclusions,exclusion_by_split=exclusion_groups,prediction_rows=prediction,
        warning_by_run=warning_runs,warning_by_scenario=warning_groups,development_event_association=event_association,
        original_aggregates=aggregates,paired_ml_minus_trend=paired,control_timing=control,
        alternate_controls=controls,steady_alternate_calibration=calibration,
        definitions=dict(unmatched='No unmatched observed event onset within the next two seconds; includes late episodes.',
          late='Unmatched episode during an already-started sustained high-utilization event.',
          other_unmatched='Unmatched and not late; no claim that all such opportunities are fully independent.',
          rate_denominator='Duration-weighted rows with features and complete 3.75-second future support. This is discrete opportunity exposure, not continuous decision availability. Covered-source denominator is also reported unchanged.',
          margin_sensitivity='0.5/1-second lead margins are descriptive offline timing sensitivities. They do not simulate admission, stale reads, route activation or prevented degradation.'),
        limitations=['Separate cohorts are not pooled. Adjacent rows are not independent repetitions.',
            'Warnings use no-intervention prediction test only. Live rerouting traces are not relabeled.',
            'Original future-support/cooldown matching retained; no model or trigger retuning.'])
    assert sha(pub/'selected_tree.json')==MODEL_SHA
    save(out/'paper-evidence.json',report)
    for name,data in [('exclusions-by-run',exclusions),('exclusions-by-split',exclusion_groups),('prediction-rows',prediction),
                      ('warnings-by-run',warning_runs),('warnings-by-scenario',warning_groups),('paired-differences',paired),('network-aggregates',aggregates)]:
        table(out/(name+'.csv'),data)
    print(json.dumps(dict(output=str(out),exclusions=exclusion_groups,warnings=warning_groups[:4],paired=paired,control=control),indent=2))
    return report

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--published',type=Path,default=root)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.repo,a.published,a.output)
