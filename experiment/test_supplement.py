"""Supplement registration, failure preservation and variable-control restoration."""
import io,json,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import run_supplement_batch as batch

class RegistrationTests(unittest.TestCase):
    def test_controls_first_and_new_whole_run_seeds(self):
        plan=batch.plan()
        self.assertEqual(len(plan),18)
        self.assertEqual([(r['scenario'],r['seed']) for r in plan[:6]],[(s,n) for n in [41,42,43] for s in ['ramp','bursty']])
        for seed in [44,45,46]:
            rows=[r for r in plan[6:] if r['seed']==seed]
            self.assertEqual({r['policy'] for r in rows},set(batch.POLICIES))
            self.assertEqual(len(rows),4)
        self.assertTrue(all(r['scenario']=='bursty' for r in plan[6:]))

    def test_registration_checks_real_frozen_sources(self):
        p,m=batch.load_protocol(Path(__file__).parent)
        self.assertEqual(p['settings']['model_sha256'],m['settings']['model_sha256'])

    def test_failed_attempt_retained_and_not_silently_resumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'results/runs';root.mkdir(parents=True)
            for name in ['supplement_protocol.json','matched_protocol.json']:(base/name).write_text('{}')
            def failing(net,**kw):
                out=root/'failed-raw';out.mkdir();(out/'diagnostic.txt').write_text('retained')
                raise RuntimeError('injected sender failure')
            p=dict(additional_source_sha256={})
            with patch.object(batch,'load_protocol',return_value=(p,{})),redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'sender failure'):
                    batch.run({},base=base,control_runner=failing,control_inspector=lambda _:None,
                        policy_runner=lambda *a,**k:None,policy_inspector=lambda _:None)
            folder=root/json.loads((root/'supplement-registry-v1.json').read_text())['batch']
            state=json.loads((folder/'batch.json').read_text())
            self.assertEqual(state['outcome'],'failed');self.assertEqual(state['runs'],[])
            self.assertEqual(state['attempts'][0]['candidate_raw_folders'],['failed-raw'])
            self.assertTrue((root/'failed-raw/diagnostic.txt').exists())
            with self.assertRaisesRegex(ValueError,'requires evidence review'):batch.validate_resume(base,folder,state,p)

    def test_bursty_cannot_start_before_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(batch,'load_protocol',return_value=({},{})):
                with self.assertRaisesRegex(ValueError,'controls first'):
                    batch.run({},stage='bursty',base=tmp,control_runner=lambda:None,control_inspector=lambda:None,
                        policy_runner=lambda:None,policy_inspector=lambda:None)

    def test_adverse_control_outcome_is_not_filtered_for_benefit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'results/runs';folder=root/'control';trial=root/'trial'
            folder.mkdir(parents=True);trial.mkdir();(trial/'raw').write_text('source')
            item=dict(stage='controls',policy='fixed_alternate',scenario='bursty',seed=41,requested_bps=11500000,duration=60)
            (folder/'control.json').write_text(json.dumps(dict(trial='trial',route='alternate',scenario='bursty',seed=41,duration=60,requested_scale_bps=11500000)))
            report=dict(outcome='completed',control_screen_failures=[],trial=dict(sender=dict(bits_per_second=8e6),
                receiver=dict(bits_per_second=7e6,lost_percent=12.5)),source_audit=dict(discard_percent=.2))
            record=batch.control_record(base,folder,item,report)
            self.assertEqual(record['udp_loss_percent'],12.5)
            report['control_screen_failures']=['restoration']
            with self.assertRaisesRegex(ValueError,'quality'):batch.control_record(base,folder,item,report)

