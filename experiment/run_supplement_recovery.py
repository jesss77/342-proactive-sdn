"""One prospective, whole-block recovery; original failed batch stays immutable."""
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
import importlib,json,os,shutil,subprocess,sys,time
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from run_matched_batch import sha,write,child,evidence_hashes,check_report
from run_supplement_batch import load_protocol as load_original,plan as original_plan

SETTINGS=dict(id='bursty-supplement-recovery-v1',seeds=[44,45,46],policies=['fixed','reactive','early_warning','ml'],
    scale_bps=11500000,duration_s=60,interval_s=.25,coverage='all',readiness_duration_s=60,
    readiness_clocksource='tsc',cpu_count=1,
    parent_batch='20261120-173253-671820-advisor-supplement',
    parent_archive_sha256='fb5d184b1888add78828938b72bf37bda99233996ea3b4c25b5def46d28ba07c',
    original_supplement_protocol_sha256='e6ab6a81507065959e199b78d22872dc5d9d4be56492da855c7ca90d8a7636a0',
    recovery_rule='One new attempt per full four-policy seed block; restart incomplete seed44 block, then seeds45/46. Stop on any failed cell/readiness check; no automatic replacements.',
    analysis_rule='Use complete quality-valid recovery blocks for extra paired comparisons. Retain original accepted reactive44 and failed early_warning44 as incomplete-block diagnostics; never pool them with replacements.',
    freshness_scope='Preserve original pre-entry freshness gate and shared action, including pre-install verification aging. Measure actual age/decision-to-readback; do not claim exact packet activation.')
OWN_SOURCES=['run_supplement_recovery.py','test_supplement_recovery.py','SUPPLEMENT_RECOVERY.md']

def plan():return [dict(r,recovery=True) for r in original_plan()[6:]]

def load_protocol(base):
    base=Path(base);old,matched=load_original(base)
    p=json.loads((base/'supplement_recovery_protocol.json').read_text())
    if p.get('settings')!=SETTINGS or p.get('plan')!=plan():raise ValueError('Recovery registration changed')
    if sha(base/'supplement_protocol.json')!=SETTINGS['original_supplement_protocol_sha256']:
        raise ValueError('Original supplement protocol changed')
    if set(p.get('additional_source_sha256',{}))!=set(OWN_SOURCES):raise ValueError('Recovery source pins incomplete')
    if len(p.get('frozen_source_sha256',{}))!=68 or len(p.get('parent_files_sha256',{}))!=828:
        raise ValueError('Recovery parent/source pins incomplete')
    for name,digest in dict(p['frozen_source_sha256'],**p['additional_source_sha256']).items():
        if Path(name).name!=name or (base/name).is_symlink() or sha(base/name)!=digest:
            raise ValueError('Recovery/frozen source changed: '+name)
    return p,matched

