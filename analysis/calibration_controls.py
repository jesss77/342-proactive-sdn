"""Re-inspect recorded primary calibration and six dual-profile alternate controls."""
import argparse,csv,json,subprocess,sys
from pathlib import Path

ALTERNATE=[
 '20261115-172226-437713-path-control-alternate-12000000bps',
 '20261115-174622-324468-path-control-alternate-12000000bps',
 '20261115-174650-556326-path-control-alternate-12000000bps',
 '20261115-174718-568518-path-control-alternate-16000000bps',
 '20261115-175651-482492-path-control-alternate-16000000bps',
 '20261115-175719-445352-path-control-alternate-16000000bps']

def run(repo,output):
    repo=Path(repo).resolve();output=Path(output).resolve()
    if output.is_relative_to(repo):raise ValueError('Write derivatives outside the checkpoint')
    output.mkdir(parents=True,exist_ok=False)
    subprocess.run([sys.executable,str(repo/'summarize_calibration.py'),'--runs',str(repo/'results/runs'),'--output',str(output/'primary')],check=True,stdout=subprocess.DEVNULL)
    sys.path.insert(0,str(repo))
    from run_path_control import inspect_control
    with (output/'primary/runs.csv').open(newline='') as f:primary=list(csv.DictReader(f))
    rows=[dict(condition='primary calibration',profile='historical primary: recorded source250/cburst16KiB; see raw qdisc/class evidence',run=r['run'],
        requested_mbps=float(r['offered_mbps']),sender_mbps=float(r['sender_mbps']),receiver_mbps=float(r['receiver_mbps']),
        udp_sequence_loss_percent=float(r['receiver_sequence_loss_percent']),
        bottleneck_root_drops=int(r['bottleneck_drops']),path_and_accounting_check='passed recorded primary checks') for r in primary]
    reports=[]
    for name in ALTERNATE:
        r=inspect_control(repo/'results/runs'/name)
        if r['outcome']!='completed' or r['control_screen_failures']:raise ValueError('Alternate control failed: '+name)
        reports.append(r);t=r['trial']
        rows.append(dict(condition='alternate fixed control',profile=r['profile']['id'],run=name,
            requested_mbps=t['requested_bps']/1e6,sender_mbps=t['sender']['bits_per_second']/1e6,
            receiver_mbps=t['receiver']['bits_per_second']/1e6,udp_sequence_loss_percent=t['receiver']['lost_percent'],
            bottleneck_root_drops=sum(t['queue_drop_deltas'][n] for n in ['s1-eth4','s3-eth2']),
            path_and_accounting_check='passed selected/inactive counters, collector and restoration checks'))
    with (output/'controls.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (output/'alternate-reviews.json').write_text(json.dumps(reports,indent=2)+'\n')
    (output/'README.md').write_text('# Recorded calibration controls\n\nTwelve re-inspected controls; profiles and traffic engines are explicitly separated in controls.csv. Primary results predate the common dual-profile controls and are not matched policy comparisons. Root drops and UDP sequence loss have distinct definitions. All original records remain in the checkpoint.\n')
    print(json.dumps(dict(primary_controls=len(primary),alternate_controls=len(reports),output=str(output))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.repo,a.output)
