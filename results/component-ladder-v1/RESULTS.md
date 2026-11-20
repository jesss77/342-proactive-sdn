# Four-case loaded diagnostic: independently verified

The completed diagnostic did not reproduce the earlier endpoint/collector
failure. All four guest reviews reproduce exactly from the new full checkpoint.
This is a short, fixed-order diagnostic, not evidence that the intermittent
fault is fixed or a new matched policy-benefit study.

Checkpoint: `342-sdn-checkpoint-20261120-234612.tar.gz`.
SHA-256: `b851a04ab1762953dea2b36ae64268373bc961b4cef6ce490d56ee70b25f4005`.
All **11,298 regular files** safely extracted; all **76 installed source/artifact
pins** match. The registered diagnostic protocol remains
`aa193d5c1d2d02a2955a0f3680276149c8f4d8b491c1353ee63c0aae30ebae1b`.
No source, model, buffer, clock, profile, threshold or quality criterion changed.

## Setup and outcomes

The same 60-second bursty seed44 schedule uses an 11.5 Mbit/s scale, 1,200-byte
UDP payloads, default sockets and the original dual-path profile. The first
three cases retain the primary route. The fourth adds the frozen reactive
trigger and common one-way action. All cases retain probes, snapshots and
vmstat; the first omits continuous `tc` polling and the policy loop. The first
call's 60-second idle readiness check independently reproduces its pass.

Jess reported plugged in with other host work still running. Neither an
otherwise-idle host nor a historical power/load cause is claimed. One case per
component and a fixed order limit causal and statistical interpretation. Seed44
was already observed; this is not a fresh prediction test.

| Case | Sender Mbit/s | Receiver Mbit/s | UDP loss % | Source discard % | Max pacing gap ms | Collector CPU % of one core |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| source_receiver | 7.829832 | 6.402957 | 18.198909 | 0.648138 | 144.913943 | inapplicable |
| collector | 7.865555 | 6.419921 | 18.345843 | 0.194710 | 58.122306 | 10.891 |
| fixed_loop | 7.854022 | 6.403408 | 18.442389 | 0.343302 | 51.126452 | 12.902 |
| reactive_loop | 7.839448 | 7.519966 | 4.047187 | 0.526428 | 52.863315 | 10.148 |

All four cases have zero endpoint UDP-error deltas, clean profile/route
restoration and correctly reproduced native sender/receiver summaries. Each of
the three monitored cases has zero query failures and invalid intervals on all
four queues. The first case's absent collector is explicitly inapplicable,
not reported as zero-cost/zero-failure monitoring. Root drops, UDP sequence loss
and source pacing discard retain their separate accounting bases.

The roughly 18% sequence loss in the first three cases is retained as an
outcome of the bursty source on the 10 Mbit/s primary bottleneck. The reactive
case has 4.047% loss, one verified in-traffic alternate switch and nine denied
requests (eight admission-headroom, one stale-observation). These single-run
values are not pooled into the original 36-trial means or incomplete supplement.

## Timing and resource limits

The maximum query durations were 236.484 ms (collector), 151.881 ms (fixed loop)
and 117.737 ms (reactive), against the requested 250 ms interval. The collector
case's median query was 24.932 ms. Its maximum leaves limited timing margin;
a zero-invalid result in one window does not prove monitoring cannot fail.

Source-only pacing still had a 144.914 ms maximum gap and 0.648% discarded
budget. Short source stalls can therefore occur without the continuous
collector or policy loop. This does not establish that the earlier 383 ms
collector overrun and receiver-buffer errors had the same cause. All four
source audits pass the unchanged inherited 5% limit; no perfect-pacer claim is
made. Guest one-second user-plus-system CPU means were 18.13%, 27.95%, 33.33%
and 23.77% in ladder order. These are descriptive windows, not an estimate of
component causal effect under uncontrolled concurrent host work.

Reactive action, relative to source start:

| Event / interval | Seconds |
| --- | ---: |
| Observation available | 11.347169 |
| Decision recorded | 11.358296 |
| Programming started | 11.546531 |
| Final readback finished | 12.161469 |
| Measurement age at programming start | 0.199362 |
| Full decision to final readback | 0.803173 |
| Programming/readback subinterval | 0.614937 |

The full 0.803 s decision-to-readback interval exceeds the original benchmark's
maximum 0.413 s, though this action's 0.199 s programming-start observation age
is within the original observed maximum 0.236 s. Hardware/session variation
remains material. Flow readback is not a first-selected-UDP-packet activation
measurement or one-way application delay. Traffic-window received-probe RTT
median/p95 were 11.5/58.6 ms; missing replies and received-reply statistics stay
separate. No counterfactual primary onset is manufactured after rerouting.

## Preservation and interpretation

All 10,720 previous-checkpoint file contents remain preserved: 10,719 files are
byte-identical and the continuing Mininet session log only appends records.
All 828 initial supplement and 122 recovery/review pins match. Both failed
batches and their rejection decisions are unchanged. All 36 original matched
trial evidence hashes were checked again; their original 19 action records are
intact. No new complete supplemental four-policy block exists.

This closes the bounded diagnostic execution and raw-audit task. It does not
identify a root-cause fix, reopen a failed batch or establish an ML advantage.
Keep the original three-seed matched study as the efficacy evidence. Do not
start another full recovery simply because these four windows passed. A small
separately registered packet-activation pilot remains an optional timing task;
its capture overhead and quality must be checked. Existing offline evidence
consolidation and the final paper should proceed alongside that decision.

## Reproduce

From the repository root, Python 3.12, with new scratch directories:

```bash
python3 tools/audit_component_ladder.py --extract scratch/component-checkpoint --output scratch/component-audit
```

The tool verifies the exact archive, installed/captured pins, preserved prior
files, all four inspections, source budgets/native endpoint accounting,
collector intervals, environment/readiness records, actual action timestamps
and original benchmark hashes. It starts no traffic and fits no model.
[Full audit](audit.json) and [machine-readable table](component-results.csv)
retain exact run IDs, values, costs and raw evidence hashes.