def verify_parent(base,p):
    base=Path(base).resolve()
    for name,digest in p['parent_files_sha256'].items():
        rel=PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:raise ValueError('Unsafe parent path')
        path=base.joinpath(*rel.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(base) or sha(path)!=digest:
            raise ValueError('Preserved parent evidence changed: '+name)
    parent=child(base/'results/runs',SETTINGS['parent_batch'])
    state=json.loads((parent/'batch.json').read_text())
    if (state.get('outcome')!='failed' or len(state['runs'])!=7 or len(state['attempts'])!=8
        or [a['status'] for a in state['attempts']]!=['passed']*7+['failed']):
        raise ValueError('Parent stopped state differs')
    return dict(batch=parent.name,files_verified=len(p['parent_files_sha256']),parent_outcome='failed',original_state_edited=False)

def inspect_readiness(folder,before,after,elapsed,clock_before,clock_after):
    from inspect_experiment import queue_summary
    from dual_path_profile import QUEUES
    folder=Path(folder);rows=[json.loads(s) for s in (folder/'samples.jsonl').read_text().splitlines()]
    stats=json.loads((folder/'samples.jsonl.stats.json').read_text());failures=[]
    queues={q:queue_summary(rows,q) for q in QUEUES}
    if os.cpu_count()!=1:failures.append('cpu_count')
    if clock_before!=SETTINGS['readiness_clocksource'] or clock_after!=clock_before:failures.append('clocksource')
    if not 57<=elapsed<=66 or not 57<=stats.get('elapsed_s',0)<=66:failures.append('readiness_duration')
    if stats.get('schema_version')!=6 or stats.get('coverage')!='all' or set(stats.get('queried_qdiscs',[]))!=set(QUEUES):
        failures.append('coverage')
    if any(q['failed_queries'] or q['invalid_intervals'] or q['interval_count']<215 for q in queues.values()):
        failures.append('collector_quality')
    rates={}
    for dev in QUEUES:
        a=before.get(dev,{});b=after.get(dev,{})
        if 'error' in a or 'error' in b or 'tx_bytes' not in a or 'tx_bytes' not in b or elapsed<=0:
            failures.append('idle_counter:'+dev);continue
        rate=8*(b['tx_bytes']-a['tx_bytes'])/elapsed;rates[dev]=rate
        if not 0<=rate<=100000:failures.append('not_idle:'+dev)
    return dict(outcome='passed' if not failures else 'failed',screen_failures=failures,
        elapsed_s=elapsed,clock_before=clock_before,clock_after=clock_after,queues=queues,stats=stats,idle_rates_bps=rates,
        scope='Idle collector only, no generated UDP/probes or rule/profile changes. Passing does not guarantee loaded timing.')

def readiness(net,base,folder):
    from experiment_config import verify_route
    from run_experiment import interface_counts
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    clock=Path('/sys/devices/system/clocksource/clocksource0/current_clocksource')
    m=dict(outcome='running',started=datetime.now(timezone.utc).isoformat(),no_traffic_generated=True)
    def save():write(folder/'readiness.json',m)
    save()
    try:
        if os.cpu_count()!=1:raise ValueError('Original one-vCPU guest required')
        m['route_before']=verify_route(net,'primary',folder,'before')
        first_clock=clock.read_text().strip();before=interface_counts();started=time.monotonic()
        command=['/usr/bin/python3',str(Path(base)/'collect_path.py'),str(folder/'samples.jsonl'),
            '--route','primary','--coverage','all','--interval','.25','--duration','60']
        m['command']=command;save();print('READINESS: 60-second idle collector check; no traffic or rule changes',flush=True)
        with (folder/'collector.log').open('x') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
        elapsed=time.monotonic()-started;after=interface_counts();last_clock=clock.read_text().strip()
        m['route_after']=verify_route(net,'primary',folder,'after')
        report=inspect_readiness(folder,before,after,elapsed,first_clock,last_clock)
        m.update(outcome=report['outcome'],report=report);save()
        if report['screen_failures']:raise ValueError('Idle readiness failed: '+','.join(report['screen_failures']))
        print('READINESS: passed',flush=True)
        return report
    except BaseException as e:
        m.update(outcome='failed',error=repr(e));save();raise

def validate_resume(base,folder,state,p):
    registered=plan();root=Path(base)/'results/runs'
    if (state.get('outcome') not in ['paused','completed'] or state.get('protocol_sha256')!=sha(Path(base)/'supplement_recovery_protocol.json')
        or state.get('plan')!=registered or len(state['runs'])%4 or len(state['runs'])>12
        or len(state['runs'])!=len(state['attempts']) or any(a['status']!='passed' for a in state['attempts'])
        or any({k:r[k] for k in item}!=item for r,item in zip(state['runs'],registered))):
        raise ValueError('Failed/partial/changed recovery requires review; no automatic retry')
    if sha(folder/'supplement_recovery_protocol.json')!=state['protocol_sha256']:raise ValueError('Captured registration changed')
    for name,digest in p['additional_source_sha256'].items():
        if sha(folder/name)!=digest:raise ValueError('Captured recovery source changed')
    for record in state['runs']:
        for key,hkey in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:
            if evidence_hashes(child(root,record[key]))!=record[hkey]:raise ValueError('Accepted recovery evidence changed')
    for record in state['readiness']:
        if record['status']!='passed' or evidence_hashes(folder/record['folder'])!=record['evidence_sha256']:
            raise ValueError('Readiness evidence changed')

def run(net,limit=4,resume=None,base=BASE,run_trial=None,inspect_trial=None,source_auditor=None,
        readiness_check=readiness,parent_check=verify_parent):
    base=Path(base).resolve();p,matched=load_protocol(base);parent=parent_check(base,p)
    if type(limit) is not int or limit not in [4,8,12]:raise ValueError('Acquire complete blocks: limit 4, 8 or 12')
    if run_trial is None or inspect_trial is None:
        import run_policy_experiment as runner
        runner=importlib.reload(runner);run_trial=runner.run;inspect_trial=runner.inspect_policy
    if source_auditor is None:
        from source_integrity import source_integrity_audit
        source_auditor=source_integrity_audit
    root=base/'results/runs';registered=plan();registry=root/'supplement-recovery-registry-v1.json'
    if resume is None:
        if registry.exists():raise ValueError('Recovery already registered; inspect/resume instead')
        folder=root/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-bursty-supplement-recovery')
        folder.mkdir(parents=True)
        state=dict(role='prospective_whole_block_recovery',registered_at=datetime.now(timezone.utc).isoformat(),
            protocol_sha256=sha(base/'supplement_recovery_protocol.json'),plan=registered,parent=parent,
            outcome='paused',attempts=[],runs=[],readiness=[])
        for name in ['supplement_recovery_protocol.json',*p['additional_source_sha256']]:shutil.copy2(base/name,folder/name)
        with registry.open('x') as f:json.dump(dict(batch=folder.name),f)
    else:
        folder=child(root,Path(resume).name)
        if not registry.exists() or json.loads(registry.read_text())['batch']!=folder.name:raise ValueError('Unregistered recovery resume')
        state=json.loads((folder/'batch.json').read_text());validate_resume(base,folder,state,p)
    def save():write(folder/'batch.json',state)
    save();(root/'active-supplement-recovery-v1.txt').write_text(str(folder)+'\n')
    count=len(state['runs'])
    if count==12:print('Recovery already complete:',folder,flush=True);return folder
    state['outcome']='running';save();print('Recovery batch:',folder,flush=True)
    try:
        ready=folder/'readiness'/f'{len(state["readiness"]):02d}'
        entry=dict(folder=ready.relative_to(folder).as_posix(),status='running');state['readiness'].append(entry);save()
        try:
            readiness_check(net,base,ready)
            entry.update(status='passed',evidence_sha256=evidence_hashes(ready));save()
        except BaseException as e:entry.update(status='failed',error=repr(e));raise
        for item in registered[count:min(count+limit,12)]:
            load_protocol(base);parent_check(base,p)
            attempt=dict(item,status='running');state['attempts'].append(attempt);save()
            before={x.name for x in root.iterdir() if x.is_dir()}
            print('RECOVERY ACQUISITION:',len(state['runs'])+1,'/12',item,flush=True)
            try:
                raw=Path(run_trial(net,policy=item['policy'],scenario=item['scenario'],seed=item['seed'],
                    duration=item['duration'],requested_bps=item['requested_bps']))
                attempt['folder']=raw.name
                if raw.resolve().parent!=root:raise ValueError('Foreign recovery raw folder')
                report=inspect_trial(raw)
                reviews=folder/'reviews';reviews.mkdir(exist_ok=True)
                write(reviews/(f'{len(state["attempts"])-1:02d}-'+raw.name+'.json'),report)
                record=check_report(base,raw,item,matched,report,source_auditor)
                load_protocol(base);parent_check(base,p)
                state['runs'].append(record);attempt['status']='passed';save()
                print('RECOVERY RESULT:',json.dumps({k:v for k,v in record.items() if not k.endswith('_sha256')}),flush=True)
            except BaseException as e:
                attempt.update(status='failed',error=repr(e),candidate_raw_folders=sorted({x.name for x in root.iterdir() if x.is_dir()}-before));raise
        state['outcome']='completed' if len(state['runs'])==12 else 'paused'
    except BaseException:
        state['outcome']='failed';save();raise
    finally:save()
    print('Recovery:',state['outcome'],'| accepted',len(state['runs']),'/12 | complete blocks',len(state['runs'])//4,'|',folder,flush=True)
    return folder

if 'net' in globals():run(net,limit=globals().get('limit',4),resume=globals().get('resume'))
