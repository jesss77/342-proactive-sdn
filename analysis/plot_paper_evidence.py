"""Standalone scientific figures from the consolidated evidence and frozen capture pilot."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle,FancyBboxPatch

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def lines(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]

def run(repo,analysis,out):
    repo=Path(repo);out=Path(out);out.mkdir(parents=True,exist_ok=False);data=read(Path(analysis)/'paper-evidence.json')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,
        'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'pdf.fonttype':42,'svg.fonttype':'none',
        'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':300})
    files=[]
    def save(fig,name):
        for suffix in ['pdf','svg','png']:
            path=out/(name+'.'+suffix)
            kwargs=dict(metadata={'CreationDate':None,'ModDate':None}) if suffix=='pdf' else {}
            fig.savefig(path,bbox_inches='tight',pad_inches=.035,**kwargs);files.append(path)
        plt.close(fig)
    # The original four-host diamond, including the two idle hosts.
    fig,ax=plt.subplots(figsize=(3.45,2.05));ax.set_xlim(-.6,5.6);ax.set_ylim(-1.55,2.0);ax.axis('off')
    pos={'h1':(-.15,.2),'s1':(1,.2),'s2':(2.5,1.1),'s3':(2.5,-.65),'s4':(4,.2),'h2':(5.15,.2),'h3':(.45,-1.05),'h4':(4.55,-1.05)}
    for a,b,rate,color in [('h1','s1',100,'#333333'),('s1','s2',100,'#0072B2'),('s2','s4',10,'#0072B2'),
                           ('s1','s3',20,'#009E73'),('s3','s4',20,'#009E73'),('s4','h2',100,'#333333'),
                           ('h3','s1',100,'#aaaaaa'),('h4','s4',100,'#aaaaaa')]:
        x,y=pos[a],pos[b];ax.plot([x[0],y[0]],[x[1],y[1]],color=color,lw=1.7,zorder=1)
        if a not in ['h3','h4']:
            xx=(x[0]+y[0])/2;yy=(x[1]+y[1])/2+.16
            ax.text(xx,yy,str(rate),ha='center',va='bottom',fontsize=7,color=color,bbox=dict(fc='white',ec='none',pad=.4))
    for name,(x,y) in pos.items():
        ax.add_patch(Circle((x,y),.22,fc='white',ec='#222222' if name not in ['h3','h4'] else '#999999',zorder=3))
        ax.text(x,y,name,ha='center',va='center',zorder=4,fontsize=8)
    ax.text(2.5,1.6,'OS-Ken controller / OpenFlow 1.3',ha='center',fontsize=8)
    ax.text(2.5,1.32,'Primary',ha='center',color='#0072B2',fontsize=7)
    ax.text(2.5,-1.02,'Alternate',ha='center',color='#009E73',fontsize=7)
    ax.text(.45,-1.43,'idle',ha='center',fontsize=7,color='#777777');ax.text(4.55,-1.43,'idle',ha='center',fontsize=7,color='#777777')
    ax.text(2.5,-1.42,'Link labels: configured Mbit/s',ha='center',fontsize=7)
    save(fig,'01-topology')
    # Independent paired results, with the later cohort clearly separated.
    fig,axes=plt.subplots(1,3,figsize=(7.1,2.0),layout='constrained')
    selected=[r for r in data['paired_ml_minus_trend'] if r['scenario'] in ['ramp','bursty']]
    for ax,key,label in zip(axes,['delta_receiver_mbps','delta_loss_pp','delta_rtt_p95_ms'],
        ['Goodput difference (Mbit/s)','Loss difference (pp)','Probe p95 RTT difference (ms)']):
        for i,r in enumerate(selected):
            ax.scatter(i,r[key],marker='D' if r['cohort']!='original' else 'o',s=30,color='#D55E00' if r['cohort']!='original' else '#0072B2',zorder=3)
        ax.axhline(0,color='#555555',lw=.8);ax.axvspan(5.5,6.5,color='#eeeeee',zorder=0)
        ax.set_xticks(range(7),['R41','R42','R43','B41','B42','B43','B51']);ax.tick_params(axis='x',labelsize=6)
        ax.set_xlabel('Matched realization')
        ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    save(fig,'02-paired-differences')
    # The real captured run: measured source, observed utilization and queue occupancy.
    root=repo/'results/runs';batch=root/'20261121-012117-648967-packet-activation-pilot';review=read(batch/'capture/review.json')
    policy=root/'20261121-014335-222889-policy-ml-ramp-seed1';trial=root/read(policy/'policy.json')['trial']
    sender=read(trial/'sender-native.json');start=sender['start_monotonic_ns']/1e9
    src=lines(trial/'sender-samples.jsonl');t=[];rate=[]
    for a,b in zip(src,src[1:]):
        dt=(b['monotonic_ns']-a['monotonic_ns'])/1e9
        t.append((a['monotonic_ns']+b['monotonic_ns'])/2e9-start);rate.append(8*sender['payload_bytes']*(b['sent_packets']-a['sent_packets'])/dt/1e6)
    raw=lines(policy/'samples.jsonl');qt=[];primary=[];alternate=[];qp=[];qa=[]
    for a,b in zip(raw,raw[1:]):
        pairs={}
        for dev in ['s2-eth2','s3-eth2']:
            x,y=a['qdiscs'][dev],b['qdiscs'][dev]
            dt=(y['tc_start']+y['tc_end']-x['tc_start']-x['tc_end'])/2
            pairs[dev]=8*(y['root_qdisc']['bytes']-x['root_qdisc']['bytes'])/dt/y['capacity_bps']
        q=b['qdiscs']['s2-eth2'];qt.append((q['tc_start']+q['tc_end'])/2-start)
        primary.append(pairs['s2-eth2']);alternate.append(pairs['s3-eth2']);qp.append(q['root_qdisc']['qlen']);qa.append(b['qdiscs']['s3-eth2']['root_qdisc']['qlen'])
    action=review['actions'][0];packet=review['capture']['timing']['first_alternate_packet']
    packet_t=(packet['observed_monotonic_low_ns']+packet['observed_monotonic_high_ns'])/2e9-start
    fig,axes=plt.subplots(3,1,figsize=(3.45,3.2),sharex=True,layout='constrained')
    axes[0].plot(t,rate,color='#333333',lw=.8,label='Measured sender payload');axes[0].set_ylabel('Mbit/s');axes[0].legend(loc='upper right')
    axes[1].plot(qt,primary,color='#0072B2',lw=.9,label='Primary');axes[1].plot(qt,alternate,color='#009E73',lw=.9,label='Alternate')
    threshold=read(repo/'dataset_protocol.json')['label_config']['utilization_threshold']
    axes[1].axhline(threshold,ls=':',color='#777777',lw=.7);axes[1].set_ylabel('Utilization');axes[1].legend(loc='upper right')
    axes[2].plot(qt,qp,color='#0072B2',lw=.8);axes[2].plot(qt,qa,color='#009E73',lw=.8);axes[2].set_ylabel('Queued packets');axes[2].set_xlabel('Seconds from native source start')
    for ax in axes:
        ax.axvline(action['decision_at']-start,color='#D55E00',ls='--',lw=.8)
        ax.axvline(packet_t,color='#7b3294',ls=':',lw=.9);ax.grid(alpha=.15);ax.set_xlim(0,60)
    axes[0].set_title('Captured ML ramp, seed 1')
    save(fig,'03-aligned-captured-trace')
    # Distinct control timestamps; not an atomic-installation or outage plot.
    origin=action['decision_at'];first=review['capture']['timing']['first_alternate_after_decision_s']
    points=[('Observation available',1000*(action['admission']['observed_at']-origin)),('Decision',0),
            ('Programming starts',1000*(action['started']-origin)),('First alternate UDP',500*(first[0]+first[1])),
            ('Final flow readback',1000*(action['verified_finished']-origin))]
    fig,ax=plt.subplots(figsize=(3.45,1.75));yy=np.arange(len(points))[::-1]
    for y,(label,x) in zip(yy,points):
        ax.plot([0,x],[y,y],color='#bbbbbb',lw=.8);ax.scatter(x,y,color='#7b3294' if 'UDP' in label else '#0072B2',s=22,zorder=3)
        ax.text(x+5,y,f'{x:.1f}',va='center',fontsize=7)
    ax.set_yticks(yy,[x[0] for x in points]);ax.set_xlim(-15,240);ax.set_xlabel('Milliseconds relative to decision');ax.grid(axis='x',alpha=.2)
    save(fig,'04-forwarding-timing')
    # Offline event coverage under explicit, descriptive lead-margin budgets.
    fig,ax=plt.subplots(figsize=(3.45,2.2));budgets=np.linspace(0,2,201)
    for method,style in [('ML','-'),('trend','--')]:
        for scenario,color in [('ramp','#0072B2'),('bursty','#D55E00')]:
            g=[r for r in data['warning_by_run'] if (r['method'],r['scenario'])==(method,scenario)]
            leads=[v for r in g for v in r['lead_s']];n=sum(r['scorable_events'] for r in g)
            ax.step(budgets,[sum(v>=b for v in leads)/n for b in budgets],where='post',ls=style,color=color,
                label=('Ramp' if scenario=='ramp' else 'Bursty')+' '+('ML' if method=='ML' else 'trend'))
    ax.set(xlabel='Required offline lead margin (s)',ylabel='Scorable events warned',ylim=(-.02,1.02),xlim=(0,2));ax.legend(ncol=2);ax.grid(alpha=.2)
    save(fig,'05-warning-margin')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (out/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(figures=5,standalone_files=len(files),output=str(out))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.repo,a.analysis,a.output)
