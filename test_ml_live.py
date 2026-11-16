import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from build_trace_dataset import intervals,features_at
from live_policy import LiveDecider
from ml_trigger import load_runtime_model,ModelTrigger
from test_live_policy import frames,BOUNDS
import test_live_policy as live_test_fixtures
from test_path_controls import fixture,Process

BASE=Path(__file__).resolve().parent


class MLLiveTests(unittest.TestCase):
    def test_live_and_offline_features_and_predictions_match(self):
        model,_=load_runtime_model(BASE)
        raw=frames([.2+i*.025 for i in range(40)])
        offline=intervals(raw,0,100);history=[];expected={}
        for r in offline:
            history.append(r);expected[r['available']]=features_at(history)
        live=LiveDecider('ml',BOUNDS,model=model);seen=0
        for row in raw:
            result=live.observe(row,0,row['monotonic_end']+.01)
            key=max(row['qdiscs'][dev]['tc_end'] for dev in ['s1-eth3','s2-eth2'])
            if expected.get(key) is not None:
                self.assertEqual(result['features'],expected[key])
                self.assertEqual(result['model_probability'],model.probability(expected[key]));seen+=1
        self.assertGreater(seen,20);self.assertEqual(live.inference_statistics()['calls'],seen)

    def test_stale_and_missing_standby_data_never_infer(self):
        model,_=load_runtime_model(BASE);live=LiveDecider('ml',BOUNDS,model=model)
        raw=frames([.95]*24)
        for row in raw[:12]: live.observe(row,0,row['monotonic_end']+.01)
        calls=live.inference_statistics()['calls']
        result=live.observe(raw[12],0,raw[12]['monotonic_end']+.6)
        self.assertEqual(result['status'],'invalid_or_stale')
        raw[13]['qdiscs']['s1-eth4']=dict(tc_exit=1,tc_error='injected')
        result=live.observe(raw[13],0,raw[13]['monotonic_end']+.01)
        self.assertIsNone(result['reason']);self.assertEqual(live.inference_statistics()['calls'],calls)

    def test_success_stops_additional_inference(self):
        model,_=load_runtime_model(BASE);trigger=ModelTrigger(model)
        f={name:0. for name in model.model['features']};f['utilization']=.8
        trigger.update(1,f);trigger.mark_applied()
        self.assertIsNone(trigger.update(1.25,f));self.assertIsNone(trigger.last_inference)
        self.assertEqual(trigger.statistics()['calls'],1)

    def test_model_or_feature_version_change_refuses_preflight(self):
        for change in ['model','features']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp)
                for name in ['selected_tree.json','dataset_protocol.json','build_trace_dataset.py']:
                    (base/name).write_bytes((BASE/name).read_bytes())
                name='selected_tree.json' if change=='model' else 'build_trace_dataset.py'
                with (base/name).open('a') as f: f.write('\n')
                with self.assertRaises(ValueError): load_runtime_model(base)

    def test_post_compute_freshness_rejection_never_calls_action(self):
        from run_policy_experiment import request_from_decision
        class Actor:
            def request(self,*args): raise AssertionError('Must not change rules')
        r=request_from_decision(Actor(),None,dict(admission_observed_at=1),True,.5,clock=lambda:1.6)
        self.assertFalse(r['applied']);self.assertEqual(r['rejection'],'stale_policy_observation')

    def test_ml_inspector_checks_model_binding_and_inference(self):
        from run_policy_experiment import inspect_policy
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trial=root/'trial';trial.mkdir();live_test_fixtures.DynamicScreenTests().fixture(trial)
            (trial/'sender-native.json').write_text(json.dumps(dict(start_monotonic_ns=0,end_monotonic_ns=20000000000,
                start_wall_epoch_s=100,end_wall_epoch_s=120)))
            folder=root/'policy';folder.mkdir();model,context=load_runtime_model(BASE)
            sources={}
            for name in ['ml_trigger.py','tree_model.py','selected_tree.json','build_trace_dataset.py']:
                (folder/name).write_bytes((BASE/name).read_bytes());sources[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
            counters={dev:dict(tx_bytes=1000000 if dev in ['s1-eth3','s2-eth2'] else 0)
                for dev in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']}
            meta=dict(policy='ml',scenario='ramp',seed=1,outcome='completed',trial='trial',actions=[],
                counters_before={k:dict(tx_bytes=0) for k in counters},counters_after=counters,
                route_restoration=dict(verified=True,failures=[]),policy_thread_cpu_s=.01,policy_loop_elapsed_s=20,
                model=context,source_sha256=sources,inference=dict(calls=1,cpu=dict(total_ns=100)))
            (folder/'policy.json').write_text(json.dumps(meta))
            (folder/'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in frames([.2]*10)))
            (folder/'samples.jsonl.stats.json').write_text(json.dumps(dict(schema_version=6,coverage='all',cpu_percent_one_core=dict(self_s=1,children_s=1))))
            (folder/'restoration.json').write_text(json.dumps(dict(failures=[])))
            for phase in ['idle','loaded']: (folder/f'ping-{phase}.txt').write_text('[101] reply time=10 ms\n0% packet loss')
            self.assertEqual(inspect_policy(folder)['screen_failures'],[])
            meta['inference']=None;(folder/'policy.json').write_text(json.dumps(meta))
            self.assertIn('ml_inference_not_observed',inspect_policy(folder)['screen_failures'])
            with (folder/'tree_model.py').open('a') as f: f.write('# changed')
            self.assertIn('ml_model_binding',inspect_policy(folder)['screen_failures'])

    def test_shared_ml_loop_restores_after_post_action_worker_failure(self):
        import run_policy_experiment as policy
        net,state,ovs=fixture();now=[10.];ready=threading.Event();release=threading.Event();workers=[]
        real_thread=threading.Thread
        class RecordedThread(real_thread):
            def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs);workers.append(self)
        class Decider:
            def __init__(self,p,bounds,model):
                self.assert_model=model;self.fired=False
            def observe(self,row,start,t):
                return dict(status='ready',reason=None if self.fired else 'frozen_tree_probability',
                    admission_observed_at=t,features={},sample=row['sample'],model_probability=.9)
            def admission(self,d,links):
                from routing_action import Admission
                return Admission('alternate',d['admission_observed_at'],1000000,0,15900000,links,'fixture')
            def mark_applied(self): self.fired=True;release.set()
            def inference_statistics(self): return dict(calls=1,cpu=dict(total_ns=100))
        def sleep(seconds):
            now[0]+=seconds
            if seconds==.02:
                self.assertTrue(ready.wait(timeout=5))
                if release.is_set(): workers[0].join(timeout=5);self.assertFalse(workers[0].is_alive())
        def counts(): return {dev:dict(tx_bytes=0) for dev in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']}
        def collector(args,**kwargs): Path(args[2]).write_text('{"sample":0}\n');return Process()
        def recorded(_net,base,*args,**kwargs):
            p=Path(base)/'results/runs/failed-ml-trial';p.mkdir()
            (p/'sender-samples.jsonl').write_text('{"monotonic_ns":0,"elapsed_s":0}\n')
            kwargs['on_created'](p);ready.set()
            if not release.wait(timeout=5): raise RuntimeError('fixture action timeout')
            raise RuntimeError('injected after inference')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in ['run_policy_experiment.py','live_policy.py','routing_policy.py','routing_action.py','operating_bounds.json',
                'dual_path_profile.py','collect_path.py','run_continuous_trial.py','continuous_udp.py','traffic_scenarios.py',
                'build_trace_dataset.py','inspect_experiment.py','topology.py','diamond_controller.py','experiment_config.py',
                'ml_trigger.py','tree_model.py','selected_tree.json','dataset_protocol.json']:
                (base/name).write_bytes((BASE/name).read_bytes())
            with patch.object(policy,'BASE',base),patch.object(policy.os,'cpu_count',lambda:1),\
                 patch.object(policy,'LiveDecider',Decider),patch.object(policy,'interface_counts',counts),\
                 patch.object(policy.recorder,'run',recorded),patch.object(policy.threading,'Thread',RecordedThread),\
                 patch('subprocess.Popen',collector),patch('builtins.print'),\
                 self.assertRaisesRegex(RuntimeError,'injected after inference'):
                policy.run(net,policy='ml',duration=5,clock=lambda:now[0],sleep=sleep)
            meta=json.loads(next(base.glob('results/runs/*/policy.json')).read_text())
            self.assertEqual(meta['outcome'],'error');self.assertTrue(meta['actions'][0]['applied'])
            self.assertTrue(meta['route_restoration']['verified']);self.assertFalse(ovs.overlay)
            self.assertTrue(all(v==1600 for v in state['classes'].values()));self.assertEqual(state['source_limit'],50)


if __name__=='__main__': unittest.main()
