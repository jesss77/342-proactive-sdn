import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import packet_activation as capture
import run_activation_pilot as pilot

BASE = Path(__file__).resolve().parent
NS = 1_000_000_000
SENDER = dict(run_id='11'*16,payload_bytes=1200,sent_packets=2,start_monotonic_ns=100*NS,end_monotonic_ns=160*NS)


def frame(sequence=0, token=None, sent_ns=110*NS):
    eth = bytes(12)+b'\x08\x00'
    ip = bytearray(20); ip[0]=0x45; ip[2:4]=struct.pack('!H',1228); ip[9]=17
    ip[12:16]=bytes([10,0,0,1]); ip[16:20]=bytes([10,0,0,2])
    udp=struct.pack('!HHHH',12345,5202,1208,0)
    payload=capture.HEADER.pack(b'S342',bytes.fromhex(token or SENDER['run_id']),sequence,sent_ns)+bytes(1164)
    return eth+ip+udp+payload


def pcap(path, packets, order='<', unit=1):
    magic={('<',1):b'\x4d\x3c\xb2\xa1',('>',1):b'\xa1\xb2\x3c\x4d',
           ('<',1000):b'\xd4\xc3\xb2\xa1',('>',1000):b'\xa1\xb2\xc3\xd4'}[order,unit]
    with Path(path).open('wb') as f:
        f.write(magic+struct.pack(order+'HHIIII',2,4,0,0,128,1))
        for stamp, data in packets:
            f.write(struct.pack(order+'IIII',stamp//NS,(stamp%NS)//unit,min(128,len(data)),len(data)))
            f.write(data[:128])


class DecoderTests(unittest.TestCase):
    def test_endian_precision_and_intentionally_short_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            for order in ['<','>']:
                for unit in [1,1000]:
                    p=Path(tmp)/'frame.pcap';pcap(p,[(1710*NS+2_000_000,frame())],order,unit)
                    r=capture.read_pcap(p,SENDER,5202)
                    self.assertEqual(r['records'][0]['sequence'],0)
                    self.assertEqual(r['records'][0]['sent_monotonic_ns'],110*NS)
                    self.assertEqual(r['timestamp_unit_ns'],unit)

    def test_corrupt_truncated_wrong_identity_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.pcap'
            for data in [frame(token='22'*16),frame(sequence=2),frame(sent_ns=99*NS)]:
                pcap(p,[(1710*NS,data)])
                with self.assertRaises(ValueError):capture.read_pcap(p,SENDER,5202)
            pcap(p,[(1710*NS,frame()),(1711*NS,frame())])
            with self.assertRaisesRegex(ValueError,'Duplicate'):capture.read_pcap(p,SENDER,5202)
            pcap(p,[(1710*NS,frame())]);p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError,'Truncated'):capture.read_pcap(p,SENDER,5202)

    def test_fragment_wrong_port_and_non_ethernet_rejected(self):
        data=bytearray(frame());data[20:22]=struct.pack('!H',0x2000)
        with self.assertRaisesRegex(ValueError,'fragmented'):capture.decode_frame(data,len(data),SENDER,5202)
        with self.assertRaisesRegex(ValueError,'port'):capture.decode_frame(frame(),1242,SENDER,9999)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'link.pcap';pcap(p,[]);b=bytearray(p.read_bytes());b[20:24]=struct.pack('<I',113);p.write_bytes(b)
            with self.assertRaisesRegex(ValueError,'link type'):capture.read_pcap(p,SENDER,5202)

    def fixture(self,folder,alternate=True):
        processes={d:dict(exit=0,forced_kill=False,cpu_seconds=.1) for d in capture.INTERFACES}
        (folder/'capture-processes.json').write_text(json.dumps(processes))
        for i,d in enumerate(capture.INTERFACES):
            packets=[(1710*NS+2_000_000,frame())] if i==0 else ([(1720*NS+2_000_000,frame(1,sent_ns=120*NS))] if alternate else [])
            pcap(folder/(d+'.pcap'),packets)
            n=len(packets)
            (folder/(d+'.tcpdump.log')).write_text(f'{n} packets captured\n{n} packets received by filter\n0 packets dropped by kernel\n')
        return dict(offset_low_ns=1600*NS-1000,offset_high_ns=1600*NS+1000,first_monotonic_ns=98*NS,last_monotonic_ns=165*NS)

    def test_selected_packet_uses_capture_time_not_embedded_send_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);bounds=self.fixture(folder)
            action=dict(started=119.9,decision_at=119.8,admission=dict(observed_at=119.7))
            r=capture.analyze_capture(folder,SENDER,dict(unique_packets=1),5202,bounds,action)
            lo,hi=r['timing']['first_alternate_after_decision_s']
            self.assertAlmostEqual((lo+hi)/2,.202,places=6)
            self.assertEqual(r['captured_union_datagrams'],2)  # Downstream loss does not invalidate egress capture.
            self.assertEqual(r['timing']['first_alternate_packet']['sequence'],1)

    def test_capture_loss_missing_packet_and_unlogged_switch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);bounds=self.fixture(folder)
            with self.assertRaisesRegex(ValueError,'without a recorded action'):
                capture.analyze_capture(folder,SENDER,{},5202,bounds,None)
            (folder/(capture.INTERFACES[0]+'.tcpdump.log')).write_text('1 packet captured\n1 packet received by filter\n1 packet dropped by kernel\n')
            with self.assertRaisesRegex(ValueError,'dropped packets'):
                capture.analyze_capture(folder,SENDER,{},5202,bounds,None)
            bounds=self.fixture(folder,alternate=False)
            with self.assertRaisesRegex(ValueError,'reconcile'):
                capture.analyze_capture(folder,SENDER,{},5202,bounds,None)

    def test_no_action_is_retained_without_fabricated_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);bounds=self.fixture(folder,alternate=False)
            r=capture.analyze_capture(folder,dict(SENDER,sent_packets=1),{},5202,bounds,None)
            self.assertIsNone(r['timing']);self.assertFalse(r['observed_switch'])


