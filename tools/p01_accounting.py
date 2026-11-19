"""Reconcile the historical P01 summary; this does not accept its failed measurements."""
import argparse,hashlib,json,re
from pathlib import Path

def run(repo,output):
    repo=Path(repo).resolve();output=Path(output).resolve()
    if output.is_relative_to(repo) or output.exists():raise ValueError('Use a new output outside checkpoint inputs')
    folder=repo/'results/archive/results/P01-primary-3M'
    text=(folder/'client.txt').read_text(encoding='utf-8')
    receiver=json.loads((folder/'server.json').read_text())['end']['sum_received']
    total=int(re.search(r'0/(\d+)\s+\(0%\)\s+sender',text)[1])
    seconds=float(re.search(r'0\.00-([\d.]+)\s+sec[^\n]*sender',text)[1])
    received=receiver['packets']-receiver['lost_packets']
    if receiver['bytes']!=received*1200:raise ValueError('Payload counts disagree')
    rate=receiver['bytes']*8/receiver['seconds']
    if abs(rate-receiver['bits_per_second'])>1e-8:raise ValueError('Receiver summary rate disagrees')
    result=dict(requested_bps=3000000,sender_datagrams=total,sender_duration_s_rounded=seconds,
        sender_bps_approx_from_rounded_duration=total*1200*8/seconds,receiver_sequence_total=receiver['packets'],
        receiver_sequence_missing=receiver['lost_packets'],receiver_sequence_loss_percent=receiver['lost_percent'],
        received_datagrams=received,receiver_bytes=receiver['bytes'],receiver_duration_s=receiver['seconds'],
        receiver_bps_recomputed=rate,sender_based_missing_datagrams=total-received,
        input_sha256={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ['client.txt','server.json']},
        interpretation='Requested sending rate was not achieved; intervals and loss denominators differ. Arithmetic reconciles, original anomaly remains diagnostic and excluded. No layer/drop counters are summed.')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(receiver_bps=rate,status='Reconciled; remains excluded')))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.repo,a.output)
