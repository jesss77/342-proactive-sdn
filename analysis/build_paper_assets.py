"""Generate every final-paper table and figure from pinned code and saved measurements.

V1 values are checked against the raw-backed consolidated replay. V2 values are
computed from immutable per-trial summaries; unavailable V2 raw logs are never
claimed to have been verified. No network traffic, fitting or image generation.
"""
from collections import Counter
from pathlib import Path
import argparse,ast,csv,hashlib,json,math,shutil,statistics,zipfile

ROOT=Path(__file__).resolve().parents[1]
POLICIES=['fixed','reactive','early_warning','ml']
SEEDS=[41,42,43]
CAPTURE_BATCH='20261121-012117-648967-packet-activation-pilot'
CAPTURE_POLICY='20261121-014335-222889-policy-ml-ramp-seed1'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,data):Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def normalize(value):
    if isinstance(value,dict):return {k.replace('\\','/'):normalize(v) for k,v in value.items()}
    if isinstance(value,list):return [normalize(v) for v in value]
    return value
def write_csv(path,rows):
    if not rows:raise ValueError('Empty paper data: '+str(path))
    with Path(path).open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def fmt(value,digits=3):return f'{value:.{digits}f}'

def validate_v2(data):
    rows=data['completed'];plan=data['plan']
    identity=lambda r:(r['scenario'],r['bg_bps'],r['seed'],r['policy'])
    expected={(s,b,k,p) for s in ['ramp','bursty'] for b in [0,4_000_000,14_000_000] for k in SEEDS for p in POLICIES}
    if len(rows)!=len(expected) or {identity(r) for r in rows}!=expected:
        raise ValueError('V2 requires exactly one record for each registered cell')
    if [{k:r[k] for k in plan[0]} for r in rows]!=plan:
        raise ValueError('V2 records differ from registered identities/order')
    for r in rows:
        for k in ['sender_mbps','receiver_mbps','udp_loss_percent','rtt_p95_ms']:
            if isinstance(r[k],bool) or not isinstance(r[k],(int,float)) or not math.isfinite(r[k]) or r[k]<0:
                raise ValueError('Invalid reported V2 value: '+k)
        if not 0<=r['udp_loss_percent']<=100:raise ValueError('Invalid V2 loss percentage')
    return rows

def load_v2(repo=ROOT):
    folder=Path(repo)/'data/v2';meta=read(folder/'manifest.json')
    for name,pin in meta['files'].items():
        if Path(name).name!=name or sha(folder/name)!=pin['sha256']:
            raise ValueError('Pinned V2 input differs: '+name)
    data=read(folder/'v2-batch.json');validate_v2(data)
    return meta,data

def topology(source):
    """Read literal link declarations from the frozen Mininet source, without importing Mininet."""
    tree=ast.parse(Path(source).read_text());links=[]
    for loop in [n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.iter,ast.List)]:
        items=ast.literal_eval(loop.iter)
        if items and len(items[0])==3:
            calls=[n for n in ast.walk(loop) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='addLink']
            rate=next(ast.literal_eval(k.value) for k in calls[0].keywords if k.arg=='bw')
            links.extend(dict(a=f'h{h}',b=f's{s}',capacity_mbps=rate,port_a=0,port_b=p) for h,s,p in items)
        elif items and len(items[0])==5:
            links.extend(dict(a=f's{a}',b=f's{b}',capacity_mbps=rate,port_a=pa,port_b=pb) for a,b,pa,pb,rate in items)
    if len(links)!=8:raise ValueError('Unexpected frozen topology link declarations')
    return links

def defaults(source,cls,method):
    tree=ast.parse(Path(source).read_text());c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    f=next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name==method)
    out={}
    for arg,value in zip(f.args.args[-len(f.args.defaults):],f.args.defaults):
        try:out[arg.arg]=ast.literal_eval(value)
        except ValueError:pass
    return out

