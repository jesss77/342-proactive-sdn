"""Standalone scientific figures from independently checked matched trial rows."""
from pathlib import Path
import json,sys,statistics
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
out=args.output.resolve()
if out.is_relative_to(args.report.resolve().parent):
    raise ValueError('Plot output must be outside preserved report inputs')
out.mkdir(parents=True,exist_ok=False)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

data=json.loads(args.report.read_text(encoding='utf-8'));rows=data['rows'];assert len(rows)==36
figures=out/'figures';figures.mkdir(exist_ok=True)
policies=['fixed','reactive','early_warning','ml'];names=['Fixed','Reactive','Early warning','ML']
scenarios=['steady','ramp','bursty'];seeds=[41,42,43]
colors=['#555555','#0072B2','#D55E00','#8D3C91'];markers=['o','s','^']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
    'axes.spines.right':False,'axes.titleweight':'bold','savefig.facecolor':'white',
    'svg.fonttype':'none','axes.labelcolor':'black','text.color':'black'})
outputs=[]
def save(fig,name):
    for ext in ['png','svg']:
        path=figures/(name+'.'+ext);fig.savefig(path,dpi=220,bbox_inches='tight');outputs.append(path.relative_to(out).as_posix())
    plt.close(fig)

def points(ax,scenario,extract,zero=True):
    all_values=[]
    for j,policy in enumerate(policies):
        values=[]
        for k,seed in enumerate(seeds):
            row=next(r for r in rows if (r['scenario'],r['policy'],r['seed'])==(scenario,policy,seed))
            value=extract(row)
            if value is None:continue
            values.append(value);all_values.append(value)
            ax.scatter(j+(k-1)*.12,value,marker=markers[k],s=38,color=colors[j],edgecolor='white',linewidth=.45,zorder=3)
        if values:
            ax.vlines(j,min(values),max(values),color=colors[j],linewidth=1.2,alpha=.75)
            ax.hlines(statistics.mean(values),j-.22,j+.22,color=colors[j],linewidth=2.1,zorder=4)
        else:ax.text(j,.04,'n/a',transform=ax.get_xaxis_transform(),ha='center',fontsize=9,color='#666666')
    ax.set_xticks(range(4),names,rotation=16,ha='right');ax.set_xlim(-.5,3.5)
    ax.grid(axis='y',alpha=.2,zorder=0);ax.set_axisbelow(True)
    if zero:ax.set_ylim(bottom=0,top=max(all_values)*1.16 if all_values and max(all_values)>0 else 1)
    return all_values

legend=[Line2D([],[],color='#444444',marker=m,linestyle='None',label=f'Seed {s}',markersize=5) for s,m in zip(seeds,markers)]
legend.append(Line2D([],[],color='#444444',linewidth=2,label='Mean; vertical line shows observed range'))
caption='Each point is one whole trial. Three seeds per policy/scenario; ranges are descriptive, not confidence intervals.'

specs=[('receiver_mbps','Receiver goodput (Mbit/s)'),('udp_loss_percent','UDP loss (%)'),('traffic_reply_p95_ms','Within-run reply RTT p95 (ms)')]
fig,axes=plt.subplots(3,3,figsize=(12.6,9.2),layout='constrained')
for i,(key,label) in enumerate(specs):
    for j,scenario in enumerate(scenarios):
        points(axes[i,j],scenario,lambda r,k=key:r[k])
        if i==0:axes[i,j].set_title(scenario.capitalize())
        if j==0:axes[i,j].set_ylabel(label)
fig.suptitle('Matched networking outcomes across all 36 trials',fontsize=15)
fig.legend(handles=legend,loc='outside lower center',ncol=4,fontsize=8.5)
save(fig,'01-networking-outcomes')

fig,axes=plt.subplots(2,3,figsize=(12.6,6.6),layout='constrained')
for i,(key,label) in enumerate([('collector_cpu_percent_one_core','Collector CPU (% of one core)'),('policy_cpu_percent_one_core','Policy-thread CPU (% of one core)')]):
    for j,scenario in enumerate(scenarios):
        points(axes[i,j],scenario,lambda r,k=key:r[k])
        if i==0:axes[i,j].set_title(scenario.capitalize())
        if j==0:axes[i,j].set_ylabel(label)
