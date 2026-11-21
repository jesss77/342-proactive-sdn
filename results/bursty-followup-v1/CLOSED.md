# Bursty follow-up closed after registered quality stop

**New live acquisition is closed.** The separately registered follow-up attempted
seven of sixteen cells: six individually passed quality checks, one failed, and
nine were not attempted. Only seed51 forms a complete additional four-policy
block. Seed52 is incomplete. No retry, replacement seed or recovery cycle follows.
The model, source, controller and quality rule remain frozen.

All seven guest reviews and native endpoint summaries reproduce independently
from checkpoint `342-sdn-checkpoint-20261121-164948.tar.gz`, SHA-256
`a4c9f96e7a5029d7a28d2abf1ef86e7a62c84722e23eb0c585e286ab4f78c64d`.
All 85 installed pins match, as do the original topology/controller. Completed
activation-parent evidence, the original 36 matched raw trials/19 actions and
the independently reviewed seed51 raw files remain verified. The failed state
remains byte-identical after audit and the runner correctly refuses resumption.

## Retained attempts and exclusions

| Seed | Policy | Quality | Receiver Mbit/s | UDP loss % | Actions | Denials |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 51 | fixed | passed | 6.018180 | 21.383819 | 0 | 0 |
| 51 | reactive | passed | 7.611531 | 0.649418 | 1 | 0 |
| 51 | ML | passed | 7.659231 | 0 | 1 | 0 |
| 51 | early warning | passed | 7.657106 | 0.077230 | 1 | 0 |
| 52 | reactive | passed, partial block | 5.996842 | 20.345282 | 0 | 68 |
| 52 | early warning | passed, partial block | 7.370923 | 2.211188 | 1 | 7 |
| 52 | fixed | failed collector quality | 5.974337 | 20.187503 | 0 | 0 |
| 52 | ML | not attempted | — | — | — | — |
| 53–54 | all four policies | eight cells not attempted | — | — | — | — |

Seed52 reactive was not rejected for high loss or failure to switch. Its 68
denials were 63 insufficient-headroom and five stale-observation rejections.
Early warning had five headroom and two stale-observation denials before one
successful action. Both are valid individual outcomes and remain visible.
They cannot enter a complete four-policy paired mean because seed52 ML is
missing and fixed fails measurement quality. The quality stop was not selected
according to which policy performed better.

## Exact collector failure

The failed fixed-policy folder is
`20261121-163951-906144-policy-fixed-bursty-seed52`; its native trial is
`20261121-163957-044894-primary-continuous-bursty-7546736bps`.

At source second47.676, sample200 began 21.290 ms late and its full collection
cycle took **282.226 ms**, finishing **53.516 ms after the next scheduled
deadline**. The `tc` query itself took 164.546 ms, below the 250 ms interval.
Sample201 records one skipped deadline; its query-midpoint interval is
304.213 ms. Each of the four queues therefore has one invalid interval from
the same shared scheduling event, not four independent failures. There are
zero failed queries or counter resets. The original zero-invalid-interval
quality rule correctly rejects this run.

Endpoint UDP-error deltas and sender send errors are zero. All profile and
route restorations pass. Source planned-budget discard is 0.7111%, with a
193.227 ms maximum pacing gap; disclose it separately from network loss.
Guest one-second mean/max user+system CPU is 22.1%/63%, with no zero-idle
window or swap. These observations do not identify the host/kernel scheduling
cause. Passing idle readiness did not guarantee loaded polling quality.

Early-warning seed52's full decision-to-final-readback delay was **1.039749 s**,
versus the printed programming-start-to-readback subinterval **0.561264 s**.
Programming began with a 0.486992 s old observation. There is no packet capture
in this cohort, so neither interval is first selected-UDP activation time.
Retain this timing variation rather than generalizing the earlier clean pilot.

## Interpretation and next work

The [original benchmark](../matched-v1/RESULTS.md) stays the main matched
comparison. [Seed51](seed51/RESULTS.md) stays a separate follow-up realization:
ML had lower loss than early warning in that pair, but a slightly higher probe
p95 RTT. One additional complete block does not establish a general ML advantage.
Do not combine partial seed52 with original/complete blocks or claim all sixteen
planned trials completed. Do not claim the earlier intermittent fault was fixed.

The final paper should distinguish the completed core comparison from limited
follow-up repeatability. Final offline work includes consolidated calibration
and parameter tables, warning denominators/rates and exclusions, individual
paired variation, and literature/claim verification. No more traffic is needed
under the agreed bounded stopping decision.

## Reproduce the failure audit without traffic

```bash
python3 tools/audit_closed_bursty_followup.py \
  --extract scratch/closed-followup \
  --output scratch/closed-followup-audit
```

Use fresh directories. The audit verifies the exact archive, 85 installed pins,
original topology/controller, parent and previous seed51 evidence, two readiness
records, seven saved inspections/native summaries, independent per-queue interval
classification, source accounting, denial reasons and unchanged failed state.
It confirms the original runner refuses to resume and issues **no review receipt**.
See [closed-audit.json](closed-audit.json), [all-attempts.csv](all-attempts.csv),
and the [post-PR4 attrition table](POST_PR4_ATTRITION.md).
