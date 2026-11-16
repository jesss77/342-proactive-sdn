"""Frozen tree threshold trigger; shared live validity/admission/action remain external."""
import hashlib
import json
import math
from pathlib import Path
import time
from tree_model import TreeModel

FROZEN_MODEL_SHA='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595'


def load_runtime_model(base):
    base=Path(base);path=base/'selected_tree.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=FROZEN_MODEL_SHA:
        raise ValueError('Frozen ML model bytes changed; live action refused')
    model=TreeModel.load(path)
    protocol=json.loads((base/'dataset_protocol.json').read_text())
    feature_sha=hashlib.sha256((base/'build_trace_dataset.py').read_bytes()).hexdigest()
    if (model.model.get('acquisition_protocol_id')!=protocol['id']
        or model.model.get('label_config')!=protocol['label_config']
        or model.model.get('profile_id')!=protocol['profile_id']
        or model.model.get('feature_source_sha256')!=feature_sha):
        raise ValueError('Live feature/target/profile version differs from the frozen tree')
    return model,dict(sha256=FROZEN_MODEL_SHA,threshold=model.threshold,nodes=len(model.nodes),
        feature_source_sha256=feature_sha,profile_id=model.model['profile_id'],
        label_config=model.model['label_config'],training_dataset_fingerprint=model.model['dataset_fingerprint'])


class ModelTrigger:
    def __init__(self,model):
        self.model=model;self.fired=False;self.previous=None;self.last_inference=None
        self.cpu=[];self.wall=[]

    def update(self,available,features,valid=True):
        self.last_inference=None
        if (not valid or not isinstance(available,(int,float)) or not math.isfinite(available)
            or (self.previous is not None and not 0<available-self.previous<=.5)):
            self.previous=None;return None
        self.previous=available
        if self.fired: return None
        wall=time.perf_counter_ns();cpu=time.thread_time_ns()
        probability=self.model.probability(features)
        cpu=time.thread_time_ns()-cpu;wall=time.perf_counter_ns()-wall
        self.cpu.append(cpu);self.wall.append(wall)
        self.last_inference=dict(model_probability=probability,model_threshold=self.model.threshold,
            inference_cpu_ns=cpu,inference_wall_ns=wall)
        return 'frozen_tree_probability' if probability>=self.model.threshold else None

    def mark_applied(self): self.fired=True

    def statistics(self):
        def stats(values):
            ordered=sorted(values)
            return dict(total_ns=sum(ordered),median_ns=ordered[len(ordered)//2],
                p95_ns=ordered[round((len(ordered)-1)*.95)],max_ns=ordered[-1]) if ordered else dict(total_ns=0,median_ns=None,p95_ns=None,max_ns=None)
        return dict(calls=len(self.cpu),cpu=stats(self.cpu),wall=stats(self.wall),
            note='Model calls only. CPU is a subset of policy-thread CPU, not an additional additive cost. No inference after the successful one-way action.')
