"""Reproduce received-reply mean RTT from original timestamped probe logs."""
from pathlib import Path
import argparse,csv,json,re,statistics
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--repo',type=Path,required=True)
p.add_argument('--networking',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();repo=a.repo.resolve();out=a.output.resolve()
if out.is_relative_to(repo) or out.is_relative_to(a.networking.resolve()):
    raise ValueError('Write latency derivatives outside preserved inputs')
out.mkdir(parents=True,exist_ok=False)
data=json.loads((a.networking/'matched-report.json').read_text(encoding='utf-8'));rows=data['rows']
latency=[]
for row in rows:
    folder=repo/'results/runs'/row['folder'];trial=repo/'results/runs'/row['trial']
    native=json.loads((trial/'sender-native.json').read_text())
    start,end=native['start_wall_epoch_s'],native['end_wall_epoch_s']
    values=[];censored=0
    for line in (folder/'ping-loaded.txt').read_text().splitlines():
        stamp=re.search(r'^\[([\d.]+)\]',line)
        if not stamp or not start<=float(stamp[1])<=end:continue
        m=re.search(r'time([=<])([\d.]+)\s*ms',line)
        if m:
            if m[1]=='<':censored+=1
            else:values.append(float(m[2]))
    report=json.loads((a.networking/'reviews'/(row['folder']+'.json')).read_text())
    expected=report['rtt']['traffic_only']
    assert len(values)+censored==expected['replies']
    assert censored==expected['censored_below_1ms']==0
    ordered=sorted(values)
    # Match the recorded nearest-observation quantile convention; do not
    # silently replace it with averaging the central pair for even counts.
    assert ordered[round((len(ordered)-1)*.5)]==expected['milliseconds']['median']
    assert ordered[round((len(ordered)-1)*.95)]==expected['milliseconds']['p95']
    latency.append(dict(scenario=row['scenario'],policy=row['policy'],seed=row['seed'],folder=row['folder'],
        received_replies=len(values),reply_mean_rtt_ms=statistics.mean(values),reply_median_rtt_ms=expected['milliseconds']['median'],
        reply_p95_rtt_ms=expected['milliseconds']['p95'],traffic_window_loss_percent=None,
        note='Traffic-window received-reply RTT; not one-way delay or a missing-reply latency estimate'))
with (out/'latency-supplement.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(latency[0]));w.writeheader();w.writerows(latency)
(out/'latency-supplement.json').write_text(json.dumps(latency,indent=2)+'\n')
print(json.dumps(dict(trials=len(latency),output=str(out))))