fig.suptitle('Monitoring and policy computation costs',fontsize=15)
fig.legend(handles=legend,loc='outside lower center',ncol=4,fontsize=8.5)
save(fig,'02-computation-costs')

fig,axes=plt.subplots(1,3,figsize=(12.8,4.1),layout='constrained',gridspec_kw={'width_ratios':[1.05,1.3,1]})
matrix=np.array([[sum(r['actions'] for r in rows if r['scenario']==s and r['policy']==p) for p in policies] for s in scenarios])
axes[0].imshow(matrix,cmap='Blues',vmin=0,vmax=3,aspect='auto')
for i in range(3):
    for j in range(4):axes[0].text(j,i,f'{matrix[i,j]}/3',ha='center',va='center',color='white' if matrix[i,j]>=2 else 'black',fontsize=11)
axes[0].set_yticks(range(3),[s.capitalize() for s in scenarios]);axes[0].set_xticks(range(4),names,rotation=25,ha='right');axes[0].set_title('Trials with an applied switch')
for p,policy in enumerate(policies):
    for i,scenario in enumerate(scenarios):
        selected=[r for r in rows if r['scenario']==scenario and r['policy']==policy and r['actions']]
        for row in selected:
            k=seeds.index(row['seed']);x=i+(p-1.5)*.17+(k-1)*.018
            axes[1].scatter(x,row['command_readback_ms'],color=colors[p],marker=markers[k],s=28)
axes[1].set_xticks(range(3),[s.capitalize() for s in scenarios]);axes[1].set_ylabel('Command and readback elapsed (ms)');axes[1].set_title('Applied actions only');axes[1].set_ylim(bottom=0);axes[1].grid(axis='y',alpha=.2)
for i,scenario in enumerate(scenarios):
    for j,seed in enumerate(seeds):
        row=next(r for r in rows if r['scenario']==scenario and r['policy']=='ml' and r['seed']==seed)
        axes[2].scatter(i+(j-1)*.1,row['inference_wall_p95_us'],color=colors[3],marker=markers[j],s=35)
axes[2].set_xticks(range(3),[s.capitalize() for s in scenarios]);axes[2].set_ylabel('Within-run inference wall p95 (µs)');axes[2].set_title('ML until switch or trial end');axes[2].set_ylim(bottom=0);axes[2].grid(axis='y',alpha=.2)
fig.suptitle('Routing behavior and control cost',fontsize=15)
control_legend=[Line2D([],[],color=colors[i],marker='o',linestyle='None',label=names[i],markersize=5) for i in [1,2,3]]
fig.legend(handles=control_legend+legend[:3],loc='outside lower center',ncol=6,fontsize=8.5)
save(fig,'03-routing-and-inference')

fig,axes=plt.subplots(3,3,figsize=(12.6,9.2),layout='constrained')
queue_specs=[(lambda r:r['sampled_queue_max_packets']['s2-eth2'],'Primary bottleneck max queue\n(packets, sampled)'),
    (lambda r:r['queue_drops']['s2-eth2'],'Primary bottleneck drops\n(events)'),
    (lambda r:r['queue_drops']['s1-eth4']+r['queue_drops']['s3-eth2'],'Alternate-path drops\n(events)')]
for i,(extract,label) in enumerate(queue_specs):
    for j,scenario in enumerate(scenarios):
        points(axes[i,j],scenario,extract)
        if i==0:axes[i,j].set_title(scenario.capitalize())
        if j==0:axes[i,j].set_ylabel(label,fontsize=9)
fig.suptitle('Queue occupancy and drop localization',fontsize=15)
fig.legend(handles=legend,loc='outside lower center',ncol=4,fontsize=8.5)
save(fig,'04-queues-and-drops')

receipt=dict(figures=outputs,trials=36,rows_preserved=36,style='individual-seed points, mean and observed range; no confidence intervals',
    matplotlib=matplotlib.__version__,numpy=np.__version__)
(figures/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
