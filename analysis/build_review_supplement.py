"""Reproduce manuscript clarifications from the frozen replay; never fit or acquire traffic.

Requires an existing reproduce.py output. Original tables/figures remain unchanged.
All new display cells are generated below from measured records or frozen model nodes.
"""
from pathlib import Path
import argparse,csv,hashlib,json,statistics,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def semantic_sha(p):
    def normalize(v):
        if isinstance(v,dict):return {k.replace('\\','/'):normalize(x) for k,x in v.items()}
        if isinstance(v,list):return [normalize(x) for x in v]
        if isinstance(v,str):return v.replace('\\','/')
        return v
    p=Path(p)
    value=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()] if p.suffix=='.jsonl' else read(p)
    return hashlib.sha256(json.dumps(normalize(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def stats(values):return dict(n=len(values),mean=statistics.mean(values),median=statistics.median(values),min=min(values),max=max(values))
def run(replay,out):
    replay=Path(replay).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    lab=replay/'inputs/lab';pub=replay/'inputs/publication'
    sys.path.insert(0,str(lab))
    from tree_model import TreeModel
    from tree_metrics import warning_report,row_report
    from train_tree import baseline
    from build_paper_assets import load_v2
    load_v2(ROOT)
    assert sha(lab/'selected_tree.json')==sha(ROOT/'experiment/selected_tree.json')=='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595'
    model=TreeModel.load(lab/'selected_tree.json');summary=read(replay/'heldout/summary.json')
    rows=[json.loads(x) for x in (replay/'heldout/rows.jsonl').read_text().splitlines()]
    scores=[model.probability(r['features']) if r['features'] is not None else 0. for r in rows]
    metrics=row_report(rows,scores,model.threshold)
    assert metrics==read(replay/'heldout/test_report.json')['metrics']['rows']
    warning=warning_report(rows,scores,summary['runs'],model.threshold)
    trend=warning_report(rows,baseline(rows,'past_trend'),summary['runs'],.5)
    event_audit=[];late_lags=[]
    for s,w,tw in zip(summary['runs'],warning['by_run'],trend['by_run']):
        group=[(r,p) for r,p in zip(rows,scores) if r['run']==s['run']]
        events=[e for e in s['events'] if e['onset_observed']]
        warned={a['event'] for a in w['alarms'] if a['event'] is not None}
        for i,e in enumerate(events):
            selected=[]
            for r,p in group:
                if r['label']!=1:continue
                upcoming=[(j,z) for j,z in enumerate(events) if r['available']<z['onset']<=r['available']+2]
                if upcoming and min(upcoming,key=lambda a:a[1]['onset'])[0]==i:selected.append((r,p))
            event_audit.append(dict(run=s['run'],scenario=s['scenario'],seed=s['seed'],event=i,onset=e['onset'],
                advance_episode=i in warned,positive_rows=len(selected),true_positive_rows=sum(p>=model.threshold for r,p in selected)))
        for a in tw['alarms']:
            if a['late'] and a['event'] is None:
                active=[e for e in events if e['onset']<=a['available']<e['end']]
                assert len(active)==1
                late_lags.append(dict(run=s['run'],scenario=s['scenario'],delay_s=a['available']-active[0]['onset']))
    assert sum(e['positive_rows'] for e in event_audit)==206
    assert sum(e['true_positive_rows'] for e in event_audit)==168
    episode={}
    for name in ['ramp','bursty']:
        es=[e for e in event_audit if e['scenario']==name]
        ls=[x['delay_s'] for x in late_lags if x['scenario']==name]
        episode[name]=dict(events=len(es),events_with_eligible_positive_rows=sum(e['positive_rows']>0 for e in es),
            events_with_any_true_positive_row=sum(e['true_positive_rows']>0 for e in es),
            events_with_advance_episode=sum(e['advance_episode'] for e in es),
            true_positive_rows_on_unwarned_events=sum(e['true_positive_rows'] for e in es if not e['advance_episode']),
            trend_late_delay_s=stats(ls) if ls else None)
    original=read(pub/'results/bursty-followup-v1/closed-audit.json')['original_action_audit']['rows']
    with (ROOT/'data/v2/v2_timing.csv').open(newline='') as f:timing=list(csv.DictReader(f))
    time_stats={}
    for cohort,acts in [('V1',original),('V2',timing)]:
        age=[1000*(a['program_start_measurement_age_s'] if cohort=='V1' else float(a['obs_age_s'])) for a in acts]
        elapsed=[1000*(a['program_and_readback_s'] if cohort=='V1' else float(a['switch_elapsed_s'])) for a in acts]
        time_stats[cohort]=dict(observation_age_at_programming_ms=stats(age),programming_to_readback_ms=stats(elapsed))
    v2=read(ROOT/'data/v2/v2-batch.json');moderate=[r for r in v2['completed'] if r['bg_bps']==4_000_000]
    background=dict(trials=len(moderate),max_reported_bg_loss_percent=max(r['bg_loss_percent'] for r in moderate),
        max_reported_alternate_root_drop_sum=max(r['s3_drops'] for r in moderate),
        note='Reported background process-lifetime summaries, not independently rechecked foreground-aligned raw endpoint records.')
    tables={}
    def table(key,caption,heads,values,widths=None,wide=False,note=''):
        tables[key]=dict(caption=caption,heads=heads,rows=values,widths=widths,wide=wide,note=note)
    table('confusion','Held-out ML confusion counts; pooled metrics sum these counts.',
        ['Scenario','TP','FP','FN','TN'],[[n.capitalize()]+[r[k] for k in ['tp','fp','fn','tn']] for n,r in [*metrics['by_scenario'].items(),('pooled',metrics['pooled'])]],
        [.32,.17,.17,.17,.17])
    action_rows=[]
    for seed in [41,42,43]:
        for policy in ['ml','early_warning']:
            a=next((a for a in timing if (a['scenario'],a['bg_mbps'],a['seed'],a['policy'])==('bursty','4',str(seed),policy)),None)
            action_rows.append([str(seed),'ML' if policy=='ml' else 'Trend']+([a['trigger_offset_s'],a['demand_mbps'],a['bg_obs_mbps']] if a else ['No move','—','—']))
    table('admission_timing','V2 bursty traffic with 4 Mbit/s background: reported successful programming starts and admission estimates.',
        ['Seed','Policy','Start s','Demand Mbit/s','Alt. load Mbit/s'],action_rows,[.1,.14,.2,.28,.28],
        note='Start is relative to foreground source start, not the decision or first forwarded packet. No move means no successful action, not no trigger request. CSV values retain their published precision.')
    tree=read(ROOT/'experiment/selected_tree.json');feature_alias={'upstream_mean_1s_bps':'R1','util_ewma_1s':'E','util_mean_2s':'U2','upstream_bps':'R','util_slope_2s':'S'}
    splits=[];leaves=[]
    for i,n in enumerate(tree['nodes']):
        if n['feature']<0:leaves.append([str(i),format(n['p1'],'.9f'),'Yes' if n['p1']>=model.threshold else 'No'])
        else:splits.append([str(i),feature_alias[tree['features'][n['feature']]],format(n['threshold'],'.9g'),str(n['left']),str(n['right'])])
    table('tree_splits','Frozen tree split nodes. Follow left when the feature is at most the threshold; otherwise follow right. Node 0 is the root.',
        ['Node','Feature','Threshold','Left','Right'],splits,[.12,.15,.45,.14,.14],
        note='R1: one-second upstream mean (bit/s); E: utilization EWMA; U2: two-second utilization mean; R: current upstream rate (bit/s); S: two-second utilization slope (per second). Thresholds shown to nine significant digits; exact binary values are in selected_tree.json.')
    table('tree_leaves','Frozen tree leaf scores and whether they request admission at the unchanged 0.65 threshold.',
        ['Node','Positive-class score','Requests admission'],leaves,[.15,.45,.4],
        note='Scores are weighted training class fractions, not calibrated probabilities. Float32 input comparison matches the exported CART implementation.')
    paths=[replay/'heldout/summary.json',replay/'heldout/rows.jsonl',replay/'heldout/test_report.json',pub/'results/bursty-followup-v1/closed-audit.json',ROOT/'data/v2/v2_timing.csv',ROOT/'data/v2/v2-batch.json',ROOT/'experiment/selected_tree.json']
    report=dict(fitting_performed=False,traffic_started=False,model_sha256=sha(ROOT/'experiment/selected_tree.json'),
        input_digests={('replay/'+p.relative_to(replay).as_posix()) if p.is_relative_to(replay) else ('repository/'+p.relative_to(ROOT).as_posix()):
            dict(sha256=semantic_sha(p) if p.is_relative_to(replay) else sha(p),
                 basis='Canonical JSON (sorted keys, normalized path separators)' if p.is_relative_to(replay) else 'Original file bytes') for p in paths},
        confusion=metrics,episode_audit=episode,event_rows=event_audit,trend_late_episodes=late_lags,
        timing=time_stats,moderate_background=background)
    save(out/'review-evidence.json',report);save(out/'tables.json',tables)
    for key,t in tables.items():
        with (out/(key+'.csv')).open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(t['heads']);w.writerows(t['rows'])
    print(json.dumps(dict(output=str(out),episode=episode,timing=time_stats,background=background),indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.replay,a.output)
