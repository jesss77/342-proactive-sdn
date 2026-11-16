import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from routing_action import (Admission, BASE_PORTS, COOKIE, COOKIE_FILTER,
                            RoutingAction, ofctl, verify_overlay)
from routing_policy import Trigger


class FakeOVS:
    def __init__(self):
        self.overlay={};self.commands=[];self.fail_add_once=None;self.fail_delete=None
        self.extra={};self.alternate_baseline=False

    def text(self,switch):
        lines=[]
        for host,port in BASE_PORTS[switch].items():
            if self.alternate_baseline and switch in ['s1','s4'] and port==3: port=4
            lines.append(f'cookie=0x0, duration=12s, table=0, n_packets=0, n_bytes=0, '
                f'priority=100,dl_dst=00:00:00:00:00:{host:02x} actions=output:{port}')
        if switch in self.overlay:
            flow=self.overlay[switch]
            fields,actions=flow.split(',actions=')
            lines.append(fields.replace('table=0,','table=0,n_packets=5,')+' actions='+actions)
        lines.extend(self.extra.get(switch,[]))
        return '\n'.join(lines)

    def __call__(self,switch,args):
        self.commands.append((switch,args))
        if 'dump-flows' in args: return self.text(switch),'',0
        if 'add-flow' in args:
            if self.fail_add_once==switch:
                self.fail_add_once=None
                return '', 'injected add failure',1
            self.overlay[switch]=args[-1]
        elif 'del-flows' in args:
            assert args[-1]==COOKIE_FILTER
            if self.fail_delete==switch: return '', 'injected delete failure',1
            self.overlay.pop(switch,None)
        else: raise AssertionError(args)
        return '','',0

    def mutations(self):
        return [(s,a) for s,a in self.commands if 'add-flow' in a or 'del-flows' in a]


