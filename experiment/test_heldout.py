import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import heldout_dataset as evaluation
from heldout_dataset import FROZEN_MODEL_SHA,test_plan,frozen_model,guest_reproduction,validate_test_selection
from run_heldout_batch import run,PIPELINE
from fixed_trace_dataset import load_protocol,read,sha
from train_tree import load_data
from build_trace_dataset import label_rows
from test_trace_dataset import trace

BASE=Path(__file__).resolve().parent


class HeldoutTests(unittest.TestCase):
    def fixture(self,base):
        protocol=load_protocol(BASE/'dataset_protocol.json')
        for name in set(protocol['source_sha256'])|set(PIPELINE)|{'selected_tree.json','dataset_protocol.json'}:
            (base/name).write_bytes((BASE/name).read_bytes())
        # Unit fixture pins describe its current isolated source. Production
        # acquisition protocol stays unchanged after the real test closes.
        for name in protocol['source_sha256']:
            protocol['source_sha256'][name]=sha(base/name)
        (base/'dataset_protocol.json').write_text(json.dumps(protocol))
        model=frozen_model(base/'selected_tree.json',protocol)
        r=base/'results/derived/tree-review-fixture';r.mkdir(parents=True)
        (r/'review.json').write_text(json.dumps(dict(dataset_fingerprint=model.model['dataset_fingerprint'],
            model_parameters=model.model['parameters'],alarm_threshold=model.threshold,
            metrics={'validation':{'rows':{'pooled':dict(n=599,tp=170,fp=35,fn=37,tn=357)}}})))
        calls=[]
        def acquire(_net,**kwargs):
            calls.append(kwargs)
            f=base/'results/runs'/f"fixture-policy-fixed-{kwargs['scenario']}-seed{kwargs['seed']}";f.mkdir()
            return f
        def inspect(_folder):
            return dict(screen_failures=[],applied_actions=[],denied_requests=[],receiver_mbps=7,udp_loss_percent=10,
                trial={'run':'fixture-native'})
        def audit(_folder): return dict(discard_percent=.1)
        return protocol,model,calls,acquire,inspect,audit

    def test_registered_plan_has_only_six_fresh_identities(self):
        p=load_protocol(BASE/'dataset_protocol.json');plan=test_plan(p)
        self.assertEqual(len(plan),6)
        self.assertEqual({r['seed'] for r in plan},{31,32,33})
        self.assertEqual({r['split'] for r in plan},{'test'})
        self.assertFalse({r['seed'] for r in plan}&set(p['partitions']['train']+p['partitions']['validation']))

    def test_model_byte_change_rejected_before_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);p,m,calls,acquire,inspect,audit=self.fixture(base)
            obj=read(base/'selected_tree.json');obj['alarm_threshold']=.5
            (base/'selected_tree.json').write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'model bytes changed'):
                run(None,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            self.assertEqual(calls,[])

    def test_guest_reproduction_required_before_any_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);p,m,calls,acquire,inspect,audit=self.fixture(base)
            (base/'results/derived/tree-review-fixture/review.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'reproduction is required'):
                run(None,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            self.assertEqual(calls,[])

    def test_existing_model_batch_cannot_be_silently_reacquired(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            base=Path(tmp);p,m,calls,acquire,inspect,audit=self.fixture(base)
            run(None,limit=1,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            with self.assertRaisesRegex(ValueError,'already registered'):
                run(None,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            self.assertEqual(len(calls),1)

    def test_acquisition_source_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);p,m,calls,acquire,inspect,audit=self.fixture(base)
            (base/'continuous_udp.py').write_text('# changed\n')
            with self.assertRaisesRegex(ValueError,'source changed'):
                run(None,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            self.assertEqual(calls,[])

    def test_failure_stops_and_keeps_raw_reference(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            base=Path(tmp);p,m,calls,acquire,inspect,audit=self.fixture(base)
            def fail(_net,**kwargs):
                acquire(_net,**kwargs);raise RuntimeError('fixture endpoint error')
            with self.assertRaisesRegex(RuntimeError,'endpoint error'):
                run(None,base=base,run_trial=fail,inspect_trial=inspect,source_auditor=audit)
            folder=next(base.glob('results/runs/*-frozen-heldout-batch'));state=read(folder/'batch.json')
            self.assertEqual(state['outcome'],'failed');self.assertEqual(len(calls),1)
            self.assertTrue(state['attempts'][0]['candidate_raw_folders'])
            with self.assertRaisesRegex(ValueError,'requires evidence review'):
                run(None,resume=folder,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)

    def test_selection_blocks_development_duplicate_and_partial_data(self):
        p=load_protocol(BASE/'dataset_protocol.json')
        selected=dict(role='heldout_test',protocol_id=p['id'],model_sha256=FROZEN_MODEL_SHA,
            runs=[dict(item,folder=f'raw-{i}') for i,item in enumerate(test_plan(p))])
        self.assertEqual(len(validate_test_selection(selected,p)),6)
        for case in ['train','duplicate','partial','path']:
            bad=copy.deepcopy(selected)
            if case=='train': bad['runs'][0].update(split='train',seed=11)
            elif case=='duplicate': bad['runs'][1]=bad['runs'][0]
            elif case=='partial': bad['runs'].pop()
            else: bad['runs'][0]['folder']='../outside'
            with self.subTest(case=case),self.assertRaises(ValueError): validate_test_selection(bad,p)

    def test_complete_test_evaluation_never_fits_or_enters_training_loader(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            base=Path(tmp);p,m,calls,acquire,inspect,audit=self.fixture(base)
            folder=run(None,limit=2,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            self.assertEqual(read(folder/'batch.json')['outcome'],'paused')
            run(None,limit=6,resume=folder,base=base,run_trial=acquire,inspect_trial=inspect,source_auditor=audit)
            self.assertEqual(len(calls),6);self.assertTrue(all(c['policy']=='fixed' for c in calls))
            state=read(folder/'batch.json')
            def load(_repo,name,_protocol):
                item=next(r for r in state['runs'] if r['folder']==name)
                rows,events=label_rows(trace([.2]*20+[.95]*12+[.2]*24))
                return rows,dict(run=name,scenario=item['scenario'],seed=item['seed'],rows=len(rows),
                    eligible=sum(r['label'] is not None for r in rows),positive=sum(r['label']==1 for r in rows),
                    negative=sum(r['label']==0 for r in rows),events=events)
            with patch.object(evaluation,'load_fixed_trace',load),patch('train_tree.fit_model',side_effect=AssertionError('Must never fit')):
                report=evaluation.evaluate(base,folder,base/'results/derived/heldout-review')
            self.assertFalse(report['fitting_performed']);self.assertFalse(report['threshold_changed'])
            self.assertEqual(sha(base/'selected_tree.json'),FROZEN_MODEL_SHA)
            with self.assertRaises(ValueError): load_data(base/'results/derived/heldout-review')


if __name__=='__main__': unittest.main()
