# Bursty follow-up — seed 51, first block independently verified

Four of sixteen registered follow-up cells are complete. All four guest reviews,
common quality/accounting records and native endpoint summaries reproduce.
All 85 installed files and the completed activation-parent evidence match.
Original 36-trial raw hashes and 19 actions remain verified. No extra reserved-seed
acquisition was found. Both stopped supplemental matrices remain closed.

| Policy | Sender Mbit/s | Receiver Mbit/s | UDP loss % | Probe RTT median / p95 ms | Actions |
| --- | ---: | ---: | ---: | ---: | ---: |
| fixed | 7.661099 | 6.018180 | 21.383819 | 15.30 / 66.6 | 0 |
| reactive | 7.662167 | 7.611531 | 0.649418 | 9.75 / 20.6 | 1 |
| ML | 7.662217 | 7.659231 | 0 | 10.00 / 16.6 | 1 |
| early warning | 7.665147 | 7.657106 | 0.077230 | 9.86 / 16.0 | 1 |

All endpoint UDP-error deltas, access/upstream/alternate root drops, failed
queries and invalid intervals are zero. Primary bottleneck root drops are
10,256 / 311 / 0 / 37 respectively; do not add those to sequence loss.
Readiness, shared path proof and profile/route restoration pass. All adverse,
no-action and successful-action outcomes remain retained.

ML's loss is 0.077230 percentage points lower than early warning in this one
pair; its receiver rate is 0.002125 Mbit/s higher, while probe p95 RTT is 0.6 ms
higher. This is one realization, not evidence of general ML superiority.
Source discard is 0.1214 / 0.1096 / 0.1064 / 0.0644%; maximum pacing gaps are
35.553 / 40.292 / 44.395 / 41.969 ms. Keep achieved source variation visible.

ML acted on its first model call, at source second 2.465 (decision) and 2.550
(programming start), with approximately 30% measured utilization. Its final
readback is at 2.637. The first sustained high-utilization onset in the separate
matched fixed run is at source second 2.820. This descriptive source-relative
alignment does not label the intervened run, measure its first alternate packet,
or prove a counterfactual prevented event. The early-warning decision is at
3.048 and the reactive decision at 4.100. Do not retune the frozen model based
on this follow-up.

Checkpoint: `342-sdn-checkpoint-20261121-162658.tar.gz`, SHA-256
`105c065734e32ae486cf3623ed2d01e9da5afc3a7a4e98c0bc2337c38d67a767`.
It contains 12,277 regular files. Batch:
`20261121-161023-478471-bursty-followup`, paused at four accepted cells.
Exact paused batch SHA-256:
`21dc6954aa2eabc0608efc4f385a12e12a8ae0fca189d5b3e28c953f3c2db1a4`.

The [review receipt](review-receipt.json) binds those exact bytes and checkpoint.
Only seed 52's next four-policy block is unlocked. Future blocks require their
own exported review; no repeated start or failed-batch retry is authorized.

Reproduce in fresh derived/extraction directories, without traffic or fitting:

```bash
python3 tools/audit_bursty_followup.py \
  --archive evidence/raw/342-sdn-checkpoint-20261121-162658.tar.gz \
  --expected-sha256 105c065734e32ae486cf3623ed2d01e9da5afc3a7a4e98c0bc2337c38d67a767 \
  --extract scratch/followup-seed51 \
  --output scratch/followup-seed51-audit
```

See [audit.json](audit.json) and [results.csv](results.csv). The current
post-failure cohort remains separate from the original seeds 41–43 and from
the invalid/partial supplemental attempts.
