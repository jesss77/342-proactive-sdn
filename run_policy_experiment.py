"""Same live sampler/profile/source/action for all four frozen policy modes.

One trial starts on primary; at most one alternate action. ML never refits here.
"""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import hashlib
import importlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
# Mininet keeps imported modules across source updates. Refresh the inspector
# and shared feature code before binding this trial's live dependencies.
import inspect_experiment as inspector
inspector=importlib.reload(inspector)
import build_trace_dataset as trace_dataset
trace_dataset=importlib.reload(trace_dataset)
import live_policy as live
live=importlib.reload(live)
import run_continuous_trial as recorder
recorder=importlib.reload(recorder)
from dual_path_profile import dual_profile,LINKS,QUEUES
from routing_action import RoutingAction
from live_policy import LiveDecider,JSONLTailer,load_bounds
from traffic_scenarios import continuous_schedule
from run_experiment import stop,interface_counts
from inspect_experiment import inspect_trial,queue_summary,ping_statistics
from ml_trigger import load_runtime_model,FROZEN_MODEL_SHA


def read_source_start(folder):
    p=Path(folder)/'sender-samples.jsonl'
    if not p.exists(): return None
    with p.open() as f: line=f.readline()
    if not line.endswith('\n'): return None
    r=json.loads(line)
    return r['monotonic_ns']/1e9-r['elapsed_s']


def request_from_decision(actor,decider,decision,links_up,max_age_s,clock=time.monotonic):
    # Apply the same freshness bound after feature/inference/link-read work
    # for all four policies, before entering the unchanged shared action.
    age=clock()-decision['admission_observed_at']
    if not 0<=age<=max_age_s:
        return dict(applied=False,rejection='stale_policy_observation',observation_age_s=age)
    return actor.request(decider.admission(decision,links_up),decision['reason'])


