"""Supplemental variable-load fixed-alternate control; original sources stay frozen.

Controller remains primary. Both paths calibrated, all four qdiscs observed.
An idle manual alternate action is followed by explicitly offered test traffic.
The idle admission guard is not a certificate for that subsequent offered load.
"""
from datetime import datetime
from pathlib import Path
from contextlib import ExitStack
import importlib
import json
import math
import os
import shutil
import sys
import time

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import run_continuous_trial as recorder
recorder=importlib.reload(recorder)  # Existing Mininet may cache the pre-hook module.
from dual_path_profile import dual_profile, QUEUES
from routing_action import RoutingAction,Admission
from run_experiment import stop,interface_counts
from inspect_experiment import inspect_trial,queue_summary,ping_statistics
from traffic_scenarios import continuous_schedule
from source_integrity import source_integrity_audit
from run_matched_batch import load_protocol, COMMON_SOURCES, ML_SOURCES, EXTRA_SOURCES, sha


def run(net,route='alternate',requested_bps=11500000,duration=60,scenario='ramp',seed=41,
        clock=time.monotonic,sleep=time.sleep):
    if route not in ['primary','alternate'] or type(requested_bps) is not int or not 0<requested_bps<=24000000:
        raise ValueError('Supported fixed path and positive rate up to 24 Mbit/s required')
    if not math.isfinite(duration) or not 5<=duration<=120 or os.cpu_count()!=1:
        raise ValueError('5–120 seconds and the one-vCPU guest required')
    if route!='alternate' or requested_bps!=11500000 or duration!=60 or scenario not in ['ramp','bursty'] or seed not in [41,42,43]:
        raise ValueError('Only registered supplemental fixed-alternate cells are supported')
    frozen=load_protocol(BASE)
    plan=continuous_schedule(scenario,requested_bps,duration,seed)
    folder=BASE/'results/runs'/(
        datetime.now().strftime('%Y%m%d-%H%M%S-%f')+f'-schedule-path-control-{route}-{scenario}-seed{seed}')
    folder.mkdir(parents=True)
    meta=dict(purpose='Fixed-path capacity characterization; not an automatic policy result',
        route=route,requested_bps=requested_bps,duration=duration,interval_s=.25,
        collector_coverage='all',outcome='running',source_sha256={},scenario=scenario,seed=seed,
        requested_scale_bps=requested_bps,planned_segments=plan,
        frozen_matched_protocol_sha256=sha(BASE/'matched_protocol.json'))
    def save(): (folder/'control.json').write_text(json.dumps(meta,indent=2)+'\n')
    import hashlib
    for name in dict.fromkeys(COMMON_SOURCES+ML_SOURCES+EXTRA_SOURCES+['run_path_control.py',
            'run_schedule_path_control.py','matched_protocol.json']):
        shutil.copy2(BASE/name,folder/name)
        meta['source_sha256'][name]=hashlib.sha256((BASE/name).read_bytes()).hexdigest()
    save();actor=None;collector=ping=None
    def execute(node,args): return net[node].pexec(args)
    def verify_selected(_net,expected,out,phase='before'):
        if expected!=actor.route: raise RuntimeError('Unexpected selected route')
        proof=actor.verify(expected)
        for switch,text in proof.items(): (Path(out)/f'{phase}-{switch}-flows.txt').write_text(text)
        return dict(mode='owned_hostpair',selected_route=expected,
                    s1=dict(output_port=4 if expected=='alternate' else 3),
                    s4=dict(output_port=4 if expected=='alternate' else 3))
    try:
        actor=RoutingAction(execute,folder/'action.jsonl',clock=clock)
        with dual_profile(net,folder) as profile:
            meta['profile']=profile;save()
            # Actual byte activity is bounded before the manual idle action.
            def idle_counts():
                values=[]
                for node,dev in [('h1','h1-eth0'),('s1','s1-eth4'),('s3','s3-eth2')]:
                    out,err,code=execute(node,['cat',f'/sys/class/net/{dev}/statistics/tx_bytes'])
                    if code: raise RuntimeError(err)
                    values.append(int(out.strip()))
                return values
            t0=clock();before=idle_counts();sleep(1)
            after=idle_counts();t1=clock()
            if not .9<=t1-t0<=2: raise RuntimeError('Idle observation timing failed')
            rates=[8*(b-a)/(t1-t0) for a,b in zip(before,after)]
            if any(not 0<=r<=100000 for r in rates): raise RuntimeError('Control requires idle testbed')
            links=True
            for dev in ['s1-eth4','s3-eth2','s4-eth4']:
                out,err,code=execute('s1',['cat',f'/sys/class/net/{dev}/carrier'])
                links=links and code==0 and out.strip()=='1'
            meta['idle_admission_measurement']=dict(start=t0,end=t1,before=before,after=after,rates_bps=rates,links_up=links)
            if route=='alternate':
                admission=Admission('alternate',t1,max(rates[0],100000),max(rates[1:]),
                    3000000,links,'Idle control action only; subsequent offered load is capacity characterization')
                meta['action']=actor.request(admission,'fixed_alternate_capacity_control')
                if not meta['action']['applied']: raise RuntimeError('Idle action denied')
            meta['counters_before']=interface_counts()
            out,err,code=execute('h1',['ping','-n','-D','-c','10','-i','.2','-w','5',net['h2'].IP()])
            (folder/'ping-idle.txt').write_text(out+err)
            if code: raise RuntimeError('Idle RTT probe failed')
            with ExitStack() as files:
                try:
                    import subprocess
                    log=files.enter_context((folder/'collector.log').open('w'))
                    collector=subprocess.Popen(['/usr/bin/python3',str(BASE/'collect_path.py'),
                        str(folder/'samples.jsonl'),'--route',route,'--coverage','all',
                        '--interval','.25','--duration',str(duration+30)],stdout=log,stderr=subprocess.STDOUT)
                    sleep(2)
                    if collector.poll() is not None: raise RuntimeError('Collector did not start')
                    ping_log=files.enter_context((folder/'ping-loaded.txt').open('w'))
                    ping=net['h1'].popen(['ping','-n','-D','-i','.2',net['h2'].IP()],
                                          stdout=ping_log,stderr=subprocess.STDOUT)
                    trial=recorder.run(net,BASE,requested_bps,route,duration,plan=plan,seed=seed,scenario=scenario,
                        route_verifier=verify_selected,trial_context=dict(route_verification='owned_hostpair',
                        kind='fixed_path_control',control=folder.name,profile=profile['id'],
                        supplemental=True,scenario=scenario,seed=seed))
                    meta['trial']=trial.name;save()
                    if json.loads((trial/'metadata.json').read_text())['outcome']!='completed':
                        raise RuntimeError('Control traffic failed; inspect trial')
                    if collector.poll() is not None or ping.poll() is not None:
                        raise RuntimeError('Collector/probe exited unexpectedly')
                    sleep(2)
                finally:
                    meta['ping_exit']=stop(ping);meta['collector_exit']=stop(collector)
                    save()
            if meta['collector_exit']!=0: raise RuntimeError('Collector did not stop cleanly')
            meta['forwarding_before_cleanup']=verify_selected(net,route,folder,'selected')
            meta['counters_after']=interface_counts()
            actor.close();meta['route_restoration']=dict(verified=True,failures=[])
        meta['outcome']='completed'
    except BaseException as e:
        meta.update(outcome='error',error=str(e))
    finally:
        if actor is not None and actor.claimed:
            try: actor.close();meta['route_restoration']=dict(verified=True,failures=[])
            except Exception as e: meta['route_restoration']=dict(verified=False,failures=[str(e)]);meta['outcome']='error'
        save()
    print('Path control:',meta['outcome'],'| route restoration:',meta.get('route_restoration'),flush=True)
    print('Saved:',folder,flush=True)
    if meta['outcome']!='completed': raise RuntimeError(meta.get('error','Control failed'))
    report=inspect_control(folder)
    derived=BASE/'results/derived';derived.mkdir(exist_ok=True)
    # Mininet is root; normal guest analysis can read the new unique file.
    with (derived/(folder.name+'.json')).open('x') as f: json.dump(report,f,indent=2)
    print('CONTROL REVIEW:',json.dumps(report),flush=True)
    return folder


