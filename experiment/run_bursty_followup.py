"""Separately registered four-block bursty follow-up; no retries of failed batches."""
from datetime import datetime
from pathlib import Path, PurePosixPath
import importlib
import json
import os
import shutil

from run_matched_batch import sha, write, child, evidence_hashes, check_report

BASE = Path(__file__).resolve().parent
PROTOCOL = 'bursty_followup_protocol.json'
REGISTRY = 'bursty-followup-registry-v1.json'
OWN = ['run_bursty_followup.py', 'test_bursty_followup.py', 'BURSTY_FOLLOWUP.md']
SETTINGS = dict(id='bursty-followup-v1', seeds=[51,52,53,54], scenario='bursty',
    requested_bps=11500000, duration=60, block_size=4, interval_s=.25,
    activation_batch='20261121-012117-648967-packet-activation-pilot',
    activation_checkpoint_sha256='7d4c4fdcabe24b952e69fd0a078382ffbd34f0416a78ae45edd41fb958267c16',
    capture_enabled=False, extra_clock_probe_enabled=False,
    scope='Separate post-failure cohort, original frozen policies/settings. No fitting or benefit-based exclusion. Stop at first quality/execution/restoration failure; no repeats or replacement seeds.')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def plan():
    orders = [ ['fixed','reactive','ml','early_warning'],
               ['reactive','early_warning','fixed','ml'],
               ['early_warning','ml','reactive','fixed'],
               ['ml','fixed','early_warning','reactive'] ]
    return [dict(block=b,position=i,policy=policy,scenario='bursty',seed=seed,
                 requested_bps=11500000,duration=60)
            for b,(seed,order) in enumerate(zip(SETTINGS['seeds'],orders)) for i,policy in enumerate(order)]


def load_protocol(base):
    import run_activation_pilot as activation
    base = Path(base).resolve(); activation.load_protocol(base)
    p = json.loads((base/PROTOCOL).read_text())
    require(p['settings'] == SETTINGS and p['plan'] == plan(), 'Follow-up plan/settings changed')
    require(len(p['frozen_source_sha256']) == 81 and set(p['additional_source_sha256']) == set(OWN),
            'Follow-up source pins incomplete')
    for name,digest in dict(p['frozen_source_sha256'],**p['additional_source_sha256']).items():
        require(Path(name).name == name and not (base/name).is_symlink() and sha(base/name) == digest,
                'Follow-up/frozen source changed: '+name)
    return p


def verify_parent(base,p):
    import run_activation_pilot as activation
    base = Path(base).resolve(); activation.verify_parent(base,activation.load_protocol(base))
    for name,digest in p['activation_evidence_sha256'].items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in name and ':' not in name,
                'Unsafe activation evidence path')
        path = base.joinpath(*rel.parts)
        require(not path.is_symlink() and path.resolve().is_relative_to(base) and sha(path) == digest,
                'Reviewed activation evidence changed: '+name)
    root = base/'results/runs'; batch = child(root,SETTINGS['activation_batch'])
    require(json.loads((root/activation.REGISTRY).read_text())['batch'] == batch.name, 'Activation registry differs')
    state = json.loads((batch/'batch.json').read_text()); activation.validate_state(base,batch,state)
    require(state['outcome'] == 'completed' and len(state['attempts']) == 3, 'Completed reviewed activation pilot required')
    return dict(batch=batch.name,files_verified=len(p['activation_evidence_sha256']),old_failed_batches_reopened=False)


def check_unused(root):
    for folder in Path(root).iterdir():
        if not folder.is_dir():
            continue
        for name in ['policy.json','metadata.json','control.json','component.json']:
            path = folder/name
            if path.is_file():
                identity = json.loads(path.read_text())
                require(identity.get('seed') not in SETTINGS['seeds'],
                        'Reserved seed already acquired; inspect instead: '+folder.name)


