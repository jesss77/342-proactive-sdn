# Registered matched networking evaluation

The v14 frozen-tree pilot passed in Ubuntu: one verified in-traffic switch,
8.808311 Mbit/s received, zero UDP/queue loss, clean screening and restoration.
There were 45 model calls: median/p95 wall time 21.224/53.662 microseconds.
The routing command/readback took 80.442 ms; this is not packet interruption.
The model and threshold remain unchanged after the separate prediction test.

The next batch has 36 trials: four modes (fixed, reactive, early_warning, ml),
three scenarios (steady, ramp, bursty), three fresh evaluation seeds (41–43).
Each source lasts 60 seconds. Steady is a 3 Mbit/s low-load action-cost control;
ramp/bursty retain the development scale of 11.5 Mbit/s. Do not treat steady
as an overload benchmark. Each cell uses an identical source schedule across
all modes; achieved sending/pacing are measured and may differ.

The common v14 loop, model, features, action, bounds, topology, source and
collector are pinned before collection. No changes to them are included in
this update. Only the trigger differs within matched comparisons. Scenario
order rotates across seeds, and Williams policy orders spread run-order
effects. With nine blocks, each mode appears two or three times per position.
This reduces order imbalance; three repetitions do not remove VM variability.

The first four trials are the complete steady seed-41 block. The wrapper
pauses for inspection after them; resume continues the original registered
batch. It does not rerun accepted cells. A registry blocks a silent second
batch, failed/interrupted batches stop for review, and every failed raw folder
reference is retained. Model/source changes block new trials and resumption.
Already accepted raw files are hashed and checked before resuming.

Quality acceptance uses the common route/collector/source/restoration checks,
not a demand for switching or QoS improvement. No trigger, denied action or
unnecessary low-load switch is a reportable outcome. Applied actions require
in-traffic path proof. Fixed must never request an action; at most one applied
action is allowed for any automatic mode. ML must have a frozen model binding
and observed inference. Sender integrity retains the same 5% pacing discard
limit and explicit diagnostics; it is not a perfect offered-schedule guarantee.

The first accepted seed-1 ML pilot is rechecked from local raw records under
the identical source pins before any matched collection. Evaluation records
are not model training/validation data. Prediction labels and warning metrics
remain in the untouched fixed-primary held-out report; rerouted traces do not
provide counterfactual primary-path congestion truth.

Before starting, export the fresh held-out and live ML checkpoint to Windows.
After installing v15 in T3, run in the existing primary Mininet T2:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_matched_batch.py').read(), '/home/jess/342-proactive-sdn/run_matched_batch.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_matched_batch.py', 'limit': 4})
```

After reviewing the first four results, resume the saved batch using the
active-matched-batch.txt pointer and limit 32. Do not start another batch.
Each run takes roughly 65–70 seconds; four trials take about five minutes,
and all 36 take about forty minutes, subject to VM scheduling.

Report all four modes' goodput, loss, queue/drop localization, reply RTT plus
probe loss, actions/denials, action timing and collector/policy/inference cost.
Pair differences by scenario/seed; keep scenarios separate and show three-run
spread. Inference CPU is included in policy CPU. Keep achieved source and
discard diagnostics beside results. A single pilot or high row F1 is not a
comparative benefit claim. No settings are retuned on these evaluation runs.
