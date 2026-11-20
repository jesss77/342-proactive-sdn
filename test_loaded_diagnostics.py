import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import run_loaded_diagnostics as diagnostic

BASE = Path(__file__).resolve().parent


class RegistrationTests(unittest.TestCase):
    def test_real_protocol_keeps_all_frozen_sources_and_only_four_diagnostic_cases(self):
        p = diagnostic.load_protocol(BASE)
        self.assertEqual(len(p['frozen_source_sha256']), 72)
        self.assertEqual([x['case'] for x in p['plan']], ['source_receiver', 'collector', 'fixed_loop', 'reactive_loop'])
        self.assertEqual([x['policy'] for x in p['plan']], [None, None, 'fixed', 'reactive'])
        self.assertFalse(p['plan'][0]['collector'])
        self.assertTrue(all(x['collector'] for x in p['plan'][1:]))
        self.assertIn('other work remains running', p['settings']['host_conditions'])


class BatchTests(unittest.TestCase):
    def fixture(self, root):
        self.base = root
        (root / diagnostic.PROTOCOL).write_text('{}')
        self.p = dict(frozen_source_sha256={}, additional_source_sha256={})
        self.calls = []
        self.reports = {}

    def environment(self, folder):
        (folder / 'environment.json').write_text('{"host_work":"retained"}')

    def readiness(self, net, base, folder):
        folder.mkdir()
        (folder / 'readiness.json').write_text('{}')

    def execute(self, net, base, item, parent):
        self.calls.append(item['case'])
        root = base / 'results/runs'
        raw = root / ('raw-' + item['case']); raw.mkdir()
        trial = root / ('trial-' + item['case']); trial.mkdir()
        (trial / 'metadata.json').write_text('{}')
        (raw / ('policy.json' if item['policy'] else 'component.json')).write_text(json.dumps(dict(trial=trial.name)))
        self.reports[raw.name] = dict(outcome='completed', screen_failures=[], sender_mbps=8.,
            receiver_mbps=6., udp_loss_percent=25., restoration=dict(failures=[]),
            route_restoration=dict(verified=True, failures=[]))
        return raw

    def run_case(self, case='source_receiver', **kw):
        with patch.object(diagnostic, 'load_protocol', return_value=self.p), \
             patch.object(diagnostic, 'verify_prior', return_value=dict(prior_edited=False)), \
             contextlib.redirect_stdout(io.StringIO()):
            return diagnostic.run(None, base=self.base, case=case, executor=kw.pop('executor', self.execute),
                inspector=lambda p: self.reports[p.name], readiness_check=kw.pop('readiness_check', self.readiness),
                environment_check=self.environment, **kw)

    def batch(self):
        root = self.base / 'results/runs'
        return root / json.loads((root / diagnostic.REGISTRY).read_text())['batch']

    def test_one_call_one_case_and_no_duplicate_or_skipped_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp)); self.run_case()
            with self.assertRaisesRegex(ValueError, 'Next registered case is collector'):
                self.run_case('source_receiver')
            with self.assertRaisesRegex(ValueError, 'Next registered case is collector'):
                self.run_case('reactive_loop')
            self.assertEqual(self.calls, ['source_receiver'])
            for case in ['collector', 'fixed_loop', 'reactive_loop']:
                self.run_case(case)
            self.assertEqual(json.loads((self.batch() / 'batch.json').read_text())['outcome'], 'completed')
            with self.assertRaisesRegex(ValueError, 'already complete'):
                self.run_case('reactive_loop')
            self.assertEqual(len(self.calls), 4)

    def test_quality_failure_retains_report_and_raw_then_refuses_every_next_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp))
            def bad(*args):
                raw = self.execute(*args)
                self.reports[raw.name]['screen_failures'] = ['udp_error']
                return raw
            with self.assertRaisesRegex(ValueError, 'quality/restoration'):
                self.run_case(executor=bad)
            state = json.loads((self.batch() / 'batch.json').read_text())
            self.assertEqual(state['outcome'], 'failed')
            self.assertEqual(state['attempts'][0]['status'], 'failed')
            self.assertTrue((self.batch() / 'review-source_receiver.json').exists())
            self.assertEqual(len(state['new_raw_folders']), 2)
            for case in ['source_receiver', 'collector']:
                with self.assertRaisesRegex(ValueError, 'cannot resume or retry'):
                    self.run_case(case)
            self.assertEqual(len(self.calls), 1)

    def test_mid_execution_failure_keeps_both_folders_and_no_unbounded_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp))
            def interrupted(*args):
                self.execute(*args)
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                self.run_case(executor=interrupted)
            state = json.loads((self.batch() / 'batch.json').read_text())
            self.assertIn('raw-source_receiver', state['new_raw_folders'])
            self.assertIn('trial-source_receiver', state['new_raw_folders'])
            with self.assertRaisesRegex(ValueError, 'cannot resume or retry'):
                self.run_case()

    def test_readiness_failure_starts_no_loaded_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(Path(tmp))
            def bad(*args):
                self.readiness(*args)
                raise ValueError('readiness failed')
            with self.assertRaisesRegex(ValueError, 'readiness failed'):
                self.run_case(readiness_check=bad)
            self.assertEqual(self.calls, [])
            self.assertEqual(json.loads((self.batch() / 'batch.json').read_text())['attempts'], [])

    def test_changed_raw_or_environment_prevents_next_acquisition(self):
        for target in ['raw', 'environment', 'review']:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                self.fixture(Path(tmp)); self.run_case()
                paths = dict(raw=self.base / 'results/runs/trial-source_receiver/metadata.json',
                    environment=self.batch() / 'environment-source_receiver/environment.json',
                    review=self.batch() / 'review-source_receiver.json')
                paths[target].write_text('mutation')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    self.run_case('collector')
                self.assertEqual(self.calls, ['source_receiver'])