def environment_check(folder,base):
    from run_loaded_diagnostics import environment
    environment(folder)
    info = json.loads((Path(folder)/'environment.json').read_text())
    require(info['cpu_count'] == 1 and info['clocksource'] == 'tsc', 'Original one-vCPU/tsc guest required')
    active = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            args = (entry/'cmdline').read_bytes().split(b'\0')
        except (OSError,ProcessLookupError):
            continue
        text = ' '.join(x.decode(errors='replace') for x in args)
        if (str(Path(base)) in text and any(Path(x.decode(errors='replace')).name in ['continuous_udp.py','collect_path.py'] for x in args)
                or args and Path(args[0].decode(errors='replace')).name == 'tcpdump'
                and any(dev in text for dev in ['s1-eth3','s1-eth4'])):
            active.append(entry.name)
    require(not active, 'Active project source/collector/capture; no processes killed: '+str(active))


def validate_resume(base,folder,state,p):
    root = Path(base)/'results/runs'
    require(state['outcome'] in ['paused','completed'] and state['plan'] == plan()
            and state['protocol_sha256'] == sha(Path(base)/PROTOCOL)
            and sha(Path(folder)/PROTOCOL) == state['protocol_sha256']
            and len(state['runs']) == len(state['attempts']) <= 16 and len(state['runs'])%4 == 0
            and all(a['status'] == 'passed' for a in state['attempts']),
            'Failed/partial/changed follow-up cannot resume or retry')
    for name,digest in dict(p['frozen_source_sha256'],**p['additional_source_sha256']).items():
        require(sha(Path(folder)/name) == digest, 'Captured follow-up source changed: '+name)
    for item,record in zip(plan(),state['runs']):
        require({k:record[k] for k in item} == item, 'Completed cell order differs')
        for key,hkey in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:
            require(evidence_hashes(child(root,record[key])) == record[hkey], 'Follow-up raw evidence changed')
    for attempt,record in zip(state['attempts'],state['runs']):
        require(attempt['folder'] == record['folder'] and attempt['trial'] == record['trial']
                and sha(Path(folder)/attempt['review']) == attempt['review_sha256'], 'Saved follow-up review changed')
    for r in state['readiness']:
        require(r['status'] == 'passed' and evidence_hashes(Path(folder)/r['folder']) == r['evidence_sha256'],
                'Follow-up readiness changed')


def check_block_review(path,folder,state):
    require(path is not None, 'Export and independently review the completed block before continuing')
    path = Path(path).resolve(strict=True); r = json.loads(path.read_text())
    require(r['kind'] == 'independent_bursty_followup_block_review' and r['batch'] == Path(folder).name
            and r['accepted_cells'] == len(state['runs']) and r['batch_sha256'] == sha(Path(folder)/'batch.json')
            and r['quality_passed'] is True and r['all_outcomes_retained'] is True
            and len(r['checkpoint_sha256']) == 64, 'Independent block review does not bind this exact paused batch')
    return dict(file=path.name,sha256=sha(path),checkpoint_sha256=r['checkpoint_sha256'],accepted_cells=r['accepted_cells'])


