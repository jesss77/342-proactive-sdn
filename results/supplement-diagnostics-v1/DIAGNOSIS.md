# Stopped supplemental batch: independent diagnostic audit

All 828 exported file hashes and 68 frozen source hashes match. All seven
accepted records reproduce exactly; the eighth attempt reproduces its
`collector_quality` failure. The six fixed-alternate controls are independently
accepted. The extra bursty comparison has no complete four-policy block.

The exact raw archive is in `evidence/raw/342-sdn-supplement-diagnostics-20261120-184224-133635.tar.gz`.
SHA-256: `fb5d184b1888add78828938b72bf37bda99233996ea3b4c25b5def46d28ba07c`.
No model, source, raw metadata or quality threshold was changed by this audit.

## What failed

Early-warning bursty seed 44 had one skipped shared polling deadline. Each of
the four queues therefore has one invalid interval, not four independent
collector failures. Query exit statuses were successful and counters did not
reset. At sample 134, the complete collection cycle was 251.076 ms, including
a 241.539 ms query. With start lateness, completion was 3.198 ms beyond the
next 250 ms deadline. Sample 135 records one skipped deadline; the actual
query-midpoint interval was 372.126 ms. The inspector correctly rejected the
run under the frozen zero-invalid-interval rule.

This happened at source seconds 30.74–31.11. Route programming/readback ended
at 11.402 s, so the missed deadline was later than the action. The data do not
identify the precise host/kernel scheduling cause. One-second resource logs
show no swap activity and substantial idle CPU near that point; these averages
do not resolve a short scheduling delay. Guest `tsc` remained unchanged, as in
the original 36 runs. Restoration passed. The failure is retained even though
it occurred after switching; no post-switch quality exception is introduced.

## Fixed-alternate controls

Every transmitted datagram arrived in all six variable controls; no queue drops,
UDP errors, invalid collector intervals or restoration failures were observed.
Both alternate egress counters carried the data and primary counters remained
zero. Source pacing shortfall is separate from network loss and reached 0.638%
of planned budget. Report achieved source rates rather than treating the
11.5M schedule scale as a constant sending rate.

| Scenario | Seed | Sender Mbit/s | Receiver Mbit/s | UDP loss % | Source discard % |
| --- | --- | --- | --- | --- | --- |
| ramp | 41 | 8.246508 | 8.246146 | 0.000 | 0.000 |
| bursty | 41 | 7.326304 | 7.324519 | 0.000 | 0.436 |
| ramp | 42 | 8.157654 | 8.155388 | 0.000 | 0.010 |
| bursty | 42 | 7.023040 | 7.021513 | 0.000 | 0.638 |
| ramp | 43 | 8.582639 | 8.580577 | 0.000 | 0.028 |
| bursty | 43 | 8.181685 | 8.180788 | 0.000 | 0.110 |

These controls strengthen the asymmetric-path limitation: permanently using
the stronger alternate delivered these workloads without observed packet
loss. They do not establish general path dominance or an advantage of ML.

## Incomplete trigger comparison and timing

| Policy, seed 44 | Quality | UDP loss % | Age at program start (s) | Decision to readback (s) | Program/readback only (s) |
| --- | --- | --- | --- | --- | --- |
| reactive | accepted | 4.066 | 0.692 | 1.174 | 0.483 |
| early_warning | failed | 3.645 | 1.159 | 1.744 | 0.602 |

Do not use this incomplete block as an accepted paired policy result. Keep its
networking outcomes visible as diagnostics. The original 0.5 s freshness gate
is before shared-action rule verification, so it does not guarantee a 0.5 s
measurement age at programming start. The latter interval excludes neither
link reads nor pre-install verification when reported as full decision-to-
readback time. These measurements still do not establish the first selected
UDP packet's activation time.

All 36 original raw trial records were hash-rechecked for the separate action
audit. Their 19 applied actions had maximum programming-start measurement age
0.236 s and maximum full decision-to-final-readback time 0.413 s. The original
benchmark is unchanged; the slower initial supplemental actions remain a
measured limitation, not a reason to alter their recorded outcomes.

## Prospective recovery

See [the recovery registration](../../SUPPLEMENT_RECOVERY.md). Preserve the old
failed batch, run one 60 s idle collector check, then restart the whole seed-44
block once under the exact frozen source/settings. Keep both earlier seed-44
attempts outside complete-block means. Then acquire seeds 45–46 only if the
first complete block passes. Stop on any further failure. No automatic retries,
seed changes or model/threshold/collector changes are authorized by the plan.

## Reproduce this audit

Extract the original checkpoint using the existing recreation workflow. Then,
from this repository, with Python 3.12 and new output/extraction directories:

```bash
python3 tools/audit_stopped_supplement.py \
  --archive evidence/raw/342-sdn-supplement-diagnostics-20261120-184224-133635.tar.gz \
  --sha256 fb5d184b1888add78828938b72bf37bda99233996ea3b4c25b5def46d28ba07c \
  --extract scratch/supplement-raw \
  --output scratch/supplement-audit \
  --published . \
  --original-repo scratch/reproduced/checkpoint/342-proactive-sdn
```

`audit.json` preserves full independent inspections and interval/action timing.
The CSVs keep sender pacing, receiver sequence loss, received-probe RTT and
controller timing separate. No fitting or live traffic occurs during replay.
