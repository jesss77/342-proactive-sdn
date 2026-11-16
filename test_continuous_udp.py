"""Protocol/pacing tests and a host-loopback control, not Mininet acceptance."""
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from continuous_udp import Schedule, Pacer, packet, decode, canonical_summaries
from traffic_scenarios import continuous_schedule


class ContinuousTests(unittest.TestCase):
    def test_linear_schedule_integral_and_continuity(self):
        s = Schedule([dict(requested_bps=100, end_bps=300, requested_seconds=2),
                      dict(requested_bps=300, end_bps=100, requested_seconds=2)])
        self.assertEqual([s.cumulative_bits(t) for t in [0, 1, 2, 3, 4, 5]],
                         [0, 150, 400, 650, 800, 800])
        self.assertEqual(s.index(2), 1)

    def test_pacer_caps_catchup_and_records_discard(self):
        p = Pacer(Schedule([dict(requested_bps=96000, requested_seconds=2)]), 1200, 2)
        self.assertEqual(p.advance(.5), 2)
        self.assertEqual(p.discarded_bits, 28800)
        self.assertEqual(p.advance(.65), 1)
        self.assertEqual(p.credit, 4800)
        with self.assertRaises(ValueError):
            p.advance(.6)

    def test_packet_identity_size_and_sequence(self):
        run_id = uuid.uuid4().hex
        data = packet(run_id, 123, 456, 1200)
        self.assertEqual(len(data), 1200)
        self.assertEqual(decode(data, run_id, 1200), (123, 456))
        with self.assertRaises(ValueError):
            decode(data, uuid.uuid4().hex, 1200)
        with self.assertRaises(ValueError):
            decode(data[:-1], run_id, 1200)

    def test_invalid_schedule_rejected(self):
        for segments in [[], [dict(requested_bps=0, requested_seconds=1)],
                         [dict(requested_bps=1, requested_seconds=float('nan'))],
                         [dict(requested_bps=1, end_bps=-1, requested_seconds=1)]]:
            with self.assertRaises(ValueError):
                Schedule(segments)

    def test_continuous_schedules_reproducible_and_duration_fixed(self):
        for name in ['steady', 'ramp', 'bursty']:
            a = continuous_schedule(name, 12_000_000, 60, 11)
            self.assertEqual(a, continuous_schedule(name, 12_000_000, 60, 11))
            self.assertAlmostEqual(sum(s['requested_seconds'] for s in a), 60)
            self.assertAlmostEqual(Schedule(a).duration, 60)
        self.assertNotEqual(continuous_schedule('ramp', seed=1), continuous_schedule('ramp', seed=2))
        self.assertNotEqual(continuous_schedule('bursty', seed=1), continuous_schedule('bursty', seed=2))

    def endpoints(self):
        run_id = uuid.uuid4().hex
        sender = dict(run_id=run_id, payload_bytes=1200, sent_packets=10, sent_bytes=12000,
                      start_monotonic_ns=1_000_000_000, end_monotonic_ns=2_000_000_000,
                      stopped_by_signal=False, send_errors={})
        receiver = dict(run_id=run_id, payload_bytes=1200, unique_packets=8,
                        unique_bytes=9600, highest_sequence=9, jitter_ns=100000,
                        last_received_monotonic_ns=2_100_000_000)
        return sender, receiver

    def test_accounting_uses_sender_total_including_trailing_loss(self):
        sender, receiver = self.endpoints()
        tx, rx = canonical_summaries(sender, receiver)
        self.assertEqual(rx['end']['sum_received']['lost_packets'], 2)
        self.assertEqual(rx['end']['sum_received']['lost_percent'], 20)
        self.assertAlmostEqual(rx['end']['sum_received']['seconds'], 1.1)
        self.assertEqual(tx['end']['sum_sent']['lost_packets'], 0)

    def test_endpoint_mismatch_and_corrupt_counts_rejected(self):
        sender, receiver = self.endpoints()
        for change in [dict(run_id=uuid.uuid4().hex), dict(unique_bytes=9601),
                       dict(highest_sequence=10), dict(unique_packets=11)]:
            with self.assertRaises(ValueError):
                canonical_summaries(sender, dict(receiver, **change))
        with self.assertRaises(ValueError):
            canonical_summaries(dict(sender, stopped_by_signal=True), receiver)

    def test_host_loopback_persistent_two_phase_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            run_id = uuid.uuid4().hex
            plan = dict(run_id=run_id, segments=[
                dict(requested_bps=1_000_000, requested_seconds=.25),
                dict(requested_bps=2_000_000, requested_seconds=.25)])
            (folder / 'plan.json').write_text(json.dumps(plan))
            script = Path(__file__).with_name('continuous_udp.py')
            common = ['--plan', str(folder / 'plan.json'), '--host', '127.0.0.1']
            receiver = subprocess.Popen([sys.executable, str(script), 'receive', *common,
                '--port', '0', '--output', str(folder / 'rx.json'), '--samples', str(folder / 'rx.jsonl'),
                '--ready', str(folder / 'ready.json'), '--max-duration', '2'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic()+5
                while not (folder / 'ready.json').exists():
                    if receiver.poll() is not None or time.monotonic() > deadline:
                        raise AssertionError('Loopback receiver readiness failed: ' + receiver.communicate(timeout=1)[1])
                    time.sleep(.01)
                port = json.loads((folder / 'ready.json').read_text())['address'][1]
                result = subprocess.run([sys.executable, str(script), 'send', *common,
                    '--port', str(port), '--output', str(folder / 'tx.json'),
                    '--samples', str(folder / 'tx.jsonl')], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                if os.name == 'posix':
                    receiver.send_signal(signal.SIGINT)
                receiver.wait(timeout=5)
                self.assertEqual(receiver.returncode, 0, receiver.stderr.read())
                tx = json.loads((folder / 'tx.json').read_text())
                rx = json.loads((folder / 'rx.json').read_text())
                self.assertTrue(all(n > 0 for n in tx['segment_sent_packets']))
                self.assertGreater(rx['unique_packets'], 0, json.dumps(dict(tx=tx, rx=rx)))
                self.assertLess(rx['highest_sequence'], tx['sent_packets'])
                self.assertEqual(rx['stopped_by_signal'], os.name == 'posix')
                _client, server = canonical_summaries(tx, rx)
                self.assertEqual(server['end']['sum_received']['lost_packets'],
                                 tx['sent_packets']-rx['unique_packets'])
            finally:
                if receiver.poll() is None:
                    receiver.terminate()
                    receiver.wait(timeout=3)
                receiver.stdout.close()
                receiver.stderr.close()

    @unittest.skipUnless(os.name == 'posix', 'Recorder uses POSIX endpoint shutdown; tested in Ubuntu')
    def test_recorded_loopback_trial_lifecycle(self):
        import io
        import shutil
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import run_continuous_trial as recorder
        real_popen = subprocess.Popen
        class Stats:
            returncode = None
            def poll(self): return self.returncode
            def send_signal(self, sig): self.returncode = -int(sig)
            def wait(self, **kwargs): return self.returncode
            def kill(self): self.returncode = -9
        def popen(command, **kwargs):
            return Stats() if command[0] == 'vmstat' else real_popen(command, **kwargs)
        class Node:
            def __init__(self, name): self.name = name
            def IP(self): return '127.0.0.1'
            def pexec(self, command):
                if command[0] == 'nstat':
                    return 'UdpInErrors 0\nUdpRcvbufErrors 0\nUdpSndbufErrors 0\n', '', 0
                return 'qdisc fixture (dropped 0)\n', '', 0
            def popen(self, command, **kwargs): return real_popen(command, **kwargs)
        class Net(dict):
            def get(self, *names): return [self[name] for name in names]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ['continuous_udp.py', 'run_continuous_trial.py',
                         'experiment_config.py', 'traffic_scenarios.py']:
                shutil.copy2(Path(__file__).with_name(name), base / name)
            for name in ['topology.py', 'diamond_controller.py', 'requirements.txt']:
                (base / name).write_text('# loopback fixture only\n')
            net = Net({name: Node(name) for name in ['h1', 'h2', 's1', 's2', 's4']})
            with patch.object(recorder, 'verify_route', return_value={'fixture': True}), patch.object(
                    recorder.subprocess, 'Popen', side_effect=popen), redirect_stdout(io.StringIO()):
                proof_calls = []
                def owned_proof(_net, route, folder, phase='before'):
                    proof_calls.append(phase)
                    return dict(mode='owned_hostpair', selected_route=route)
                created = []
                import threading
                abort = threading.Event()
                out = recorder.run(net, base, requested_bps=1_000_000, duration=1, udp_port=0,
                    route_verifier=owned_proof, trial_context=dict(route_verification='owned_hostpair'),
                    capture_links=recorder.route_spec('primary')['links'], on_created=created.append,
                    abort_event=abort)
                self.assertEqual(created, [out])
                self.assertEqual(proof_calls, ['before', 'after'])
            metadata = json.loads((out / 'metadata.json').read_text())
            self.assertEqual(metadata['outcome'], 'completed', metadata)
            self.assertEqual(metadata['forwarding_before']['mode'], 'owned_hostpair')
            self.assertEqual(metadata['trial_context']['route_verification'], 'owned_hostpair')
            self.assertEqual(metadata['exits']['client'], 0)
            self.assertEqual(metadata['exits']['server'], 0)
            self.assertTrue((out / 'sender-native.json').exists())
            self.assertTrue((out / 'receiver-native.json').exists())
            server = json.loads((out / 'server.json').read_text())
            self.assertGreater(server['end']['sum_received']['bytes'], 0)


if __name__ == '__main__':
    unittest.main()
