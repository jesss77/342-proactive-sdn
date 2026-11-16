"""Reproduce frozen-model metrics without sklearn; no fitting or route changes."""
import argparse
import json
from pathlib import Path
from train_tree import load_data,review,baseline
from tree_model import TreeModel
from tree_metrics import row_report


def run(dataset,model_path,output):
    rows,summary,fingerprint=load_data(dataset)
    model=TreeModel.load(model_path)
    if model.model.get('dataset_fingerprint')!=fingerprint: raise ValueError('Frozen model/development input fingerprint differs')
    protocol=summary['protocol']
    if (model.model.get('label_config')!=protocol['label_config'] or model.model.get('profile_id')!=protocol['profile_id']
        or model.model.get('feature_source_sha256')!=protocol['source_sha256']['build_trace_dataset.py']):
        raise ValueError('Frozen model target/profile/feature version differs')
    metrics={split:review(model,[r for r in rows if r['split']==split],
        [s for s in summary['runs'] if s['split']==split]) for split in ['train','validation']}
    validation=[r for r in rows if r['split']=='validation']
    baselines={name:row_report(validation,baseline(validation,name),.5) for name in ['always_negative','past_trend']}
    report=dict(dataset_fingerprint=fingerprint,model_parameters=model.model['parameters'],
        alarm_threshold=model.threshold,node_count=len(model.nodes),metrics=metrics,baselines=baselines,
        assessment='Frozen development-model reproduction; no fresh test data, fitting, live ML routing or QoS claim')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(parameters=report['model_parameters'],threshold=model.threshold,nodes=len(model.nodes),
       validation=metrics['validation']['rows'],baselines={k:v['scenario_macro_f1'] for k,v in baselines.items()},
       report=str(output/'review.json')),indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--model',default=str(Path(__file__).with_name('selected_tree.json')))
    p.add_argument('--output',required=True);a=p.parse_args();run(a.dataset,a.model,a.output)
