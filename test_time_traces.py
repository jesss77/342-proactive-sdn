import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'tools'))
from build_time_traces import sender_intervals,queue_intervals,path_observation

class TraceTests(unittest.TestCase):
    def test_actual_times_and_unlogged_tail_conserve_packets(self):
        rows=sender_intervals([dict(monotonic_ns=101000000000,sent_packets=10),
            dict(monotonic_ns=103000000000,sent_packets=30)],
            dict(start_monotonic_ns=100000000000,end_monotonic_ns=104000000000,sent_packets=35))
        self.assertEqual([r['packets_delta'] for r in rows],[10,20,5])
        self.assertEqual([r['payload_bps'] for r in rows],[96000,96000,48000])
        with self.assertRaisesRegex(ValueError,'reset'):
            sender_intervals([dict(monotonic_ns=101000000000,sent_packets=40),dict(monotonic_ns=102000000000,sent_packets=30)],
                dict(start_monotonic_ns=100000000000,end_monotonic_ns=104000000000,sent_packets=40))

    def test_missing_queue_does_not_bridge_or_borrow(self):
        raw=[]
        for i in range(5):
            q=dict(tc_start=i*.25,tc_end=i*.25+.004,tc_exit=0,capacity_bps=10e6,
                root_qdisc=dict(bytes=i*1000,drops=0,backlog=0,qlen=0))
            raw.append(dict(utc='fixture',requested_interval=.25,qdiscs={'s2-eth2':q} if i!=2 else {'s1-eth4':q}))
        rows=queue_intervals(raw,'s2-eth2',0)
        self.assertEqual(len(rows),2)
        self.assertAlmostEqual(rows[0]['available_s'],.254)
        self.assertAlmostEqual(rows[1]['t0_s'],.752)

    def test_counter_envelope_not_clipped_into_fake_packet_proof(self):
        obs=path_observation([dict(valid=True,departure_bps=100,observation_left_s=.8,observation_right_s=1.1)],dict(started_s=1.0))
        self.assertEqual(obs['left_s'],.8)
        self.assertIn('not a first-UDP',obs['meaning'])
        self.assertIsNone(path_observation([],None))

if __name__=='__main__':unittest.main()
