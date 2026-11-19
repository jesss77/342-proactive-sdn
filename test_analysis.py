from pathlib import Path
import importlib.util
import tempfile
import unittest

root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('matched_analysis',root/'tools/analyze_matched.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)

class AnalysisTests(unittest.TestCase):
    def test_pairs_are_by_seed_and_keep_losses_in_percentage_points(self):
        rows=[]
        for seed in [41,42,43]:
            rows.extend([dict(policy='fixed',scenario='ramp',seed=seed,receiver_mbps=7.,udp_loss_percent=10.),
                         dict(policy='ml',scenario='ramp',seed=seed,receiver_mbps=8.,udp_loss_percent=2.)])
        result=analysis.summarize(list(reversed(rows)))
        pair=next(x for x in result['paired'] if x['scenario']=='ramp' and x['policy']=='ml')
        self.assertEqual(pair['metrics']['receiver_mbps']['mean'],1.)
        self.assertEqual(pair['metrics']['udp_loss_percent']['mean'],-8.)
        self.assertEqual(pair['metrics']['receiver_mbps']['n'],3)

    def test_missing_rtt_and_absent_actions_are_not_imputed_as_zero(self):
        rows=[dict(policy='fixed',scenario='steady',seed=41,traffic_reply_p95_ms=None,actions=0),
              dict(policy='ml',scenario='steady',seed=41,traffic_reply_p95_ms=12.,actions=1)]
        result=analysis.summarize(rows)
        pair=next(x for x in result['paired'] if x['scenario']=='steady' and x['policy']=='ml')
        self.assertEqual(pair['metrics']['traffic_reply_p95_ms']['n'],0)
        self.assertIsNone(pair['metrics']['traffic_reply_p95_ms']['mean'])
        self.assertEqual(pair['metrics']['actions']['mean'],1)

    def test_worse_results_keep_their_sign(self):
        rows=[dict(policy='fixed',scenario='bursty',seed=41,receiver_mbps=8.),
              dict(policy='ml',scenario='bursty',seed=41,receiver_mbps=6.)]
        result=analysis.summarize(rows)
        pair=next(x for x in result['paired'] if x['scenario']=='bursty' and x['policy']=='ml')
        self.assertEqual(pair['metrics']['receiver_mbps']['mean'],-2.)

    def test_derivatives_cannot_overwrite_preserved_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'outside the preserved'):
                analysis.analyze(tmp,None,Path(tmp)/'results/derived')

if __name__=='__main__':unittest.main()
