import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from build_trace_dataset import FEATURES,label_rows
from test_trace_dataset import trace
from fixed_trace_dataset import development_plan,load_protocol
from tree_model import TreeModel,canonical_hash
from tree_metrics import binary_metrics,row_report,warning_report
from train_tree import training_weights,fit_model,export_model,load_data

BASE=Path(__file__).resolve().parent


def features(value=.2): return {name:value if name=='utilization' else 0. for name in FEATURES}
def model():
    return dict(format='cmps342-cart-json-v1',features=FEATURES,alarm_threshold=.5,nodes=[
       dict(feature=0,threshold=.5,left=1,right=2,p1=.5),
       dict(feature=-1,threshold=0,left=-1,right=-1,p1=.1),
       dict(feature=-1,threshold=0,left=-1,right=-1,p1=.9)])


class PortableTreeTests(unittest.TestCase):
    def test_split_tie_and_float32_comparison(self):
        tree=TreeModel(model())
        self.assertFalse(tree.alarm(features(.5)))
        self.assertFalse(tree.alarm(features(.500000001)))
        self.assertTrue(tree.alarm(features(.5001)))

    def test_input_allowlist_and_nonfinite_values_rejected(self):
        for mutation in ['extra','missing','nan','overflow']:
            x=features()
            if mutation=='extra': x['seed']=11
            elif mutation=='missing': x.pop(FEATURES[-1])
            elif mutation=='nan': x['utilization']=float('nan')
            else: x['utilization']=1e99
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): TreeModel(model()).probability(x)

    def test_invalid_or_unreachable_nodes_rejected(self):
        for mutation in ['cycle','shared','probability','unreachable','feature']:
            m=model()
            if mutation=='cycle': m['nodes'][0]['left']=0
            elif mutation=='shared': m['nodes'][0]['right']=1
            elif mutation=='probability': m['nodes'][1]['p1']=2
            elif mutation=='unreachable': m['nodes'].append(copy.deepcopy(m['nodes'][-1]))
            else: m['features']=list(reversed(FEATURES))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): TreeModel(m)

    def test_row_metrics_keep_scenarios_separate(self):
        rows=[dict(label=1,scenario='ramp',run='a'),dict(label=1,scenario='bursty',run='b')]
        r=row_report(rows,[1,0],.5)
        self.assertEqual(r['scenario_macro_f1'],.5)
        self.assertEqual(r['by_scenario']['bursty']['recall'],0)

    def test_warning_replay_uses_features_not_labels_for_episode_times(self):
        labeled,events=label_rows(trace([.2]*20+[.95]*8+[.2]*40))
        rows=[dict(run='a',scenario='ramp',**r) for r in labeled]
        probs=[1. if 15<=i<=24 else 0. for i in range(len(rows))]
        summary=[dict(run='a',scenario='ramp',events=events)]
        report=warning_report(rows,probs,summary,.5)['by_run'][0]
        self.assertEqual(report['true_warnings'],1);self.assertAlmostEqual(report['median_lead_s'],.998)
        for r in rows: r['label']=0
        again=warning_report(rows,probs,summary,.5)['by_run'][0]
        self.assertEqual(report['alarms'],again['alarms'])

    def test_equal_run_training_weight(self):
        rows=[{'run':'a'}]*2+[{'run':'b'}]*8
        weights=training_weights(rows)
        self.assertAlmostEqual(sum(weights[:2]),sum(weights[2:]))

    def test_development_loader_blocks_test_and_future_features(self):
        protocol=load_protocol(BASE/'dataset_protocol.json')
        selection=dict(protocol_id=protocol['id'],runs=[dict(item,folder=f'raw-{i}') for i,item in enumerate(development_plan(protocol))])
        for case in ['test','feature']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                summary=dict(complete_development=True,protocol=protocol,source_audit_policy={'id':'measured-fixed-source-integrity-v1'},feature_allowlist=FEATURES)
                row=dict(run='raw-0',scenario='ramp',seed=11,split='test' if case=='test' else 'train',available=1.,
                    features=dict(features(),planned_bps=1) if case=='feature' else features(),label=0,excluded_reason=None)
                for name,value in [('protocol.json',protocol),('selection.json',selection),('summary.json',summary)]:
                    (folder/name).write_text(json.dumps(value))
                (folder/'rows.jsonl').write_text(json.dumps(row)+'\n')
                with self.assertRaises(ValueError): load_data(folder)


@unittest.skipUnless(importlib.util.find_spec('sklearn') is not None,'Optional sklearn training dependency; portable inference does not require it')
class SklearnTreeTests(unittest.TestCase):
    def rows(self):
        return [dict(run='a' if i<10 else 'b',split='train',features=features(i/20),label=int(i>=10)) for i in range(20)]

    def test_fit_rejects_validation_rows(self):
        rows=self.rows();rows[0]['split']='validation'
        with self.assertRaises(ValueError): fit_model(rows,dict(max_depth=2,min_samples_leaf=2,class_weight=None))

    def test_export_matches_library_probabilities(self):
        rows=self.rows();params=dict(max_depth=2,min_samples_leaf=2,class_weight=None)
        fitted=fit_model(rows,params)
        exported=export_model(fitted,.5,params,'fixture',{'id':'p','label_config':{},'profile_id':'p','source_sha256':{'build_trace_dataset.py':'x'}})
        tree=TreeModel(exported)
        for x in [i/37 for i in range(38)]:
            f=features(x);expected=fitted.predict_proba([[f[k] for k in FEATURES]])[0][1]
            self.assertAlmostEqual(tree.probability(f),expected)


if __name__=='__main__': unittest.main()
