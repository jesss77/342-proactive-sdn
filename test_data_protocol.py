import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_event_targets import audit_rows
from build_trace_dataset import detect_events,label_rows,FEATURES
from fixed_trace_dataset import load_protocol,development_plan,validate_selection,load_fixed_trace,build
from run_dataset_batch import run
from test_trace_dataset import trace

BASE=Path(__file__).resolve().parent


class ProtocolTests(unittest.TestCase):
    def setUp(self): self.protocol=load_protocol(BASE/'dataset_protocol.json')

    def test_whole_run_partition_and_reserved_test_seeds(self):
        plan=development_plan(self.protocol)
        self.assertEqual(len(plan),16)
        self.assertEqual(sum(r['split']=='train' for r in plan),10)
        self.assertEqual(sum(r['split']=='validation' for r in plan),6)
        self.assertFalse(set(r['seed'] for r in plan)&{31,32,33})
        self.assertEqual(len({(r['scenario'],r['seed']) for r in plan}),16)

    def test_selection_rejects_leakage_duplicates_and_missing_runs(self):
        plan=development_plan(self.protocol)
        runs=[dict(r,folder=f'raw-{i}') for i,r in enumerate(plan)]
        selection=dict(protocol_id=self.protocol['id'],runs=runs)
        self.assertEqual(len(validate_selection(selection,self.protocol)),16)
        for mutation in ['heldout','wrong_split','duplicate','missing','traversal']:
            selected=copy.deepcopy(selection)
            if mutation=='heldout': selected['runs'][0].update(split='test',seed=31)
            elif mutation=='wrong_split': selected['runs'][0]['split']='validation'
            elif mutation=='duplicate': selected['runs'][1]=selected['runs'][0]
            elif mutation=='missing': selected['runs'].pop()
            else: selected['runs'][0]['folder']='../raw'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                validate_selection(selected,self.protocol)

    def test_protocol_edits_rejected(self):
        for field,value in [('interval_s',.1),('scale_bps',12000000),('label_config',{})]:
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'protocol.json';p=copy.deepcopy(self.protocol);p[field]=value
                path.write_text(json.dumps(p))
                with self.subTest(field=field),self.assertRaises(ValueError): load_protocol(path)

    def test_intervened_trace_is_not_training_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);f=repo/'results/runs/raw';f.mkdir(parents=True)
            (f/'policy.json').write_text(json.dumps(dict(policy='reactive',actions=[{'applied':True}],outcome='completed')))
            with self.assertRaisesRegex(ValueError,'untouched'): load_fixed_trace(repo,'raw',self.protocol)

    def test_derivatives_cannot_overwrite_raw_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)
            with self.assertRaisesRegex(ValueError,'raw evidence'):
                build(repo,'missing',BASE/'dataset_protocol.json',repo/'results/runs/derived')

    def test_complete_build_keeps_grouping_separate_from_feature_allowlist(self):
        import csv
        import fixed_trace_dataset as builder
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            repo=Path(tmp);plan=development_plan(self.protocol)
            selected=[dict(item,folder=f'raw-{i}') for i,item in enumerate(plan)]
            selection=repo/'selection.json'
            selection.write_text(json.dumps(dict(protocol_id=self.protocol['id'],runs=selected)))
            def load(_repo,name,_protocol):
                item=next(r for r in selected if r['folder']==name)
                rows,events=label_rows(trace([.2]*20+[.95]*12+[.2]*24))
                summary=dict(run=name,scenario=item['scenario'],seed=item['seed'],rows=len(rows),
                    eligible=sum(r['label'] is not None for r in rows),positive=sum(r['label']==1 for r in rows),
                    negative=sum(r['label']==0 for r in rows),events=events)
                return rows,summary
            with patch.object(builder,'load_fixed_trace',load):
                result=build(repo,selection,BASE/'dataset_protocol.json',repo/'derived')
            self.assertTrue(result['complete_development']);self.assertEqual(len(result['runs']),16)
            self.assertEqual(result['feature_allowlist'],FEATURES)
            with (repo/'derived/dataset.csv').open() as f:
                reader=csv.DictReader(f);rows=list(reader)
                self.assertEqual(set(reader.fieldnames),set(FEATURES)|{'run','scenario','seed','split','available','label','excluded_reason','lead_to_onset_s'})
            self.assertTrue(rows);self.assertFalse({r['seed'] for r in rows}&{'31','32','33'})