def run(net,policy='reactive',scenario='ramp',requested_bps=11500000,duration=60,seed=1,
        clock=time.monotonic,sleep=time.sleep):
    bounds=load_bounds(BASE/'operating_bounds.json')
    model,model_context=load_runtime_model(BASE) if policy=='ml' else (None,None)
    decider=LiveDecider(policy,bounds,model=model)
    if os.cpu_count()!=1 or not 5<=duration<=120:
        raise ValueError('One-vCPU protocol and duration 5–120 seconds required')
    plan=continuous_schedule(scenario,requested_bps,duration,seed)
    if max(max(s['requested_bps'],s.get('end_bps',s['requested_bps'])) for s in plan)>bounds['max_tested_payload_bps']:
        raise ValueError('Schedule exceeds the tested 16M payload envelope; use scale 11.5M for variable scenarios')
    folder=BASE/'results/runs'/(
        datetime.now().strftime('%Y%m%d-%H%M%S-%f')+f'-policy-{policy}-{scenario}-seed{seed}')
    folder.mkdir(parents=True)
    meta=dict(policy=policy,scenario=scenario,seed=seed,requested_scale_bps=requested_bps,
        duration=duration,planned_segments=plan,starting_route='primary',max_actions=1,
        outcome='running',validity='pending_review',actions=[],source_sha256={},bounds=bounds,
        scope='single h1/h2 flow; no generated background; one-way alternate action then cleanup')
    if model_context is not None: meta['model']=model_context
    def save(): (folder/'policy.json').write_text(json.dumps(meta,indent=2)+'\n')
    source_names=['run_policy_experiment.py','live_policy.py','routing_policy.py','routing_action.py',
        'operating_bounds.json','dual_path_profile.py','collect_path.py','run_continuous_trial.py',
        'continuous_udp.py','traffic_scenarios.py','build_trace_dataset.py','inspect_experiment.py',
        'topology.py','diamond_controller.py','experiment_config.py']
    if model is not None: source_names+=['ml_trigger.py','tree_model.py','selected_tree.json']
    for name in source_names:
        shutil.copy2(BASE/name,folder/name)
        meta['source_sha256'][name]=hashlib.sha256((BASE/name).read_bytes()).hexdigest()
    save();actor=None;collector=ping=None;worker=None;abort=threading.Event()
    created=queue.Queue();result={};route_lock=threading.RLock()
    def execute(node,args): return net[node].pexec(args)
    def proof(_net,_route,out,phase='before'):
        with route_lock:
            actual=actor.route
            if phase=='before' and actual!='primary': raise RuntimeError('Trial must start on primary')
            texts=actor.verify(actual)
            for switch,text in texts.items(): (Path(out)/f'{phase}-{switch}-flows.txt').write_text(text)
            return dict(mode='owned_hostpair',selected_route=actual)
    def traffic():
        try:
            result['folder']=recorder.run(net,BASE,requested_bps,'primary',duration,plan=plan,
                seed=seed,scenario=scenario,route_verifier=proof,capture_links=LINKS,
                trial_context=dict(route_verification='owned_hostpair',dynamic_routing=True,
                    kind='policy_experiment',policy=policy,parent=folder.name),
                on_created=created.put,abort_event=abort)
        except BaseException as e: result['error']=repr(e)
    try:
        actor=RoutingAction(execute,folder/'action.jsonl',clock=clock)
        with dual_profile(net,folder) as profile:
            meta['profile']=profile
            # Idle guard covers all branches before starting the one-source trial.
            before=interface_counts();t0=clock();sleep(1);after=interface_counts();t1=clock()
            if not .9<=t1-t0<=2: raise RuntimeError('Idle observation timing failed')
            idle=[]
            for dev in QUEUES:
                a,b=before[dev],after[dev]
                if 'error' in a or 'error' in b: raise RuntimeError('Idle counter missing')
                value=8*(b['tx_bytes']-a['tx_bytes'])/(t1-t0);idle.append(value)
            if any(not 0<=r<=100000 for r in idle): raise RuntimeError('Policy trial requires idle testbed')
            meta['idle_guard']=dict(start=t0,end=t1,rates_bps=idle)
            out,err,code=execute('h1',['ping','-n','-D','-c','10','-i','.2','-w','5',net['h2'].IP()])
            (folder/'ping-idle.txt').write_text(out+err)
            if code: raise RuntimeError('Idle probe failed')
            meta['counters_before']=interface_counts();save()
            with ExitStack() as files:
                try:
                    log=files.enter_context((folder/'collector.log').open('w'))
                    collector=subprocess.Popen(['/usr/bin/python3',str(BASE/'collect_path.py'),
                        str(folder/'samples.jsonl'),'--route','primary','--coverage','all',
                        '--interval','.25','--duration',str(duration+40)],stdout=log,stderr=subprocess.STDOUT)
                    sleep(2)
                    if collector.poll() is not None: raise RuntimeError('Collector exited before traffic')
                    pinglog=files.enter_context((folder/'ping-loaded.txt').open('w'))
                    ping=net['h1'].popen(['ping','-n','-D','-i','.2',net['h2'].IP()],stdout=pinglog,stderr=subprocess.STDOUT)
                    tail=JSONLTailer(folder/'samples.jsonl');trial=None;source_start=None
                    pending=[];cpu0=time.thread_time();loop_start=clock()
                    decisions=files.enter_context((folder/'decisions.jsonl').open('w'))
                    worker=threading.Thread(target=traffic,name='sdn-traffic-recorder')
                    worker.start()
                    try:
                        while worker.is_alive():
                            if trial is None:
                                try: trial=created.get_nowait();meta['trial']=trial.name;save()
                                except queue.Empty: pass
                            if source_start is None and trial is not None:
                                source_start=read_source_start(trial)
                            new=tail.read();pending.extend(new)
                            source_done=trial is not None and (trial/'sender-native.json').exists()
                            if source_start is not None and not source_done:
                                for row in pending:
                                    d=decider.observe(row,source_start,clock())
                                    if d['reason'] and actor.route=='primary':
                                        links=True
                                        for dev in ['s1-eth4','s3-eth2','s4-eth4']:
                                            out,err,code=execute('s1',['cat',f'/sys/class/net/{dev}/carrier'])
                                            links=links and code==0 and out.strip()=='1'
                                        with route_lock:
                                            applied=request_from_decision(actor,decider,d,links,bounds['max_read_age_s'],clock)
                                        d['action']=applied;meta['actions'].append(applied);save()
                                        if applied['applied']: decider.mark_applied()
                                    d['route_after_decision']=actor.route
                                    decisions.write(json.dumps(d)+'\n');decisions.flush()
                                pending=[]
                            if collector.poll() is not None or ping.poll() is not None:
                                raise RuntimeError('Monitor/probe exited during traffic')
                            if clock()-loop_start>duration+30: raise RuntimeError('Policy trial watchdog expired')
                            sleep(.02)
                    finally:
                        abort.set();worker.join();tail.close()
                        if trial is None:
                            try: trial=created.get_nowait();meta['trial']=trial.name
                            except queue.Empty: pass
                        meta['policy_thread_cpu_s']=time.thread_time()-cpu0
                        meta['policy_loop_elapsed_s']=clock()-loop_start
                        meta['inference']=decider.inference_statistics()
                        save()
                    if 'error' in result: raise RuntimeError(result['error'])
                    trial=result.get('folder')
                    if trial is None or json.loads((trial/'metadata.json').read_text())['outcome']!='completed':
                        raise RuntimeError('Traffic recorder failed; inspect trial')
                    meta['trial']=trial.name
                    sleep(2)
                finally:
                    abort.set()
                    if worker is not None and worker.ident is not None: worker.join()
                    meta['ping_exit']=stop(ping);meta['collector_exit']=stop(collector)
                    meta['counters_after']=interface_counts();save()
            if meta['collector_exit']!=0: raise RuntimeError('Collector shutdown failed')
            meta['selected_route_before_cleanup']=actor.route
            actor.close();meta['route_restoration']=dict(verified=True,failures=[])
        meta['outcome']='completed'
    except BaseException as e:
        meta.update(outcome='error',validity='invalid',error=str(e))
    finally:
        abort.set()
        if worker is not None and worker.ident is not None: worker.join()
        if actor is not None and actor.claimed:
            try: actor.close();meta['route_restoration']=dict(verified=True,failures=[])
            except Exception as e: meta['route_restoration']=dict(verified=False,failures=[str(e)]);meta['outcome']='error'
        meta['inference']=decider.inference_statistics();save()
    print('Policy experiment:',meta['outcome'],'| saved:',folder,flush=True)
    if meta['outcome']!='completed': raise RuntimeError(meta.get('error','Policy trial failed'))
    report=inspect_policy(folder)
    derived=BASE/'results/derived';derived.mkdir(exist_ok=True)
    with (derived/(folder.name+'.json')).open('x') as f: json.dump(report,f,indent=2)
    print('POLICY REVIEW:',json.dumps({k:report[k] for k in ['policy','scenario','sender_mbps',
        'receiver_mbps','udp_loss_percent','queue_drop_deltas','screen_failures','applied_actions',
        'in_traffic_switch_verified','restoration','route_restoration','rtt','overhead','model','inference']}),flush=True)
    return folder


