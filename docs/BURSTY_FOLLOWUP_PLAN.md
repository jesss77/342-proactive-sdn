# Reserved bursty follow-up cohort — November 21, 2026

This records the prospective reservation. Its subsequent implementation is
[BURSTY_FOLLOWUP.md](../BURSTY_FOLLOWUP.md); the original reservation JSON is
retained unchanged. Acquisition has not started.

The additional bursty comparison can be strengthened with new independent,
matched traffic realizations. Failed measurements cannot be converted into
valid repetitions. Preserve the original 36-trial benchmark, both stopped
supplemental batches and all their outcomes. This is a prospective design
reservation, **not an armed acquisition protocol or a completed experiment**.

## Fixed target

Reserve seeds **51–54**, four whole-run realizations not present in the latest
independently verified checkpoint. Each seed receives fixed, reactive, simple
early-warning and frozen-ML routing: **16 scheduled trials**. Four blocks permit
one complete Williams order, balancing policy position and directed immediate
predecessors. Seeds/order are fixed now, before inspecting any new outcomes.

| Seed | Policy order |
| --- | --- |
| 51 | fixed → reactive → ml → early_warning |
| 52 | reactive → early_warning → fixed → ml |
| 53 | early_warning → ml → reactive → fixed |
| 54 | ml → fixed → early_warning → reactive |

Use the existing 60-second bursty schedule at 11.5 Mbit/s scale, 1,200-byte
payloads, 250 ms all-queue sampling, original dual profile, one-vCPU guest,
default endpoint buffers, current-load admission and one successful switch.
Reuse the original shared policy runner and exact frozen tree/threshold.
Capture and the activation pilot's extra clock observer are absent here.
Record achieved sender rates/pacing and actual resource/host conditions.
Do not claim the fixed schedule scale is a constant sending rate.

## Gates before acquisition

1. Finish or formally stop the current activation pilot, then review its raw
   evidence. A capture-only instrumentation failure is not silently relabeled
   as a platform failure or ignored; assess its scope explicitly. No active or
   unreviewed failed run may be bypassed.
2. Establish eligibility for an uncaptured run: unchanged source/model/profile,
   no active source/capture/collector, verified primary route/restoration,
   recorded one-vCPU/clock/settings and a full clean idle check. Use the saved
   uncaptured/loaded diagnostic evidence honestly: passing windows do not
   identify a root-cause fix or guarantee the next block will pass.
3. Implement and test a separate source-pinned acquisition runner/registry.
   Verify the reserved seeds remain unused in the guest and capture the exact
   parent evidence. Never delete or resume either old failed registry.
4. Acquire only the first complete four-policy block, then export/review it
   before explicitly continuing the remaining three registered blocks.

No platform or controller patch is currently justified as a root-cause fix.
If a change becomes necessary, version it and renew calibration before deciding
whether these reserved comparisons still answer the same question. Do not
silently change vCPUs, clock, socket buffers, polling, freshness, admission,
model or trigger parameters under this design.

## Bounded stopping and analysis

Every scheduled cell is attempted at most once. Retain adverse/no-action,
admission-denied and unnecessary-switch results. Stop on a measurement,
identity, execution or restoration failure; preserve its raw references and
do not replace it with another seed or repeat until a desired outcome appears.
If the failure recurs, report the incomplete follow-up and finish from the
accepted evidence rather than opening another automatic recovery cycle.

Report this cohort separately from original seeds41–43. Show each complete
seed's paired ML-versus-early-warning differences, not only pooled means.
Keep attrition visible: scheduled/attempted/quality-valid counts, incomplete
blocks and every failure reason. Do not count thousands of polling rows as
independent network-performance repetitions. No failed cell may silently enter
an accepted mean, nor may its exclusion disappear from the paper.

If all four blocks complete, the study has three original and four supplemental
matched seeds. A combined seven-seed sensitivity summary must identify cohort
and session differences; it is not a newly untouched confirmatory experiment.
The principal claim remains whether an additional ML networking benefit was
observed beyond the simple early-warning rule. No benefit is required for a
trial to pass. This design adds no prediction test, fitting or retuning.

The old sentence about incomplete repetitions remains true for the old failed
cohorts. A successful new cohort would add evidence and narrow the limitation;
it would not erase the earlier measurement/replication failures.
