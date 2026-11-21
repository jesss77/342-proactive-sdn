# CMPS342 — Pilot trace labeling

This offline tool turns acquisition-screened primary-path traces into an auditable
pilot dataset. It does not train a model or change a running network. Raw files
are read only; outputs must use a new directory outside `results/runs`.

The supported protocol is fixed primary routing, one continuous UDP flow, the
`forward-cburst16k-source250-v1` profile and schema-5 polling at 250 ms. A source
snapshot checksum mismatch or failed acquisition screen rejects the trace.

## Definition and timing

The provisional target is a **sustained high-utilization event**: counter-derived
egress departures at least 85% of the configured 10 Mbit/s for at least one
continuous second. This is an operational load definition, not a claim that 85%
itself establishes packet loss or physical saturation. Its relationship to queue
growth and drops must be calibrated before final held-out evaluation.

Onset is the beginning of the first qualifying measured interval. Confirmation
occurs later, at the end of the read that establishes the required duration.
At each decision time, the target is a **new onset in the next two seconds**.
Already-started events, missing/invalid history, gaps, counter resets and
incomplete future support are excluded. The two-second horizon plus one-second
duration also receives a conservative 0.75-second sampling/query guard. No
missing counter is replaced by zero and no failed-read gap is bridged.

Rates use actual query-midpoint elapsed time. A feature vector becomes available
only when both current queue reads have finished. This differs from pretending
that a read was available at its midpoint. Kernel devices in a batch dump are
read sequentially, and 250 ms acquisition does not establish finer kernel
counter freshness or exact packet-level onset time.

## Features and splits

`FEATURES` is the model-input allowlist: current utilization, actual-time weighted
one/two-second means, a one-second EWMA, a two-second utilization slope, observed
upstream departures, queue/backlog, current drop rate and query duration. They
use only present/past counters; source plans, future samples, seed, scenario,
run identity and absolute time are not model inputs.

CSV identity/split/label/lead-time columns are audit metadata. A later trainer
must select exactly the allowlist, not every numeric column. Labels and lead
times are offline targets and diagnostics, never predictors.

The explicit selection assigns seed 1 to pilot training, seed 2 to validation
and seed 3 to pilot testing, keeping each entire run and corresponding seed in
one partition. No adjacent-row random split is permitted. Six short traces
support pipeline validation, not a strong generalization claim. Final evaluation
requires additional independent seeds and matched policy trials; do not tune on
the pilot test partition or reinterpret it as untouched final evidence.

## Reproduce

From the repository after installing the three added files:

```bash
python3 -m unittest -v test_trace_dataset
python3 build_trace_dataset.py --repo . --selection pilot_trace_selection.json \
    --output results/derived/pilot-labels-v1
```

An existing output directory is refused. Outputs include all eligible/excluded
rows, exclusions, event timing, full acquisition inspections, input hashes and
source-window/packet-accounting checks. Rebuilding into a second output directory
must reproduce the same dataset bytes. Keep the original failed v4 ramp outside
the explicit acquisition-screened selection.

The final reviewed local build is `pilot-v3`; earlier `pilot-v1` and `pilot-v2`
are development derivatives retained for provenance, not alternative datasets
to select by model accuracy. The guard was added before any model training.
