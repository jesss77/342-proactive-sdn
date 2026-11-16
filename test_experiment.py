"""Local contract tests; Linux/Mininet measurements remain separate acceptance tests."""
import json
from pathlib import Path
import tempfile
import unittest
import os
import shutil
from experiment_config import calibrated_profile, route_spec, validate_flow
from collect_path import root_qdisc, query_qdisc, query_qdiscs
from inspect_experiment import sample_intervals, counter_delta, inspect_trial, ping_statistics, queue_rows, queue_summary
from traffic_scenarios import schedule


class FakeNode:
    def __init__(self, state, fail_interface=None):
        self.state = state
        self.fail_interface = fail_interface

    def pexec(self, args):
        interface = args[args.index('dev') + 1]
        if args[1] == '-s' and args[2] == 'class':
            rate = 10 if interface == 's2-eth2' else 20 if interface in ['s1-eth4', 's3-eth2'] else 100
            return f'class htb 5:1 root leaf 10: rate {rate}Mbit ceil {rate}Mbit burst 15Kb cburst 1600b', '', 0
        if args[1] == '-s':
            return 'qdisc netem 10: parent 5:1 limit 50 delay 1ms', '', 0
        if args[1] == 'class':
            value = int(args[-1])
            if interface == self.fail_interface and value == 16384:
                return '', 'injected class failure', 1
            self.state[interface] = value
        else:
            self.state['source_limit'] = int(args[-1])
        return '', '', 0


