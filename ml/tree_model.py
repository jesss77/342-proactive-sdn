"""Small JSON CART inference, no pickle or optional ML runtime dependency."""
import hashlib
import json
import math
from pathlib import Path
import struct
from ml.build_trace_dataset import FEATURES


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def f32(value):
    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
        raise ValueError('Model features must be finite numeric values')
    try: result=struct.unpack('!f',struct.pack('!f',value))[0]
    except (OverflowError,struct.error): raise ValueError('Feature outside float32 range')
    if not math.isfinite(result): raise ValueError('Feature outside float32 range')
    return result


class TreeModel:
    def __init__(self,model):
        self.model=model
        if model.get('format')!='cmps342-cart-json-v1' or model.get('features')!=FEATURES:
            raise ValueError('Unexpected model format/feature order')
        threshold=model.get('alarm_threshold')
        if not isinstance(threshold,(int,float)) or not 0<threshold<1: raise ValueError('Invalid alarm threshold')
        nodes=model.get('nodes')
        if not isinstance(nodes,list) or not 1<=len(nodes)<=127: raise ValueError('Invalid tree size')
        seen=set()
        def visit(index):
            if not isinstance(index,int) or index<0 or index>=len(nodes) or index in seen:
                raise ValueError('Invalid/cyclic/shared tree node')
            seen.add(index);node=nodes[index]
            p=node.get('p1')
            if not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
                raise ValueError('Invalid leaf probability')
            if node.get('feature')==-1:
                if node.get('left')!=-1 or node.get('right')!=-1: raise ValueError('Leaf has children')
            else:
                feature=node.get('feature');cut=node.get('threshold')
                if not isinstance(feature,int) or not 0<=feature<len(FEATURES) or not isinstance(cut,(int,float)) or not math.isfinite(cut):
                    raise ValueError('Invalid split')
                visit(node.get('left'));visit(node.get('right'))
        visit(0)
        if len(seen)!=len(nodes): raise ValueError('Unreachable tree nodes')
        self.nodes=nodes;self.threshold=threshold

    @classmethod
    def load(cls,path): return cls(json.loads(Path(path).read_text()))

    def probability(self,features):
        if set(features)!=set(FEATURES): raise ValueError('Feature allowlist mismatch')
        values=[f32(features[name]) for name in FEATURES]
        index=0
        while self.nodes[index]['feature']!=-1:
            node=self.nodes[index]
            index=node['left'] if values[node['feature']]<=node['threshold'] else node['right']
        return self.nodes[index]['p1']

    def alarm(self,features): return self.probability(features)>=self.threshold
