"""Run from idle primary Mininet. Tests host-pair routing, then restores it.

This is connectivity/control acceptance only, not an experiment or QoS result.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from network.routing_action import RoutingAction, Admission, owned_lines, ofctl, verify_overlay



def wait_for_packet_counts(actor, clock=time.monotonic, sleep=time.sleep,
                           timeout_s=3., poll_s=.1):
    """Require all five probes on both rules, allowing bounded stats propagation.

    This observation wait is separate from action/forwarding latency. No extra
    traffic is sent and no acceptance threshold or OVS setting is changed.
    """
    started=clock();deadline=started+timeout_s;polls=0
    while True:
        polls+=1;counts={}
        for switch in ['s1','s4']:
            text=actor._command(switch,ofctl('dump-flows',switch),'selected_rule_packet_proof')
            verify_overlay(text,switch,'alternate')
            line=owned_lines(text)[0]
            match=re.search(r'n_packets=(\d+)',line)
            if not match: raise RuntimeError('Selected rule packet statistic is missing')
            counts[switch]=int(match[1])
        now=clock()
        actor._log(dict(event='packet_counter_poll',poll=polls,counts=counts,
                        observation_wait_s=now-started))
        if all(count>=5 for count in counts.values()):
            return dict(counts=counts,polls=polls,observation_wait_s=now-started,
                        note='Statistics observation delay, not forwarding activation latency')
        if now>=deadline:
            raise RuntimeError('Selected rule packet counters did not reach five on both edges '
                               f'within the observation window: {counts}')
        sleep(min(poll_s,deadline-now))


def run(net, clock=time.monotonic, sleep=time.sleep):
    folder=BASE/'results/runs'/(
        datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-routing-smoke')
    folder.mkdir(parents=True)
    meta=dict(purpose='Idle h1/h2 IPv4 rerouting smoke; no QoS result',outcome='running',
              phases=[],restoration=None,source_sha256={})
    def save(): (folder/'smoke.json').write_text(json.dumps(meta,indent=2)+'\n')
    for rel in ['network/routing_action.py', 'control/routing_policy.py',
            'control/run_routing_smoke.py', 'network/topology.py',
            'network/diamond_controller.py']:
        name = Path(rel).name
        shutil.copy2(BASE / rel, folder / name)
        meta['source_sha256'][name] = hashlib.sha256((BASE / rel).read_bytes()).hexdigest()

    save();actor=None
    def execute(node,args): return net[node].pexec(args)
    def counters():
        counts={}
        for dev in ['s1-eth3','s1-eth4','s2-eth2','s3-eth2']:
            out,err,code=execute('s1',['cat',f'/sys/class/net/{dev}/statistics/tx_packets'])
            if code: raise RuntimeError(err)
            counts[dev]=int(out.strip())
        return counts
    def probe(name,src,dst,path):
        before=counters()
        out,err,code=execute(src,['ping','-n','-c','5','-i','0.1','-W','2',net[dst].IP()])
        (folder/(name+'.ping.txt')).write_text(out+err)
        after=counters()
        if code or not re.search(r'5 packets transmitted, 5 received',out):
            raise RuntimeError('Connectivity probe failed: '+name)
        deltas={k:after[k]-before[k] for k in before}
        needed=['s1-eth4','s3-eth2'] if path=='alternate' else ['s1-eth3','s2-eth2']
        if any(deltas[k]<5 for k in needed):
            raise RuntimeError('Counter path proof failed: '+name)
        meta['phases'].append(dict(name=name,source=src,destination=dst,
                                   expected_path=path,tx_packet_deltas=deltas))
        save()
    try:
        actor=RoutingAction(execute,folder/'action.jsonl',clock=clock)
        probe('before_selected','h1','h2','primary')
        # Bound idle source/alternate activity from actual counters over one second.
        def source_bytes():
            out,err,code=execute('h1',['cat','/sys/class/net/h1-eth0/statistics/tx_bytes'])
            if code: raise RuntimeError(err)
            return int(out.strip())
        def alternate_bytes():
            values=[]
            for dev in ['s1-eth4','s3-eth2']:
                out,err,code=execute('s1',['cat',f'/sys/class/net/{dev}/statistics/tx_bytes'])
                if code: raise RuntimeError(err)
                values.append(int(out.strip()))
            return values
        t0=clock();src0=source_bytes();alt0=alternate_bytes()
        sleep(1)
        src1=source_bytes();alt1=alternate_bytes();t1=clock()
        if not .9 <= t1-t0 <= 2:
            raise RuntimeError('Idle counter observation duration is outside the accepted range')
        demand=8*(src1-src0)/(t1-t0)
        background=max(8*(b-a)/(t1-t0) for a,b in zip(alt0,alt1))
        if not 0<=demand<=100000 or not 0<=background<=100000:
            raise RuntimeError('Smoke requires an idle testbed; traffic detected')
        links=True
        for dev in ['s1-eth4','s3-eth2','s4-eth4']:
            out,err,code=execute('s1',['cat',f'/sys/class/net/{dev}/carrier'])
            links=links and code==0 and out.strip()=='1'
        certificate=Admission('alternate',t1,max(demand,100000),background,3_000_000,
            links,'Smoke-only conservative 3 Mbit/s admission budget; not calibrated path capacity')
        meta['admission_measurement']=dict(start=t0,end=t1,source_bps=demand,
            background_bps=background,links_up=links,source_bytes_before=src0,
            source_bytes_after=src1,alternate_bytes_before=alt0,alternate_bytes_after=alt1)
        meta['action']=actor.request(certificate,'manual_idle_connectivity_smoke')
        if not meta['action']['applied']: raise RuntimeError('Admission denied')
        probe('alternate_selected','h1','h2','alternate')
        meta['rule_packet_proof']=wait_for_packet_counts(actor,clock=clock,sleep=sleep)
        save()
        probe('alternate_unselected', 'h3', 'h4', 'alternate')
        actor.close(); meta['restoration'] = dict(verified=True, failures=[])
        probe('restored_selected', 'h1', 'h2', 'primary')
        probe('restored_unselected', 'h3', 'h4', 'alternate')
        meta['outcome']='completed'
    except BaseException as error:
        meta['outcome']='failed';meta['error']=str(error)
        raise
    finally:
        if actor is not None and actor.claimed:
            try:
                actor.close();meta['restoration']=dict(verified=True,failures=[])
            except Exception as error:
                meta['restoration']=dict(verified=False,failures=[str(error)])
                meta['outcome']='failed'
        save()
        print('Routing smoke:',meta['outcome'],'| restoration:',meta['restoration'],flush=True)
        print('Saved:',folder,flush=True)
    return folder


if 'net' in globals(): run(net)
