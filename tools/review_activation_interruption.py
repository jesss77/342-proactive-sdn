"""Explicit one-use review of the reported idle cancellation, before any pilot trial."""
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sys
sys.dont_write_bytecode = True

EXPECTED_BATCH = '20261121-005102-775241-packet-activation-pilot'
EXPECTED_PROTOCOL = '48d4c2ddade50ee3266c1bfa811b3c2f8cff622fffa63dcb11678b4ec312f237'
LEDGER = 'activation-interruption-review-v1.json'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def active_processes(base):
    proc = Path('/proc')
    require(proc.is_dir(), 'Run this review in the Linux guest')
    base = Path(base).resolve()
    scripts = {str(base/n).encode() for n in ['collect_path.py', 'continuous_udp.py']}
    captures = {b's1-eth3', b's1-eth4'}
    found = []
    for p in proc.glob('[0-9]*/cmdline'):
        try:
            args = p.read_bytes().split(b'\0')
            if scripts.intersection(args):
                found.append(dict(pid=int(p.parent.name), kind='project_collector_or_udp'))
            elif args and args[0].split(b'/')[-1] == b'tcpdump' and (
                captures.intersection(args) or any(a.startswith(str(base).encode()+b'/') for a in args)):
                found.append(dict(pid=int(p.parent.name), kind='project_capture'))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def review(base, loader=None, parent_check=None, process_check=active_processes):
    base = Path(base).resolve(strict=True); sys.path.insert(0, str(base))
    import run_activation_pilot as pilot
    from run_matched_batch import sha, write, child, evidence_hashes
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    root = base/'results/runs'; registry = root/pilot.REGISTRY; ledger = root/LEDGER
    require(not ledger.exists() and not ledger.is_symlink(), 'One-time activation review already used; no repeated restart')
    require(sha(base/pilot.PROTOCOL) == EXPECTED_PROTOCOL, 'Original activation protocol digest differs')
    p = (loader or pilot.load_protocol)(base)
    parent = (parent_check or pilot.verify_parent)(base,p)
    require(not registry.is_symlink(), 'Registry is a symlink')
    registry_bytes = registry.read_bytes(); identity = json.loads(registry_bytes)
    require(identity.get('batch') == EXPECTED_BATCH, 'Not the specifically reported interrupted batch')
    folder = child(root,identity['batch']); state_path = folder/'batch.json'
    state_bytes = state_path.read_bytes(); state = json.loads(state_bytes)
    require(state.get('outcome') == 'failed' and state.get('error') == 'KeyboardInterrupt()'
            and state.get('attempts') == [] and state.get('new_raw_folders') == [],
            'Not an empty cancelled readiness; traffic/execution/quality failures cannot restart here')
    require(state.get('plan') == pilot.plan() and state.get('protocol_sha256') == EXPECTED_PROTOCOL
            and sha(folder/pilot.PROTOCOL) == EXPECTED_PROTOCOL, 'Captured registration differs')
    expected_pins = dict(p['frozen_source_sha256'], **p['additional_source_sha256'])
    require(state.get('captured_source_sha256') == expected_pins, 'Captured source pin set differs')
    for name, digest in expected_pins.items():
        require(Path(name).name == name and not (folder/name).is_symlink() and sha(folder/name) == digest,
                'Captured source changed: '+name)
    before = folder/'before'
    require(before.is_dir() and {x.name for x in before.iterdir()} == {'environment'},
            'Execution/capture/clock/review evidence present; acquisition may have begun')
    require(not any(folder.rglob('*.pcap')), 'Packet capture exists; refuse cancellation exception')
    env = before/'environment'
    info = json.loads((env/'environment.json').read_text())
    require(info.get('cpu_count') == 1 and info.get('clocksource') == 'tsc', 'Environment preflight differs')
    version = json.loads((env/'tcpdump-version.json').read_text())
    require(version.get('exit') == 0 and 'tcpdump version 4.99.4' in version.get('text','')
            and 'libpcap version 1.10.4' in version.get('text',''), 'Capture capability preflight differs')
    for dev in ['s1-eth3','s1-eth4']:
        t = json.loads((env/(dev+'-timestamp-types.json')).read_text())
        require(t.get('exit') == 0 and re.search(r'^\s*host\s+\(',t.get('text',''),re.M),
                'Timestamp-type preflight differs')
    ready = folder/'readiness'; meta = json.loads((ready/'readiness.json').read_text())
    require(meta.get('outcome') == 'failed' and meta.get('error') == 'KeyboardInterrupt()'
            and meta.get('no_traffic_generated') is True and meta.get('report') is None
            and 'readiness_sha256' not in state,
            'Readiness has a quality result or is not the reported cancellation')
    rows = []; partial_tail = False
    samples = ready/'samples.jsonl'
    if samples.exists():
        for line in samples.read_text().splitlines(keepends=True):
            if not line.endswith('\n'):
                partial_tail = True
                continue
            if line.strip():
                r = json.loads(line)
                require(r.get('schema_version') == 6 and r.get('coverage') == 'all'
                        and r.get('requested_interval') == .25 and set(r.get('qdiscs',{})) == set(QUEUES),
                        'Completed partial collector row has wrong schema/coverage')
                rows.append(r)
    queues = {q:queue_summary(rows,q) for q in QUEUES}
    require(not any(q['failed_queries'] or q['invalid_intervals'] for q in queues.values()),
            'Completed partial samples contain a collector-quality failure; no waiver')
    stats = None
    if (ready/'samples.jsonl.stats.json').exists():
        stats = json.loads((ready/'samples.jsonl.stats.json').read_text())
        require(stats.get('schema_version') == 6 and stats.get('coverage') == 'all'
                and set(stats.get('queried_qdiscs',[])) == set(QUEUES), 'Partial collector statistics differ')
    active = process_check(base)
    require(not active, 'Project collector, UDP or capture process still active; no changes made: '+str(active))
    old_hashes = evidence_hashes(folder)
    review_name = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'-reviewed-activation-idle-interruption'
    target = child(root,review_name); target.mkdir()
    record = dict(kind='explicit_pre_acquisition_activation_cancellation_amendment',status='prepared',
        reviewed_at=datetime.now(timezone.utc).isoformat(),old_batch=folder.name,
        protocol_sha256=EXPECTED_PROTOCOL,review_helper_sha256=sha(Path(__file__)),
        reason='Reported KeyboardInterrupt during initial idle readiness; zero traffic attempts and no quality result',
        old_batch_files_sha256=old_hashes,registry_sha256=sha(registry),parent=parent,
        traffic_attempts=0,accepted_trials=0,completed_partial_samples=len(rows),
        incomplete_tail_preserved=partial_tail,partial_queue_summary=queues,partial_collector_stats=stats,
        scope='One manual pre-acquisition coordination exception. Preserve failed batch/state/raw byte-for-byte; archive only activation registry. Not a reset/retry of a measured traffic or quality failure.',
        source_model_quality_or_plan_changed=False)
    (target/'batch-before.json').write_bytes(state_bytes)
    def save():
        write(target/'review.json',record)
    save(); moved = False
    # Reserve the one-use ledger before moving the pointer. Failures remain
    # blocked; do not delete the ledger to manufacture another cancellation.
    with ledger.open('x') as f:
        json.dump(dict(status='prepared',review=target.name,old_batch=folder.name,protocol_sha256=EXPECTED_PROTOCOL),f,indent=2)
    try:
        require(registry.read_bytes() == registry_bytes and state_path.read_bytes() == state_bytes,
                'Coordination/state changed during review')
        active = process_check(base)
        require(not active, 'Project process became active; refuse registry archive: '+str(active))
        registry.rename(target/'registry-before.json'); moved = True
        require(evidence_hashes(folder) == old_hashes, 'Interrupted batch changed during review')
        (parent_check or pilot.verify_parent)(base,p)
        require((target/'registry-before.json').read_bytes() == registry_bytes, 'Archived registry differs')
        record['status'] = 'archived_registry_raw_unchanged'; save()
        write(ledger,dict(status='committed',review=target.name,old_batch=folder.name,
            protocol_sha256=EXPECTED_PROTOCOL,zero_traffic_attempts=True))
    except BaseException as error:
        if moved:
            require(not registry.exists(), 'New coordination appeared during rollback; inspect review folder')
            (target/'registry-before.json').rename(registry)
        record.update(status='review_failed_registry_restored',error=repr(error)); save()
        write(ledger,dict(status='review_failed_no_automatic_restart',review=target.name,old_batch=folder.name,error=repr(error)))
        raise
    print(json.dumps(dict(review=str(target),preserved_batch=str(folder),traffic_attempts=0,
        completed_partial_samples=len(rows),old_batch_unchanged=True,source_or_quality_changed=False,
        next='Review this result, then run the unchanged before command once. Let the entire 60-second idle check finish; it can be quiet.'),indent=2),flush=True)
    return record,target


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: review_activation_interruption.py REPOSITORY')
    review(sys.argv[1])
