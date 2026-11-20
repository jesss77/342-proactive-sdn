"""Time-aligned explanatory traces from frozen raw logs; never invent packet activation times."""
import argparse,csv,hashlib,json,math,sys
from pathlib import Path

POLICIES=['fixed','reactive','early_warning','ml']
CASES=[('ramp',42),('bursty',42),('steady',41)]
QUEUES=['s1-eth3','s2-eth2','s1-eth4','s3-eth2']
def read_lines(path):return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]
def sender_intervals(samples,native):
    start=native['start_monotonic_ns']/1e9;previous_t=start;previous_n=0;result=[]
    records=[(r['monotonic_ns']/1e9,r['sent_packets']) for r in samples]
    end=native['end_monotonic_ns']/1e9
    if records and (records[-1][0]>end or records[-1][1]>native['sent_packets']):raise ValueError('Sender sample exceeds final totals')
    if not records or records[-1]!=(end,native['sent_packets']):records.append((end,native['sent_packets']))
    for t,n in records:
        if t<=previous_t or n<previous_n:raise ValueError('Sender counter/time reset')
        result.append(dict(t0_s=previous_t-start,t1_s=t-start,mid_s=(t+previous_t)/2-start,
            packets_delta=n-previous_n,payload_bps=8*1200*(n-previous_n)/(t-previous_t)))
        previous_t,previous_n=t,n
    if sum(r['packets_delta'] for r in result)!=native['sent_packets']:raise ValueError('Sender interval accounting mismatch')
    return result

def queue_intervals(raw,queue,start):
    from inspect_experiment import queue_rows,sample_intervals
    selected=list(queue_rows(raw,queue));bounds={}
    for r in selected:
        if 'tc_start' in r and 'tc_end' in r:bounds[(r['tc_start']+r['tc_end'])/2]=(r['tc_start'],r['tc_end'])
    result=[]
    for r in sample_intervals(selected):
        current=r['monotonic'];previous=current-r['actual_dt_s']
        prior=min(bounds,key=lambda x:abs(x-previous))
        if abs(prior-previous)>1e-7:raise ValueError('Cannot identify prior counter read')
        result.append(dict(queue=queue,t0_s=previous-start,t1_s=current-start,available_s=bounds[current][1]-start,
            observation_left_s=bounds[prior][0]-start,observation_right_s=bounds[current][1]-start,
            departure_bps=r['qdisc_departure_bps'] if r['sampling_valid'] else None,
            utilization=r['utilization'] if r['sampling_valid'] else None,queue_packets=r['queue_packets'],
            backlog_bytes=r['backlog_bytes'],root_drops_delta=r['drops_delta'],valid=r['sampling_valid']))
    return result

def path_observation(alternate,action):
    if action is None:return None
    candidates=[r for r in alternate if r['valid'] and r['departure_bps']>0 and r['observation_right_s']>=action['started_s']]
    if not candidates:return dict(status='No qualifying alternate departure interval')
    r=candidates[0]
    return dict(status='First nonzero alternate root departure interval overlapping/following request',
        left_s=r['observation_left_s'],right_s=r['observation_right_s'],
        meaning='Counter observation includes probes/control; not a first-UDP-packet activation timestamp or a packet disruption measurement')