def comparison_literal(source,return_reason):
    tree=ast.parse(Path(source).read_text())
    for n in ast.walk(tree):
        if isinstance(n,ast.If) and any(isinstance(x,ast.Return) and isinstance(x.value,ast.Constant) and x.value.value==return_reason for x in n.body):
            candidates=[x for x in ast.walk(n.test) if isinstance(x,ast.Compare)]
            return ast.literal_eval(candidates[0].comparators[-1])
    raise ValueError('Frozen comparison not found: '+return_reason)

def trend_floor(source):
    tree=ast.parse(Path(source).read_text())
    return next(ast.literal_eval(n.comparators[0]) for n in ast.walk(tree) if isinstance(n,ast.Compare)
        and isinstance(n.left,ast.Name) and n.left.id=='u' and isinstance(n.ops[0],ast.GtE)
        and isinstance(n.comparators[0],ast.Constant))

def capture_data(lab):
    root=Path(lab)/'results/runs';batch=root/CAPTURE_BATCH;policy=root/CAPTURE_POLICY
    review=read(batch/'capture/review.json');meta=read(policy/'policy.json');trial=root/meta['trial']
    sender=read(trial/'sender-native.json');start=sender['start_monotonic_ns']/1e9
    samples=[json.loads(x) for x in (trial/'sender-samples.jsonl').read_text().splitlines()]
    source=[]
    for a,b in zip(samples,samples[1:]):
        dt=(b['monotonic_ns']-a['monotonic_ns'])/1e9
        if dt<=0:raise ValueError('Non-increasing sender sample timestamps')
        source.append(dict(source_midpoint_s=(a['monotonic_ns']+b['monotonic_ns'])/2e9-start,
            sender_payload_mbps=8*sender['payload_bytes']*(b['sent_packets']-a['sent_packets'])/dt/1e6))
    samples=[json.loads(x) for x in (policy/'samples.jsonl').read_text().splitlines()];queues=[]
    for a,b in zip(samples,samples[1:]):
        row={}
        for dev,label in [('s2-eth2','primary'),('s3-eth2','alternate')]:
            x,y=a['qdiscs'][dev],b['qdiscs'][dev]
            dt=(y['tc_start']+y['tc_end']-x['tc_start']-x['tc_end'])/2
            if dt<=0:raise ValueError('Non-increasing qdisc query midpoints')
            row[label+'_query_midpoint_s']=(y['tc_start']+y['tc_end'])/2-start
            row[label+'_utilization']=8*(y['root_qdisc']['bytes']-x['root_qdisc']['bytes'])/dt/y['capacity_bps']
            row[label+'_queue_packets']=y['root_qdisc']['qlen']
        queues.append(row)
    action=review['actions'][0];timing=review['capture']['timing'];origin=action['decision_at']
    low,high=timing['first_alternate_after_decision_s']
    points=[('Observation available',1000*(action['admission']['observed_at']-origin)),('Decision',0.),
        ('Programming starts',1000*(action['started']-origin)),('First alternate UDP',500*(low+high)),
        ('Final flow readback',1000*(action['verified_finished']-origin))]
    measured_timing=[dict(event=label,milliseconds_after_decision=value,
        low_ms=1000*low if label=='First alternate UDP' else value,
        high_ms=1000*high if label=='First alternate UDP' else value) for label,value in points]
    input_paths=[policy/'policy.json',policy/'samples.jsonl',trial/'sender-native.json',trial/'sender-samples.jsonl',
        batch/'capture/review.json',batch/'capture/clock-map.jsonl',batch/'capture/s1-eth3.pcap',batch/'capture/s1-eth4.pcap']
    inputs={p.relative_to(lab).as_posix():sha(p) for p in input_paths}
    packet=timing['first_alternate_packet']
    events=dict(decision_s=action['decision_at']-start,
        first_alternate_egress_s=(packet['observed_monotonic_low_ns']+packet['observed_monotonic_high_ns'])/2e9-start,
        threshold=read(Path(lab)/'dataset_protocol.json')['label_config']['utilization_threshold'])
    return source,queues,measured_timing,events,inputs

