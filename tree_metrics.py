"""Row classification plus causal warning-episode replay; no routing actions."""
from collections import defaultdict
import statistics
from build_trace_dataset import covers


def binary_metrics(truth,predictions):
    if len(truth)!=len(predictions): raise ValueError('Prediction length differs')
    tp=sum(y==1 and p for y,p in zip(truth,predictions));fp=sum(y==0 and p for y,p in zip(truth,predictions))
    fn=sum(y==1 and not p for y,p in zip(truth,predictions));tn=sum(y==0 and not p for y,p in zip(truth,predictions))
    return dict(n=len(truth),tp=tp,fp=fp,fn=fn,tn=tn,
      precision=tp/(tp+fp) if tp+fp else 0.,recall=tp/(tp+fn) if tp+fn else 0.,
      f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.,
      accuracy=(tp+tn)/len(truth) if truth else None)


def row_report(rows,probabilities,threshold):
    if len(rows)!=len(probabilities): raise ValueError('Prediction length differs')
    selected=[(r,p) for r,p in zip(rows,probabilities) if r['label'] is not None]
    def score(pairs): return binary_metrics([r['label'] for r,p in pairs],[p>=threshold for r,p in pairs])
    scenarios={name:score([(r,p) for r,p in selected if r['scenario']==name]) for name in ['ramp','bursty']}
    runs={name:score([(r,p) for r,p in selected if r['run']==name]) for name in sorted({r['run'] for r,p in selected})}
    return dict(pooled=score(selected),by_scenario=scenarios,by_run=runs,
      scenario_macro_f1=sum(m['f1'] for m in scenarios.values())/2)


def warning_report(rows,probabilities,summaries,threshold,horizon=2.,cooldown=5.,future_support=3.75):
    """Predict on all available histories; labels/event truth only score alarms.

    Alarm episodes are rising threshold crossings with a fixed cooldown.
    This replay does not simulate network interventions or the one-action cap.
    """
    if len(rows)!=len(probabilities): raise ValueError('Prediction length differs')
    grouped=defaultdict(list)
    for r,p in zip(rows,probabilities): grouped[r['run']].append((r,p))
    reports=[]
    for summary in summaries:
        pairs=grouped[summary['run']];active=False;last_alarm=float('-inf');previous=None
        alarms=[];censored=[];events=[e for e in summary['events'] if e['onset_observed']]
        matched=set();leads=[];late=0
        support=[dict(t0=r['t0'],t1=r['t1'],valid=r.get('excluded_reason')!='invalid_sample') for r,p in pairs]
        for r,p in pairs:
            t=r['available']
            if r['features'] is None or (previous is not None and not 0<t-previous<=.5): active=False
            previous=t
            if r['features'] is None: continue
            high=p>=threshold;fire=high and not active and t-last_alarm>=cooldown;active=high
            if not fire: continue
            last_alarm=t
            if not covers(support,t,t+future_support): censored.append(t);continue
            possible=[i for i,e in enumerate(events) if i not in matched and t<e['onset']<=t+horizon]
            match=min(possible,key=lambda i:events[i]['onset']) if possible else None
            if match is not None: matched.add(match);leads.append(events[match]['onset']-t)
            is_late=any(e['onset']<=t<e['end'] for e in events);late+=int(is_late)
            alarms.append(dict(available=t,event=match,late=is_late))
        scorable=sum(any(r['features'] is not None and e['onset']-horizon<=r['available']<e['onset']
                     and covers(support,r['available'],r['available']+future_support) for r,p in pairs) for e in events)
        tp=len(matched);fp=len(alarms)-tp
        duration=sum(r['t1']-r['t0'] for r,p in pairs)
        reports.append(dict(run=summary['run'],scenario=summary['scenario'],events=len(events),scorable_events=scorable,
            true_warnings=tp,false_warnings=fp,late_warnings=late,censored_warnings=len(censored),
            event_recall_all=tp/len(events) if events else None,
            event_recall_scorable=tp/scorable if scorable else None,
            warning_precision=tp/len(alarms) if alarms else 0.,
            false_warnings_per_minute=60*fp/duration if duration else None,
            lead_s=leads,median_lead_s=statistics.median(leads) if leads else None,alarms=alarms))
    return dict(by_run=reports,note='Operational high-utilization onsets, not packet-loss onset. Prediction episodes without interventions; not the live one-action routing policy. Tail warnings without full future support are censored explicitly.')