def extract(repo,row):
    folder=repo/'results/runs'/row['folder'];trial=repo/'results/runs'/row['trial']
    native=json.loads((trial/'sender-native.json').read_text());start=native['start_monotonic_ns']/1e9
    raw=read_lines(folder/'samples.jsonl');decisions=read_lines(folder/'decisions.jsonl')
    queues={q:queue_intervals(raw,q,start) for q in QUEUES};events=[];applied=None
    for d in decisions:
        if not d.get('reason'):continue
        a=d.get('action') or {};e=dict(decision_s=d['decision_at']-start,available_s=d.get('feature_available',start)-start,
            sample_age_s=d.get('sample_age_s'),reason=d['reason'],applied=bool(a.get('applied')),
            rejection=a.get('rejection'),model_probability=d.get('model_probability'),
            started_s=a['started']-start if 'started' in a else None,
            readback_finished_s=a['verified_finished']-start if 'verified_finished' in a else None)
        events.append(e)
        if e['applied']:applied=e
    files=[folder/'samples.jsonl',folder/'decisions.jsonl',folder/'action.jsonl',trial/'sender-samples.jsonl',trial/'sender-native.json']
    return dict(policy=row['policy'],scenario=row['scenario'],seed=row['seed'],folder=row['folder'],trial=row['trial'],
        origin='sender-native.start_monotonic_ns; all axes are seconds relative to this run',
        sender=sender_intervals(read_lines(trial/'sender-samples.jsonl'),native),queues=queues,events=events,
        path_counter_observation=path_observation(queues['s1-eth4'],applied),
        input_sha256={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

def csv_write(path,rows):
    if not rows:return
    with path.open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def build(repo,report,output,plots=False):
    repo=Path(repo).resolve();output=Path(output).resolve()
    if output.is_relative_to(repo):raise ValueError('Trace derivatives must be outside frozen inputs')
    output.mkdir(parents=True,exist_ok=False);sys.path.insert(0,str(repo))
    data=json.loads(Path(report).read_text());runs=[]
    for scenario,seed in CASES:
        for policy in POLICIES:
            row=next(r for r in data['rows'] if (r['scenario'],r['seed'],r['policy'])==(scenario,seed,policy))
            runs.append(extract(repo,row))
    bundle=dict(selection='All four policies for ramp seed 42 and bursty seed 42; all four steady seed 41. Explanatory middle-seed ramp, adverse reactive-burst block and known low-load action; not a representative statistical estimate or performance-selected replacement.',
        time_convention='Source and decisions use guest monotonic time. Counter rates span actual query midpoints, availability is read completion; observation envelopes cover read start/end. No global cross-run wall-clock alignment.',
        packet_activation_measured=False,runs=runs)
    (output/'traces.json').write_text(json.dumps(bundle,indent=2)+'\n',encoding='utf-8')
    for r in runs:
        stem=f"{r['scenario']}-{r['policy']}-seed{r['seed']}"
        csv_write(output/(stem+'-source.csv'),r['sender'])
        csv_write(output/(stem+'-queues.csv'),[x for q in QUEUES for x in r['queues'][q]])
        csv_write(output/(stem+'-events.csv'),r['events'])
    (output/'README.md').write_text('# Time-aligned explanatory traces\n\n'+bundle['selection']+'\n\n'+bundle['time_convention']+'\n\nReadback shading is command/readback duration, not packet activation. Blue/orange counter curves and observed branch fractions include probe/control packets. Failed/invalid counter intervals remain gaps. Primary utilization after rerouting is observed behavior, not counterfactual no-intervention event truth. Red crosses mark denied requests; green lines mark trigger evaluation and purple spans mark command/readback. The first nonzero alternate-counter envelope is an observation interval only. Exact UDP activation remains unmeasured and warrants a small separate packet-observation pilot after the supplemental controls.\n',encoding='utf-8')
    if plots:plot(bundle,output)
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(traces=len(runs),figures=6 if plots else 0,packet_activation_measured=False,output=str(output))))

