"""Resource timeline summary shared by the retained scientific audits."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse,hashlib,json,re,statistics,sys,tarfile
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_stopped_supplement import read,lines,sha,save,intervals,actions,original_action_audit

def resources(path,native,tz):
    fields=None;rows=[]
    for line in Path(path).read_text().splitlines():
        p=line.split()
        if p[:3]==['r','b','swpd']:fields=p[:-1];continue
        if fields and len(p)==len(fields)+2 and re.fullmatch(r'\d{4}-\d\d-\d\d',p[-2]):
            stamp=datetime.fromisoformat(p[-2]+'T'+p[-1]).replace(tzinfo=tz).timestamp()
            row={name:float(x) for name,x in zip(fields,p[:-2])}
            row.update(source_s=stamp-native['start_wall_epoch_s'],epoch_s=stamp,local_time=p[-2]+' '+p[-1])
            rows.append(row)
    # The first vmstat data line describes averages since boot, not a one-second window.
    selected=[r for r in rows[1:] if 0<=r['source_s']<=60]
    return dict(rows=rows,traffic_rows=len(selected),
        mean_user_system_percent=statistics.mean(r['us']+r['sy'] for r in selected),
        max_user_system_percent=max(r['us']+r['sy'] for r in selected),
        zero_idle_windows=sum(r['id']==0 for r in selected),max_runnable=max(r['r'] for r in selected),
        max_swap_in=max(r['si'] for r in selected),max_swap_out=max(r['so'] for r in selected),
        scope='Guest one-second resource intervals; not precise host scheduling attribution')
