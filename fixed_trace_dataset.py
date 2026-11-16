"""Explicit dual-profile fixed-primary dataset, kept separate from old pilots."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from build_trace_dataset import CONFIG,FEATURES,intervals,label_rows
from source_integrity import source_integrity_audit,AUDIT_POLICY
from traffic_scenarios import continuous_schedule


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())


def load_protocol(path):
    p=read(path)
    expected=dict(id='dual-fixed-highutil-v1',profile_id='dual-forward-cburst16k-source250-v1',
      duration_s=60,scale_bps=11500000,interval_s=.25,payload_bytes=1200,
      label_config={**CONFIG,'version':'highutil85-duration1-horizon2-v1',
                    'scope':'Frozen operational target for dual-fixed development; not packet-loss ground truth'})
    if any(p.get(k)!=v for k,v in expected.items()): raise ValueError('Unexpected frozen protocol')
    if p.get('partitions')!={'train':[11,12,13,14,15],'validation':[21,22,23],'test':[31,32,33]}:
        raise ValueError('Unexpected whole-run seed partitions')
    if p.get('scenarios')!=['ramp','bursty'] or not p.get('source_sha256'):
        raise ValueError('Missing scenarios or pinned acquisition source')
    expected_profile=dict(id=expected['profile_id'],forward_links=[['h1','h1-eth0',100],
        ['s1','s1-eth3',100],['s2','s2-eth2',10],['s1','s1-eth4',20],['s3','s3-eth2',20],['s4','s4-eth1',100]],
        cburst_bytes=16384,burst_bytes=15360,source_queue_packets=250,bottleneck_queue_packets=50,delay_ms=1)
    if p.get('profile')!=expected_profile: raise ValueError('Unexpected calibration profile')
    if any(Path(name).name!=name or '/' in name or '\\' in name or len(digest)!=64
           for name,digest in p['source_sha256'].items()): raise ValueError('Invalid pinned source')
    return p


def development_plan(protocol):
    return [dict(split=split,scenario=scenario,seed=seed)
      for split in ['train','validation'] for i,seed in enumerate(protocol['partitions'][split])
      for scenario in (protocol['scenarios'] if i%2==0 else list(reversed(protocol['scenarios'])))]


def validate_selection(selection,protocol,allow_partial=False):
    if selection.get('protocol_id')!=protocol['id']: raise ValueError('Protocol mismatch')
    runs=selection['runs'];identities=set();folders=set()
    allowed={tuple(sorted(x.items())) for x in development_plan(protocol)}
    for item in runs:
        if item['split']=='test': raise ValueError('Held-out acquisition/evaluation is not enabled in the development builder')
        identity={k:item[k] for k in ['split','scenario','seed']}
        if tuple(sorted(identity.items())) not in allowed: raise ValueError('Identity outside registered development partition')
        key=(item['scenario'],item['seed'])
        if key in identities or item['folder'] in folders: raise ValueError('Duplicate run/identity')
        if Path(item['folder']).name!=item['folder'] or '/' in item['folder'] or '\\' in item['folder']:
            raise ValueError('Invalid run folder')
        identities.add(key);folders.add(item['folder'])
    if not allow_partial and len(runs)!=len(allowed): raise ValueError('Development dataset incomplete')
    return runs


def load_fixed_trace(repo,name,protocol):
    # This loader can audit an explicitly supplied pilot; selection validation
    # separately prevents pilot/held-out identities entering development data.
    repo=Path(repo).resolve()
    if Path(name).name!=name or '/' in name or '\\' in name: raise ValueError('Invalid raw folder')
    f=repo/'results/runs'/name;m=read(f/'policy.json')
    if (m.get('policy')!='fixed' or m.get('actions') or m.get('outcome')!='completed'
        or m.get('starting_route')!='primary' or m.get('selected_route_before_cleanup')!='primary'):
        raise ValueError('Only untouched completed fixed-primary traces can train a predictor')
    if m.get('profile')!=protocol['profile'] or m.get('duration')!=protocol['duration_s']:
        raise ValueError('Profile/duration differs from frozen protocol')
    if m.get('requested_scale_bps')!=protocol['scale_bps'] or m.get('scenario') not in protocol['scenarios']:
        raise ValueError('Workload differs from frozen protocol')
    if m['planned_segments']!=continuous_schedule(m['scenario'],protocol['scale_bps'],protocol['duration_s'],m['seed']):
        raise ValueError('Recorded schedule is inconsistent')
    for source,digest in protocol['source_sha256'].items():
        if m['source_sha256'].get(source)!=digest or sha(f/source)!=digest:
            raise ValueError('Acquisition source differs: '+source)
    sys.path.insert(0,str(repo))
    from run_policy_experiment import inspect_policy
    report=inspect_policy(f)
    if report['screen_failures'] or report['applied_actions'] or report['denied_requests']:
        raise ValueError('Acquisition/route screen failed')
    stats=report['collector']['stats']
    if stats.get('schema_version')!=6 or stats.get('interval_s')!=protocol['interval_s'] or stats.get('coverage')!='all':
        raise ValueError('Sampling protocol differs')
    if any(report['route_counter_deltas'][dev]['tx_bytes']>1000 for dev in ['s1-eth4','s3-eth2']):
        raise ValueError('Unexpected alternate-path traffic')
    trial_name=m['trial']
    if Path(trial_name).name!=trial_name: raise ValueError('Invalid trial reference')
    trial=repo/'results/runs'/trial_name;native=read(trial/'sender-native.json')
    if native['payload_bytes']!=protocol['payload_bytes']: raise ValueError('Payload differs')
    start=native['start_monotonic_ns']/1e9;finish=native['end_monotonic_ns']/1e9
    raw=[json.loads(s) for s in (f/'samples.jsonl').read_text().splitlines()]
    records=intervals(raw,start,finish)
    if not records or any(not r['valid'] for r in records): raise ValueError('Paired history contains invalid intervals')
    labeled,events=label_rows(records,protocol['label_config'])
    inputs=[f/'policy.json',f/'samples.jsonl',f/'samples.jsonl.stats.json',f/'restoration.json',
        f/'action.jsonl',f/'ping-loaded.txt',trial/'metadata.json',trial/'sender-native.json',
        trial/'receiver-native.json',trial/'sender-samples.jsonl']
    hashes={str(path.relative_to(repo)):sha(path) for path in inputs}
    summary=dict(run=name,scenario=m['scenario'],seed=m['seed'],rows=len(labeled),
       eligible=sum(r['label'] is not None for r in labeled),positive=sum(r['label']==1 for r in labeled),
       negative=sum(r['label']==0 for r in labeled),events=events,
       source_audit=source_integrity_audit(trial),raw_sha256=hashes,inspection=report)
    return labeled,summary


def build(repo,selection,protocol_path,output,allow_partial=False):
    repo=Path(repo).resolve();output=Path(output).resolve()
    if output.is_relative_to(repo/'results/runs'): raise ValueError('Derivatives cannot be written into raw evidence')
    protocol=load_protocol(protocol_path);selection=read(selection)
    selected=validate_selection(selection,protocol,allow_partial)
    all_rows=[];summaries=[]
    for item in selected:
        rows,summary=load_fixed_trace(repo,item['folder'],protocol)
        if (summary['scenario'],summary['seed'])!=(item['scenario'],item['seed']): raise ValueError('Identity differs from selection')
        summary['split']=item['split'];summaries.append(summary)
        all_rows.extend(dict(run=item['folder'],scenario=item['scenario'],seed=item['seed'],split=item['split'],**r) for r in rows)
    result=dict(protocol=protocol,protocol_sha256=sha(protocol_path),feature_allowlist=FEATURES,
       builder_sha256=sha(__file__),source_audit_policy=AUDIT_POLICY,
       source_audit_sha256=sha(Path(__file__).with_name('source_integrity.py')),
       complete_development=len(selected)==len(development_plan(protocol)),runs=summaries,
       total_eligible=sum(s['eligible'] for s in summaries),total_positive=sum(s['positive'] for s in summaries),
       total_observed_events=sum(e['onset_observed'] for s in summaries for e in s['events']),
       note='Whole-run development partitions. No test data, source schedule, seed or scenario is a model feature.')
    output.mkdir(parents=True,exist_ok=False)
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    (output/'selection.json').write_text(json.dumps(selection,indent=2)+'\n')
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (output/'rows.jsonl').open('x') as f:
        for r in all_rows: f.write(json.dumps(r)+'\n')
    columns=['run','scenario','seed','split','available','label','excluded_reason','lead_to_onset_s']+FEATURES
    with (output/'dataset.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for r in all_rows: writer.writerow({**{k:r[k] for k in columns if k in r},**(r['features'] or {})})
    print(json.dumps({k:result[k] for k in ['complete_development','total_eligible','total_positive','total_observed_events']},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--selection',required=True)
    p.add_argument('--protocol',default=str(Path(__file__).with_name('dataset_protocol.json')))
    p.add_argument('--output',required=True);p.add_argument('--allow-partial',action='store_true')
    a=p.parse_args();build(a.repo,a.selection,a.protocol,a.output,a.allow_partial)
