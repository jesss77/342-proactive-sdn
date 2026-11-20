# Prospective recovery after the collector-quality stop

The original supplemental batch is preserved as failed: six accepted fixed-
alternate controls, one accepted reactive seed-44 run, and one failed early-
warning seed-44 run. No complete extra four-policy block exists. All eight raw
trial pairs and the failed state remain evidence; no original validity metadata
or registration is rewritten.

The diagnostic archive SHA-256 is
`fb5d184b1888add78828938b72bf37bda99233996ea3b4c25b5def46d28ba07c`.
Independent audit reproduced seven accepted records and the collector-quality
rejection. One shared collector deadline was skipped, producing one invalid
interval per queue. The preceding collection cycle lasted 251.076 ms against
250 ms; its query lasted 241.539 ms. The next midpoint interval was 372.126 ms.
There were no query failures or counter resets. The skip occurred around source
second 31, roughly twenty seconds after route readback. This temporal separation
does not prove the skip's host/kernel cause. One-second resource logs cannot
identify the precise scheduling cause. The guest clock was consistently `tsc`,
as in all 36 original matched runs; no clock change is proposed.

## Frozen recovery rules

- Preserve the six accepted alternate controls. Do not reacquire them.
- Restart the entire incomplete seed-44 four-policy block once; then collect
  seeds 45 and 46 once. Retain the original reactive-44 run and failed early-
  warning-44 run as incomplete-block diagnostics, outside complete-block means.
- Use the same twelve cells and Williams orders fixed before initial collection.
  This is a disclosed response to a quality failure, not an untouched new test.
- No model, trigger, profile, workload, sampling interval, freshness code,
  admission rule, action budget or quality threshold changes. The original
  source-integrity limit stays 5%; skipped intervals are not waived after a
  successful switch. Adverse loss, denials and unnecessary/no actions remain
  outcomes, not reasons to retry.
- Run a 60-second idle all-queue collector check before each acquisition call.
  It generates no UDP/probes and changes no rules or profiles. Require the
  original clock/one-vCPU setting, primary baseline, idle counters, complete
  four-queue coverage and zero failed queries/invalid intervals. Passing idle
  readiness does not establish loaded stability or a root-cause fix.
- Acquire one complete four-policy block first. Stop on any readiness/cell
  failure and retain its raw references. No automatic retry, seed replacement
  or repeated recovery is permitted by this registration.
- Use a separate recovery registry and active pointer. Pin all 828 exported
  parent files plus all 68 original/current source files. Never edit the old
  registry, batch or accepted/failed raw evidence to make it resumable.
- Keep original, initial supplemental and recovery results identifiable in
  all analysis. Only complete quality-valid recovery blocks enter the extra
  paired comparison. Do not select runs according to the winning policy.

## Timing limitation retained, not concealed

The original 0.5-second freshness check occurs before entering the shared action.
Primary-rule verification can add delay before programming. For the initial
supplement, measurement age at programming start was 0.692 s (reactive) and
1.159 s (early warning); decision-to-final-readback was longer than the reported
program/readback interval. All 19 applied actions in the original 36-run study
had programming-start ages at most 0.236 s. This recovery preserves the code,
records actual ages, and makes no claim that the pre-entry check guarantees
freshness at programming time. Rule readback is not first-UDP-packet activation.
Changing that behavior would require a separately identified controller variant.

After acquisition, export a fresh full project checkpoint and independently
verify recovery identities, hashes, quality, exclusions, timing and all paired
outcomes. The earlier small diagnostic exporter covers the stopped parent;
it is not the export procedure for this new recovery batch.
