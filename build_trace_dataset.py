"""Offline pilot labels and causal features. Never mutates source evidence.

Truth is an operational sustained high-utilization event, not proof of loss.
Only primary, fixed-route, schema-5 continuous traces are currently supported.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

CONFIG = dict(version='primary-highutil85-duration1-horizon2-v1-pilot',
              utilization_threshold=.85, confirmation_s=1., horizon_s=2.,
              history_s=2., ewma_tau_s=1., future_guard_s=.75, route='primary',
              scope='pilot only; not final held-out evaluation')
FEATURES = ['utilization', 'util_mean_1s', 'util_mean_2s', 'util_ewma_1s',
            'util_slope_2s', 'upstream_bps', 'upstream_mean_1s_bps',
            'queue_packets', 'backlog_bytes', 'drops_per_s', 'query_duration_s']
EPS = 1e-7


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def finite_number(x):
    return isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)


def intervals(rows, start, finish):
    """Rates use query midpoints; decisions wait until both reads have ended."""
    result, previous = [], None
    for row in rows:
        qs = row.get('qdiscs', {})
        pair = [qs.get(k, {}) for k in ['s1-eth3', 's2-eth2']]
        good = (row.get('schema_version') in [5, 6] and row.get('route') == 'primary'
                and row.get('requested_interval') == .25)
        for q in pair:
            root = q.get('root_qdisc', {})
            good = good and q.get('tc_exit') == 0 and not q.get('tc_error')
            good = good and root.get('root') is True
            good = good and all(finite_number(q.get(k)) for k in ['tc_start', 'tc_end'])
            good = good and all(finite_number(root.get(k)) and root[k] >= 0
                                for k in ['bytes', 'drops', 'backlog', 'qlen'])
            good = good and q.get('capacity_bps', 0) > 0
            if good:
                good = q['tc_end'] >= q['tc_start']
        if not good:
            previous = None
            continue
        if previous is not None:
            prev_row, prev_pair = previous
            mids = [(q['tc_start'] + q['tc_end'])/2 for q in pair]
            old_mids = [(q['tc_start'] + q['tc_end'])/2 for q in prev_pair]
            dts = [b-a for a, b in zip(old_mids, mids)]
            valid = not row.get('skipped_before_sample', 0)
            valid = valid and all(0 < dt <= 2*row['requested_interval'] for dt in dts)
            valid = valid and all(q['tc_end']-q['tc_start'] <= row['requested_interval']
                                  for q in pair + prev_pair)
            deltas = [{k:q['root_qdisc'][k]-old['root_qdisc'][k]
                       for k in ['bytes', 'drops']} for q, old in zip(pair, prev_pair)]
            valid = valid and all(min(d.values()) >= 0 for d in deltas)
            t0, t1 = old_mids[1], mids[1]
            available = max(q['tc_end'] for q in pair)
            if t0 >= start and t1 <= finish:
                result.append(dict(t0=t0, t1=t1, available=available, valid=bool(valid),
                    utilization=8*deltas[1]['bytes']/dts[1]/pair[1]['capacity_bps']
                        if valid else None,
                    upstream_bps=8*deltas[0]['bytes']/dts[0] if valid else None,
                    queue_packets=pair[1]['root_qdisc']['qlen'],
                    backlog_bytes=pair[1]['root_qdisc']['backlog'],
                    drops_delta=deltas[1]['drops'],
                    drops_per_s=deltas[1]['drops']/dts[1] if valid else None,
                    query_duration_s=max(q['tc_end']-q['tc_start'] for q in pair)))
        previous = row, pair
    return result


def covers(rows, left, right):
    """Every instant in the requested interval needs valid counter support."""
    cursor = left
    for r in rows:
        if r['t1'] <= cursor + EPS:
            continue
        if r['t0'] > cursor + EPS or not r['valid']:
            return False
        cursor = max(cursor, r['t1'])
        if cursor >= right-EPS:
            return True
    return False


def detect_events(rows, threshold=.85, confirmation=1.):
    events, block = [], []
    known_low = False
    block_observed = False

    def close():
        if block and block[-1]['t1']-block[0]['t0'] >= confirmation-EPS:
            confirmed = next(r['available'] for r in block
                             if r['t1']-block[0]['t0'] >= confirmation-EPS)
            events.append(dict(onset=block[0]['t0'], end=block[-1]['t1'],
                confirmed_available=confirmed, onset_observed=block_observed,
                duration_s=block[-1]['t1']-block[0]['t0'],
                root_drops=sum(r['drops_delta'] for r in block),
                peak_queue_packets=max(r['queue_packets'] for r in block)))

    previous_end = None
    for r in rows:
        if previous_end is not None and r['t0'] > previous_end+EPS:
            close(); block = []; known_low = False
        previous_end = r['t1']
        if not r['valid']:
            close(); block = []; known_low = False
        elif r['utilization'] >= threshold:
            if not block:
                block_observed = known_low
            block.append(r)
        else:
            close(); block = []; known_low = True
    close()
    return events


def weighted_mean(rows, key, left, right):
    total = weight = 0.
    for r in rows:
        dt = max(0., min(r['t1'], right)-max(r['t0'], left))
        if dt:
            if not r['valid']:
                raise ValueError('Invalid history')
            total += dt*r[key]; weight += dt
    if abs(weight-(right-left)) > 1e-5:
        raise ValueError('Incomplete history')
    return total/weight


def features_at(history, config=CONFIG):
    """No future row, schedule, seed, scenario, epoch time or run ID input."""
    r = history[-1]
    end = r['t1']; left = end-config['history_s']
    if not covers(history, left, end):
        return None
    # Restart EWMA after invalid/discontinuous observations.
    ewma, last = None, None
    for p in history:
        if not p['valid'] or (last is not None and p['t0'] > last+EPS):
            ewma = None
        if p['valid']:
            alpha = 1-math.exp(-(p['t1']-p['t0'])/config['ewma_tau_s'])
            ewma = p['utilization'] if ewma is None else ewma+alpha*(p['utilization']-ewma)
        last = p['t1']
    pieces = [(max(p['t0'], left), min(p['t1'], end), p['utilization'])
              for p in history if p['valid'] and p['t1'] > left and p['t0'] < end]
    weights = [b-a for a,b,_ in pieces]
    xs = [(a+b)/2-end for a,b,_ in pieces]
    ys = [v for _,_,v in pieces]
    sw = sum(weights); mx = sum(w*x for w,x in zip(weights,xs))/sw
    my = sum(w*y for w,y in zip(weights,ys))/sw
    denom = sum(w*(x-mx)**2 for w,x in zip(weights,xs))
    slope = sum(w*(x-mx)*(y-my) for w,x,y in zip(weights,xs,ys))/denom if denom else 0.
    return dict(utilization=r['utilization'], util_mean_1s=weighted_mean(history,'utilization',end-1,end),
        util_mean_2s=weighted_mean(history,'utilization',left,end), util_ewma_1s=ewma,
        util_slope_2s=slope, upstream_bps=r['upstream_bps'],
        upstream_mean_1s_bps=weighted_mean(history,'upstream_bps',end-1,end),
        **{k:r[k] for k in ['queue_packets','backlog_bytes','drops_per_s','query_duration_s']})


def label_rows(rows, config=CONFIG):
    events = detect_events(rows, config['utilization_threshold'], config['confirmation_s'])
    result = []
    for i, r in enumerate(rows):
        features = features_at(rows[:i+1], config) if r['valid'] else None
        t = r['available']
        reason, label, lead = None, None, None
        if not r['valid']:
            reason = 'invalid_sample'
        elif features is None:
            reason = 'incomplete_past_history'
        elif any(e['onset'] <= t < e['end'] for e in events):
            reason = 'event_already_started'
        # A sustained run can be confirmed only at the next observation. The
        # .75 s guard covers the accepted .5 s interval and .25 s query bounds.
        elif not covers(rows, t, t+config['horizon_s']+config['confirmation_s']
                        +config['future_guard_s']):
            reason = 'incomplete_or_invalid_future'
        else:
            upcoming = [e['onset']-t for e in events if e['onset_observed'] and
                        t < e['onset'] <= t+config['horizon_s']]
            label = int(bool(upcoming))
            lead = min(upcoming) if upcoming else None
        result.append(dict(t0=r['t0'], t1=r['t1'], available=t, features=features,
                           label=label, excluded_reason=reason, lead_to_onset_s=lead))
    return result, events


def source_window_audit(trial):
    native = load_json(trial/'sender-native.json')
    rows = [json.loads(s) for s in (trial/'sender-samples.jsonl').read_text().splitlines()]
    previous_t = native['start_monotonic_ns']/1e9
    previous_packets = 0; gaps = []; count = 0
    for r in rows:
        t = r['monotonic_ns']/1e9; delta = r['sent_packets']-previous_packets
        if t <= previous_t or delta < 0 or r['discarded_budget_bits'] != 0:
            raise ValueError('Source-window audit failed')
        gaps.append(t-previous_t); previous_t=t; previous_packets=r['sent_packets']; count+=1
    if previous_packets > native['sent_packets']:
        raise ValueError('Source count exceeds native total')
    return dict(samples=count, max_sample_gap_s=max(gaps,default=None),
                unlogged_tail_packets=native['sent_packets']-previous_packets,
                note='Source logging is independent; these observations are audit-only, not features.')


def build(repo, selection, output):
    repo=Path(repo).resolve(); output=Path(output).resolve()
    if output.is_relative_to((repo/'results/runs').resolve()):
        raise ValueError('Derivatives must be outside raw runs')
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(repo))
    from inspect_experiment import inspect_experiment
    plan=load_json(selection); all_rows=[]; summaries=[]; hashes={}
    identities=set()
    for selected in plan['runs']:
        name=selected['experiment']
        if Path(name).name != name or selected['split'] not in ['train','validation','test']:
            raise ValueError('Invalid explicit run/split')
        f=repo/'results/runs'/name; meta=load_json(f/'experiment.json')
        if (meta['route']!='primary' or meta['policy']!='fixed' or meta['interventions']
                or meta['interval_s'] != .25):
            raise ValueError('Only untouched fixed primary traces supported')
        if meta['profile']['id'] != 'forward-cburst16k-source250-v1':
            raise ValueError('Unexpected calibration profile')
        for phase in ['forwarding_before','forwarding_after']:
            if any(meta[phase][switch]['output_port'] != 3 for switch in ['s1','s4']):
                raise ValueError('Primary route proof differs')
        identity=(meta['scenario'],meta['seed'])
        if identity in identities: raise ValueError('Duplicate scenario/seed in pilot split')
        identities.add(identity)
        if meta['traffic_engine']!='continuous' or len(meta['trials'])!=1:
            raise ValueError('Expected one continuous flow')
        for src, digest in meta['source_sha256'].items():
            if sha(f/src)!=digest: raise ValueError('Run source hash mismatch: '+src)
        if sha(repo/'inspect_experiment.py') != meta['source_sha256']['inspect_experiment.py']:
            raise ValueError('Inspector differs from recorded acquisition version')
        report=inspect_experiment(f)
        qs=report['collector']['qdiscs']
        if (report['outcome']!='completed' or report['restoration']['failures']
            or any(t['screen_failures'] for t in report['trials'])
            or any(q['failed_queries'] or q['invalid_intervals'] for q in qs.values())):
            raise ValueError('Rejected acquisition trace: '+name)
        trial=repo/'results/runs'/meta['trials'][0]['run']
        native=load_json(trial/'sender-native.json')
        start=native['start_monotonic_ns']/1e9; finish=native['end_monotonic_ns']/1e9
        raw=[json.loads(s) for s in (f/'samples.jsonl').read_text().splitlines()]
        records=intervals(raw,start,finish)
        if not records or any(not r['valid'] for r in records):
            raise ValueError('Invalid paired interval stream')
        labeled, events=label_rows(records)
        for r in labeled:
            all_rows.append(dict(run=name, scenario=meta['scenario'], seed=meta['seed'],
                                 split=selected['split'], **r))
        ping=(f/'ping-loaded.txt').read_text()
        match=re.search(r'(\d+) packets transmitted, (\d+) received',ping)
        missing=report['trials'][0]['sender_based_missing_datagrams']
        drops=report['trials'][0]['queue_drop_deltas']['s2-eth2']
        observed_ping_loss=int(match[1])-int(match[2]) if match else None
        summary=dict(run=name,scenario=meta['scenario'],seed=meta['seed'],split=selected['split'],
            rows=len(labeled),eligible=sum(r['label'] is not None for r in labeled),
            positive=sum(r['label']==1 for r in labeled),
            negative=sum(r['label']==0 for r in labeled),
            exclusions={reason:sum(r['excluded_reason']==reason for r in labeled)
                        for reason in sorted({r['excluded_reason'] for r in labeled if r['excluded_reason']})},
            events=[dict(e,onset_since_source_s=e['onset']-start,
                         confirmation_delay_s=e['confirmed_available']-e['onset']) for e in events],
            source_audit=source_window_audit(trial),
            root_drops=drops,udp_missing=missing,ping_missing=observed_ping_loss,
            packet_accounting_exact=(observed_ping_loss is not None and drops==missing+observed_ping_loss))
        summaries.append(summary)
        for p in [f/'experiment.json',f/'samples.jsonl',f/'ping-loaded.txt',
                  trial/'metadata.json',trial/'sender-native.json',trial/'receiver-native.json',
                  trial/'sender-samples.jsonl']:
            hashes[str(p.relative_to(repo))]=sha(p)
        (output/(name+'.inspection.json')).write_text(json.dumps(report,indent=2)+'\n')
    with (output/'rows.jsonl').open('w') as f:
        for r in all_rows: f.write(json.dumps(r)+'\n')
    with (output/'dataset.csv').open('w',newline='') as f:
        columns=['run','scenario','seed','split','available','label','excluded_reason','lead_to_onset_s']+FEATURES
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for r in all_rows:
            writer.writerow({**{k:r[k] for k in columns if k in r},**(r['features'] or {})})
    summary=dict(config=CONFIG,feature_allowlist=FEATURES,runs=summaries,
                 total_eligible=sum(s['eligible'] for s in summaries),
                 total_positive=sum(s['positive'] for s in summaries),
                 total_observed_events=sum(sum(e['onset_observed'] for e in s['events']) for s in summaries),
                 split_note='Explicit whole-run pilot split. Six traces are insufficient for a final generalization claim.',
                 measurement_note='Counter sampling at 250 ms bounds observed onset resolution; kernel counter freshness is not independently established by timely queries.',
                 source_hashes=hashes,builder_sha256=sha(__file__))
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (output/'selection.json').write_text(json.dumps(plan,indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True);parser.add_argument('--selection',required=True)
    parser.add_argument('--output',required=True)
    a=parser.parse_args()
    report=build(a.repo,a.selection,a.output)
    print(json.dumps({k:report[k] for k in ['total_eligible','total_positive','total_observed_events']},indent=2))
    for r in report['runs']:
        print(r['scenario'],r['seed'],r['split'],'events',len(r['events']),
              'positive',r['positive'],'negative',r['negative'],'accounted',r['packet_accounting_exact'])
