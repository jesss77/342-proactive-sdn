import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import run_matched_batch as batch
from traffic_scenarios import continuous_schedule

BASE=Path(__file__).resolve().parent

class MatchedTests(unittest.TestCase):
    def fixture(self,repo):
        p=copy.deepcopy(json.loads((BASE/'matched_protocol.json').read_text()))
        for name in p['source_sha256']:shutil.copy2(BASE/name,repo/name)
        batch.write(repo/'matched_protocol.json',p)
        (repo/'results/runs').mkdir(parents=True)
        self.reports={};self.count=0;self.repo=repo;self.p=p
        return p

    def trial(self,net,policy,scenario,seed,duration,requested_bps):
        self.count+=1;root=self.repo/'results/runs'
        folder=root/f'run-{self.count}-policy-{policy}-{scenario}-seed{seed}';folder.mkdir()
        raw=root/f'trial-{self.count}';raw.mkdir()
        names=batch.COMMON_SOURCES+(batch.ML_SOURCES if policy=='ml' else [])
        for name in names:shutil.copy2(self.repo/name,folder/name)
        schedule=continuous_schedule(scenario,requested_bps,duration,seed)
        m=dict(outcome='completed',policy=policy,scenario=scenario,seed=seed,duration=duration,
            requested_scale_bps=requested_bps,planned_segments=schedule,
            profile=dict(id=batch.SETTINGS['profile_id']),trial=raw.name,
            source_sha256={n:self.p['source_sha256'][n] for n in names})
        batch.write(folder/'policy.json',m);batch.write(raw/'metadata.json',dict(traffic_plan=schedule,
            seed=seed,scenario=scenario,trial_context=dict(kind='policy_experiment',policy=policy,parent=folder.name)))
        self.reports[folder.name]=dict(outcome='completed',screen_failures=[],restoration=dict(failures=[]),
            route_restoration=dict(verified=True,failures=[]),applied_actions=[],denied_requests=[],
            in_traffic_switch_verified=False,trial=dict(run=raw.name),receiver_mbps=2.99,sender_mbps=3.,
            udp_loss_percent=0.,model=dict(sha256=batch.SETTINGS['model_sha256'],threshold=.65) if policy=='ml' else None,
            inference=dict(calls=200) if policy=='ml' else None)
        return folder

    def run_batch(self,**kwargs):
        return batch.run(None,base=self.repo,run_trial=self.trial,
            inspect_trial=lambda path:self.reports[path.name],
            source_auditor=lambda path:dict(discard_percent=.01),
            pilot_checker=lambda *args:dict(folder='accepted-pilot'),**kwargs)

    def test_plan_has_36_unique_cells_equal_schedules_and_balanced_positions(self):
        rows=batch.plan()
        self.assertEqual(len(rows),36)
        self.assertEqual(len({(r['policy'],r['scenario'],r['seed']) for r in rows}),36)
        self.assertEqual({r['seed'] for r in rows},{41,42,43})
        for block in range(9):
            group=[r for r in rows if r['block']==block]
            self.assertEqual({r['policy'] for r in group},set(batch.POLICIES))
            self.assertEqual(len({(r['scenario'],r['seed'],r['requested_bps'],r['duration']) for r in group}),1)
        for policy in batch.POLICIES:
            counts=[sum(r['policy']==policy and r['position']==i for r in rows) for i in range(4)]
            self.assertLessEqual(max(counts)-min(counts),1)
        self.assertEqual({r['requested_bps'] for r in rows if r['scenario']=='steady'},{3000000})

    def test_pause_resume_keeps_each_cell_once_and_all_no_action_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            self.fixture(Path(tmp));folder=self.run_batch(limit=4)
            state=json.loads((folder/'batch.json').read_text());self.assertEqual(state['outcome'],'paused')
            self.assertEqual(len(state['runs']),4)
            self.run_batch(limit=36,resume=folder)
            state=json.loads((folder/'batch.json').read_text());self.assertEqual(state['outcome'],'completed')
            self.assertEqual(len(state['runs']),36);self.assertEqual(self.count,36)
            self.run_batch(limit=36,resume=folder);self.assertEqual(self.count,36)
            with self.assertRaisesRegex(ValueError,'already registered'):self.run_batch()

    def test_source_change_blocks_before_any_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp));(Path(tmp)/'live_policy.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):self.run_batch()
            self.assertEqual(self.count,0)

    def test_failed_quality_keeps_reference_and_cannot_resume_or_restart(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            self.fixture(Path(tmp));original=self.trial
            def bad(*args,**kwargs):
                folder=original(*args,**kwargs);self.reports[folder.name]['screen_failures']=['udp_error'];return folder
            self.trial=bad
            with self.assertRaisesRegex(ValueError,'quality'):self.run_batch(limit=4)
            root=Path(tmp)/'results/runs';folder=Path((root/'active-matched-batch.txt').read_text().strip())
            state=json.loads((folder/'batch.json').read_text())
            self.assertEqual(state['outcome'],'failed');self.assertEqual(len(state['runs']),0)
            self.assertEqual(self.count,1);self.assertTrue(state['attempts'][0]['candidate_raw_folders'])
            self.assertTrue((root/state['attempts'][0]['folder']).exists())
            with self.assertRaisesRegex(ValueError,'requires evidence review'):self.run_batch(resume=folder)
            with self.assertRaisesRegex(ValueError,'already registered'):self.run_batch()

    def test_resume_rejects_raw_mutation_and_pipeline_change(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            self.fixture(Path(tmp));folder=self.run_batch(limit=1)
            state=json.loads((folder/'batch.json').read_text());raw=Path(tmp)/'results/runs'/state['runs'][0]['trial']
            (raw/'metadata.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'raw evidence changed'):self.run_batch(resume=folder)
            self.assertEqual(self.count,1)
            (Path(tmp)/'run_matched_batch.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):self.run_batch(resume=folder)

    def test_no_accepted_live_pilot_refuses_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError,'live ML seed-1 pilot'):
                batch.run(None,base=Path(tmp),run_trial=self.trial,inspect_trial=lambda path:self.reports[path.name])
            self.assertEqual(self.count,0)

    def test_real_pilot_gate_requires_accepted_same_source_and_parent_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(Path(tmp))
            folder=self.trial(None,policy='ml',scenario='ramp',seed=1,duration=60,requested_bps=11500000)
            report=self.reports[folder.name];report['in_traffic_switch_verified']=True
            report['applied_actions']=[dict(applied=True)]
            inspect=lambda path:self.reports[path.name]
            with patch('source_integrity.source_integrity_audit',return_value=dict(discard_percent=0)):
                self.assertEqual(batch.pilot_gate(Path(tmp),p,inspect)['folder'],folder.name)
                raw=Path(tmp)/'results/runs'/report['trial']['run']
                meta=json.loads((raw/'metadata.json').read_text());meta['trial_context']['parent']='another-run'
                batch.write(raw/'metadata.json',meta)
                with self.assertRaisesRegex(ValueError,'live ML seed-1 pilot'):batch.pilot_gate(Path(tmp),p,inspect)

    def test_identity_model_and_claimed_switch_are_checked_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(Path(tmp));item=next(r for r in batch.plan() if r['policy']=='ml')
            folder=self.trial(None,**{k:item[k] for k in ['policy','scenario','seed','duration','requested_bps']})
            original=copy.deepcopy(self.reports[folder.name])
            for mutation in ['missing_inference','wrong_model','unverified_switch','restoration']:
                report=copy.deepcopy(original)
                if mutation=='missing_inference':report['inference']=None
                elif mutation=='wrong_model':report['model']['sha256']='bad'
                elif mutation=='unverified_switch':report['applied_actions']=[dict(applied=True)]
                else:report['route_restoration']['verified']=False
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                    batch.check_report(Path(tmp),folder,item,p,report,lambda _:dict(discard_percent=0))
            m=json.loads((folder/'policy.json').read_text());m['seed']=31;batch.write(folder/'policy.json',m)
            with self.assertRaisesRegex(ValueError,'identity'):batch.check_report(Path(tmp),folder,item,p,original,lambda _:dict(discard_percent=0))

    def test_denied_or_steady_switch_outcome_is_retained_not_selected_for_benefit(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            p=self.fixture(Path(tmp));item=next(r for r in batch.plan() if r['policy']=='ml')
            folder=self.trial(None,**{k:item[k] for k in ['policy','scenario','seed','duration','requested_bps']})
            report=self.reports[folder.name];report['denied_requests']=[dict(rejection='over_budget')]
            record=batch.check_report(Path(tmp),folder,item,p,report,lambda _:dict(discard_percent=0))
            self.assertEqual(record['denials'],1)
            report['denied_requests']=[];report['applied_actions']=[dict(applied=True)]
            report['in_traffic_switch_verified']=True
            record=batch.check_report(Path(tmp),folder,item,p,report,lambda _:dict(discard_percent=0))
            self.assertEqual(record['actions'],1)

    def test_runner_error_preserves_both_new_raw_folders(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            self.fixture(Path(tmp));original=self.trial
            def fail(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('worker failed')
            self.trial=fail
            with self.assertRaisesRegex(RuntimeError,'worker failed'):self.run_batch()
            root=Path(tmp)/'results/runs';folder=Path((root/'active-matched-batch.txt').read_text().strip())
            state=json.loads((folder/'batch.json').read_text())
            self.assertEqual(len(state['attempts'][0]['candidate_raw_folders']),2)
            self.assertEqual(self.count,1)

if __name__=='__main__':unittest.main()