def plot(bundle,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.size':8,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    names=['Fixed','Reactive','Early warning','Frozen tree']
    for scenario,seed in CASES:
        fig,axes=plt.subplots(5,4,figsize=(17,11),sharex=True,sharey='row',layout='constrained')
        for col,policy in enumerate(POLICIES):
            run=next(r for r in bundle['runs'] if (r['scenario'],r['seed'],r['policy'])==(scenario,seed,policy));q=run['queues']
            axes[0,col].set_title(names[col]);axes[0,col].plot([x['mid_s'] for x in run['sender']],[x['payload_bps']/1e6 for x in run['sender']],color='#555555',label='Actual sender payload')
            for queue,color,label in [('s1-eth3','#0072B2','Primary branch'),('s1-eth4','#D55E00','Alternate branch')]:
                axes[0,col].plot([x['t1_s'] for x in q[queue]],[x['departure_bps']/1e6 if x['departure_bps'] is not None else np.nan for x in q[queue]],color=color,lw=.8,label=label)
            axes[1,col].plot([x['t1_s'] for x in q['s2-eth2']],[100*x['utilization'] if x['utilization'] is not None else np.nan for x in q['s2-eth2']],color='#0072B2')
            axes[1,col].axhline(85,color='#777777',ls='--',lw=.7);axes[1,col].set_ylim(0,120)
            for queue,color,style in [('s2-eth2','#0072B2','-'),('s1-eth4','#D55E00','-'),('s3-eth2','#CC79A7',':')]:
                valid=q[queue];axes[2,col].plot([x['t1_s'] for x in valid],[x['queue_packets'] if x['valid'] else np.nan for x in valid],color=color,ls=style,lw=.8,label=queue)
                drops=[x for x in valid if x['valid'] and x['root_drops_delta']>0]
                axes[3,col].vlines([x['t1_s'] for x in drops],0,[x['root_drops_delta'] for x in drops],color=color,lw=.8)
            primary={x['t1_s']:x for x in q['s1-eth3']}
            pairs=[(x,primary[x['t1_s']]) for x in q['s1-eth4'] if x['t1_s'] in primary and x['valid'] and primary[x['t1_s']]['valid']]
            axes[4,col].plot([x['t1_s'] for x,p in pairs],[x['departure_bps']/(x['departure_bps']+p['departure_bps']) if x['departure_bps']+p['departure_bps'] else np.nan for x,p in pairs],color='#D55E00')
            axes[4,col].set_ylim(-.1,1.1);axes[4,col].set_xlabel('Seconds from this run\'s source start')
            for e in run['events']:
                if e['applied']:
                    for ax in axes[:,col]:
                        ax.axvline(e['decision_s'],color='#009E73',lw=.9,ls='--')
                        ax.axvspan(e['started_s'],e['readback_finished_s'],color='#8D3C91',alpha=.3)
                elif e['rejection']:axes[4,col].scatter(e['decision_s'],.5,marker='x',s=14,color='#C43B3B',zorder=4)
            observation=run['path_counter_observation']
            if observation and 'left_s' in observation:axes[4,col].axvspan(observation['left_s'],observation['right_s'],color='#8D3C91',alpha=.16,hatch='//')
            for ax in axes[:,col]:ax.set_xlim(0,60);ax.grid(alpha=.15);ax.set_axisbelow(True)
        for i,label in enumerate(['Payload / branch rate\n(Mbit/s; different accounting)','Primary utilization (%)','Sampled queue (packets)','Root drops / interval','Observed alternate\nbranch byte fraction']):axes[i,0].set_ylabel(label)
        axes[0,0].set_ylim(0,5 if scenario=='steady' else 17)
        axes[2,0].set_ylim(0,6 if scenario=='steady' else 55)
        handles,labels=axes[0,0].get_legend_handles_labels()
        qh,ql=axes[2,0].get_legend_handles_labels()
        fig.legend(handles+qh,labels+['Queue '+s for s in ql],loc='outside lower center',ncol=6)
        fig.suptitle(f'{scenario.capitalize()} seed {seed}: monotonic-time alignment across four separate runs\nGreen: trigger; purple: command/readback or counter-observation interval; red crosses: admission denial. No exact packet activation.',fontsize=12)
        for ext in ['png','svg']:fig.savefig(output/f'timeline-{scenario}-seed{seed}.{ext}',dpi=190,bbox_inches='tight')
        plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',required=True);p.add_argument('--report',required=True);p.add_argument('--output',required=True);p.add_argument('--plots',action='store_true')
    a=p.parse_args();build(a.repo,a.report,a.output,a.plots)