def inspect_control(folder):
    folder=Path(folder);meta=json.loads((folder/'control.json').read_text())
    trial=folder.parent/meta['trial'];assessment=inspect_trial(trial)
    rows=[json.loads(s) for s in (folder/'samples.jsonl').read_text().splitlines()]
    queues={name:queue_summary(rows,name) for name in QUEUES}
    stats=json.loads((folder/'samples.jsonl.stats.json').read_text())
    restoration=json.loads((folder/'restoration.json').read_text())
    native=json.loads((trial/'sender-native.json').read_text())
    windows=[(native['start_wall_epoch_s'],native['end_wall_epoch_s'])]
    rtt={phase:ping_statistics((folder/f'ping-{phase}.txt').read_text()) for phase in ['idle','loaded']}
    rtt['traffic_only']=ping_statistics((folder/'ping-loaded.txt').read_text(),windows)
    active=['s1-eth4','s3-eth2'] if meta['route']=='alternate' else ['s1-eth3','s2-eth2']
    deltas={dev:{k:after[k]-meta['counters_before'][dev][k] for k in after}
            for dev,after in meta['counters_after'].items()}
    failures=list(assessment['screen_failures'])
    expected=continuous_schedule(meta['scenario'],meta['requested_scale_bps'],meta['duration'],meta['seed'])
    trial_meta=json.loads((trial/'metadata.json').read_text())
    if (meta['planned_segments']!=expected or trial_meta.get('traffic_plan')!=expected
        or trial_meta.get('seed')!=meta['seed'] or trial_meta.get('scenario')!=meta['scenario']
        or trial_meta.get('trial_context',{}).get('control')!=folder.name):
        failures.append('schedule_or_identity')
    frozen=load_protocol(folder.parent.parent.parent)
    if meta['frozen_matched_protocol_sha256']!=sha(folder/'matched_protocol.json'):
        failures.append('frozen_protocol')
    for name,digest in frozen['source_sha256'].items():
        if meta['source_sha256'].get(name)!=digest or sha(folder/name)!=digest:
            failures.append('captured_source:'+name)
    audit=source_integrity_audit(trial)
    if any(q['failed_queries'] or q['invalid_intervals'] for q in queues.values()): failures.append('collector_timing_or_query')
    if restoration['failures'] or not meta['route_restoration']['verified']: failures.append('restoration')
    if not rows or stats.get('schema_version')!=6 or stats.get('coverage')!='all': failures.append('collector_coverage')
    if any(deltas[dev]['tx_bytes']<100000 for dev in active): failures.append('active_path_not_demonstrated')
    inactive=[dev for dev in QUEUES if dev not in active]
    limit=max(deltas[dev]['tx_bytes'] for dev in active)*.01
    if any(deltas[dev]['tx_bytes']>limit for dev in inactive): failures.append('inactive_path_data')
    return dict(control=folder.name,route=meta['route'],outcome=meta['outcome'],
        scenario=meta['scenario'],seed=meta['seed'],requested_scale_bps=meta['requested_scale_bps'],source_audit=audit,
        trial=assessment,collector=dict(qdiscs=queues,process_overhead=stats),rtt=rtt,
        route_counter_deltas=deltas,profile=meta['profile'],restoration=restoration,
        route_restoration=meta['route_restoration'],control_screen_failures=failures,
        note='Fixed manual path control, not reactive/ML QoS evidence; readback times include CLI overhead')


if 'net' in globals():
    run(net,scenario=globals().get('scenario','ramp'),seed=globals().get('seed',41))