class EventAuditTests(unittest.TestCase):
    def test_highutil_target_is_not_equated_to_loss(self):
        rows=trace([.2]*12+[.9]*12+[.2]*20)
        result=audit_rows(rows,detect_events)
        self.assertEqual(result['observed_events'],1)
        self.assertEqual(result['total_root_drops'],0)
        self.assertIsNone(result['event_details'][0]['first_drop_interval_since_onset_s'])

    def test_drop_accounting_keeps_transients_outside_sustained_events(self):
        rows=trace([.2]*12+[.9]*12+[.2]*20)
        rows[12]['drops_delta']=2;rows[30]['drops_delta']=3
        result=audit_rows(rows,detect_events)
        self.assertEqual(result['drops_inside_sustained_highutil'],2)
        self.assertEqual(result['drops_outside_sustained_highutil'],3)
        self.assertEqual(result['event_details'][0]['first_drop_interval_since_onset_s'],0)


class BatchTests(unittest.TestCase):
    def fixture(self,base):
        p=load_protocol(BASE/'dataset_protocol.json')
        # The protocol's real source pins are replaced only for this isolated
        # fixture, preserving filename/partition semantics.
        for name in p['source_sha256']:
            (base/name).write_text('# fixture\n')
            p['source_sha256'][name]=hashlib.sha256((base/name).read_bytes()).hexdigest()
        for name in ['run_dataset_batch.py','fixed_trace_dataset.py']:
            (base/name).write_bytes((BASE/name).read_bytes())
        (base/'dataset_protocol.json').write_text(json.dumps(p))
        calls=[]
        def acquire(_net,**kwargs):
            calls.append(kwargs)
            folder=base/'results/runs'/f"trial-{kwargs['scenario']}-{kwargs['seed']}";folder.mkdir()
            return folder
        def inspect(_folder):
            return dict(screen_failures=[],applied_actions=[],denied_requests=[],receiver_mbps=7,udp_loss_percent=10)
        return calls,acquire,inspect

    def test_pause_resume_has_no_duplicate_runs_or_test_collection(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            base=Path(tmp);calls,acquire,inspect=self.fixture(base)
            folder=run(None,limit=2,base=base,run_trial=acquire,inspect_trial=inspect)
            self.assertEqual(json.loads((folder/'batch.json').read_text())['outcome'],'paused')
            run(None,limit=16,resume=folder,base=base,run_trial=acquire,inspect_trial=inspect)
            state=json.loads((folder/'batch.json').read_text())
            self.assertEqual(state['outcome'],'completed');self.assertEqual(len(calls),16)
            self.assertTrue(all(c['policy']=='fixed' for c in calls))
            self.assertFalse({c['seed'] for c in calls}&{31,32,33})

    def test_failed_run_reference_is_retained_and_batch_stops(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            base=Path(tmp);calls,acquire,inspect=self.fixture(base)
            def fail(_net,**kwargs):
                folder=base/'results/runs/fixture-policy-fixed-ramp-seed11';folder.mkdir()
                raise RuntimeError('source failure')
            with self.assertRaisesRegex(RuntimeError,'source failure'):
                run(None,limit=2,base=base,run_trial=fail,inspect_trial=inspect)
            state=json.loads(next(base.glob('results/runs/*-fixed-development-batch/batch.json')).read_text())
            self.assertEqual(state['outcome'],'failed');self.assertEqual(len(state['attempts']),1)
            self.assertIn('fixture-policy-fixed-ramp-seed11',state['attempts'][0]['candidate_raw_folders'])

    def test_quality_failure_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            base=Path(tmp);calls,acquire,inspect=self.fixture(base)
            def bad(path): return dict(inspect(path),screen_failures=['udp_error'])
            with self.assertRaisesRegex(RuntimeError,'screening'):
                run(None,limit=16,base=base,run_trial=acquire,inspect_trial=bad)
            self.assertEqual(len(calls),1)

    def test_source_change_prevents_any_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);calls,acquire,inspect=self.fixture(base)
            (base/'continuous_udp.py').write_text('# changed\n')
            with self.assertRaisesRegex(ValueError,'source changed'):
                run(None,base=base,run_trial=acquire,inspect_trial=inspect)
            self.assertEqual(calls,[])


if __name__=='__main__': unittest.main()
