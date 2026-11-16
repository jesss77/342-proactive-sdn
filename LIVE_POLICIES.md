# CMPS342 — Live non-ML policy pilot

Frozen operating profile: `dual-forward-cburst16k-source250-v1`, one vCPU,
continuous 1,200-byte UDP source, 250 ms all-four-queue batch monitoring. The
alternate has three clean 12 Mbit/s and three clean 16 Mbit/s steady controls.
`operating_bounds.json` records those limits and evidence. It is not a maximum
capacity certificate or a guarantee for arbitrary future bursts.

The admission budget is 15.9 Mbit/s, rounded below the worst observed 16 Mbit/s
payload goodput. Comparing link-counter rates to this smaller number is
deliberately conservative. Admission permits current estimated selected demand
plus standby load at most 80% of that budget (12.72 Mbit/s), with live links.
Source demand is the recent maximum upstream primary departure rate, a
conservative aggregate estimate in this one-generated-pair experiment. No
generated h3/h4 background is included in this pilot. Future background-flow
experiments require separate flow-demand/accounting validation.

`run_policy_experiment.py` runs fixed/reactive/early-warning policies with the
same source, profile, collector, two-second history and shared action. It starts
on primary and permits at most one alternate action. Reactive confirms high
observed utilization for one second. Early warning uses the existing positive
past-trend forecast; these trigger parameters remain provisional. No Decision
Tree is implemented by this update.

The source runs once without endpoint restarts. A recorder worker captures all
six forward queues while the main thread reads complete JSONL observations.
Decisions reject invalid/stale samples (>0.5 s age), gaps, down standby links or
insufficient headroom. Plans/seed/future samples are not feature inputs. Policy
and offline features share the same causal implementation. Requested vs. actual
source time and decision/readback time are recorded separately.

Both path rates and source queue are restored only after recorder/monitoring
shutdown. A fatal controller error cancels the recorder through a checked event
and waits for endpoint cleanup. Every decision, rejection, attempted action and
restoration is retained. No trigger or an admission denial can be a valid policy
outcome; it is not silently excluded as a program failure. In-traffic action
verification is a separate implementation-gate field, not a QoS success claim.

Workloads must stay inside the tested 16 Mbit/s payload envelope. The default
variable-scenario scale is 11.5 Mbit/s so every possible seeded peak is at most
15.525 Mbit/s. This differs from the earlier 12 Mbit/s-scale pilot dataset; use
identical newly recorded plans across later policy comparisons. Do not pool the
old pilots into matched policy results. Final target/measurement calibration,
independent datasets and model/evaluation checkpoints remain open.

After installation in the idle primary Mininet session:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_policy_experiment.py').read(), '/home/jess/342-proactive-sdn/run_policy_experiment.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_policy_experiment.py', 'policy': 'reactive', 'scenario': 'ramp', 'requested_bps': 11500000, 'duration': 60, 'seed': 1})
```

Review quality, path counters, action timing, source delivery and cleanup before
any matched series or claim of improved QoS. Loop-thread CPU and collector plus
child CPU are separate measurements; do not call them total system overhead.