class ExperimentTests(unittest.TestCase):
    def test_route_ports_and_rates(self):
        spec = route_spec('alternate')
        self.assertEqual((spec['egress'], spec['upstream'], spec['capacity_bps']),
                         ('s3-eth2', 's1-eth4', 20_000_000))
        self.assertEqual([r for _, _, r in spec['links']], [100, 20, 20, 100])
        with self.assertRaises(ValueError):
            route_spec('typo')

    def test_controller_mismatch_rejected(self):
        line = 'priority=100,dl_dst=00:00:00:00:00:02 actions=output:3'
        validate_flow(line, '00:00:00:00:00:02', 3)
        with self.assertRaises(RuntimeError):
            validate_flow(line, '00:00:00:00:00:02', 4)

    def test_profile_restores_after_trial_exception(self):
        state = {}
        net = {n: FakeNode(state) for n in ['h1', 's1', 's2', 's3', 's4']}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'trial failed'):
                with calibrated_profile(net, 'alternate', tmp):
                    self.assertEqual(state['s3-eth2'], 16384)
                    self.assertEqual(state['source_limit'], 250)
                    raise RuntimeError('trial failed')
            self.assertTrue(all(v == 1600 for k,v in state.items() if k != 'source_limit'))
            self.assertEqual(state['source_limit'], 50)
            self.assertEqual(json.loads(Path(tmp, 'restoration.json').read_text())['failures'], [])

    def test_partial_apply_rolls_back(self):
        state = {}
        net = {n: FakeNode(state, 's2-eth2') for n in ['h1', 's1', 's2', 's4']}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                with calibrated_profile(net, 'primary', tmp):
                    self.fail('Failed apply cannot enter trial')
        self.assertEqual(state, {'h1-eth0': 1600, 's1-eth3': 1600})

    def test_root_only_not_parent_plus_child(self):
        root = root_qdisc(json.dumps([dict(root=True, drops=5), dict(drops=5)]))
        self.assertEqual(root['drops'], 5)

    def test_actual_dt_used_and_reset_flagged(self):
        def row(t, b):
            return dict(tc_exit=0, tc_start=t, tc_end=t+.01, utc='test',
                        requested_interval=.25, capacity_bps=10_000_000,
                        root_qdisc=dict(bytes=b, drops=0, backlog=0, qlen=0))
        values = list(sample_intervals([row(0, 0), row(.3, 375000), row(.6, 1)]))
        self.assertAlmostEqual(values[0]['qdisc_departure_bps'], 10_000_000)
        self.assertTrue(values[0]['sampling_valid'])
        self.assertTrue(values[1]['counter_reset'])
        self.assertIsNone(values[1]['utilization'])

    def test_failed_query_not_bridged(self):
        rows = [dict(tc_exit=1), dict(tc_exit=0, root_qdisc=dict(bytes=0, drops=0),
                tc_start=2, tc_end=2.01)]
        self.assertEqual(list(sample_intervals(rows)), [])

    def test_counter_reset_rejected(self):
        with self.assertRaises(ValueError):
            counter_delta('dropped 10', 'dropped 2', r'dropped (\d+)')

    def test_seed_reproducibility_and_scenario_validation(self):
        self.assertEqual(schedule('bursty', seed=19), schedule('bursty', seed=19))
        self.assertNotEqual(schedule('bursty', seed=19), schedule('bursty', seed=20))
        with self.assertRaises(ValueError):
            schedule('steady', rate=0)

    def trial_fixture(self, folder, route, rate, drops):
        path = Path(folder)
        meta = dict(route=route, outcome='completed', exits=dict(client=0, server=0),
                    clock_before='tsc', clock_after='tsc', requested_bps=rate,
                    requested_seconds=20, client_elapsed_s=20.1, payload_bytes=1200)
        (path / 'metadata.json').write_text(json.dumps(meta))
        sent = rate*20//8
        missing = sum(drops.values())
        for name, key, size in [('client', 'sum_sent', sent),
                                ('server', 'sum_received', sent-missing*1200)]:
            summary = dict(bytes=size, seconds=20, bits_per_second=size*8/20,
                           lost_percent=100*missing/(sent/1200))
            (path / f'{name}.json').write_text(json.dumps(dict(end={key: summary})))
        for _node, interface, _rate in route_spec(route)['links']:
            for phase, value in [('before', 0), ('after', drops.get(interface, 0))]:
                (path / f'{phase}-{interface}-queue.txt').write_text(f'dropped {value}')
        for host in ['h1', 'h2']:
            for phase in ['before', 'after']:
                (path / f'{phase}-{host}-udp.txt').write_text(
                    'UdpInErrors 0\nUdpRcvbufErrors 0\nUdpSndbufErrors 0\n')
        (path / 'vmstat.txt').write_text('2026-11-14 18:00:00\n2026-11-14 18:00:01\n')
        return path

    def test_alternate_overload_allows_first_20mbit_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.trial_fixture(tmp, 'alternate', 24_000_000, {'s1-eth4': 1000})
            self.assertEqual(inspect_trial(path)['screen_failures'], [])

    def test_alternate_access_loss_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.trial_fixture(tmp, 'alternate', 24_000_000, {'h1-eth0': 1})
            self.assertIn('access_link_drop', inspect_trial(path)['screen_failures'])

    def test_alternate_low_load_path_loss_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.trial_fixture(tmp, 'alternate', 12_000_000, {'s1-eth4': 1})
            self.assertIn('below_capacity_delivery', inspect_trial(path)['screen_failures'])

    def test_rtt_traffic_window_excludes_probe_warmup(self):
        text = ('[1.0] reply time=1.0 ms\n[2.0] reply time=20.0 ms\n'
                '[3.0] reply time<1 ms\n[4.0] reply time=1.0 ms\n'
                '0% packet loss')
        result = ping_statistics(text, [(1.5, 3.5)])
        self.assertEqual(result['replies'], 2)
        self.assertEqual(result['milliseconds']['median'], 20)
        self.assertEqual(result['censored_below_1ms'], 1)
        self.assertIsNone(result['loss_percent'])

    def test_long_query_and_skipped_deadline_flagged(self):
        a = dict(tc_exit=0, tc_start=0, tc_end=.01, utc='test',
                 requested_interval=.1, capacity_bps=10_000_000,
                 root_qdisc=dict(bytes=0, drops=0))
        b = dict(a, tc_start=.1, tc_end=.22, root_qdisc=dict(bytes=1000, drops=0))
        self.assertFalse(list(sample_intervals([a, b]))[0]['sampling_valid'])
        b = dict(a, tc_start=.2, tc_end=.21, skipped_before_sample=1,
                 root_qdisc=dict(bytes=1000, drops=0))
        self.assertFalse(list(sample_intervals([a, b]))[0]['sampling_valid'])

    def test_query_records_its_interface_capacity_and_time(self):
        from types import SimpleNamespace
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout=json.dumps([
                dict(root=True, bytes=100, drops=2)]), stderr='')
        clock = iter([10.0, 10.02])
        result = query_qdisc('s1-eth4', 20_000_000, runner, lambda: next(clock))
        self.assertEqual(calls[0][-1], 's1-eth4')
        self.assertEqual(result['capacity_bps'], 20_000_000)
        self.assertEqual((result['tc_start'], result['tc_end']), (10, 10.02))
        self.assertEqual(result['root_qdisc']['drops'], 2)

    def test_dual_queues_keep_independent_drops_and_rates(self):
        def row(t, a, b, drops):
            queues = {}
            for name, count, lost, rate, offset in [
                ('s1-eth4', a, drops, 20_000_000, 0),
                ('s3-eth2', b, 0, 20_000_000, .02)]:
                queues[name] = dict(tc_exit=0, tc_start=t+offset, tc_end=t+offset+.01,
                    capacity_bps=rate, root_qdisc=dict(bytes=count, drops=lost, qlen=0))
            return dict(utc='test', requested_interval=.25, qdiscs=queues,
                        tc_exit=0, root_qdisc=dict(bytes=b, drops=0),
                        tc_start=t+.02, tc_end=t+.03, capacity_bps=20_000_000)
        rows = [row(0, 0, 0, 0), row(.25, 625000, 312500, 8)]
        a = list(sample_intervals(queue_rows(rows, 's1-eth4')))[0]
        b = list(sample_intervals(queue_rows(rows, 's3-eth2')))[0]
        self.assertEqual((a['drops_delta'], b['drops_delta']), (8, 0))
        self.assertAlmostEqual(a['utilization'], 1)
        self.assertAlmostEqual(b['utilization'], .5)
        self.assertEqual(queue_summary(rows, 's1-eth4')['sampled_drop_delta'], 8)

    def test_failed_upstream_query_does_not_break_downstream(self):
        rows = []
        for i in range(3):
            queues = {name: dict(tc_exit=0, tc_start=i*.25, tc_end=i*.25+.01,
                capacity_bps=20_000_000, root_qdisc=dict(bytes=i*1000, drops=0))
                for name in ['s1-eth4', 's3-eth2']}
            if i == 1:
                queues['s1-eth4'] = dict(tc_error='failed')
            rows.append(dict(utc='test', requested_interval=.25, qdiscs=queues))
        self.assertEqual(len(list(sample_intervals(queue_rows(rows, 's1-eth4')))), 0)
        self.assertEqual(len(list(sample_intervals(queue_rows(rows, 's3-eth2')))), 2)

    def test_legacy_rows_do_not_claim_unobserved_upstream(self):
        row = dict(egress='s3-eth2', tc_exit=0, root_qdisc=dict(bytes=1, drops=0))
        self.assertEqual(list(queue_rows([row], 's1-eth4')), [])
        self.assertEqual(list(queue_rows([row], 's3-eth2')), [row])

    def test_query_failure_is_recorded(self):
        import subprocess
        def runner(*args, **kwargs):
            raise subprocess.TimeoutExpired('tc', 2)
        ticks = iter([0, 2])
        result = query_qdisc('s1-eth4', 20_000_000, runner, lambda: next(ticks))
        self.assertIn('tc_error', result)
        self.assertNotIn('root_qdisc', result)

    def test_batch_one_command_keeps_devices_and_root_only(self):
        from types import SimpleNamespace
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps([
                dict(dev='s1-eth4', root=True, bytes=100, drops=8),
                dict(dev='s1-eth4', parent='5:1', bytes=100, drops=8),
                dict(dev='s3-eth2', root=True, bytes=90, drops=0),
                dict(dev='other', root=True, bytes=999, drops=999)]))
        ticks = iter([1, 1.02])
        batch, queues = query_qdiscs([('s1-eth4', 20_000_000), ('s3-eth2', 20_000_000)],
                                     runner, lambda: next(ticks))
        self.assertEqual(calls, [['tc', '-j', '-s', 'qdisc', 'show']])
        self.assertEqual(queues['s1-eth4']['root_qdisc']['drops'], 8)
        self.assertEqual(queues['s3-eth2']['root_qdisc']['drops'], 0)
        self.assertEqual(queues['s1-eth4']['tc_start'], queues['s3-eth2']['tc_start'])
        self.assertEqual(batch['tc_end'], 1.02)

    def test_batch_missing_queue_does_not_borrow_other_counters(self):
        from types import SimpleNamespace
        runner = lambda *a, **k: SimpleNamespace(returncode=0, stderr='', stdout=json.dumps([
            dict(dev='s1-eth4', root=True, bytes=10, drops=1)]))
        _batch, queues = query_qdiscs([('s1-eth4', 20_000_000), ('s3-eth2', 20_000_000)], runner)
        self.assertIn('root_qdisc', queues['s1-eth4'])
        self.assertIn('tc_error', queues['s3-eth2'])
        self.assertNotIn('root_qdisc', queues['s3-eth2'])

    def test_batch_timeout_marks_both_without_fabricated_zero(self):
        import subprocess
        def runner(*a, **k): raise subprocess.TimeoutExpired('tc', 2)
        _batch, queues = query_qdiscs([('s1-eth4', 20_000_000), ('s3-eth2', 20_000_000)], runner)
        self.assertTrue(all('tc_error' in q and 'root_qdisc' not in q for q in queues.values()))

    def test_batch_rejects_invalid_json_shape(self):
        from types import SimpleNamespace
        runner = lambda *a, **k: SimpleNamespace(returncode=0, stderr='', stdout='{}')
        batch, queues = query_qdiscs([('s2-eth2', 10_000_000)], runner)
        self.assertIn('tc_error', batch)
        self.assertNotIn('root_qdisc', queues['s2-eth2'])

    @unittest.skipUnless(os.name == 'posix' and shutil.which('tc'), 'Native tc schema checked on Ubuntu')
    def test_native_batch_json_device_and_counter_schema(self):
        # Loopback is a read-only schema check, not a capacity measurement.
        batch, queues = query_qdiscs([('lo', 1)])
        self.assertEqual(batch.get('tc_exit'), 0, batch)
        self.assertIn('root_qdisc', queues['lo'], batch)
        self.assertEqual(queues['lo']['root_qdisc']['dev'], 'lo')

    def test_sweep_balances_interval_order(self):
        from run_interval_sweep import interval_order
        plan = interval_order(3)
        self.assertEqual(len(plan), 9)
        for repetition in [1, 2, 3]:
            self.assertEqual({item['interval_s'] for item in plan
                              if item['repetition'] == repetition}, {.5, .25, .1})
        self.assertEqual([plan[i]['interval_s'] for i in [0, 3, 6]], [.5, .25, .1])
        with self.assertRaises(ValueError):
            interval_order(0)

    def test_sweep_stops_and_preserves_reference_after_experiment_failure(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import run_interval_sweep as sweep
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ['run_interval_sweep.py', 'collect_path.py', 'inspect_experiment.py']:
                (base / name).write_text('# simulated source snapshot\n')
            def failed_experiment(*args, **kwargs):
                folder = base / 'results/runs/failed-experiment'
                folder.mkdir(parents=True)
                (folder / 'experiment.json').write_text(json.dumps(dict(outcome='error')))
                return folder
            with patch.object(sweep, 'BASE', base), patch.object(
                    sweep, 'run_experiment', side_effect=failed_experiment) as runner:
                with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    sweep.run_sweep({})
            self.assertEqual(runner.call_count, 1)
            metadata = json.loads(next(base.glob('results/runs/*/sweep.json')).read_text())
            self.assertEqual(metadata['outcome'], 'incomplete')
            self.assertEqual(metadata['experiments'][0]['folder'], 'failed-experiment')


if __name__ == '__main__':
    unittest.main()