class ClockAndLifecycleTests(unittest.TestCase):
    def test_offset_drift_bracket_gap_and_source_coverage(self):
        rows=[dict(before_ns=(98*NS+i*NS//2),wall_ns=(1698*NS+i*NS//2+1000),after_ns=(98*NS+i*NS//2+2000)) for i in range(135)]
        self.assertEqual(capture.clock_bounds(rows,100*NS,160*NS)['observed_envelope_ns'],2000)
        for change in ['drift','bracket','gap','coverage']:
            bad=[dict(x) for x in rows]
            if change=='drift':bad[50]['wall_ns']+=20_000_000
            if change=='bracket':bad[50]['after_ns']+=20_000_000
            if change=='gap':bad[50]['before_ns']-=3*NS
            finish=170*NS if change=='coverage' else 160*NS
            with self.subTest(change=change),self.assertRaises(ValueError):capture.clock_bounds(bad,100*NS,finish)

    def test_clock_thread_stops_and_preserves_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'clock.jsonl';probe=capture.ClockProbe(p);probe.start();probe.stop()
            self.assertFalse(probe.thread.is_alive())
            self.assertGreaterEqual(len(p.read_text().splitlines()),2)

    def test_both_capture_children_and_clock_stop_after_worker_or_startup_failure(self):
        for startup_failure in [False,True]:
            calls=[]
            class Probe:
                def __init__(self,p):pass
                def start(self):calls.append('clock_start')
                def stop(self):calls.append('clock_stop')
            class Cap:
                def __init__(self,p,d):self.interface=d
                def start(self):
                    calls.append('start_'+self.interface)
                    if startup_failure and self.interface==capture.INTERFACES[-1]:raise RuntimeError('startup')
                def stop(self):calls.append('stop_'+self.interface);return dict(exit=0)
            def bad(*a,**k):raise RuntimeError('worker')
            with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(RuntimeError,'execution/cleanup'):
                pilot.execute_step(None,BASE,dict(capture=True),Path(tmp),run_fn=bad,probe_factory=Probe,capture_factory=Cap)
            self.assertIn('clock_stop',calls)
            self.assertTrue(all('stop_'+d in calls for d in capture.INTERFACES))

    def test_wait4_preserves_per_capture_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=capture.Capture(tmp,capture.INTERFACES[0]);c.started=1.;signals=[]
            c.proc=SimpleNamespace(pid=123,returncode=None,send_signal=lambda s:signals.append(s),kill=lambda:None)
            usage=SimpleNamespace(ru_utime=.02,ru_stime=.01)
            with patch.object(capture.os,'wait4',return_value=(123,0,usage),create=True), \
                 patch.object(capture.os,'WNOHANG',1,create=True), \
                 patch.object(capture.os,'waitstatus_to_exitcode',return_value=0,create=True):r=c.stop()
            self.assertEqual(r['exit'],0);self.assertAlmostEqual(r['cpu_seconds'],.03)
            self.assertEqual(len(signals),1);self.assertIs(c.stop(),r)


class BatchTests(unittest.TestCase):
    def fixture(self,base):
        self.base=base;(base/'results/runs').mkdir(parents=True);(base/pilot.PROTOCOL).write_text('{}')
        self.p=dict(frozen_source_sha256={},additional_source_sha256={});self.calls=[]

    def env(self,p):(p/'environment.json').write_text('{}')
    def ready(self,net,base,p):p.mkdir();(p/'ready.json').write_text('{}')
    def execute(self,net,base,item,out):
        self.calls.append(item['step']);root=base/'results/runs'
        raw=root/('policy-'+item['step']);raw.mkdir();trial=root/('trial-'+item['step']);trial.mkdir()
        (raw/'policy.json').write_text(json.dumps(dict(trial=trial.name)));(trial/'source.json').write_text('{}')
        return raw
    def inspect(self,base,out,raw,item):
        return dict(step=item['step'],capture_enabled=item['capture'],outcome='completed',screen_failures=[],
            sender_mbps=8.,receiver_mbps=8.,udp_loss_percent=0.,clock_mapping={},capture=None)
    def call(self,step='before',**kw):
        with patch.object(pilot,'load_protocol',return_value=self.p),patch.object(pilot,'verify_parent',return_value={}),contextlib.redirect_stdout(io.StringIO()):
            return pilot.run(None,step,base=self.base,executor=kw.pop('executor',self.execute),inspector=kw.pop('inspector',self.inspect),
                environment_check=self.env,readiness_check=self.ready,**kw)
    def batch(self):
        root=self.base/'results/runs';return root/json.loads((root/pilot.REGISTRY).read_text())['batch']

    def test_off_on_off_order_once_per_call_and_no_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp));self.call()
            with self.assertRaisesRegex(ValueError,'Next registered'):self.call('after')
            self.call('capture');self.call('after')
            self.assertEqual(self.calls,['before','capture','after'])
            with self.assertRaisesRegex(ValueError,'already complete'):self.call('after')

    def test_quality_failure_keeps_raw_and_blocks_every_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp))
            def bad(*a):r=self.inspect(*a);r['screen_failures']=['collector_quality'];return r
            with self.assertRaisesRegex(ValueError,'quality failed'):self.call(inspector=bad)
            state=json.loads((self.batch()/'batch.json').read_text())
            self.assertEqual(state['outcome'],'failed');self.assertEqual(len(state['new_raw_folders']),2)
            self.assertTrue((self.batch()/'before/review.json').exists())
            for step in ['before','capture']:
                with self.assertRaisesRegex(ValueError,'cannot retry'):self.call(step)

    def test_changed_clock_capture_or_policy_evidence_blocks_next_call(self):
        for target in ['step','policy']:
            with tempfile.TemporaryDirectory() as tmp:
                self.fixture(Path(tmp));self.call()
                p=self.batch()/'before/environment/environment.json' if target=='step' else self.base/'results/runs/policy-before/policy.json'
                p.write_text('changed')
                with self.assertRaisesRegex(ValueError,'changed'):self.call('capture')
                self.assertEqual(self.calls,['before'])

    def test_real_registration_is_additive_and_matches_reported_capture_capability(self):
        p=pilot.load_protocol(BASE)
        self.assertEqual(len(p['frozen_source_sha256']),76)
        self.assertEqual([r['capture'] for r in p['plan']],[False,True,False])
        self.assertEqual(p['settings']['capture_interfaces'],['s1-eth3','s1-eth4'])
        self.assertEqual(p['settings']['direction'],'out')


if __name__=='__main__':unittest.main()
