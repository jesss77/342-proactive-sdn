# Live integration of the unchanged frozen tree

The first fresh prediction test completed under v13 with 642 eligible rows,
206 positives and 29 observed high-utilization events. The frozen tree's row
F1 was 0.956522 on ramps and 0.811111 on bursty traffic. Warning episodes were
weaker: 2/3 ramp and 9/26 burst events warned within two seconds, with 24
false warning episodes (20 late) across the six runs. This is not proof of
networking benefit. The model/threshold are not retuned after these outcomes.

v14 adds an `ml` trigger to the same LiveDecider and policy runner. The tree
bytes remain pinned at SHA-256
`63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595`,
threshold .65, fifteen nodes. The model's label/profile context and exact
feature-source SHA must match before any traffic or rule action. Inference
uses the unchanged shared causal feature functions and Python-only JSON CART.
No source plan, seed, future counters, retraining, target changes or new
heuristic filter enters the trigger.

All four policies share history warming, four-queue validity, observation-age,
link/headroom admission, the same selected-pair action, one successful switch,
and cleanup. v14 also rechecks the same .5-second observation bound after
feature/inference/link-read work for every policy, before the shared action.
Record that common-loop version in final matched comparisons rather than
pooling earlier pilot versions as though they were identical.

Each evaluated ML decision logs probability, threshold, CPU and wall duration.
Inference stops after a successful one-way action; continued monitoring still
captures path/queue/delivery evidence. The summary includes call count and
CPU/wall totals, median, p95 and maximum. Inference CPU is a subset of the
policy-thread CPU, not a separately additive cost. No probability, no trigger,
or an admission denial can still be a valid reported policy outcome; a switch
and its benefit must be reviewed from actual data.

ML trials capture model, inference code and feature code; the inspector checks
model binding and observed inference as well as common quality/restoration.
Offline replay of all 3,703 development histories confirmed exactly equal live
and offline feature values and predicted probabilities using the actual live
source-start estimator. This is algorithm parity, not live action evidence.

The first guest acceptance trial uses the already viewed pilot ramp seed 1,
60 seconds, scale 11.5 Mbit/s. It does not reuse fresh test results to tune the
model or threshold. Final networking evaluation requires new matched runs and
must retain false/no-action outcomes and steady-load controls.

Acquisition source snapshots and raw data remain immutable. Old development
and held-out acquisition helpers deliberately refuse new collection once
their pinned acquisition source changes at this live-integration stage.
Completed datasets remain reviewable using captured source/protocol evidence.

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_policy_experiment.py').read(), '/home/jess/342-proactive-sdn/run_policy_experiment.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_policy_experiment.py', 'policy': 'ml', 'scenario': 'ramp', 'requested_bps': 11500000, 'duration': 60, 'seed': 1})
```