class ScheduleLifecycleTests(unittest.TestCase):
    def exercise(self,failed=False):
        import run_schedule_path_control as control
        from test_path_controls import fixture,Process
        from traffic_scenarios import continuous_schedule
        from run_matched_batch import COMMON_SOURCES,ML_SOURCES,EXTRA_SOURCES
        net,state,ovs=fixture();now=[10.];calls=[]
        def clock():return now[0]
        def sleep(s):now[0]+=s
        expected=continuous_schedule('bursty',11500000,60,42)
        def recorded(_net,base,rate,route,duration,**kw):
            self.assertEqual((rate,route,duration),(11500000,'alternate',60))
            self.assertEqual(kw['plan'],expected);self.assertEqual(kw['seed'],42)
            out=Path(base)/'results/runs/fixture-trial';out.mkdir()
            self.assertEqual(kw['route_verifier'](_net,route,out)['selected_route'],'alternate')
            (out/'metadata.json').write_text(json.dumps(dict(outcome='error' if failed else 'completed',
                traffic_plan=expected,seed=42,scenario='bursty',trial_context=kw['trial_context'])))
            (out/'sender-native.json').write_text(json.dumps(dict(start_wall_epoch_s=100,end_wall_epoch_s=160)))
            return out
        def counts():
            value=1000000 if calls else 0;calls.append(value)
            return {d:dict(tx_bytes=value if d in ['s1-eth4','s3-eth2'] else 0,tx_packets=value//1200,rx_bytes=0,rx_packets=0)
                for d in ['s1-eth3','s1-eth4','s2-eth2','s3-eth2','s4-eth3','s4-eth4']}
        def collector(command,**kw):
            self.assertIn('all',command);self.assertIn('.25',command)
            out=Path(command[2]);rates={'s1-eth3':100e6,'s2-eth2':10e6,'s1-eth4':20e6,'s3-eth2':20e6}
            rows=[dict(schema_version=6,coverage='all',utc='fixture',requested_interval=.25,qdiscs={d:dict(interface=d,capacity_bps=r,
                tc_start=i*.25,tc_end=i*.25+.004,tc_exit=0,root_qdisc=dict(bytes=10000*i,drops=0,backlog=0,qlen=0))
                for d,r in rates.items()}) for i in range(4)]
            out.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            Path(str(out)+'.stats.json').write_text(json.dumps(dict(schema_version=6,coverage='all')))
            return Process()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);names=list(dict.fromkeys(COMMON_SOURCES+ML_SOURCES+EXTRA_SOURCES+[
                'run_path_control.py','run_schedule_path_control.py','matched_protocol.json']))
            for n in names:(base/n).write_text('# fixture')
            pinned={n:batch.sha(base/n) for n in COMMON_SOURCES+ML_SOURCES+EXTRA_SOURCES}
            with patch.object(control,'BASE',base),patch.object(control.os,'cpu_count',lambda:1),\
                 patch.object(control,'load_protocol',return_value=dict(source_sha256=pinned)),\
                 patch.object(control.recorder,'run',recorded),patch.object(control,'interface_counts',counts),\
                 patch('subprocess.Popen',collector),patch.object(control,'inspect_trial',return_value=dict(screen_failures=[])),\
                 patch.object(control,'source_integrity_audit',return_value=dict(discard_percent=0)),redirect_stdout(io.StringIO()):
                if failed:
                    with self.assertRaisesRegex(RuntimeError,'Control traffic failed'):
                        control.run(net,scenario='bursty',seed=42,clock=clock,sleep=sleep)
                else:
                    out=control.run(net,scenario='bursty',seed=42,clock=clock,sleep=sleep)
                    report=control.inspect_control(out)
                    self.assertEqual(report['control_screen_failures'],[])
                    self.assertEqual(report['scenario'],'bursty')
            self.assertFalse(ovs.overlay)
            self.assertEqual(state['source_limit'],50)
            self.assertTrue(all(v==1600 for v in state['classes'].values()))

    def test_variable_schedule_all_queue_coverage_and_restore(self):self.exercise()
    def test_source_failure_restores_rules_and_both_profiles(self):self.exercise(True)

if __name__=='__main__':unittest.main()
