# Supplemental experiment registration

This adds evidence requested after PR4. The original 36-run benchmark, its
protocol, the model and the common experiment source files remain unchanged.
The additional seeds were chosen before supplemental acquisition. No trial is
accepted or rejected based on whether ML wins or whether QoS improves.

1. Complete time-aligned explanatory plots from existing raw evidence. They
   align source rate, observed counter utilization, queue occupancy and drops,
   trigger requests and command/readback intervals. These logs do not measure
   the first selected UDP packet on the alternate path.
2. Acquire six fixed-alternate controls: ramp and bursty, seeds 41–43. Apply
   the selected-pair alternate rule while idle, then hold it throughout the
   same 60-second workload used by the matched study. The idle admission check
   is not a claim about future offered traffic. These are a capacity-asymmetry
   comparator, not another predictive trigger.
3. After reviewing all six controls, acquire three additional bursty blocks,
   seeds 44–46, across fixed, reactive, early-warning and frozen-tree policies.
   Rotate their order using three Williams orders, continuing original block
   numbers at nine. Three additional blocks do not completely balance four
   positions; publish individual seed differences and order. Report the
   original and supplemental groups separately, with an explicitly identified
   combined six-seed bursty analysis as a sensitivity check. This extension
   follows observed variation and is not a new untouched confirmatory test.
4. Review the need for a small, separately instrumented activation pilot after
   steps 2–3. Existing counter envelopes and rule readback are not exact packet
   activation timestamps. Never pool instrumented QoS with the original study
   without identifying the different instrumentation.

The registered scale is 11.5 Mbit/s, duration 60 seconds, payload 1200 bytes,
collector interval 250 ms with all four forward queues, and the original
dual-path profile. The source generates the original seeded continuous
schedule. Its average sending rate is different from the scale parameter.
The Decision Tree, threshold 0.65, feature implementation, admission bounds,
measurement freshness checks, one-action restriction and cleanup are frozen.

`supplement_protocol.json` pins the original registration and additional
sources. `run_supplement_batch.py` writes a separate registry, records failed
attempts and stops on quality failure. Resuming checks source and accepted raw
hashes. No automatic replacement of failed trials is allowed. Loss, denied
actions, no actions, and unnecessary actions remain outcomes. Fixed-alternate
controls use the same source-integrity, path-counter and restoration checks;
variable-load loss is measured and retained rather than filtered for success.

Run an initial single control, review its report, then resume the remaining
five controls. Select the bursty stage explicitly only after all six controls
are accepted and reviewed. No held-out prediction data is reacquired and no
fitting is performed.

## Existing explanatory traces

Rebuild outside the frozen raw checkout:

```text
python tools/build_time_traces.py --repo RAW_REPO --report results/matched-v1/matched-report.json --output NEW_DIRECTORY --plots
```

The selected blocks contain all four policies: ramp seed 42 (middle seed),
bursty seed 42 (the adverse reactive case), and steady seed 41 (the unnecessary
ML action). This is an explanatory selection, not a statistically representative
sample. Original aggregate results still use all registered runs. All timing
uses each run's source monotonic clock. Failed query periods remain gaps;
counter differences use actual elapsed query times. The source interval CSV
accounts for final native totals, including the unlogged sample tail.

Plots distinguish payload from queue-counter accounting, queue occupancy from
drops, requests from rule readback, and counter observation from packet proof.
Primary utilization after rerouting is observed behavior, not a counterfactual
event label. Neither the two-second forecast horizon nor the readback interval
is presented as useful advance warning measured at the data plane.
