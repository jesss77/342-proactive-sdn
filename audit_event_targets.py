"""Development-only operational-target review; no model fitting or target search."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys


def audit_rows(rows,detect_events,threshold=.85,confirmation=1.):
    valid=[r for r in rows if r['valid']]
    events=detect_events(rows,threshold,confirmation)
    observed=[e for e in events if e['onset_observed']]
    drops=sum(r['drops_delta'] for r in valid)
    inside=lambda r,e: e['onset']<=r['t0'] and r['t1']<=e['end']+1e-7
    event_drops=sum(r['drops_delta'] for r in valid if any(inside(r,e) for e in events))
    summaries=[]
    for e in events:
        selected=[r for r in valid if inside(r,e)]
        lossy=[r for r in selected if r['drops_delta']>0]
        summaries.append(dict(e,first_drop_interval_since_onset_s=(lossy[0]['t0']-e['onset'] if lossy else None),
            queue_positive_intervals=sum(r['queue_packets']>0 for r in selected),
            near_full_intervals=sum(r['queue_packets']>=40 for r in selected)))
    durations=[r['t1']-r['t0'] for r in valid]
    reads=[r['query_duration_s'] for r in valid]
    availability_lag=[r['available']-r['t1'] for r in valid]
    def stats(values):
        values=sorted(values)
        return dict(min=min(values),median=statistics.median(values),
                    p95=values[round((len(values)-1)*.95)],max=max(values)) if values else None
    return dict(intervals=len(rows),invalid_intervals=len(rows)-len(valid),
        events=len(events),observed_events=len(observed),event_details=summaries,
        total_root_drops=drops,drops_inside_sustained_highutil=event_drops,
        drops_outside_sustained_highutil=drops-event_drops,
        interval_s=stats(durations),query_duration_s=stats(reads),read_end_minus_counter_midpoint_s=stats(availability_lag),
        note='High utilization is the operational target, not a necessary/sufficient definition of packet loss. Drop timing uses sampled interval edges.')


def run(repo,output):
    repo=Path(repo).resolve();output=Path(output).resolve()
    if output.is_relative_to(repo/'results/runs'): raise ValueError('Do not write into raw evidence')
    sys.path.insert(0,str(repo))
    from build_trace_dataset import intervals,detect_events,label_rows
    from inspect_experiment import inspect_experiment
    from run_policy_experiment import inspect_policy
    old=[
      ('20261115-153845-837292-experiment-primary-continuous-ramp-250ms','train'),
      ('20261115-155335-039477-experiment-primary-continuous-ramp-250ms','validation'),
      ('20261115-155745-482853-experiment-primary-continuous-bursty-250ms','train'),
      ('20261115-155852-293856-experiment-primary-continuous-bursty-250ms','validation'),
      ('20261115-191455-201140-policy-fixed-ramp-seed1','development_control')]
    reports=[];hashes={}
    for name,role in old:
        folder=repo/'results/runs'/name
        policy=(folder/'policy.json').exists()
        meta=json.loads((folder/('policy.json' if policy else 'experiment.json')).read_text())
        if meta['policy']!='fixed' or (meta.get('actions',[]) if policy else meta['interventions']):
            raise ValueError('Audit requires untouched fixed primary traces')
        for source,digest in meta['source_sha256'].items():
            if hashlib.sha256((folder/source).read_bytes()).hexdigest()!=digest:
                raise ValueError('Captured source mismatch: '+source)
        inspected=inspect_policy(folder) if policy else inspect_experiment(folder)
        t=inspected['trial'] if policy else inspected['trials'][0]
        qs=inspected['collector']['qdiscs']
        if (inspected['outcome']!='completed' or inspected['restoration']['failures']
            or t['screen_failures'] or any(q['failed_queries'] or q['invalid_intervals'] for q in qs.values())):
            raise ValueError('Rejected development trace: '+name)
        trial=repo/'results/runs'/(meta['trial'] if policy else meta['trials'][0]['run'])
        native=json.loads((trial/'sender-native.json').read_text())
        start=native['start_monotonic_ns']/1e9;end=native['end_monotonic_ns']/1e9
        raw=[json.loads(s) for s in (folder/'samples.jsonl').read_text().splitlines()]
        records=intervals(raw,start,end)
        labeled,_=label_rows(records)
        report=dict(run=name,role=role,scenario=meta['scenario'],seed=meta['seed'],
            profile=meta['profile']['id'],audit=audit_rows(records,detect_events),
            eligible=sum(r['label'] is not None for r in labeled),
            positives=sum(r['label']==1 for r in labeled),
            sensitivity=[dict(threshold=t,confirmation_s=c,events=len(detect_events(records,t,c)))
                for t,c in [(.8,1),(.85,.5),(.85,1),(.85,1.5),(.9,1)]])
        report['full_trial_root_drop_delta']=t['queue_drop_deltas']['s2-eth2']
        report['drops_outside_fully_contained_source_intervals']=(report['full_trial_root_drop_delta']
             -report['audit']['total_root_drops'])
        if report['drops_outside_fully_contained_source_intervals']<0: raise ValueError('Drop accounting differs')
        reports.append(report)
        for path in [folder/'samples.jsonl',folder/('policy.json' if policy else 'experiment.json'),trial/'sender-native.json']:
            hashes[str(path.relative_to(repo))]=hashlib.sha256(path.read_bytes()).hexdigest()
    output.mkdir(parents=True,exist_ok=False)
    result=dict(scope='Development-only: original seeds 1/2 and new fixed pilot seed 1. Original pilot test seed 3 is not used in this audit.',
        runs=reports,input_sha256=hashes,
        decision='Retain 85% utilization sustained for 1 second as an operational high-utilization onset target; 2-second horizon and 2-second causal history. Do not call it ground-truth packet loss.',
        measurement='250 ms batch sampling retained for this bounded experiment. It resolves sustained 1-second events in reviewed traces; shorter spikes and independent kernel-statistic freshness are not certified.',
        held_out='New held-out seeds remain unacquired until model/threshold decisions are frozen.')
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Development event-target audit','',result['scope'],'',
      '| Trace | Sustained events | Covered drops in / outside events | Boundary/probe-window drops | Largest sampling interval |',
      '| --- | --- | --- | --- | --- |']
    for r in reports:
        a=r['audit'];lines.append(f"| {r['scenario']} seed {r['seed']} ({r['role']}) | {a['observed_events']} | {a['drops_inside_sustained_highutil']} / {a['drops_outside_sustained_highutil']} | {r['drops_outside_fully_contained_source_intervals']} | {a['interval_s']['max']:.6f} s |")
    lines.extend(['',result['decision'],'',result['measurement'],'',
      'This is a transparent operational definition, not a claim that 85% utilization universally causes congestion. Sensitivity results are descriptive and were not selected to maximize a test score.',
      '',result['held_out']])
    (output/'AUDIT.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.repo,a.output)
