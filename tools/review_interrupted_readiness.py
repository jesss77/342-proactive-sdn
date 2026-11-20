"""One reviewed restart for cancelled idle readiness; never retry a traffic/quality failure."""
from datetime import datetime,timezone
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True

def collectors(base):
    target=str(Path(base)/'collect_path.py').encode();found=[]
    if not Path('/proc').is_dir():raise ValueError('Run this helper in the Linux guest')
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if target in path.read_bytes().split(b'\0'):found.append(int(path.parent.name))
        except (FileNotFoundError,ProcessLookupError):pass
    return found

def review(base,loader=None,parent_check=None,process_check=collectors):
    base=Path(base).resolve(strict=True);sys.path.insert(0,str(base))
    import run_supplement_recovery as r
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    root=base/'results/runs';registry=root/'supplement-recovery-registry-v1.json'
    ledger=root/'readiness-interruption-review-v1.json'
    if ledger.exists():raise ValueError('An interruption review already exists; no repeated administrative restart')
    p,_=(loader or r.load_protocol)(base)
    parent=(parent_check or r.verify_parent)(base,p)
    active=process_check(base)
    if active:raise ValueError('Collector still running; no changes made. PIDs: '+str(active))
    if registry.is_symlink():raise ValueError('Registry is a symlink')
    registry_bytes=registry.read_bytes();identity=json.loads(registry_bytes)
    folder=r.child(root,identity['batch']);state_path=folder/'batch.json'
    state=json.loads(state_path.read_text())
    if (state.get('role')!='prospective_whole_block_recovery' or state.get('outcome')!='failed'
        or state.get('runs')!=[] or state.get('attempts')!=[] or len(state.get('readiness',[]))!=1):
        raise ValueError('Not an empty interrupted readiness: refuse restart. Traffic/quality failures require separate review.')
    if state.get('protocol_sha256')!=r.sha(base/'supplement_recovery_protocol.json') or state.get('plan')!=r.plan():
        raise ValueError('Registered recovery differs')
    if r.sha(folder/'supplement_recovery_protocol.json')!=state['protocol_sha256']:
        raise ValueError('Captured protocol changed')
    for name,digest in p['additional_source_sha256'].items():
        if r.sha(folder/name)!=digest:raise ValueError('Captured source changed: '+name)
    entry=state['readiness'][0]
    if entry.get('folder')!='readiness/00' or entry.get('status')!='failed' or entry.get('error')!='KeyboardInterrupt()':
        raise ValueError('Not the reviewed initial KeyboardInterrupt')
    ready=folder/'readiness/00';meta=json.loads((ready/'readiness.json').read_text())
    if (meta.get('outcome')!='failed' or meta.get('error')!='KeyboardInterrupt()'
        or meta.get('no_traffic_generated') is not True or meta.get('report') is not None):
        raise ValueError('Readiness already has a quality result or differs from the reported interruption')
    samples=ready/'samples.jsonl';rows=[];partial_tail=False
    if samples.exists():
        for line in samples.read_text().splitlines(keepends=True):
            if not line.endswith('\n'):partial_tail=True;continue
            if line.strip():rows.append(json.loads(line))
    qs={q:queue_summary(rows,q) for q in QUEUES}
    if any(q['failed_queries'] or q['invalid_intervals'] for q in qs.values()):
        raise ValueError('Completed partial samples already contain a collector-quality failure; do not restart under the interruption exception')
    pointer=root/'active-supplement-recovery-v1.txt';pointer_bytes=None
    if pointer.exists():
        if pointer.is_symlink() or Path(pointer.read_text().strip()).name!=folder.name:
            raise ValueError('Active recovery pointer differs')
        pointer_bytes=pointer.read_bytes()
    before=r.evidence_hashes(folder)
    target=root/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'-reviewed-readiness-interruption')
    target.mkdir()
    record=dict(kind='reviewed_operator_interruption_before_acquisition',status='prepared',
        review_helper_sha256=r.sha(Path(__file__)),
        coordination_sha256=dict(registry=r.sha(registry),active_pointer=r.sha(pointer) if pointer_bytes is not None else None),
        reviewed_at=datetime.now(timezone.utc).isoformat(),old_batch=folder.name,
        reason='KeyboardInterrupt during first idle readiness; no quality result and zero traffic attempts',
        accepted=0,attempts=0,parent=parent,old_batch_files_sha256=before,
        completed_partial_samples=len(rows),incomplete_tail_preserved=partial_tail,partial_queue_summary=qs,
        protocol_sha256=state['protocol_sha256'],source_or_quality_settings_changed=False,
        scope='Archive coordination pointers only. Preserve failed batch.json, readiness/raw data and original failed supplemental batch. Permit one fresh full idle check under the existing registration; no traffic trial has been retried.')
    with (target/'batch-before.json').open('xb') as f:f.write(state_path.read_bytes())
    def save():r.write(target/'review.json',record)
    save();moved=[]
    try:
        if registry.read_bytes()!=registry_bytes:raise ValueError('Registry changed during review')
        registry.rename(target/'registry-before.json');moved.append((registry,target/'registry-before.json'))
        if pointer_bytes is not None:
            if pointer.read_bytes()!=pointer_bytes:raise ValueError('Active pointer changed during review')
            pointer.rename(target/'active-pointer-before.txt');moved.append((pointer,target/'active-pointer-before.txt'))
        if r.evidence_hashes(folder)!=before:raise ValueError('Interrupted raw evidence changed')
        (parent_check or r.verify_parent)(base,p)
        record['status']='archived_pointers_raw_unchanged';save()
        with ledger.open('x') as f:json.dump(dict(review=target.name,old_batch=folder.name,
            protocol_sha256=state['protocol_sha256'],zero_traffic_attempts=True),f,indent=2)
    except BaseException as e:
        for old,new in reversed(moved):
            if old.exists():raise RuntimeError('Coordination changed during rollback; inspect review folder') from e
            new.rename(old)
        record.update(status='review_failed_pointers_restored',error=repr(e));save();raise
    print(json.dumps(dict(review=str(target),preserved_batch=str(folder),traffic_attempts=0,
        original_batch_files_unchanged=True,completed_partial_samples=len(rows),
        next='Run the original recovery start command once. Leave the 60-second idle check uninterrupted.'),indent=2),flush=True)
    return record,target

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: review_interrupted_readiness.py REPOSITORY')
    review(sys.argv[1])