class LifecycleTests(unittest.TestCase):
    def exercise(self, failed=False, collector=False):
        from test_path_controls import fixture, Process
        import run_continuous_trial as recorder
        import run_experiment
        net, settings, ovs = fixture()
        ping = Process()
        net['h1'].popen = lambda *a, **k: ping
        now = [100.]
        counts = {d: dict(tx_bytes=0) for d in ['s1-eth3', 's2-eth2', 's1-eth4', 's3-eth2']}
        def sleep(seconds):
            now[0] += seconds
        def recorded(net, base, *args, **kw):
            raw = base / 'results/runs/source'; raw.mkdir(parents=True)
            kw['on_created'](raw)
            self.assertEqual(kw['trial_context']['kind'], 'loaded_component_diagnostic')
            self.assertEqual(len(kw['capture_links']), 6)
            kw['route_verifier'](net, 'primary', raw)
            if failed:
                raise RuntimeError('injected source failure')
            (raw / 'metadata.json').write_text('{"outcome":"completed"}')
            return raw
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); folder = base / 'results/runs/component'; folder.mkdir(parents=True)
            with patch.object(diagnostic, 'load_protocol', return_value=dict(frozen_source_sha256={})), \
                 patch.object(diagnostic.importlib, 'reload', side_effect=lambda m: m), \
                 patch.object(recorder, 'run', recorded), \
                 patch.object(run_experiment, 'interface_counts', return_value=counts), \
                 patch.object(diagnostic.subprocess, 'Popen', return_value=Process()) as launch:
                if failed:
                    with self.assertRaisesRegex(RuntimeError, 'injected source failure'):
                        diagnostic.component_run(net, base, 'collector' if collector else 'source_receiver', folder,
                            clock=lambda: now[0], sleep=sleep)
                else:
                    diagnostic.component_run(net, base, 'collector' if collector else 'source_receiver', folder,
                        clock=lambda: now[0], sleep=sleep)
                self.assertEqual(launch.call_count, int(collector))
            m = json.loads((folder / 'component.json').read_text())
            self.assertEqual(m['trial'], 'source')
            self.assertTrue(m['route_restoration']['verified'])
            self.assertEqual(json.loads((folder / 'restoration.json').read_text())['failures'], [])
            self.assertEqual(settings['source_limit'], 50)
            self.assertTrue(all(v == 1600 for v in settings['classes'].values()))
            self.assertFalse(ovs.overlay)
            self.assertIsNotNone(ping.poll())

    def test_source_only_never_launches_continuous_collector_and_restores(self):
        self.exercise()

    def test_source_exception_stops_collector_and_restores_both_paths(self):
        self.exercise(failed=True, collector=True)


