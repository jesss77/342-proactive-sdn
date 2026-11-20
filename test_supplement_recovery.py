import contextlib,io,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_supplement_recovery as recovery
import test_matched as matched_fixtures

BASE=Path(__file__).resolve().parent

class RegistrationTests(unittest.TestCase):
    def test_real_registration_freezes_existing_pipeline_and_orders(self):
        p,_=recovery.load_protocol(BASE)
        rows=recovery.plan()
        self.assertEqual(len(rows),12)
        self.assertEqual([r['policy'] for r in rows[:4]],['reactive','early_warning','fixed','ml'])
        self.assertEqual({r['seed'] for r in rows},{44,45,46})
        for seed in [44,45,46]:self.assertEqual(len({r['policy'] for r in rows if r['seed']==seed}),4)
        self.assertEqual(len(p['parent_files_sha256']),828)

    def test_frozen_source_change_rejected(self):
        p,_=recovery.load_protocol(BASE)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for n in [*p['frozen_source_sha256'],*p['additional_source_sha256'],'supplement_recovery_protocol.json']:
                shutil.copy2(BASE/n,root/n)
            with (root/'routing_action.py').open('ab') as f:f.write(b'\n# mutation\n')
            with self.assertRaisesRegex(ValueError,'changed'):recovery.load_protocol(root)

class BatchTests(unittest.TestCase):
    def fixture(self,base):
        self.base=base
        self.helper=matched_fixtures.MatchedTests('test_plan_has_36_unique_cells_equal_schedules_and_balanced_positions')
        matched=self.helper.fixture(base)
        parent=base/'results/runs'/recovery.SETTINGS['parent_batch'];parent.mkdir()
        (parent/'batch.json').write_text(json.dumps(dict(outcome='failed',runs=[{}]*7,
            attempts=[dict(status='passed')]*7+[dict(status='failed')])))
        (base/'results/runs/supplement-registry-v1.json').write_text(json.dumps(dict(batch=parent.name)))
        self.parent_hashes={p.relative_to(base).as_posix():recovery.sha(p) for p in [parent/'batch.json',base/'results/runs/supplement-registry-v1.json']}
        self.p=dict(additional_source_sha256={},parent_files_sha256=self.parent_hashes)
        (base/'supplement_recovery_protocol.json').write_text('{}')
        self.matched=matched;self.readiness_calls=0

    def ready(self,net,base,folder):
        self.readiness_calls+=1;folder.mkdir(parents=True);(folder/'result.json').write_text('{}')
        return dict(outcome='passed')

    def run_batch(self,**kw):
        with patch.object(recovery,'load_protocol',return_value=(self.p,self.matched)),contextlib.redirect_stdout(io.StringIO()):
            return recovery.run(None,base=self.base,run_trial=self.helper.trial,
                inspect_trial=lambda p:self.helper.reports[p.name],source_auditor=lambda p:dict(discard_percent=.01),
                readiness_check=kw.pop('readiness_check',self.ready),**kw)

    def assert_parent_unchanged(self):
        self.assertTrue(all(recovery.sha(self.base/p)==v for p,v in self.parent_hashes.items()))

    def test_pause_resume_complete_blocks_no_duplicate_or_parent_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp));first=self.run_batch(limit=4)
            s=json.loads((first/'batch.json').read_text());self.assertEqual((s['outcome'],len(s['runs'])),('paused',4))
            self.run_batch(limit=8,resume=first)
            s=json.loads((first/'batch.json').read_text());self.assertEqual((s['outcome'],len(s['runs'])),('completed',12))
            self.assertEqual(len({(r['policy'],r['seed']) for r in s['runs']}),12)
            self.assertEqual(self.readiness_calls,2);self.assert_parent_unchanged()
            with self.assertRaisesRegex(ValueError,'already registered'):self.run_batch(limit=4)

    def test_quality_failure_retained_and_resume_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp));original=self.helper.trial
            def fail_second(*a,**kw):
                out=original(*a,**kw)
                if self.helper.count==2:self.helper.reports[out.name]['screen_failures']=['collector_quality']
                return out
            with patch.object(self.helper,'trial',side_effect=fail_second):
                with self.assertRaisesRegex(ValueError,'quality/restoration'):self.run_batch(limit=4)
            root=self.base/'results/runs';folder=root/json.loads((root/'supplement-recovery-registry-v1.json').read_text())['batch']
            s=json.loads((folder/'batch.json').read_text());self.assertEqual((s['outcome'],len(s['runs']),len(s['attempts'])),('failed',1,2))
            self.assertEqual(len(s['attempts'][-1]['candidate_raw_folders']),2)
            self.assertEqual(len(list((folder/'reviews').glob('*.json'))),2)
            with self.assertRaisesRegex(ValueError,'no automatic retry'):self.run_batch(limit=4,resume=folder)
            self.assert_parent_unchanged()

    def test_readiness_failure_starts_no_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp))
            def bad(*a):
                self.ready(*a);raise ValueError('idle failed')
            with self.assertRaisesRegex(ValueError,'idle failed'):self.run_batch(readiness_check=bad)
            self.assertEqual(self.helper.count,0);self.assert_parent_unchanged()
            folder=self.base/'results/runs'/json.loads((self.base/'results/runs/supplement-recovery-registry-v1.json').read_text())['batch']
            s=json.loads((folder/'batch.json').read_text());self.assertEqual(s['attempts'],[])
            self.assertEqual(s['readiness'][0]['status'],'failed')

    def test_parent_mutation_blocks_before_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp));p=self.base/next(iter(self.parent_hashes))
            p.write_text(p.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'Preserved parent evidence changed'):self.run_batch()
            self.assertEqual(self.readiness_calls,0);self.assertEqual(self.helper.count,0)

    def test_accepted_raw_mutation_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp));folder=self.run_batch()
            s=json.loads((folder/'batch.json').read_text());p=self.base/'results/runs'/s['runs'][0]['trial']/'metadata.json'
            p.write_text(p.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'Accepted recovery evidence changed'):self.run_batch(resume=folder)

class ReadinessTests(unittest.TestCase):
    def test_skipped_deadline_still_fails_idle_readiness(self):
        from dual_path_profile import QUEUES
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);rows=[]
            for i in range(240):
                q={dev:dict(interface=dev,capacity_bps=10000000,tc_start=i*.25,tc_end=i*.25+.005,tc_exit=0,
                    root_qdisc=dict(bytes=0,drops=0,backlog=0,qlen=0)) for dev in QUEUES}
                rows.append(dict(utc='fixture',requested_interval=.25,qdiscs=q,skipped_before_sample=0))
            (folder/'samples.jsonl.stats.json').write_text(json.dumps(dict(schema_version=6,coverage='all',elapsed_s=60,queried_qdiscs=QUEUES)))
            counts={dev:dict(tx_bytes=0) for dev in QUEUES}
            def save(): (folder/'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
            save()
            with patch.object(recovery.os,'cpu_count',return_value=1):
                self.assertEqual(recovery.inspect_readiness(folder,counts,counts,60,'tsc','tsc')['screen_failures'],[])
                rows[120]['skipped_before_sample']=1;save()
                result=recovery.inspect_readiness(folder,counts,counts,60,'tsc','tsc')
                self.assertIn('collector_quality',result['screen_failures'])
                self.assertTrue(all(q['invalid_intervals']==1 for q in result['queues'].values()))

if __name__=='__main__':unittest.main()
