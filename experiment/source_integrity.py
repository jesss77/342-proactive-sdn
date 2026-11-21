"""Measured-source audit, with the existing acquisition budget bound disclosed.

Nonzero pacing discard is recorded, not treated as corrupted counter history.
The original zero-discard pilot auditor and all raw files remain unchanged.
"""
import json
import math
from pathlib import Path

AUDIT_POLICY=dict(id='measured-fixed-source-integrity-v1',
    source_protocol='dual-fixed-highutil-v1',max_discard_fraction=.05,
    threshold_origin='Existing inspect_trial acquisition limit, unchanged; not fitted to this dataset',
    scope='Fixed-primary observed-counter prediction data. Not a perfect-source schedule certificate.',
    amendment='Replace blanket zero-discard rejection with integrity checks, inherited acquisition limit and explicit pacing diagnostics, before model fitting or fresh test use.')


def finite(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def integer(x): return isinstance(x,int) and not isinstance(x,bool) and x>=0


def source_integrity_audit(trial):
    trial=Path(trial)
    native=json.loads((trial/'sender-native.json').read_text())
    rows=[json.loads(s) for s in (trial/'sender-samples.jsonl').read_text().splitlines()]
    def fail(reason): raise ValueError(f'Source integrity failed for {trial.name}: {reason}')
    if not rows: fail('missing source samples')
    start=native.get('start_monotonic_ns');end=native.get('end_monotonic_ns')
    sent=native.get('sent_packets');payload=native.get('payload_bytes')
    planned=native.get('planned_bits');discard=native.get('discarded_budget_bits')
    if not all(integer(v) for v in [start,end,sent,payload]) or end<=start or payload==0:
        fail('invalid native timing/counts')
    if native.get('error') or native.get('stopped_by_signal') or native.get('send_errors'):
        fail('incomplete sender or send errors')
    if not finite(planned) or planned<=0 or not finite(discard) or discard<0:
        fail('invalid pacing budget')
    fraction=discard/planned
    if fraction>AUDIT_POLICY['max_discard_fraction']: fail('discard exceeds existing 5% acquisition limit')
    previous_t=start;previous_packets=0;previous_discard=0.;previous_elapsed=-1.
    gaps=[];changes=[];nonzero=0;delta_packets=[]
    for index,r in enumerate(rows):
        t=r.get('monotonic_ns');count=r.get('sent_packets');budget=r.get('discarded_budget_bits')
        elapsed=r.get('elapsed_s')
        if not integer(t) or not start<t<=end or t<=previous_t: fail(f'invalid sample time at row {index}')
        if not integer(count) or not previous_packets<=count<=sent: fail(f'packet count regression/overflow at row {index}')
        if not finite(elapsed) or elapsed<0 or elapsed<=previous_elapsed: fail(f'invalid elapsed time at row {index}')
        if not finite(budget) or not previous_discard<=budget<=discard: fail(f'discard counter regression/overflow at row {index}')
        delta=count-previous_packets
        if 'sent_packets_delta' in r and r['sent_packets_delta']!=delta: fail(f'packet delta mismatch at row {index}')
        if budget>previous_discard:
            changes.append(dict(sample=index,elapsed_s=elapsed,discard_delta_bits=budget-previous_discard))
        gaps.append((t-previous_t)/1e9);delta_packets.append(delta);nonzero+=int(budget!=0)
        previous_t=t;previous_packets=count;previous_discard=budget;previous_elapsed=elapsed
    max_gap=native.get('max_pacer_gap_s')
    if not finite(max_gap) or max_gap<0: fail('invalid native pacer gap')
    return dict(policy=AUDIT_POLICY,samples=len(rows),max_sample_gap_s=max(gaps),
        tail_sample_gap_s=(end-previous_t)/1e9,unlogged_tail_packets=sent-previous_packets,
        native_discarded_budget_bits=discard,discard_fraction=fraction,discard_percent=100*fraction,
        discarded_payload_datagram_equivalents=discard/(payload*8),
        sampled_discard_increments=changes,unlogged_tail_discard_bits=discard-previous_discard,
        max_pacer_gap_s=max_gap,legacy_zero_discard_passed=(discard==0 and nonzero==0),
        note='Pacing metrics and planned rates are audit-only, not model inputs. Labels/features come from measured counters. Nonzero discard is a retained source limitation, not network packet loss.')