def run(net,limit=4,resume=None,review=None,base=BASE,run_trial=None,inspect_trial=None,auditor=None,
        protocol_loader=load_protocol,parent_check=verify_parent,preflight=environment_check,readiness_check=None,
        report_checker=check_report,matched_loader=None):
    base = Path(base).resolve(); root = base/'results/runs'; p = protocol_loader(base)
    parent = parent_check(base,p)
    require(type(limit) is int and limit == 4, 'One complete four-policy block per call')
    if run_trial is None or inspect_trial is None:
        import run_policy_experiment as runner
        runner = importlib.reload(runner); run_trial = runner.run; inspect_trial = runner.inspect_policy
    if auditor is None:
        from source_integrity import source_integrity_audit
        auditor = source_integrity_audit
    from run_matched_batch import load_protocol as matched
    matched_protocol = (matched_loader or matched)(base)
    if readiness_check is None:
        from run_supplement_recovery import readiness
        readiness_check = readiness
    registry = root/REGISTRY
    if resume is None:
        require(not registry.exists(), 'Follow-up already registered; inspect/resume, never restart')
        check_unused(root)
        folder = root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-bursty-followup')
        folder.mkdir()
        for name in [*p['frozen_source_sha256'],*p['additional_source_sha256'],PROTOCOL]:
            shutil.copy2(base/name,folder/name)
        state = dict(outcome='paused',plan=plan(),protocol_sha256=sha(base/PROTOCOL),parent=parent,
                     attempts=[],runs=[],readiness=[],independent_reviews=[])
        write(folder/'batch.json',state)
        with registry.open('x') as f:
            json.dump(dict(batch=folder.name),f)
    else:
        resume = Path(resume).resolve()
        require(resume.parent == root and registry.exists()
                and json.loads(registry.read_text())['batch'] == resume.name, 'Unregistered follow-up resume')
        folder = child(root,resume.name); state = json.loads((folder/'batch.json').read_text())
        validate_resume(base,folder,state,p)
        require(len(state['runs']) < 16, 'Follow-up already complete; no repeats')
        state['independent_reviews'].append(check_block_review(review,folder,state))
    block = len(state['runs'])//4
    state['outcome'] = 'running'; write(folder/'batch.json',state)
    before = {d.name for d in root.iterdir() if d.is_dir()}; entry = None
    print('BURSTY FOLLOW-UP:',folder,'| block',block+1,'/4',flush=True)
    try:
        env = folder/('environment-'+str(block)); env.mkdir(); preflight(env,base)
        ready_rel = 'readiness/'+str(block); ready = dict(folder=ready_rel,status='running')
        state['readiness'].append(ready); write(folder/'batch.json',state)
        readiness_check(net,base,folder/ready_rel)
        ready.update(status='passed',evidence_sha256=evidence_hashes(folder/ready_rel)); write(folder/'batch.json',state)
        for item in plan()[block*4:(block+1)*4]:
            entry = dict(item,status='running'); state['attempts'].append(entry); write(folder/'batch.json',state)
            print('FOLLOW-UP ACQUISITION:',len(state['attempts']),'/16',item,flush=True)
            raw = run_trial(net,**{k:item[k] for k in ['policy','scenario','seed','requested_bps','duration']})
            raw = child(root,Path(raw).name); entry['folder'] = raw.name
            meta = json.loads((raw/'policy.json').read_text()); entry['trial'] = meta['trial']; write(folder/'batch.json',state)
            report = inspect_trial(raw)
            review_name = 'review-'+str(len(state['attempts'])).zfill(2)+'.json'
            with (folder/review_name).open('x') as f:
                json.dump(report,f,indent=2)
            entry.update(review=review_name,review_sha256=sha(folder/review_name))
            record = report_checker(base,raw,item,matched_protocol,report,auditor)
            entry['status'] = 'passed'; state['runs'].append(record); write(folder/'batch.json',state)
            print('FOLLOW-UP RESULT:',json.dumps({k:record[k] for k in ['policy','seed','sender_mbps','receiver_mbps','udp_loss_percent','actions','denials','source_discard_percent']}),flush=True)
        state['outcome'] = 'completed' if len(state['runs']) == 16 else 'paused'
    except BaseException as error:
        state.update(outcome='failed',error=repr(error))
        if entry is not None and entry['status'] == 'running':
            entry.update(status='failed',error=repr(error))
        state['new_raw_folders'] = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name not in before)
        raise
    finally:
        write(folder/'batch.json',state)
        print('FOLLOW-UP STATE:',state['outcome'],'| accepted',len(state['runs']),'/16 |',folder,flush=True)
    return folder


if 'net' in globals():
    run(net,limit=globals().get('limit',4),resume=globals().get('resume'),review=globals().get('review'))
elif __name__ == '__main__':
    raise SystemExit('Use existing Mininet CLI; see BURSTY_FOLLOWUP.md')
