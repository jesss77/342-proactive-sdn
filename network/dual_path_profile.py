"""Both forward paths receive the same recorded calibration for every policy."""
from contextlib import contextmanager
from pathlib import Path
import json
import re

PROFILE='dual-forward-cburst16k-source250-v1'
LINKS = [('h1', 'h1-eth0', 100), ('h3', 'h3-eth0', 100),
         ('s1', 's1-eth3', 100), ('s2', 's2-eth2', 10),
         ('s1', 's1-eth4', 20),  ('s3', 's3-eth2', 20),
         ('s4', 's4-eth1', 100), ('s4', 's4-eth2', 100)]

QUEUES=['s1-eth3','s2-eth2','s1-eth4','s3-eth2']


@contextmanager
def dual_profile(net,folder):
    folder=Path(folder);changed=[];source_touched=False
    def execute(node,args,label):
        out,err,code=net[node].pexec(args)
        with (folder/'dual-profile.jsonl').open('a') as f:
            f.write(json.dumps(dict(node=node,args=args,label=label,stdout=out,stderr=err,exit=code))+'\n')
        if code: raise RuntimeError(f'{node}/{label}: {err or out}')
        return out
    def verify(cburst,source_limit,label):
        for node,dev,rate in LINKS:
            text=execute(node,['tc','-s','class','show','dev',dev],label+'_class')
            burst='cburst 1600b' if cburst==1600 else 'cburst 16Kb'
            if not all(x in text for x in [f'rate {rate}Mbit',f'ceil {rate}Mbit','burst 15Kb',burst]):
                raise RuntimeError('Unexpected class: '+dev)
            text=execute(node,['tc','-s','qdisc','show','dev',dev],label+'_queue')
            limit = source_limit if dev in ('h1-eth0', 'h3-eth0') else 50
            if not re.search(r'netem.*limit '+str(limit)+r'\b.*delay 1ms',text):
                raise RuntimeError('Unexpected queue: '+dev)
    def set_class(node,dev,rate,value,label):
        execute(node,['tc','class','change','dev',dev,'parent','5:','classid','5:1',
                      'htb','rate',f'{rate}mbit','ceil',f'{rate}mbit','burst','15360',
                      'cburst',str(value)],label)
    def set_source(value,label):
        for host, dev in [('h1', 'h1-eth0'), ('h3', 'h3-eth0')]:
            execute(host, ['tc', 'qdisc', 'change', 'dev', dev, 'parent', '5:1', 'handle', '10:',
                       'netem', 'delay', '1ms', 'limit', str(value)], f'{label}_{host}')
    verify(1600,50,'preflight')
    try:
        for link in LINKS:
            changed.append(link)  # Attempt restoration even after uncertain command failure.
            set_class(*link,16384,'apply')
        source_touched=True;set_source(250,'apply_source')
        verify(16384,250,'active')
        yield dict(id=PROFILE,forward_links=LINKS,cburst_bytes=16384,burst_bytes=15360,
                   source_queue_packets=250,bottleneck_queue_packets=50,delay_ms=1)
    finally:
        failures=[]
        if source_touched:
            try: set_source(50,'restore_source')
            except Exception as e: failures.append(str(e))
        for link in reversed(changed):
            try: set_class(*link,1600,'restore_class')
            except Exception as e: failures.append(str(e))
        try: verify(1600,50,'restored')
        except Exception as e: failures.append(str(e))
        (folder/'restoration.json').write_text(json.dumps(dict(failures=failures),indent=2))
        if failures: raise RuntimeError('Dual-path restoration failed: '+'; '.join(failures))