class InspectionTests(unittest.TestCase):
    def inspect(self, collector=False, invalid=False):
        import inspect_experiment
        import source_integrity
        from traffic_scenarios import continuous_schedule
        from dual_path_profile import QUEUES
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); root = base / 'results/runs'; folder = root / 'component'; folder.mkdir(parents=True)
            trial = root / 'source'; trial.mkdir()
            case = 'collector' if collector else 'source_receiver'
            m = dict(case=case, trial='source', outcome='completed', collector_enabled=collector,
                source_sha256={}, profile=dict(id=diagnostic.SETTINGS['profile_id']),
                counters_before={d:dict(tx_bytes=0) for d in QUEUES},
                counters_after={d:dict(tx_bytes=1000000 if d in QUEUES[:2] else 0) for d in QUEUES},
                route_restoration=dict(verified=True, failures=[]))
            (folder / 'component.json').write_text(json.dumps(m))
            (folder / 'restoration.json').write_text('{"failures":[]}')
            (folder / 'ping-loaded.txt').write_text('[101] reply time=10 ms\n0% packet loss')
            native=dict(traffic_plan=continuous_schedule('bursty',11500000,60,44),seed=44,scenario='bursty',
                trial_context=dict(parent='component',case=case))
            (trial / 'metadata.json').write_text(json.dumps(native))
            (trial / 'sender-native.json').write_text(json.dumps(dict(start_wall_epoch_s=100,end_wall_epoch_s=160,max_pacer_gap_s=.01)))
            t=dict(screen_failures=[],sender=dict(bits_per_second=8e6),receiver=dict(bits_per_second=6e6,lost_percent=25.))
            if collector:
                rows=[]
                for i in range(240):
                    rows.append(dict(requested_interval=.25,utc='fixture',skipped_before_sample=int(invalid and i==120),
                        qdiscs={d:dict(tc_start=i*.25,tc_end=i*.25+.005,tc_exit=0,
                            capacity_bps=1e7,root_qdisc=dict(bytes=i*1000,drops=i,backlog=0,qlen=0)) for d in QUEUES}))
                (folder/'samples.jsonl').write_text('\n'.join(json.dumps(x) for x in rows))
                (folder/'samples.jsonl.stats.json').write_text(json.dumps(dict(schema_version=6,coverage='all',queried_qdiscs=QUEUES)))
            with patch.object(diagnostic,'load_protocol',return_value=dict(frozen_source_sha256={})), \
                 patch.object(inspect_experiment,'inspect_trial',return_value=t), \
                 patch.object(source_integrity,'source_integrity_audit',return_value=dict(discard_percent=0)):
                return diagnostic.inspect_component(folder)

    def test_absent_collector_is_inapplicable_and_overload_loss_is_retained(self):
        report=self.inspect()
        self.assertFalse(report['collector']['applicable'])
        self.assertNotIn('queues', report['collector'])
        self.assertEqual(report['udp_loss_percent'],25.)
        self.assertEqual(report['screen_failures'],[])

    def test_collector_stage_keeps_zero_invalid_interval_rule(self):
        self.assertEqual(self.inspect(collector=True)['screen_failures'],[])
        report=self.inspect(collector=True,invalid=True)
        self.assertIn('collector_quality',report['screen_failures'])
        self.assertTrue(all(q['invalid_intervals']==1 for q in report['collector']['queues'].values()))


if __name__ == '__main__':
    unittest.main()
