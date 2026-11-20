import contextlib,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import run_supplement_recovery as r
spec=importlib.util.spec_from_file_location('review_helper',ROOT/'tools/review_interrupted_readiness.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

class ReviewTests(unittest.TestCase):
    def fixture(self,base):
        root=base/'results/runs';folder=root/'interrupted';ready=folder/'readiness/00';ready.mkdir(parents=True)
        (base/'supplement_recovery_protocol.json').write_text('{}')
        (folder/'supplement_recovery_protocol.json').write_text('{}')
        (root/'supplement-recovery-registry-v1.json').write_text(json.dumps(dict(batch=folder.name)))
        (root/'active-supplement-recovery-v1.txt').write_text(str(folder)+'\n')
        state=dict(role='prospective_whole_block_recovery',outcome='failed',runs=[],attempts=[],plan=r.plan(),
            protocol_sha256=r.sha(base/'supplement_recovery_protocol.json'),
            readiness=[dict(folder='readiness/00',status='failed',error='KeyboardInterrupt()')])
        (folder/'batch.json').write_text(json.dumps(state))
        (ready/'readiness.json').write_text(json.dumps(dict(outcome='failed',error='KeyboardInterrupt()',no_traffic_generated=True)))
        return root,folder,ready

    def call(self,base,**kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return helper.review(base,loader=lambda _:({'additional_source_sha256':{}},{}),
                parent_check=lambda *a:dict(files_verified=828),process_check=kw.get('process_check',lambda _:[]))

    def test_preserves_raw_and_archives_pointers_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root,folder,ready=self.fixture(base);before=r.evidence_hashes(folder)
            pointer=(root/'supplement-recovery-registry-v1.json').read_bytes()
            record,review=self.call(base)
            self.assertEqual(record['attempts'],0);self.assertEqual(r.evidence_hashes(folder),before)
            self.assertEqual((review/'registry-before.json').read_bytes(),pointer)
            self.assertFalse((root/'supplement-recovery-registry-v1.json').exists())
            self.assertTrue((root/'readiness-interruption-review-v1.json').exists())
            with self.assertRaisesRegex(ValueError,'no repeated'):self.call(base)

    def test_any_traffic_attempt_refuses_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root,folder,ready=self.fixture(base);p=folder/'batch.json';s=json.loads(p.read_text())
            s['attempts']=[dict(status='running')];p.write_text(json.dumps(s));before=r.evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'Not an empty'):self.call(base)
            self.assertEqual(r.evidence_hashes(root),before)

    def test_known_partial_collector_failure_is_not_waived(self):
        from dual_path_profile import QUEUES
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root,folder,ready=self.fixture(base);rows=[]
            for i in range(2):
                rows.append(dict(utc='fixture',requested_interval=.25,skipped_before_sample=i,
                    qdiscs={q:dict(tc_exit=0,tc_start=i*.25,tc_end=i*.25+.005,capacity_bps=10000000,
                        root_qdisc=dict(bytes=i*100,drops=0,backlog=0,qlen=0)) for q in QUEUES}))
            (ready/'samples.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n');before=r.evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'collector-quality failure'):self.call(base)
            self.assertEqual(r.evidence_hashes(root),before)

    def test_active_collector_blocks_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root,folder,ready=self.fixture(base);before=r.evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'Collector still running'):self.call(base,process_check=lambda _:[123])
            self.assertEqual(r.evidence_hashes(root),before)

    def test_quality_result_is_not_reclassified_as_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root,folder,ready=self.fixture(base);p=ready/'readiness.json';s=json.loads(p.read_text())
            s['report']=dict(screen_failures=['collector_quality']);p.write_text(json.dumps(s));before=r.evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'quality result'):self.call(base)
            self.assertEqual(r.evidence_hashes(root),before)

if __name__=='__main__':unittest.main()
