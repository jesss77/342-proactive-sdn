import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_activation_pilot as pilot
from run_matched_batch import evidence_hashes,sha
from tools import review_activation_interruption as helper

BASE = Path(__file__).resolve().parents[1]


class ReviewTests(unittest.TestCase):
    def fixture(self,base):
        self.base=base;root=base/'results/runs';folder=root/helper.EXPECTED_BATCH
        env=folder/'before/environment';env.mkdir(parents=True)
        ready=folder/'readiness';ready.mkdir()
        shutil.copyfile(BASE/pilot.PROTOCOL,base/pilot.PROTOCOL)
        shutil.copyfile(BASE/pilot.PROTOCOL,folder/pilot.PROTOCOL)
        (root/pilot.REGISTRY).write_text(json.dumps(dict(batch=folder.name)))
        (folder/'batch.json').write_text(json.dumps(dict(outcome='failed',error='KeyboardInterrupt()',
            attempts=[],new_raw_folders=[],plan=pilot.plan(),protocol_sha256=helper.EXPECTED_PROTOCOL,captured_source_sha256={})))
        (env/'environment.json').write_text(json.dumps(dict(cpu_count=1,clocksource='tsc')))
        (env/'tcpdump-version.json').write_text(json.dumps(dict(exit=0,text='tcpdump version 4.99.4\nlibpcap version 1.10.4')))
        for dev in ['s1-eth3','s1-eth4']:
            (env/(dev+'-timestamp-types.json')).write_text(json.dumps(dict(exit=0,text='  host (Host)\n')))
        (ready/'readiness.json').write_text(json.dumps(dict(outcome='failed',error='KeyboardInterrupt()',no_traffic_generated=True)))
        self.p=dict(frozen_source_sha256={},additional_source_sha256={})
        return root,folder,ready

    def call(self,**kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return helper.review(self.base,loader=lambda _:self.p,
                parent_check=kw.pop('parent_check',lambda *a:dict(files_verified=571)),
                process_check=kw.pop('process_check',lambda _:[]),**kw)

    def test_preserves_failed_batch_and_archives_only_registry_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,folder,ready=self.fixture(Path(tmp));old=evidence_hashes(folder);pointer=(root/pilot.REGISTRY).read_bytes()
            record,target=self.call()
            self.assertEqual(evidence_hashes(folder),old)
            self.assertEqual((target/'registry-before.json').read_bytes(),pointer)
            self.assertFalse((root/pilot.REGISTRY).exists())
            self.assertEqual(json.loads((root/helper.LEDGER).read_text())['status'],'committed')
            self.assertEqual(record['traffic_attempts'],0)
            with self.assertRaisesRegex(ValueError,'already used'):self.call()

    def test_any_attempt_or_new_raw_folder_refuses_without_changes(self):
        for key,value in [('attempts',[dict(step='before',status='failed')]),('new_raw_folders',['traffic'])]:
            with tempfile.TemporaryDirectory() as tmp:
                root,folder,_=self.fixture(Path(tmp));path=folder/'batch.json';state=json.loads(path.read_text());state[key]=value;path.write_text(json.dumps(state));old=evidence_hashes(root)
                with self.assertRaisesRegex(ValueError,'Not an empty'):self.call()
                self.assertEqual(evidence_hashes(root),old)

    def test_any_execution_clock_or_capture_artifact_blocks_exception(self):
        for name in ['execution.json','clock-map.jsonl','review.json','s1-eth4.pcap']:
            with tempfile.TemporaryDirectory() as tmp:
                root,folder,_=self.fixture(Path(tmp));(folder/'before'/name).write_text('{}');old=evidence_hashes(root)
                with self.assertRaisesRegex(ValueError,'acquisition may have begun'):self.call()
                self.assertEqual(evidence_hashes(root),old)

    def test_existing_quality_result_is_not_reclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_,ready=self.fixture(Path(tmp));path=ready/'readiness.json';m=json.loads(path.read_text());m['report']=dict(screen_failures=['collector_quality']);path.write_text(json.dumps(m));old=evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'quality result'):self.call()
            self.assertEqual(evidence_hashes(root),old)

    def rows(self,ready,bad=False,tail=False):
        from dual_path_profile import QUEUES
        rows=[]
        for i in range(3):
            rows.append(dict(schema_version=6,coverage='all',utc='fixture',requested_interval=.25,
                skipped_before_sample=int(bad and i==2),qdiscs={d:dict(tc_exit=0,tc_start=i*.25,
                    tc_end=i*.25+.004,capacity_bps=10000000,root_qdisc=dict(bytes=0,drops=0,backlog=0,qlen=0)) for d in QUEUES}))
        (ready/'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n'+('{"partial":' if tail else ''))

    def test_known_partial_collector_failure_is_not_waived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_,ready=self.fixture(Path(tmp));self.rows(ready,bad=True);old=evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'collector-quality failure'):self.call()
            self.assertEqual(evidence_hashes(root),old)

    def test_valid_completed_partial_rows_and_unfinished_tail_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,folder,ready=self.fixture(Path(tmp));self.rows(ready,tail=True);old=evidence_hashes(folder)
            record,_=self.call()
            self.assertEqual(record['completed_partial_samples'],3);self.assertTrue(record['incomplete_tail_preserved'])
            self.assertEqual(evidence_hashes(folder),old)

    def test_active_project_process_prevents_any_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_,_=self.fixture(Path(tmp));old=evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'still active'):self.call(process_check=lambda _:[dict(pid=1,kind='collector')])
            self.assertEqual(evidence_hashes(root),old)

    def test_changed_captured_source_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,folder,_=self.fixture(Path(tmp));(folder/'source.py').write_text('original');digest=sha(folder/'source.py')
            self.p['additional_source_sha256']={'source.py':digest};path=folder/'batch.json';s=json.loads(path.read_text());s['captured_source_sha256']=dict(self.p['additional_source_sha256']);path.write_text(json.dumps(s))
            (folder/'source.py').write_text('changed');old=evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'Captured source changed'):self.call()
            self.assertEqual(evidence_hashes(root),old)

    def test_wrong_reported_batch_or_non_interrupt_error_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,folder,_=self.fixture(Path(tmp));path=folder/'batch.json';s=json.loads(path.read_text());s['error']='TimeoutError()';path.write_text(json.dumps(s));old=evidence_hashes(root)
            with self.assertRaisesRegex(ValueError,'Not an empty'):self.call()
            self.assertEqual(evidence_hashes(root),old)

    def test_parent_failure_after_move_restores_registry_and_blocks_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,folder,_=self.fixture(Path(tmp));old=evidence_hashes(folder);pointer=(root/pilot.REGISTRY).read_bytes();calls=[]
            def fail(*a):
                calls.append(1)
                if len(calls)==2:raise ValueError('parent changed')
                return {}
            with self.assertRaisesRegex(ValueError,'parent changed'):self.call(parent_check=fail)
            self.assertEqual((root/pilot.REGISTRY).read_bytes(),pointer)
            self.assertEqual(evidence_hashes(folder),old)
            self.assertEqual(json.loads((root/helper.LEDGER).read_text())['status'],'review_failed_no_automatic_restart')
            with self.assertRaisesRegex(ValueError,'already used'):self.call()


if __name__=='__main__':unittest.main()