def certificate(**changes):
    args=dict(route='alternate',observed_at=10.,selected_demand_bps=100000.,
              background_bps=0.,admission_budget_bps=3000000.,links_up=True,evidence='smoke-only')
    args.update(changes)
    return Admission(**args)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.log=Path(self.tmp.name)/'actions.jsonl';self.fake=FakeOVS()

    def actor(self,**kwargs):
        return RoutingAction(self.fake,self.log,clock=lambda:10.,**kwargs)

    def test_selected_pair_overlay_and_cookie_only_cleanup(self):
        self.fake.extra['s1']=['cookie=0x99,table=0,priority=50,ip actions=drop']
        a=self.actor();result=a.request(certificate(),'smoke')
        self.assertTrue(result['applied'])
        self.assertEqual(set(self.fake.overlay),{'s1','s4'})
        self.assertIn('nw_src=10.0.0.1,nw_dst=10.0.0.2',self.fake.overlay['s1'])
        self.assertIn('nw_src=10.0.0.2,nw_dst=10.0.0.1',self.fake.overlay['s4'])
        a.close()
        self.assertFalse(self.fake.overlay)
        self.assertEqual(self.fake.extra['s1'],['cookie=0x99,table=0,priority=50,ip actions=drop'])
        for _,args in self.fake.mutations():
            self.assertIn('OpenFlow13',args);self.assertNotIn('--bundle',args)
            if 'del-flows' in args: self.assertEqual(args[-1],COOKIE_FILTER)

    def test_second_edge_failure_rolls_back_both(self):
        a=self.actor();self.fake.fail_add_once='s4'
        with self.assertRaisesRegex(RuntimeError,'injected add failure'):
            a.request(certificate(),'smoke')
        self.assertEqual(a.route,'primary');self.assertFalse(self.fake.overlay)
        events=[json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertTrue(any(e['event']=='apply_failed' and e['rollback_error'] is None for e in events))
        a.close()

    def test_cleanup_attempts_both_edges_after_failure(self):
        a=self.actor();a.request(certificate(),'smoke');self.fake.fail_delete='s1'
        with self.assertRaisesRegex(RuntimeError,'injected delete failure'): a.close()
        self.assertEqual(a.route,'unknown');self.assertIn('s1',self.fake.overlay)
        self.assertNotIn('s4',self.fake.overlay)
        self.fake.fail_delete=None;a.close();self.assertFalse(self.fake.overlay)

    def test_admission_denials_never_change_rules(self):
        a=self.actor()
        for c in [certificate(observed_at=7),certificate(observed_at=11),
                  certificate(links_up=False),certificate(selected_demand_bps=2500000),
                  certificate(background_bps=-1),certificate(selected_demand_bps=float('nan')),
                  certificate(evidence='')]:
            self.assertFalse(a.request(c,'smoke')['applied'])
        self.assertFalse(self.fake.mutations())

    def test_existing_cookie_is_not_taken_over_or_deleted(self):
        self.fake.overlay['s1']=f'cookie=0x{COOKIE:x},table=0,priority=200,ip,nw_src=10.0.0.1,nw_dst=10.0.0.2,actions=output:4'
        with self.assertRaisesRegex(RuntimeError,'Reserved cookie'): self.actor()
        self.assertFalse(self.fake.mutations())

    def test_foreign_higher_rule_and_wrong_baseline_rejected(self):
        self.fake.extra['s1']=['cookie=0x99,table=0,priority=300,ip actions=drop']
        with self.assertRaisesRegex(RuntimeError,'higher-priority'): self.actor()
        self.fake.extra.clear();self.fake.alternate_baseline=True
        with self.assertRaisesRegex(RuntimeError,'baseline/transit'): self.actor()
        self.assertFalse(self.fake.mutations())

    def test_wrong_selected_match_is_not_accepted(self):
        bad=f'cookie=0x{COOKIE:x},table=0,priority=200,ip,nw_src=10.0.0.3,nw_dst=10.0.0.4 actions=output:4'
        with self.assertRaisesRegex(RuntimeError,'match differs'): verify_overlay(bad,'s1','alternate')

    def test_action_budget_and_cleanup_bypass(self):
        a=self.actor();a.request(certificate(),'smoke')
        self.assertEqual(a.request(certificate(),'again')['rejection'],'already_alternate')
        a.close();self.assertEqual(a.route,'primary');self.assertFalse(a.claimed)
        with self.assertRaisesRegex(RuntimeError,'verified owned state'):
            a.request(certificate(),'after close')

    def test_passive_verification_rejects_routing_overlays(self):
        from experiment_config import verify_route
        a=self.actor();a.request(certificate(),'smoke')
        fake=self.fake
        class Node:
            def __init__(self,name): self.name=name
            def pexec(self,args): return fake(self.name,args)
        with self.assertRaisesRegex(RuntimeError,'higher-priority'):
            verify_route({s:Node(s) for s in BASE_PORTS},'primary',self.tmp.name)
        a.close()


class PolicyTests(unittest.TestCase):
    def test_fixed_never_requests_action(self):
        p=Trigger('fixed')
        for i in range(20): self.assertIsNone(p.update(i*.25,dict(utilization=1,util_slope_2s=.3)))

    def test_reactive_requires_sustained_observed_time(self):
        p=Trigger('reactive')
        for t in [0,.25,.5,.75]:
            self.assertIsNone(p.update(t,dict(utilization=.9,util_slope_2s=0)))
        self.assertEqual(p.update(1.,dict(utilization=.9,util_slope_2s=0)),
                         'observed_utilization_sustained')
        p.mark_applied();self.assertIsNone(p.update(1.25,dict(utilization=.9,util_slope_2s=0)))

    def test_gap_breaks_reactive_timer(self):
        p=Trigger('reactive')
        p.update(0,dict(utilization=.9,util_slope_2s=0))
        p.update(.25,dict(utilization=.9,util_slope_2s=0))
        self.assertIsNone(p.update(2.,dict(utilization=.9,util_slope_2s=0)))
        self.assertIsNone(p.update(2.25,dict(utilization=.9,util_slope_2s=0)))

    def test_early_warning_is_past_trend_not_schedule(self):
        p=Trigger('early_warning')
        self.assertIsNone(p.update(0,dict(utilization=.6,util_slope_2s=-.3)))
        self.assertEqual(p.update(.25,dict(utilization=.7,util_slope_2s=.1)),
                         'past_trend_forecast')
        self.assertIsNone(Trigger('early_warning').update(0,dict(utilization=.7,util_slope_2s=float('nan'))))


class SmokeTests(unittest.TestCase):
    def exercise(self,fail_unselected=False,stale_rule_stats=False):
        import run_routing_smoke as smoke
        fake=FakeOVS();counts={k:0 for k in ['s1-eth3','s1-eth4','s2-eth2','s3-eth2']}
        class Node:
            def __init__(self,name): self.name=name
            def IP(self): return '10.0.0.'+self.name[1:]
            def pexec(self,args):
                if args[0]=='ovs-ofctl':
                    out,err,code=fake(self.name,args)
                    if stale_rule_stats: out=out.replace('n_packets=5','n_packets=1')
                    return out,err,code
                if args[0]=='cat':
                    path=args[1]
                    if path.endswith('/carrier'): return '1\n','',0
                    if path.endswith('/tx_bytes'): return '0\n','',0
                    dev=path.split('/')[4]
                    return str(counts[dev])+'\n','',0
                if args[0]=='ping':
                    alt=self.name=='h1' and 's1' in fake.overlay
                    if fail_unselected and self.name=='h3' and fake.overlay:
                        return '5 packets transmitted, 0 received','injected ping failure',1
                    for k in (['s1-eth4','s3-eth2'] if alt else ['s1-eth3','s2-eth2']): counts[k]+=5
                    return '5 packets transmitted, 5 received, 0% packet loss','',0
                raise AssertionError(args)
        net={n:Node(n) for n in ['h1','h2','h3','h4','s1','s2','s3','s4']}
        now=[10.]
        def clock(): return now[0]
        def sleep(seconds): now[0]+=seconds
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in ['routing_action.py','routing_policy.py','run_routing_smoke.py',
                         'topology.py','diamond_controller.py']:
                (base/name).write_text('# fixture\n')
            with patch.object(smoke,'BASE',base),patch('builtins.print'):
                if stale_rule_stats:
                    with self.assertRaisesRegex(RuntimeError,'did not reach five'):
                        smoke.run(net,clock=clock,sleep=sleep)
                elif fail_unselected:
                    with self.assertRaisesRegex(RuntimeError,'Connectivity probe failed'):
                        smoke.run(net,clock=clock,sleep=sleep)
                else: smoke.run(net,clock=clock,sleep=sleep)
            self.assertFalse(fake.overlay)
            record=json.loads(next((base/'results/runs').glob('*/smoke.json')).read_text())
            self.assertTrue(record['restoration']['verified'])
            failed=fail_unselected or stale_rule_stats
            self.assertEqual(record['outcome'],'failed' if failed else 'completed')
            if not failed: self.assertEqual(len(record['phases']),5)

    def test_full_smoke_lifecycle_and_restore(self): self.exercise()
    def test_smoke_probe_failure_also_restores(self): self.exercise(True)
    def test_packet_observation_timeout_also_restores(self): self.exercise(stale_rule_stats=True)


class PacketObservationTests(unittest.TestCase):
    def exercise(self,mode):
        from run_routing_smoke import wait_for_packet_counts
        now=[0.];logs=[];reads={'s1':0,'s4':0}
        class Actor:
            def _command(self,switch,args,label):
                reads[switch]+=1
                if mode=='missing': return ''
                src,dst=('10.0.0.1','10.0.0.2') if switch=='s1' else ('10.0.0.2','10.0.0.1')
                n=5 if mode=='delayed' and reads[switch]>=3 else 1
                return (f'cookie=0x{COOKIE:x},table=0,n_packets={n},priority=200,ip,'
                        f'nw_src={src},nw_dst={dst} actions=output:4')
            def _log(self,record): logs.append(record)
        def sleep(seconds): now[0]+=seconds
        call=lambda:wait_for_packet_counts(Actor(),clock=lambda:now[0],sleep=sleep,timeout_s=.5)
        if mode=='delayed':
            result=call();self.assertEqual(result['counts'],{'s1':5,'s4':5})
            self.assertEqual(result['polls'],3);self.assertAlmostEqual(result['observation_wait_s'],.2)
            self.assertEqual(logs[0]['counts'],{'s1':1,'s4':1})
        else:
            with self.assertRaisesRegex(RuntimeError,'match differs' if mode=='missing' else 'did not reach five'):
                call()
            self.assertLessEqual(now[0],.5)

    def test_delayed_statistics_keep_full_threshold(self): self.exercise('delayed')
    def test_statistics_never_catching_up_fails_bounded(self): self.exercise('never')
    def test_missing_rule_is_not_treated_as_a_refresh_delay(self): self.exercise('missing')


if __name__=='__main__': unittest.main()
