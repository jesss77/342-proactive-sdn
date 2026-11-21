"""Re-inspect all initial supplemental outcomes and the failed recovery from raw records."""
from pathlib import Path
import json,sys,argparse
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def run(repo,pub,out):
    repo=Path(repo);pub=Path(pub);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(repo))
    from run_policy_experiment import inspect_policy
    from run_schedule_path_control import inspect_control
    from run_matched_batch import evidence_hashes,check_report
    from source_integrity import source_integrity_audit
    import run_supplement_batch as supplement
    p,matched=supplement.load_protocol(repo);root=repo/'results/runs'
    reference=read(pub/'results/supplement-diagnostics-v1/audit.json')
    batch=root/'20261120-173253-671820-advisor-supplement';state=read(batch/'batch.json')
    assert state['outcome']=='failed' and len(state['attempts'])==8 and len(state['runs'])==7
    rows=[]
    for index,expected in enumerate(reference['reports']):
        folder=root/expected['folder'];item=expected['identity']
        report=inspect_control(folder) if item['stage']=='controls' else inspect_policy(folder)
        assert report==expected['report'],folder.name
        if index<7:
            record=state['runs'][index]
            for k,h in [('folder','policy_evidence_sha256'),('trial','trial_evidence_sha256')]:assert evidence_hashes(root/record[k])==record[h]
            checked=supplement.control_record(repo,folder,item,report) if item['stage']=='controls' else check_report(repo,folder,item,matched,report,source_integrity_audit)
            assert checked==record
        else:
            assert report['screen_failures']==['collector_quality']
            try:check_report(repo,folder,item,matched,report,source_integrity_audit)
            except ValueError as e:assert str(e)=='Matched trial quality/restoration failed'
            else:raise AssertionError('Historical failed trial unexpectedly passed')
        rows.append(dict(folder=folder.name,identity=item,status=expected['status'],report=report))
    recovery=read(pub/'results/loaded-recovery-diagnostics-v1/audit.json')
    failed=recovery['failed'];folder=root/failed['folder'];report=inspect_policy(folder)
    assert report==failed['report'] and set(report['screen_failures'])=={'udp_error','collector_quality'}
    assert evidence_hashes(folder)==failed['raw_evidence_sha256']
    assert evidence_hashes(root/failed['trial'])==failed['trial_evidence_sha256']
    r=dict(initial_supplement=rows,recovery_failed=report,source_or_quality_changed=False,traffic_started=False)
    (out/'reports.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(dict(supplement_outcomes=len(rows),recovery_failure_reproduced=True)))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--published',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.repo,a.published,a.output)
