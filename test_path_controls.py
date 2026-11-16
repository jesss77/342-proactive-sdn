from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dual_path_profile import dual_profile,LINKS,QUEUES
from test_routing import FakeOVS


class Node:
    def __init__(self,name,state,ovs): self.name=name;self.state=state;self.ovs=ovs
    def IP(self): return '10.0.0.'+self.name[1:]
    def pexec(self,args):
        if args[0]=='ovs-ofctl': return self.ovs(self.name,args)
        if args[0]=='ping': return '10 packets transmitted, 10 received, 0% packet loss\n','',0
        if args[0]=='cat': return ('1\n' if args[-1].endswith('/carrier') else '0\n'),' ',0
        dev=args[args.index('dev')+1]
        rate=next(r for _,d,r in LINKS if d==dev)
        if args[1:3]==['-s','class']:
            value=self.state['classes'][dev]
            burst='1600b' if value==1600 else '16Kb'
            return f'class htb 5:1 rate {rate}Mbit ceil {rate}Mbit burst 15Kb cburst {burst}','',0
        if args[1:3]==['-s','qdisc']:
            limit=self.state['source_limit'] if dev=='h1-eth0' else 50
            return f'qdisc netem 10: parent 5:1 limit {limit} delay 1ms','',0
        if args[1]=='class':
            self.state['classes'][dev]=int(args[-1])
            if dev==self.state.get('fail_once') and args[-1]=='16384':
                self.state['fail_once']=None
                return '','injected uncertain apply failure',1
        else: self.state['source_limit']=int(args[-1])
        return '','',0
    def popen(self,args,**kwargs):
        kwargs['stdout'].write('[101.0] reply time=10.0 ms\n5 packets transmitted, 5 received, 0% packet loss\n')
        kwargs['stdout'].flush()
        return Process()


class Process:
    returncode=None
    def poll(self): return self.returncode
    def send_signal(self,sig): self.returncode=0
    def wait(self,**kwargs): return self.returncode
    def kill(self): self.returncode=-9


def fixture():
    state=dict(classes={d:1600 for _,d,_ in LINKS},source_limit=50)
    ovs=FakeOVS()
    net={n:Node(n,state,ovs) for n in ['h1','h2','s1','s2','s3','s4']}
    return net,state,ovs


class DualProfileTests(unittest.TestCase):
    def test_both_paths_and_source_applied_and_restored(self):
        net,state,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            with dual_profile(net,tmp) as profile:
                self.assertEqual(profile['id'],'dual-forward-cburst16k-source250-v1')
                self.assertTrue(all(x==16384 for x in state['classes'].values()))
                self.assertEqual(state['source_limit'],250)
            self.assertTrue(all(x==1600 for x in state['classes'].values()))
            self.assertEqual(state['source_limit'],50)
            self.assertEqual(json.loads(Path(tmp,'restoration.json').read_text())['failures'],[])

    def test_uncertain_partial_apply_also_restored(self):
        net,state,_=fixture();state['fail_once']='s1-eth4'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,'uncertain apply'):
                with dual_profile(net,tmp): self.fail('Cannot enter failed profile')
            self.assertTrue(all(x==1600 for x in state['classes'].values()))
            self.assertEqual(state['source_limit'],50)

    def test_body_failure_restores_all_settings(self):
        net,state,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,'trial failed'):
                with dual_profile(net,tmp): raise RuntimeError('trial failed')
            self.assertTrue(all(x==1600 for x in state['classes'].values()))
            self.assertEqual(state['source_limit'],50)


class PathControlTests(unittest.TestCase):
    def test_custom_route_proof_cannot_silently_bypass_passive_mode(self):
        import run_continuous_trial as recorder
        with self.assertRaisesRegex(ValueError,'explicit owned-hostpair context'):
            recorder.run({},'.',route_verifier=lambda *args: {})

    def exercise(self,failed=False):
        import run_path_control as control
        net,state,ovs=fixture();now=[10.]
        def clock(): return now[0]
        def sleep(seconds): now[0]+=seconds
        calls=[]
        def recorded(_net,base,requested,route,duration,**kwargs):
            out=Path(base)/'results/runs/fixture-trial';out.mkdir()
            proof=kwargs['route_verifier'](_net,route,out)
            self.assertEqual(proof['mode'],'owned_hostpair')
            self.assertEqual(proof['selected_route'],'alternate')
            self.assertEqual(kwargs['trial_context']['kind'],'fixed_path_control')
            (out/'metadata.json').write_text(json.dumps(dict(outcome='error' if failed else 'completed')))
            (out/'sender-native.json').write_text(json.dumps(dict(start_wall_epoch_s=100,end_wall_epoch_s=120)))
            return out
        def counts():
            value=0 if not calls else 1000000;calls.append(value)
            return {d:dict(tx_bytes=value if d in ['s1-eth4','s3-eth2'] else 0,
                           tx_packets=value//1200,rx_bytes=0,rx_packets=0) for d in
                    ['s1-eth3','s1-eth4','s2-eth2','s3-eth2','s4-eth3','s4-eth4']}
        def collector(command,**kwargs):
            self.assertIn('--coverage',command);self.assertIn('all',command)
            output=Path(command[2]);rows=[]
            rates={'s1-eth3':100000000,'s2-eth2':10000000,'s1-eth4':20000000,'s3-eth2':20000000}
            for i in range(4):
                qs={d:dict(interface=d,capacity_bps=rate,tc_start=i*.25,tc_end=i*.25+.004,
                    tc_exit=0,root_qdisc=dict(bytes=10000*i,drops=0,backlog=0,qlen=0)) for d,rate in rates.items()}
                rows.append(dict(schema_version=6,coverage='all',utc='fixture',qdiscs=qs,requested_interval=.25))
            output.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            Path(str(output)+'.stats.json').write_text(json.dumps(dict(schema_version=6,coverage='all')))
            return Process()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in ['run_path_control.py','dual_path_profile.py','routing_action.py',
                         'run_continuous_trial.py','collect_path.py','continuous_udp.py','experiment_config.py',
                         'inspect_experiment.py','topology.py','diamond_controller.py']:
                (base/name).write_text('# fixture\n')
            with patch.object(control,'BASE',base),patch.object(control.os,'cpu_count',lambda:1),\
                 patch.object(control.recorder,'run',recorded),patch.object(control,'interface_counts',counts),\
                 patch('subprocess.Popen',collector),patch.object(control,'inspect_trial',return_value=dict(screen_failures=[])),\
                 redirect_stdout(io.StringIO()):
                if failed:
                    with self.assertRaisesRegex(RuntimeError,'Control traffic failed'):
                        control.run(net,clock=clock,sleep=sleep)
                else:
                    out=control.run(net,clock=clock,sleep=sleep)
                    report=control.inspect_control(out)
                    self.assertEqual(report['control_screen_failures'],[])
                    self.assertEqual(set(report['collector']['qdiscs']),set(QUEUES))
            self.assertFalse(ovs.overlay)
            self.assertTrue(all(x==1600 for x in state['classes'].values()))
            self.assertEqual(state['source_limit'],50)

    def test_control_full_lifecycle_and_coverage(self): self.exercise()
    def test_control_traffic_failure_restores_paths_and_profile(self): self.exercise(True)


if __name__=='__main__': unittest.main()
