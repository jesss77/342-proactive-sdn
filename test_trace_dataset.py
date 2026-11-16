import copy
import unittest
from build_trace_dataset import (CONFIG, FEATURES, covers, detect_events, features_at,
                                 intervals, label_rows, weighted_mean)


def trace(values, dt=.25):
    return [dict(t0=i*dt,t1=(i+1)*dt,available=(i+1)*dt+.002,valid=True,
                 utilization=v,upstream_bps=v*1e7,queue_packets=0,backlog_bytes=0,
                 drops_delta=0,drops_per_s=0,query_duration_s=.004)
            for i,v in enumerate(values)]


class DatasetTests(unittest.TestCase):
    def test_onset_not_confirmation_is_label_target(self):
        rows=trace([.2]*20+[.95]*8+[.2]*24)
        labeled, events=label_rows(rows)
        self.assertEqual(events[0]['onset'],5)
        self.assertAlmostEqual(events[0]['confirmed_available'],6.002)
        r=next(r for r in labeled if abs(r['available']-4.002)<.0001)
        self.assertEqual(r['label'],1)
        self.assertAlmostEqual(r['lead_to_onset_s'],.998)
        self.assertEqual(next(r for r in labeled if abs(r['available']-5.252)<.0001)['excluded_reason'],
                         'event_already_started')

    def test_future_requires_horizon_plus_confirmation(self):
        rows=trace([.2]*40)
        labeled,_=label_rows(rows)
        self.assertIsNone(next(r for r in labeled if abs(r['available']-7.502)<.0001)['label'])
        self.assertEqual(next(r for r in labeled if abs(r['available']-6.002)<.0001)['label'],0)
        self.assertIsNone(next(r for r in labeled if abs(r['available']-6.502)<.0001)['label'])

    def test_no_event_bridge_over_invalid_read(self):
        rows=trace([.2]*12+[.95]*3+[.95]+[.95]*3+[.2]*24)
        rows[15]['valid']=False
        self.assertEqual(detect_events(rows),[])
        labeled,_=label_rows(rows)
        self.assertEqual(labeled[15]['excluded_reason'],'invalid_sample')
        self.assertIsNone(labeled[14]['label'])

    def test_high_after_gap_is_left_censored(self):
        rows=trace([.2]*12+[.95]*12+[.2]*24)
        rows[11]['valid']=False
        events=detect_events(rows)
        self.assertFalse(events[0]['onset_observed'])

    def test_history_uses_seconds_and_actual_duration(self):
        rows=trace([.2,.8],dt=1)
        self.assertAlmostEqual(weighted_mean(rows,'utilization',.5,2),.6)
        features=features_at(rows)
        self.assertAlmostEqual(features['util_mean_2s'],.5)
        self.assertEqual(set(features),set(FEATURES))

    def test_future_mutation_cannot_change_features(self):
        rows=trace([.2]*20+[.95]*12+[.2]*24)
        before=label_rows(rows)[0][15]['features']
        for r in rows[16:]: r.update(utilization=8,upstream_bps=8e7)
        self.assertEqual(before,label_rows(rows)[0][15]['features'])

    def test_short_history_and_left_censored_start_excluded(self):
        rows=trace([.95]*20+[.2]*24)
        labeled,events=label_rows(rows)
        self.assertFalse(events[0]['onset_observed'])
        self.assertEqual(labeled[0]['excluded_reason'],'incomplete_past_history')
        self.assertEqual(labeled[10]['excluded_reason'],'event_already_started')

    def test_short_spike_is_not_sustained_event(self):
        self.assertEqual(detect_events(trace([.2]*12+[.95]*3+[.2]*24)),[])

    def test_gap_is_not_imputed_for_history_or_future(self):
        rows=trace([.2]*40)
        del rows[20]
        self.assertFalse(covers(rows,4,6))
        self.assertIsNone(features_at(rows[:22]))

    def test_feature_allowlist_has_no_future_or_identity(self):
        for forbidden in ['seed','scenario','run','planned_bps','label','lead_to_onset_s']:
            self.assertNotIn(forbidden,FEATURES)

    def test_midpoint_rates_wait_for_read_completion_and_reset_rejected(self):
        raw=[]
        for i in range(3):
            qs={}
            for dev,cap in [('s1-eth3',100000000),('s2-eth2',10000000)]:
                qs[dev]=dict(tc_exit=0,tc_start=i*.25,tc_end=i*.25+.01,capacity_bps=cap,
                    root_qdisc=dict(root=True,bytes=i*1000,drops=0,backlog=0,qlen=0))
            raw.append(dict(schema_version=5,route='primary',requested_interval=.25,qdiscs=qs))
        records=intervals(raw,0,1)
        self.assertAlmostEqual(records[0]['available'],.26)
        self.assertAlmostEqual(records[0]['utilization'],.0032)
        raw[2]['qdiscs']['s2-eth2']['root_qdisc']['bytes']=0
        self.assertFalse(intervals(raw,0,1)[-1]['valid'])


if __name__=='__main__': unittest.main()
