import copy
import json
from pathlib import Path
import tempfile
import unittest
from source_integrity import source_integrity_audit,AUDIT_POLICY


class SourceIntegrityTests(unittest.TestCase):
    def fixture(self,path,discard=1000):
        native=dict(start_monotonic_ns=1000000000,end_monotonic_ns=2000000000,
           sent_packets=1000,payload_bytes=1200,planned_bits=9600000,
           discarded_budget_bits=discard,max_pacer_gap_s=.03,error=None,
           stopped_by_signal=False,send_errors={})
        rows=[dict(monotonic_ns=1000000000+(i+1)*250000000,elapsed_s=(i+1)*.25,
             sent_packets=(i+1)*250,sent_packets_delta=250,
             discarded_budget_bits=0 if i==0 else discard) for i in range(3)]
        self.write(path,native,rows);return native,rows

    def write(self,path,native,rows):
        (path/'sender-native.json').write_text(json.dumps(native))
        (path/'sender-samples.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))

    def test_nonzero_discard_is_disclosed_with_inherited_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path)
            r=source_integrity_audit(path)
            self.assertFalse(r['legacy_zero_discard_passed'])
            self.assertEqual(r['native_discarded_budget_bits'],1000)
            self.assertEqual(r['unlogged_tail_packets'],250)
            self.assertEqual(r['sampled_discard_increments'][0]['sample'],1)
            self.assertEqual(AUDIT_POLICY['max_discard_fraction'],.05)

    def test_zero_discard_remains_identified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path,0)
            self.assertTrue(source_integrity_audit(path)['legacy_zero_discard_passed'])

    def test_existing_five_percent_limit_is_not_relaxed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path,480001)
            with self.assertRaisesRegex(ValueError,'5%'): source_integrity_audit(path)

    def test_native_tail_discard_is_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);native,rows=self.fixture(path,1000)
            native['discarded_budget_bits']=1500;self.write(path,native,rows)
            self.assertEqual(source_integrity_audit(path)['unlogged_tail_discard_bits'],500)

    def test_corrupt_times_counts_deltas_and_discard_rejected(self):
        for case in ['time','outside','count','delta','discard_regression','discard_overflow','nan','empty','signal']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp);native,rows=self.fixture(path)
                if case=='time': rows[1]['monotonic_ns']=rows[0]['monotonic_ns']
                elif case=='outside': rows[-1]['monotonic_ns']=native['end_monotonic_ns']+1
                elif case=='count': rows[1]['sent_packets']=200
                elif case=='delta': rows[1]['sent_packets_delta']=249
                elif case=='discard_regression': rows[-1]['discarded_budget_bits']=0
                elif case=='discard_overflow': rows[-1]['discarded_budget_bits']=1001
                elif case=='nan': rows[-1]['discarded_budget_bits']=float('nan')
                elif case=='empty': rows=[]
                else: native['stopped_by_signal']=True
                self.write(path,native,rows)
                with self.assertRaisesRegex(ValueError,'Source integrity failed'): source_integrity_audit(path)


if __name__=='__main__': unittest.main()
