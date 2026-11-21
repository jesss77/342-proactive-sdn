"""Acquisition guards for the separately registered, bounded follow-up."""
from collections import Counter
from pathlib import Path
import json
import tempfile
import unittest
import run_bursty_followup as f


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base/'results/runs'; self.root.mkdir(parents=True)
        (self.base/f.PROTOCOL).write_text('{}'); (self.base/'stub.py').write_text('# frozen\n')
        self.p = dict(frozen_source_sha256={'stub.py':f.sha(self.base/'stub.py')},additional_source_sha256={})
        self.count = 0; self.ready_count = 0

    def ready(self,net,base,folder):
        self.ready_count += 1; folder.mkdir(parents=True); (folder/'ready.json').write_text('{}')

    def trial(self,net,**item):
        self.count += 1
        folder = self.root/('policy-'+str(self.count)); folder.mkdir()
        trial = self.root/('trial-'+str(self.count)); trial.mkdir(); (trial/'raw.json').write_text('{}')
        (folder/'policy.json').write_text(json.dumps(dict(item,trial=trial.name)))
        return folder

    def checker(self,base,folder,item,protocol,report,auditor):
        if report.get('screen_failures'):
            raise ValueError('quality failure')
        trial = self.root/json.loads((folder/'policy.json').read_text())['trial']
        return dict(item,folder=folder.name,trial=trial.name,policy_evidence_sha256=f.evidence_hashes(folder),
            trial_evidence_sha256=f.evidence_hashes(trial),sender_mbps=7.8,receiver_mbps=6.4,
            udp_loss_percent=18,actions=0,denials=9,source_discard_percent=.5)

    def call(self,**kw):
        defaults = dict(base=self.base,run_trial=self.trial,inspect_trial=lambda _:dict(screen_failures=[]),auditor=lambda _:None,
            protocol_loader=lambda _:self.p,parent_check=lambda *_:dict(verified=True),preflight=lambda *_:None,
            readiness_check=self.ready,matched_loader=lambda _:None,report_checker=self.checker)
        defaults.update(kw)
        return f.run(None,**defaults)

    def state(self,folder):
        return json.loads((folder/'batch.json').read_text())

    def receipt(self,folder):
        path = self.base/'independent-review.json'
        path.write_text(json.dumps(dict(kind='independent_bursty_followup_block_review',batch=folder.name,
            accepted_cells=len(self.state(folder)['runs']),batch_sha256=f.sha(folder/'batch.json'),
            quality_passed=True,all_outcomes_retained=True,checkpoint_sha256='a'*64)))
        return path

    def test_plan_balances_positions_and_predecessors(self):
        p=f.plan(); self.assertEqual(len({(x['seed'],x['policy']) for x in p}),16)
        self.assertEqual(set(Counter((x['position'],x['policy']) for x in p).values()),{1})
        pairs=Counter((p[b+i]['policy'],p[b+i+1]['policy']) for b in range(0,16,4) for i in range(3))
        self.assertEqual(len(pairs),12); self.assertEqual(set(pairs.values()),{1})

    def test_first_block_retains_adverse_no_action_and_pauses(self):
        folder=self.call(); s=self.state(folder)
        self.assertEqual((s['outcome'],len(s['runs']),self.count,self.ready_count),('paused',4,4,1))
        self.assertTrue(all(x['udp_loss_percent']==18 and x['actions']==0 and x['denials']==9 for x in s['runs']))
        with self.assertRaises(ValueError): self.call()
        self.assertEqual(self.count,4)

    def test_resume_requires_independent_exact_batch_review(self):
        folder=self.call()
        with self.assertRaises(ValueError): self.call(resume=folder)
        receipt=self.receipt(folder)
        self.call(resume=folder,review=receipt)
        self.assertEqual((len(self.state(folder)['runs']),self.count,self.ready_count),(8,8,2))
        with self.assertRaises(ValueError): self.call(resume=folder,review=receipt)
        self.assertEqual(self.count,8)

    def test_quality_failure_retains_failed_cell_and_blocks_resume(self):
        def inspect(_): return dict(screen_failures=['collector_quality'] if self.count==2 else [])
        with self.assertRaises(ValueError): self.call(inspect_trial=inspect)
        folder=self.root/json.loads((self.root/f.REGISTRY).read_text())['batch']; s=self.state(folder)
        self.assertEqual((s['outcome'],len(s['runs']),len(s['attempts']),self.count),('failed',1,2,2))
        self.assertIn('trial-2',s['new_raw_folders']); self.assertEqual(s['attempts'][1]['status'],'failed')
        self.assertTrue((folder/'review-02.json').exists())
        with self.assertRaises(ValueError): self.call(resume=folder,review=self.receipt(folder))

    def test_worker_exception_keeps_unreturned_raw_folders(self):
        def broken(net,**item):
            self.trial(net,**item); raise RuntimeError('worker')
        with self.assertRaises(RuntimeError): self.call(run_trial=broken)
        folder=self.root/json.loads((self.root/f.REGISTRY).read_text())['batch']
        self.assertEqual(self.state(folder)['new_raw_folders'],['policy-1','trial-1'])

    def test_readiness_cancellation_has_no_traffic_or_retry(self):
        def cancelled(*args): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.call(readiness_check=cancelled)
        folder=self.root/json.loads((self.root/f.REGISTRY).read_text())['batch']
        self.assertEqual(self.count,0); self.assertEqual(self.state(folder)['attempts'],[])
        with self.assertRaises(ValueError): self.call(resume=folder,review=self.receipt(folder))

    def test_source_mutation_is_rejected_before_resume_traffic(self):
        folder=self.call(); receipt=self.receipt(folder); (folder/'stub.py').write_text('# changed')
        with self.assertRaises(ValueError): self.call(resume=folder,review=receipt)
        self.assertEqual(self.count,4)

    def test_saved_raw_or_review_mutation_rejected(self):
        folder=self.call(); receipt=self.receipt(folder); (folder/'review-01.json').write_text('{}')
        with self.assertRaises(ValueError): self.call(resume=folder,review=receipt)
        self.assertEqual(self.count,4)

    def test_unused_seed_gate_rejects_prior_acquisition(self):
        d=self.root/'old-trial'; d.mkdir(); (d/'metadata.json').write_text(json.dumps(dict(seed=51)))
        with self.assertRaises(ValueError): self.call()
        self.assertFalse((self.root/f.REGISTRY).exists()); self.assertEqual(self.count,0)

    def test_parent_or_source_gate_precedes_any_registration(self):
        def bad(*args): raise ValueError('changed parent')
        with self.assertRaises(ValueError): self.call(parent_check=bad)
        self.assertFalse((self.root/f.REGISTRY).exists())

    def test_only_complete_four_trial_calls_allowed(self):
        for limit in [1,3,8,16,True]:
            with self.assertRaises(ValueError): self.call(limit=limit)
        self.assertEqual(self.count,0)


if __name__=='__main__':
    unittest.main()
