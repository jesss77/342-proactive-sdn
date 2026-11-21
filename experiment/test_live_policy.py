import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from live_policy import LiveDecider,JSONLTailer,load_bounds
from run_continuous_trial import wait_for_client
from inspect_experiment import inspect_trial
from dual_path_profile import LINKS


BOUNDS=dict(id='dual-profile-operating-bounds-v1',profile='dual-forward-cburst16k-source250-v1',
    admission_budget_bps=15900000,headroom_fraction=.8,collector_interval_s=.25,
    max_read_age_s=.5,max_tested_payload_bps=16000000)


def frames(values,upstream_bps=9000000,background_bps=0):
    counters={k:0 for k in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']};out=[]
    for i,u in enumerate(values):
        qs={}
        rates={'s1-eth3':upstream_bps,'s2-eth2':u*1e7,'s1-eth4':background_bps,'s3-eth2':background_bps}
        for dev,rate in rates.items():
            if i: counters[dev]+=round(rate*.25/8)
            cap=100000000 if dev=='s1-eth3' else 10000000 if dev=='s2-eth2' else 20000000
            qs[dev]=dict(capacity_bps=cap,tc_start=i*.25,tc_end=i*.25+.004,tc_exit=0,
                root_qdisc=dict(root=True,bytes=counters[dev],drops=0,backlog=0,qlen=0))
        out.append(dict(schema_version=6,coverage='all',route='primary',sample=i,utc='fixture',
                        requested_interval=.25,monotonic_end=i*.25+.006,qdiscs=qs))
    return out


class LiveTests(unittest.TestCase):
    def test_fixed_never_requests_and_reactive_requests_after_history(self):
        rows=frames([.2]*12+[.95]*12)
        for policy in ['fixed','reactive']:
            d=LiveDecider(policy,BOUNDS);reasons=[]
            for r in rows:
                decision=d.observe(r,0,r['monotonic_end']+.01)
                if decision['reason']: reasons.append(decision)
            self.assertEqual(bool(reasons),policy=='reactive')
            if reasons:
                self.assertGreaterEqual(reasons[0]['feature_available'],4)
                self.assertIsNone(d.admission(reasons[0],True).rejection(reasons[0]['decision_at']))

    def test_early_warning_precedes_reactive_on_smooth_ramp(self):
        rows=frames([.2+i*.025 for i in range(40)]);times={}
        for policy in ['early_warning','reactive']:
            d=LiveDecider(policy,BOUNDS)
            for r in rows:
                result=d.observe(r,0,r['monotonic_end']+.01)
                if result['reason']:
                    times[policy]=result['feature_available'];break
        self.assertLess(times['early_warning'],times['reactive'])

    def test_stale_and_missing_standby_observations_do_not_act(self):
        rows=frames([.95]*20);d=LiveDecider('reactive',BOUNDS)
        for r in rows[:12]: result=d.observe(r,0,r['monotonic_end']+.01)
        self.assertEqual(d.observe(rows[12],0,rows[12]['monotonic_end']+.6)['status'],'invalid_or_stale')
        rows[13]['qdiscs']['s1-eth4']=dict(tc_exit=1,tc_error='injected')
        result=d.observe(rows[13],0,rows[13]['monotonic_end']+.01)
        self.assertIsNone(result['reason'])
        self.assertEqual(result['status'],'invalid_or_stale')

    def test_background_and_headroom_can_deny_a_real_trigger(self):
        rows=frames([.95]*24,background_bps=6000000);d=LiveDecider('reactive',BOUNDS)
        for r in rows:
            result=d.observe(r,0,r['monotonic_end']+.01)
            if result['reason']:
                self.assertEqual(d.admission(result,True).rejection(result['decision_at']),
                                 'insufficient_admission_headroom')
                self.assertFalse(d.trigger.fired);return
        self.fail('Expected a reactive trigger')

    def test_applied_action_disables_additional_triggers(self):
        d=LiveDecider('early_warning',BOUNDS);rows=frames([.2+i*.025 for i in range(40)])
        fired=False
        for r in rows:
            result=d.observe(r,0,r['monotonic_end']+.01)
            if fired: self.assertIsNone(result['reason'])
            elif result['reason']: d.mark_applied();fired=True
        self.assertTrue(fired)

    def test_partial_json_line_waits_until_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'stream.jsonl';tail=JSONLTailer(p)
            self.assertEqual(tail.read(),[])
            p.write_text('{"sample":')
            self.assertEqual(tail.read(),[])
            with p.open('a') as f: f.write('1}\n{"sample":2}\n')
            self.assertEqual(tail.read(),[{'sample':1},{'sample':2}]);tail.close()

    def test_bounds_are_explicit_and_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bounds.json';p.write_text(json.dumps(BOUNDS))
            self.assertEqual(load_bounds(p)['admission_budget_bps'],15900000)
            p.write_text(json.dumps(dict(BOUNDS,admission_budget_bps=20000000)))
            with self.assertRaises(ValueError): load_bounds(p)


class RecorderCancellationTests(unittest.TestCase):
    def test_cancelled_client_does_not_wait(self):
        abort=threading.Event();abort.set()
        class Client:
            def wait(self,**kwargs): raise AssertionError('Must not wait')
        with self.assertRaisesRegex(RuntimeError,'cancelled'): wait_for_client(Client(),5,abort)

    def test_cancellation_is_checked_between_short_waits(self):
        abort=threading.Event();calls=[]
        class Client:
            def wait(self,timeout):
                calls.append(timeout);abort.set();raise subprocess.TimeoutExpired('fixture',timeout)
        with self.assertRaisesRegex(RuntimeError,'cancelled'): wait_for_client(Client(),5,abort)
        self.assertLessEqual(calls[0],.2)


class DynamicScreenTests(unittest.TestCase):
    def fixture(self,tmp,drops=None):
        from test_experiment import ExperimentTests
        path=ExperimentTests().trial_fixture(tmp,'primary',12000000,drops or {})
        m=json.loads((path/'metadata.json').read_text())
        m.update(capture_links=LINKS,trial_context=dict(dynamic_routing=True))
        (path/'metadata.json').write_text(json.dumps(m))
        for dev in ['s1-eth4','s3-eth2']:
            for phase,value in [('before',0),('after',(drops or {}).get(dev,0))]:
                (path/f'{phase}-{dev}-queue.txt').write_text(f'dropped {value}')
        return path

    def test_prevented_overload_is_not_a_screen_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(tmp)
            self.assertEqual(inspect_trial(p,dynamic=True)['screen_failures'],[])
            with self.assertRaisesRegex(ValueError,'policy inspector'): inspect_trial(p)

    def test_alternate_loss_is_counted_but_access_loss_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(tmp,{'s1-eth4':1})
            self.assertNotIn('access_link_drop',inspect_trial(p,dynamic=True)['screen_failures'])
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(tmp,{'h1-eth0':1})
            self.assertIn('access_link_drop',inspect_trial(p,dynamic=True)['screen_failures'])

    def test_no_switch_is_not_automatically_a_failure(self):
        from run_policy_experiment import inspect_policy
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trial=root/'trial';trial.mkdir();self.fixture(trial)
            (trial/'sender-native.json').write_text(json.dumps(dict(start_monotonic_ns=0,
                end_monotonic_ns=20000000000,start_wall_epoch_s=100,end_wall_epoch_s=120)))
            folder=root/'policy';folder.mkdir()
            counters={dev:dict(tx_bytes=1000000 if dev in ['s1-eth3','s2-eth2'] else 0)
                      for dev in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']}
            meta=dict(policy='reactive',scenario='ramp',seed=1,outcome='completed',trial='trial',
                actions=[],counters_before={k:dict(tx_bytes=0) for k in counters},counters_after=counters,
                route_restoration=dict(verified=True,failures=[]),policy_thread_cpu_s=.01,policy_loop_elapsed_s=20)
            (folder/'policy.json').write_text(json.dumps(meta))
            (folder/'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in frames([.2]*10)))
            (folder/'samples.jsonl.stats.json').write_text(json.dumps(dict(schema_version=6,coverage='all',
                cpu_percent_one_core=dict(self_s=1,children_s=1))))
            (folder/'restoration.json').write_text(json.dumps(dict(failures=[])))
            for phase in ['idle','loaded']:
                (folder/f'ping-{phase}.txt').write_text('[101] reply time=10 ms\n0% packet loss')
            report=inspect_policy(folder)
            self.assertEqual(report['screen_failures'],[])
            self.assertFalse(report['in_traffic_switch_verified'])
            self.assertEqual(report['applied_actions'],[])


class RuntimeRefreshTests(unittest.TestCase):
    def test_runner_refreshes_stale_inspector_and_feature_modules(self):
        import importlib
        import inspect
        import inspect_experiment as inspector
        import build_trace_dataset as dataset
        import live_policy as live
        import run_policy_experiment as policy
        with patch.object(inspector,'inspect_trial',lambda path:None),\
             patch.object(dataset,'intervals',lambda *args:[]),\
             patch.object(live,'LiveDecider',None):
            importlib.reload(policy)
            self.assertIn('dynamic',inspect.signature(policy.inspect_trial).parameters)
            self.assertIsNotNone(policy.LiveDecider)
            self.assertIs(live.intervals,dataset.intervals)
            self.assertTrue(live.intervals(frames([.2,.3]),0,10))


class WorkerFailureTests(unittest.TestCase):
    def test_worker_error_cancels_and_restores_without_losing_reference(self):
        self.check_worker_cleanup(watchdog=False)

    def test_watchdog_cancels_worker_and_restores_without_losing_reference(self):
        self.check_worker_cleanup(watchdog=True)

    def check_worker_cleanup(self,watchdog):
        import run_policy_experiment as policy
        from test_path_controls import fixture,Process
        net,state,ovs=fixture();now=[10.]
        release=threading.Event();workers=[];aborts=[]
        real_thread=threading.Thread
        class RecordedThread(real_thread):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);workers.append(self)
        def sleep(seconds):
            now[0]+=seconds
            if seconds==.02:
                if watchdog:
                    # Expire the application watchdog while the worker waits
                    # for cancellation, without depending on OS scheduling.
                    now[0]+=40
                else:
                    # Let the real worker finish before advancing simulated
                    # time again. A tight fake clock can starve it on one CPU.
                    release.set();workers[0].join(timeout=5)
                    self.assertFalse(workers[0].is_alive(),'Worker did not finish')
        def counts(): return {dev:dict(tx_bytes=0) for dev in ['s1-eth3','s2-eth2','s1-eth4','s3-eth2']}
        def failed_record(_net,base,*args,**kwargs):
            p=Path(base)/'results/runs/failed-trial';p.mkdir()
            kwargs['on_created'](p)
            aborts.append(kwargs['abort_event'])
            gate=kwargs['abort_event'] if watchdog else release
            if not gate.wait(timeout=5): raise RuntimeError('Fixture synchronization timed out')
            raise RuntimeError('injected worker failure')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in ['run_policy_experiment.py','live_policy.py','routing_policy.py','routing_action.py',
                'dual_path_profile.py','collect_path.py','run_continuous_trial.py','continuous_udp.py',
                'traffic_scenarios.py','build_trace_dataset.py','inspect_experiment.py','topology.py',
                'diamond_controller.py','experiment_config.py']:
                (base/name).write_text('# fixture\n')
            (base/'operating_bounds.json').write_text(json.dumps(BOUNDS))
            with patch.object(policy,'BASE',base),patch.object(policy.os,'cpu_count',lambda:1),\
                 patch.object(policy,'interface_counts',counts),patch.object(policy.recorder,'run',failed_record),\
                 patch.object(policy.threading,'Thread',RecordedThread),\
                 patch('subprocess.Popen',lambda *a,**k:Process()),\
                 patch('builtins.print'),self.assertRaisesRegex(RuntimeError,
                     'watchdog expired' if watchdog else 'worker failure'):
                policy.run(net,duration=5,clock=lambda:now[0],sleep=sleep)
            meta=json.loads(next(base.glob('results/runs/*/policy.json')).read_text())
            self.assertEqual(meta['outcome'],'error');self.assertEqual(meta['trial'],'failed-trial')
            self.assertTrue(meta['route_restoration']['verified'])
            self.assertFalse(ovs.overlay)
            self.assertTrue(all(v==1600 for v in state['classes'].values()))
            self.assertEqual(state['source_limit'],50)
            self.assertTrue(aborts[0].is_set())
            self.assertTrue(all(not worker.is_alive() for worker in workers))


if __name__=='__main__': unittest.main()