def inspect_policy(folder):
    folder=Path(folder);m=json.loads((folder/'policy.json').read_text())
    trial=folder.parent/m['trial'];t=inspect_trial(trial,dynamic=True)
    native=json.loads((trial/'sender-native.json').read_text())
    start=native['start_monotonic_ns']/1e9;end=native['end_monotonic_ns']/1e9
    rows=[json.loads(s) for s in (folder/'samples.jsonl').read_text().splitlines()]
    qs={dev:queue_summary(rows,dev) for dev in QUEUES}
    stats=json.loads((folder/'samples.jsonl.stats.json').read_text())
    restoration=json.loads((folder/'restoration.json').read_text())
    failures=list(t['screen_failures'])
    if any(q['failed_queries'] or q['invalid_intervals'] for q in qs.values()): failures.append('collector_quality')
    if stats.get('schema_version')!=6 or stats.get('coverage')!='all': failures.append('collector_coverage')
    if restoration['failures'] or not m['route_restoration']['verified']: failures.append('restoration')
    if m['policy']=='ml':
        try:
            captured=json.loads((folder/'selected_tree.json').read_text())
            if (hashlib.sha256((folder/'selected_tree.json').read_bytes()).hexdigest()!=FROZEN_MODEL_SHA
                or m['model']['sha256']!=FROZEN_MODEL_SHA or m['model']['threshold']!=captured['alarm_threshold']
                or m['source_sha256']['build_trace_dataset.py']!=captured['feature_source_sha256']):
                raise ValueError('Frozen binding differs')
            for name in ['ml_trigger.py','tree_model.py','selected_tree.json']:
                if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=m['source_sha256'][name]:
                    raise ValueError('Captured inference source differs')
        except (OSError,ValueError,KeyError): failures.append('ml_model_binding')
        if not (m.get('inference') or {}).get('calls',0): failures.append('ml_inference_not_observed')
    applied=[a for a in m['actions'] if a.get('applied')]
    deltas={dev:{k:after[k]-m['counters_before'][dev][k] for k in after}
            for dev,after in m['counters_after'].items()}
    primary=min(deltas[dev]['tx_bytes'] for dev in ['s1-eth3','s2-eth2'])
    alternate=min(deltas[dev]['tx_bytes'] for dev in ['s1-eth4','s3-eth2'])
    switched=bool(applied and start<applied[0]['started']<applied[0]['verified_finished']<end
                  and primary>100000 and alternate>100000)
    # No switch can be a valid policy outcome (no trigger or admission denied).
    # Do not reject it merely for failing to improve QoS or fire a trigger.
    windows=[(native['start_wall_epoch_s'],native['end_wall_epoch_s'])]
    rtt={p:ping_statistics((folder/f'ping-{p}.txt').read_text()) for p in ['idle','loaded']}
    rtt['traffic_only']=ping_statistics((folder/'ping-loaded.txt').read_text(),windows)
    return dict(policy=m['policy'],scenario=m['scenario'],seed=m['seed'],outcome=m['outcome'],
        sender_mbps=t['sender']['bits_per_second']/1e6,receiver_mbps=t['receiver']['bits_per_second']/1e6,
        udp_loss_percent=t['receiver']['lost_percent'],queue_drop_deltas=t['queue_drop_deltas'],
        trial=t,collector=dict(qdiscs=qs,stats=stats),route_counter_deltas=deltas,
        screen_failures=failures,applied_actions=applied,
        denied_requests=[a for a in m['actions'] if not a.get('applied')],
        in_traffic_switch_verified=switched,rtt=rtt,restoration=restoration,
        route_restoration=m['route_restoration'],model=m.get('model'),inference=m.get('inference'),
        overhead=dict(collector_cpu_percent_one_core=sum(stats['cpu_percent_one_core'].values()),
            policy_thread_cpu_percent_one_core=100*m['policy_thread_cpu_s']/m['policy_loop_elapsed_s'],
            inference_cpu_percent_one_core=100*(m.get('inference') or {}).get('cpu',{}).get('total_ns',0)/1e9/m['policy_loop_elapsed_s']),
        interpretation='Pilot policy outcome; no gain claim before matched repeats and quality review')


if 'net' in globals():
    run(net,policy=globals().get('policy','reactive'),scenario=globals().get('scenario','ramp'),
        requested_bps=globals().get('requested_bps',11500000),duration=globals().get('duration',60),
        seed=globals().get('seed',1))
