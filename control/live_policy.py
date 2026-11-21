"""Common causal decisions for non-ML policies and a pinned tree trigger."""
import json
from pathlib import Path
import math
from ml.build_trace_dataset import intervals, features_at
from telemetry.inspect_experiment import queue_rows, sample_intervals
from network.routing_action import Admission
from control.routing_policy import Trigger


QUEUES=['s1-eth3','s2-eth2','s1-eth4','s3-eth2']


class JSONLTailer:
    def __init__(self,path): self.path=Path(path);self.stream=None;self.pending=''
    def read(self):
        if self.stream is None:
            if not self.path.exists(): return []
            self.stream=self.path.open(encoding='utf-8')
        self.pending+=self.stream.read()
        lines=self.pending.split('\n');self.pending=lines.pop()
        return [json.loads(line) for line in lines if line.strip()]
    def close(self):
        if self.stream: self.stream.close()


def load_bounds(path):
    b=json.loads(Path(path).read_text())
    if (b.get('id')!='dual-profile-operating-bounds-v1'
        or b.get('profile')!='dual-forward-cburst16k-source250-v1'
        or b.get('admission_budget_bps')!=15900000
        or b.get('headroom_fraction')!=.8 or b.get('collector_interval_s')!=.25):
        raise ValueError('Unexpected frozen operating bounds')
    return b


class LiveDecider:
    def __init__(self,policy,bounds,model=None):
        if policy=='ml':
            if model is None: raise ValueError('ML policy requires the preflight-verified frozen model')
            from ml.ml_trigger import ModelTrigger
            self.trigger=ModelTrigger(model)
        else:
            if model is not None: raise ValueError('Model supplied to a non-ML policy')
            self.trigger=Trigger(policy)
        self.bounds=bounds;self.raw=[];self.history=[]

    def observe(self,row,source_start,now):
        self.raw.append(row)
        current=intervals(self.raw[-2:],source_start,float('inf')) if len(self.raw)>1 else []
        status=dict(sample=row.get('sample'),decision_at=now,features=None,reason=None)
        if not current:
            self.trigger.update(now,{},valid=False)
            return dict(status,status='warming')
        r=current[-1];self.history.append(r)
        available=max(r['available'],row.get('monotonic_end',r['available']))
        status.update(feature_available=available,sample_age_s=now-available)
        qs={name:list(sample_intervals(queue_rows(self.raw[-2:],name))) for name in QUEUES}
        valid=(r['valid'] and all(v and v[-1]['sampling_valid'] for v in qs.values())
               and 0<=now-available<=self.bounds['max_read_age_s'])
        if not valid:
            # A problem in any branch invalidates this decision and its history.
            r['valid']=False
            self.trigger.update(available,{},valid=False)
            return dict(status,status='invalid_or_stale')
        features=features_at(self.history)
        if features is None:
            self.trigger.update(available,{},valid=False)
            return dict(status,status='warming')
        reason=self.trigger.update(available,features)
        demand=max(p['upstream_bps'] for p in self.history
                   if p['valid'] and p['t1']>=r['t1']-1.)
        background=max(qs[name][-1]['qdisc_departure_bps'] for name in ['s1-eth4','s3-eth2'])
        return dict(status,status='ready',features=features,reason=reason,
                    admission_observed_at=available,selected_demand_bps=demand,
                    background_bps=background,**(getattr(self.trigger,'last_inference',None) or {}))

    def admission(self,decision,links_up):
        return Admission('alternate',decision['admission_observed_at'],
            decision['selected_demand_bps'],decision['background_bps'],
            self.bounds['admission_budget_bps'],links_up,self.bounds['id'])

    def mark_applied(self): self.trigger.mark_applied()

    def inference_statistics(self):
        return self.trigger.statistics() if hasattr(self.trigger,'statistics') else None
