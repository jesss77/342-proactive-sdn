# Fixed-primary development acquisition

Protocol `dual-fixed-highutil-v1` freezes the existing dual calibration, one
vCPU, one h1/h2 flow, 1,200-byte UDP payload, 60-second schedules, scale
11.5 Mbit/s and 250 ms all-four-queue batch monitoring. It does not alter the
topology, controller, source engine, sampler or three policy algorithms.

The target is an observed new onset of utilization >=85% sustained for one
second within a two-second horizon. Features use only measurements already
available, with two seconds of complete history. Future support, reset/gap and
already-started-event exclusions match the reviewed causal pipeline. This is an
operational high-utilization target, not a necessary/sufficient definition of
loss. Abrupt bursts can begin dropping before a useful warning is possible.

Development audit used only original seeds 1/2 plus the fixed seed-1 control.
All sampled ramp drops were inside high-utilization events; the first sampled
drops followed observed onset by about 4.25–5.50 seconds. Bursty events often
started dropping in the onset interval, and some transient drops occurred
outside sustained events. The 0.8/0.85/0.9 threshold and 0.5/1/1.5-second
duration sensitivity was descriptive, not optimized on test results. Keep
warning lead time relative to the operational target separate from actual loss.

Sampling is fixed at 250 ms for this scope. Reviewed largest paired intervals
were 0.253–0.277 seconds; the largest query lasted 0.052 seconds. Shorter spikes,
independent kernel-counter freshness and exact packet-level onset remain
uncertified. Timely read completion is not proof of exact physical event time.

New whole-run partitions, for each of ramp and bursty:

- Training: seeds 11–15 (ten traces).
- Validation: seeds 21–23 (six traces).
- Fresh test: seeds 31–33, reserved and **not acquired by this runner**. Freeze
  model and alarm decisions before acquiring/evaluating them.

Only untouched fixed-primary traces enter this dataset. Automatic-policy
traces are excluded because routing changes censor primary-path behavior.
Exact profile, schedule, source hashes, sampler coverage, endpoint/source
quality, path counters and restoration must pass screening. Every attempt is
recorded; a failed acquisition stops the batch and preserves its raw reference.
No failed trial is silently replaced. The builder blocks incomplete development
sets by default; `--allow-partial` is only for acquisition review, not model fitting.

The first guest batch is limited to two training traces for wrapper acceptance:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_dataset_batch.py').read(), '/home/jess/342-proactive-sdn/run_dataset_batch.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_dataset_batch.py', 'limit': 2})
```

After review, resume the paused batch using the directory recorded in
`results/runs/active-development-batch.txt`. A resume validates source/protocol
and the already accepted identity prefix before acquiring new runs. Failed or
interrupted batches require explicit evidence review instead of automatic resume.

Dataset derivatives are written outside raw run folders. Features are selected
only from the shared eleven-column allowlist; partition/run identity is retained
for grouping and audit, never included as a predictor. A dataset build or a unit
test is not evidence of model quality. Model selection, untouched test metrics
and repeated four-policy network evaluation remain separate checkpoints.