def make_tables(repo,evidence,v2,matched):
    repo=Path(repo);layout=read(repo/'analysis/paper_layout.json');tables=layout['tables'];ledger={}
    def put(key,display,exact,source,calculation,level):
        tables[key]['rows']=display
        ledger[key]=dict(evidence_level=level,source=source,calculation=calculation,
            rows=[dict(row=i,cells=[dict(column=j,display=str(d),exact=v) for j,(d,v) in enumerate(zip(row,raw))])
                  for i,(row,raw) in enumerate(zip(display,exact))])
    protocol=read(repo/'experiment/dataset_protocol.json');bounds=read(repo/'experiment/operating_bounds.json')
    model=read(repo/'experiment/selected_tree.json');profile=protocol['profile'];label=protocol['label_config']
    trigger=defaults(repo/'experiment/routing_policy.py','Trigger','__init__')
    actor=defaults(repo/'experiment/routing_action.py','RoutingAction','__init__')
    floor=trend_floor(repo/'experiment/routing_policy.py');age=comparison_literal(repo/'experiment/routing_action.py','stale_admission')
    future=sum(label[k] for k in ['horizon_s','confirmation_s','future_guard_s'])
    settings=matched['protocol']['settings']
    if protocol['interval_s']!=bounds['collector_interval_s'] or settings['duration_s']!=protocol['duration_s']:
        raise ValueError('Configuration sources disagree')
    pairs=[('Foreground',f"{protocol['payload_bytes']:,}-byte UDP payload; {protocol['duration_s']:g} s; primary initially",dict(payload_bytes=protocol['payload_bytes'],duration_s=protocol['duration_s'])),
        ('Queues / delay',f"Source {profile['source_queue_packets']} packets; switch {profile['bottleneck_queue_packets']} packets; {profile['delay_ms']:g} ms/link",profile),
        ('Sampling / history',f"{1000*protocol['interval_s']:g} ms; at least {label['history_s']:g} s contiguous history",dict(interval_s=protocol['interval_s'],history_s=label['history_s'])),
        ('Event / forecast',f"Utilization >= {label['utilization_threshold']:g} for {label['confirmation_s']:g} s; new onset within {label['horizon_s']:g} s",label),
        ('Label future support',f'{future:g} s (horizon + confirmation + read guard)',future),
        ('Reactive trigger',f"Observed high utilization sustained for {trigger['confirmation_s']:g} s",trigger),
        ('Trend trigger',f"u >= {floor:g}; slope > 0; u + {trigger['horizon_s']:g} slope >= {trigger['threshold']:g}",dict(floor=floor,**trigger)),
        ('Frozen tree',f"Depth {model['parameters']['max_depth']}; minimum leaf {model['parameters']['min_samples_leaf']}; {len(model['nodes'])} nodes; score >= {model['alarm_threshold']:g}",dict(parameters=model['parameters'],nodes=len(model['nodes']),threshold=model['alarm_threshold'])),
        ('Freshness checks',f"Live pre-action {bounds['max_read_age_s']:g} s; actor entry {age:g} s",dict(live_s=bounds['max_read_age_s'],actor_s=age)),
        ('Admission',f"Current demand + alternate load <= {bounds['admission_aggregate_limit_bps']/1e6:g} Mbit/s",bounds['admission_aggregate_limit_bps']),
        ('Action limit','One successful switch; primary restored at cleanup',dict(max_actions=actor['max_actions'],cleanup='experiment/routing_action.py::close'))]
    if actor['max_actions']!=settings['max_successful_actions'] or actor['max_actions']!=1:raise ValueError('Action-limit configuration differs')
    put('parameters',[[a,b] for a,b,c in pairs],[[a,c] for a,b,c in pairs],
        ['experiment/dataset_protocol.json','experiment/operating_bounds.json','experiment/selected_tree.json','experiment/routing_policy.py','experiment/routing_action.py'],
        'Format configuration values and source-code defaults. These are settings, not empirical measurements.','configuration')
    rows=[];exact=[]
    for r in evidence['exclusion_by_split']:
        name={'train':'Train','validation':'Validation','test':'Test'}[r['split']]
        raw=[name]+[r[k] for k in ['independent_runs','rows','eligible','positive','incomplete_past_history','event_already_started','incomplete_or_invalid_future']]
        rows.append(list(map(str,raw)));exact.append(raw)
    put('dataset',rows,exact,'results/tables/paper-evidence.json#/exclusion_by_split','Sum complete raw-backed runs within each whole-run partition.','raw-backed V1 replay')
    rows=[];exact=[]
    for policy,name in zip(POLICIES,['Fixed primary','Reactive','Trend','ML']):
        values=[]
        for scenario in ['ramp','bursty']:
            for metric in ['receiver_mbps','udp_loss_percent','traffic_reply_p95_ms']:
                g=[r for r in matched['rows'] if (r['scenario'],r['policy'])==(scenario,policy)]
                if len(g)!=3:raise ValueError('V1 matched cell incomplete')
                values.append(statistics.mean(r[metric] for r in g))
        rows.append([name]+[fmt(v,1 if i in [2,5] else 3) for i,v in enumerate(values)])
        exact.append([name]+values)
    put('network',rows,exact,'results/matched/matched-report.json#/rows','Arithmetic mean of three distinct matched runs per policy/scenario. RTT is mean of within-run p95, not pooled probes.','raw-backed V1 replay')
    rows=[];exact=[]
    for method in ['ML','trend']:
        for scenario in ['ramp','bursty']:
            r=next(r for r in evidence['prediction_rows'] if (r['method'],r['scenario'])==(method,scenario))
            raw=[method+' / '+scenario,r['n'],r['precision'],r['recall'],r['f1']]
            rows.append([raw[0],str(raw[1])]+[fmt(v) for v in raw[2:]]);exact.append(raw)
    put('prediction',rows,exact,'results/tables/paper-evidence.json#/prediction_rows','Held-out fixed-primary model scoring; round only for display.','raw-backed V1 replay')
    rows=[];exact=[]
    primary=[r for r in matched['rows'] if (r['scenario'],r['policy'])==('steady','fixed')]
    lo,hi=min(r['receiver_mbps'] for r in primary),max(r['receiver_mbps'] for r in primary)
    rows.append(['Primary, 3 Mbit/s',str(len(primary)),f'{lo:.4f}-{hi:.4f}',fmt(max(r['udp_loss_percent'] for r in primary),0)])
    exact.append([rows[-1][0],len(primary),dict(min=lo,max=hi),max(r['udp_loss_percent'] for r in primary)])
    for scenario in ['ramp','bursty']:
        g=[r for r in matched['rows'] if (r['scenario'],r['policy'])==(scenario,'fixed')]
        goodput=statistics.mean(r['receiver_mbps'] for r in g);loss=statistics.mean(r['udp_loss_percent'] for r in g)
        rows.append(['Primary, '+scenario,str(len(g)),fmt(goodput),fmt(loss)]);exact.append([rows[-1][0],len(g),goodput,loss])
    for rate in [12_000_000,16_000_000]:
        g=[r for r in evidence['steady_alternate_calibration'] if r['requested_bps']==rate]
        if len(g)!=3:raise ValueError('Alternate steady controls incomplete')
        lo,hi=min(r['receiver_mbps'] for r in g),max(r['receiver_mbps'] for r in g);loss=max(r['udp_loss_percent'] for r in g)
        rows.append([f'Alternate, {rate/1e6:g} Mbit/s',str(len(g)),f'{lo:.3f}-{hi:.3f}',fmt(loss,0)])
        exact.append([rows[-1][0],len(g),dict(min=lo,max=hi),loss])
    controls=evidence['alternate_controls']
    if len(controls)!=6 or any(r['report']['trial']['sender']['packets']!=r['report']['trial']['receiver']['packets'] or r['report']['trial']['receiver']['lost_packets']!=0 for r in controls):
        raise ValueError('Alternate variable controls do not establish complete delivery')
    rows.append(['Alternate, variable',str(len(controls)),'All sent datagrams delivered','0'])
    exact.append([rows[-1][0],len(controls),dict(sent=sum(r['report']['trial']['sender']['packets'] for r in controls),lost=sum(r['report']['trial']['receiver']['lost_packets'] for r in controls)),0])
    put('validation',rows,exact,['results/matched/matched-report.json#/rows','results/tables/paper-evidence.json#/steady_alternate_calibration','results/tables/paper-evidence.json#/alternate_controls'],
        'Low-load/control goodput ranges; overloaded fixed-primary means; loss maximum for zero-loss controls. Exact packet counts verify the variable-control statement.','raw-backed V1 replay')
    rows=[];exact=[]
    for scenario in ['ramp','bursty']:
        for bg in [0,4_000_000,14_000_000]:
            values=[statistics.mean(r['udp_loss_percent'] for r in v2 if (r['scenario'],r['bg_bps'],r['policy'])==(scenario,bg,p)) for p in POLICIES]
            rows.append([scenario.capitalize(),str(bg//1_000_000)]+[fmt(v) for v in values]);exact.append([scenario.capitalize(),bg/1e6]+values)
    put('v2loss',rows,exact,'data/v2/v2-batch.json#/completed','Arithmetic mean of three reported runs per cell; V2 raw measurements unavailable. No quality exceptions are silently filtered.','reported V2 summary')
    ledger['dataset']['source_runs_by_row']=[[r['run'] for r in evidence['exclusion_by_run'] if r['split']==split] for split in ['train','validation','test']]
    ledger['network']['source_runs_by_row']=[[r['folder'] for r in matched['rows'] if r['scenario'] in ['ramp','bursty'] and r['policy']==policy] for policy in POLICIES]
    ledger['prediction']['source_runs_by_row']=[[r['run'] for r in evidence['exclusion_by_run'] if r['split']=='test' and r['scenario']==scenario] for method in ['ML','trend'] for scenario in ['ramp','bursty']]
    ledger['validation']['source_runs_by_row']=[
        [r['folder'] for r in matched['rows'] if (r['scenario'],r['policy'])==(scenario,'fixed')] for scenario in ['steady','ramp','bursty']]+[
        [r['folder'] for r in evidence['steady_alternate_calibration'] if r['requested_bps']==rate] for rate in [12_000_000,16_000_000]]+[[r['folder'] for r in controls]]
    ledger['v2loss']['source_runs_by_row']=[[r['folder'] for r in v2 if (r['scenario'],r['bg_bps'])==(scenario,bg)] for scenario in ['ramp','bursty'] for bg in [0,4_000_000,14_000_000]]
    return tables,ledger

def compare_tables(actual,expected):
    """Fail on a changed displayed cell, including labels, grouping, or rounding."""
    if set(actual)!=set(expected):raise ValueError('Paper table set differs')
    for key in actual:
        if actual[key]['heads']!=expected[key]['heads'] or actual[key]['rows']!=expected[key]['rows']:
            raise ValueError('Paper table differs from generated measurements: '+key)

def draw_new_figures(links,paired,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    plt.rcParams.update({'font.family':'DejaVu Serif','font.size':8,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    def figure_save(fig,name):
        for ext in ['pdf','png','svg']:
            kwargs=dict(metadata={'CreationDate':None,'ModDate':None}) if ext=='pdf' else {}
            fig.savefig(output/(name+'.'+ext),dpi=250,bbox_inches='tight',pad_inches=.04,**kwargs)
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(3.5,2.25));ax.set(xlim=(-.3,6.3),ylim=(-.35,3.2));ax.axis('off')
    pos={'h1':(.05,2.1),'h3':(.05,.45),'s1':(1.5,1.3),'s2':(3,2.65),'s3':(3,0),'s4':(4.5,1.3),'h2':(5.95,2.1),'h4':(5.95,.45)}
    for link in links:
        a,b=link['a'],link['b'];x,y=pos[a];u,v=pos[b]
        color='#555' if a.startswith('h') or b.startswith('h') else ('#0072B2' if 's2' in [a,b] else '#A34D00')
        ax.plot([x,u],[y,v],color=color,lw=1.4,zorder=1)
        if a.startswith('s') and b.startswith('s'):
            ax.text((x+u)/2,2.25 if 's2' in [a,b] else .22,str(link['capacity_mbps']),fontsize=7,color=color,ha='center')
    for name,(x,y) in pos.items():
        ax.add_patch(FancyBboxPatch((x-.23,y-.16),.46,.32,boxstyle='round,pad=.035',fc='white',ec='#222',lw=.8,zorder=3));ax.text(x,y,name,ha='center',va='center',zorder=4)
    access={r['capacity_mbps'] for r in links if r['a'].startswith('h')}
    if len(access)!=1:raise ValueError('Unequal access rates require new schematic labels')
    ax.text(3,3.03,'Primary',ha='center',fontsize=7,color='#0072B2');ax.text(3,-.32,'Alternate',ha='center',fontsize=7,color='#A34D00')
    ax.text(3,1.35,f'Rates: Mbit/s\nAccess: {next(iter(access))} Mbit/s',ha='center',va='center',fontsize=6.8)
    figure_save(fig,'01-topology')
    fig,axes=plt.subplots(1,2,figsize=(7.2,2.25),layout='constrained')
    for ax,cohort,title in zip(axes,['V1','V2'],['V1: idle alternate','V2: 4 Mbit/s background']):
        group=[r for r in paired if r['cohort']==cohort];x=[r['seed'] for r in group];y=[r['delta_loss_pp'] for r in group]
        ax.axhline(0,color='#555',lw=.7);ax.plot(x,y,color='#703B84',lw=.9,marker='o',ms=4)
        for xx,yy in zip(x,y):ax.annotate(f'{yy:+.3f}',(xx,yy),xytext=(0,8 if yy>=0 else -13),textcoords='offset points',ha='center',fontsize=7)
        ax.set_xticks(x);ax.set_xlabel('Matched seed');ax.set_ylabel('ML − trend loss (percentage points)',fontsize=7.5);ax.set_title(title,fontsize=8)
        ax.grid(axis='y',alpha=.2);ax.margins(x=.18,y=.3)
    figure_save(fig,'02-paired-differences')

def build(repo,lab,evidence_path,output,figures=False,v1_figures=None,check_tables=None):
    repo=Path(repo).resolve();lab=Path(lab).resolve();out=Path(output).resolve()
    if out.is_relative_to(lab):raise ValueError('Paper derivatives must be outside raw lab inputs')
    evidence=read(evidence_path);reference=read(repo/'results/tables/paper-evidence.json')
    if normalize(evidence)!=normalize(reference):raise ValueError('Replayed V1 evidence differs from saved reference')
    manifest=read(repo/'data/manifest.json')
    if sha(repo/'data/inputs.zip')!=manifest['archive_sha256']:raise ValueError('V1 raw archive differs')
    for name,digest in manifest['frozen_source_files'].items():
        if sha(repo/'experiment'/name)!=digest or sha(lab/name)!=digest:raise ValueError('Frozen source differs: '+name)
    v2meta,v2data=load_v2(repo);v2=validate_v2(v2data);matched=read(repo/'results/matched/matched-report.json')
    tables,ledger=make_tables(repo,evidence,v2,matched)
    if check_tables is not None:compare_tables(tables,read(check_tables))
    out.mkdir(parents=True,exist_ok=False);(out/'tables').mkdir();(out/'figures').mkdir();(out/'plot-data').mkdir()
    save(out/'table-data.json',tables);save(out/'table-provenance.json',ledger)
    md=['# Generated paper tables','Values are rounded only for display. Exact cells and source selectors are in table-provenance.json.']
    for i,key in enumerate(['parameters','dataset','validation','network','prediction','v2loss'],1):
        t=tables[key];write_csv(out/'tables'/(key+'.csv'),[dict(zip(t['heads'],r)) for r in t['rows']])
        md.extend([f'## Table {i}: '+t['caption'],'| '+' | '.join(h.replace('\n',' ') for h in t['heads'])+' |','| '+' | '.join(['---']*len(t['heads']))+' |'])
        md.extend('| '+' | '.join(str(v) for v in row)+' |' for row in t['rows'])
        if t['note']:md.append(t['note'])
    (out/'tables.md').write_text('\n\n'.join(md)+'\n',encoding='utf-8')
    links=topology(repo/'experiment/topology.py');write_csv(out/'plot-data/topology.csv',links)
    paired=[]
    for cohort in ['V1','V2']:
        for seed in SEEDS:
            if cohort=='V1':
                a,b=[next(r for r in matched['rows'] if (r['scenario'],r['seed'],r['policy'])==('bursty',seed,p)) for p in ['ml','early_warning']]
                rate=0;rt='traffic_reply_p95_ms'
            else:
                a,b=[next(r for r in v2 if (r['scenario'],r['bg_bps'],r['seed'],r['policy'])==('bursty',4_000_000,seed,p)) for p in ['ml','early_warning']]
                rate=4_000_000;rt='rtt_p95_ms'
            paired.append(dict(cohort=cohort,scenario='bursty',background_bps=rate,seed=seed,ml_run=a.get('folder'),trend_run=b.get('folder'),
                delta_loss_pp=a['udp_loss_percent']-b['udp_loss_percent'],delta_goodput_mbps=a['receiver_mbps']-b['receiver_mbps'],delta_rtt_p95_ms=a[rt]-b[rt]))
    write_csv(out/'plot-data/paired-differences.csv',paired)
    source,queues,timing,events,capture_inputs=capture_data(lab)
    # Bind any extracted measurement used here to the archive's original byte
    # index. Full scientific inspector replay happens before this stage in reproduce.py.
    raw_inputs=dict(capture_inputs)
    for r in matched['rows']:
        paths=[f"results/runs/{r['folder']}/{name}" for name in ['policy.json','samples.jsonl','decisions.jsonl','ping-loaded.txt']]
        paths+=[f"results/runs/{r['trial']}/{name}" for name in ['sender-native.json','receiver-native.json']]
        for rel in paths:raw_inputs[rel]=sha(lab/rel)
    with zipfile.ZipFile(repo/'data/inputs.zip') as archive:
        index=json.loads(archive.read('index.json'))['files']
    for rel,digest in raw_inputs.items():
        if index.get('lab/'+rel)!=digest:raise ValueError('Extracted measurement differs from raw archive: '+rel)
    write_csv(out/'plot-data/captured-source.csv',source);write_csv(out/'plot-data/captured-queues.csv',queues)
    write_csv(out/'plot-data/forwarding-timing.csv',timing);save(out/'plot-data/capture-events.json',events)
    groups=[]
    for scenario in ['ramp','bursty']:
        for bg in [0,4_000_000,14_000_000]:
            for policy in POLICIES:
                group=[r for r in v2 if (r['scenario'],r['bg_bps'],r['policy'])==(scenario,bg,policy)]
                row=dict(scenario=scenario,background_bps=bg,policy=policy,n=len(group))
                for k in ['sender_mbps','receiver_mbps','udp_loss_percent','rtt_p95_ms']:
                    values=[r[k] for r in group];row.update({k+'_mean':statistics.mean(values),k+'_sd':statistics.stdev(values),k+'_min':min(values),k+'_max':max(values)})
                row.update(actions=sum(r['actions'] for r in group),denials=sum(r['denials'] for r in group),quality_exceptions=sum(bool(r['screen_failures']) for r in group));groups.append(row)
    write_csv(out/'v2-aggregates.csv',groups);write_csv(out/'v2-trials.csv',v2);write_csv(out/'v2-failed-attempts.csv',v2data['failed'])
    steady=read(repo/'data/v2/v2-steady-control.json')['completed']
    fixed=read(repo/'data/v2/fixed_alternate_control.json')
    if len(steady)!=12 or {(r['policy'],r['seed']) for r in steady}!={(p,s) for p in POLICIES for s in SEEDS}:
        raise ValueError('V2 steady controls incomplete or duplicated')
    if len(fixed)!=2 or {r['scenario'] for r in fixed}!={'ramp','bursty'}:
        raise ValueError('V2 forced-alternate controls incomplete')
    control_rows=[dict(control='steady',policy=r['policy'],scenario=r['scenario'],seed=r['seed'],background_bps=r['bg_bps'],
        foreground_goodput_mbps=r['receiver_mbps'],foreground_loss_percent=r['udp_loss_percent'],background_loss_percent=r['bg_loss_percent'],
        screen_failures=json.dumps(r['screen_failures']),folder=r['folder']) for r in steady]
    control_rows += [dict(control='fixed_alternate',policy=r['policy'],scenario=r['scenario'],seed=r['seed'],background_bps=r['bg_bps'],
        foreground_goodput_mbps=r['h1_receiver_mbps'],foreground_loss_percent=r['h1_loss_percent'],background_loss_percent=r['bg_loss_percent'],
        screen_failures=json.dumps(r['screen_failures']),folder=r['folder']) for r in fixed]
    write_csv(out/'v2-controls.csv',control_rows)
    figure_catalog={
        '01-topology':dict(kind='configuration schematic; not an observed trace',generator='analysis/build_paper_assets.py::draw_new_figures',inputs=['experiment/topology.py'],data='plot-data/topology.csv'),
        '02-paired-differences':dict(kind='empirical V1 pairs plus reported V2 pairs',generator='analysis/build_paper_assets.py::draw_new_figures',inputs=['results/matched/matched-report.json','data/v2/v2-batch.json'],data='plot-data/paired-differences.csv'),
        '03-aligned-captured-trace':dict(kind='raw-backed V1 empirical trace',generator='analysis/plot_paper_evidence.py::run',inputs=capture_inputs,data=['plot-data/captured-source.csv','plot-data/captured-queues.csv','plot-data/capture-events.json']),
        '04-forwarding-timing':dict(kind='raw-backed V1 timestamps; software egress is not atomic installation',generator='analysis/plot_paper_evidence.py::run',inputs=capture_inputs,data='plot-data/forwarding-timing.csv')}
    if figures:
        if v1_figures is None:raise ValueError('--figures requires --v1-figures from the validated V1 plotting stage')
        draw_new_figures(links,paired,out/'figures')
        for name in ['03-aligned-captured-trace','04-forwarding-timing']:
            for ext in ['pdf','png','svg']:shutil.copy2(Path(v1_figures)/(name+'.'+ext),out/'figures'/(name+'.'+ext))
    sources={}
    for rel in ['analysis/build_paper_assets.py','analysis/plot_paper_evidence.py','analysis/paper_layout.json',
                'data/manifest.json','data/v2/manifest.json','results/tables/paper-evidence.json','results/matched/matched-report.json',
                'experiment/topology.py','experiment/dataset_protocol.json','experiment/operating_bounds.json','experiment/selected_tree.json','experiment/routing_policy.py','experiment/routing_action.py']:
        sources[rel]=sha(repo/rel)
    sources.update({'data/v2/'+name:pin['sha256'] for name,pin in v2meta['files'].items()})
    provenance=dict(format='paper-assets-provenance-v1',figure_catalog=figure_catalog,table_order=['parameters','dataset','validation','network','prediction','v2loss'],
        table_cell_provenance='table-provenance.json',inputs_sha256=sources,v1_archive_sha256=manifest['archive_sha256'],capture_inputs_sha256=capture_inputs,
        v1_measurement_files_verified_against_archive_index=raw_inputs,
        v2_origin=v2meta,v2_retained_trials=len(v2),v2_logged_failures=len(v2data['failed']),v2_quality_exceptions=sum(bool(r['screen_failures']) for r in v2),
        v2_control_summaries=len(control_rows),
        figures_generated=figures,v1_generated_evidence_matches_reference=True,raw_v2_verification=False,
        rounding='Only displayed cells/annotations are rounded. CSV plot data and provenance retain full numeric precision.',
        independence='Three whole runs per cell. V1 and V2 are separate platforms/cohorts; they are never pooled.',
        image_generation_used=False)
    save(out/'provenance.json',provenance)
    files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out/'SHA256SUMS.json',files)
    print(json.dumps(dict(tables=len(tables),figures=4 if figures else 0,v2_records=len(v2),output=str(out))))
    return tables,provenance

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=ROOT);p.add_argument('--lab',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--figures',action='store_true');p.add_argument('--v1-figures',type=Path);p.add_argument('--check-tables',type=Path)
    a=p.parse_args();build(a.repo,a.lab,a.evidence,a.output,a.figures,a.v1_figures,a.check_tables)
