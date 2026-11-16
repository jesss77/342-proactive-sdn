# Interpretation of the complete matched benchmark

All 36 trials were independently rechecked against the registered plan, frozen source/model hashes, preserved raw hashes, source integrity and quality/restoration screens. There were no failed queries, invalid sampled intervals, UDP endpoint errors or restoration failures in the accepted set. This is a single-VM, single-flow synthetic benchmark with three seeds per cell and one possible successful switch per trial.

## Delivery and policy comparison

Ramp loss averaged 9.740577% for fixed, 0.001947% reactive, 0% early warning and 0% ML. Receiver goodput averaged 7.510254, 8.319361, 8.328790 and 8.328941 Mbit/s respectively. Both early methods switched earlier than reactive on every ramp seed, but their delivery outcomes were essentially tied.

Bursty loss averaged 18.681719% fixed, 5.591034% reactive, 0.012666% early warning and 0.194688% ML. Both early modes improved delivery over fixed and reactive in each seed, but ML did not beat simple early warning consistently. ML had zero loss in burst seeds 41/42 and 0.584064% in seed 43; early warning retained small losses of 0.006525%–0.015846%. Mean goodput was 7.521430 Mbit/s for ML versus 7.537009 for early warning. Report direct paired differences and the three-seed spread, not a universal or statistically established ranking.

## Mechanism and adverse outcomes

Reactive encountered four insufficient-headroom denials in burst seed 41 and forty in seed 42. The latter did not switch until 47.610659 seconds and lost 15.030369% of UDP datagrams. These are real outcomes of the same current-load/headroom guard: a late trigger can reach admission when the observed flow is too large. Do not remove the guard, retune after evaluation, or omit these trials.

In steady seed 41, ML switched after roughly 30.088 seconds with utilization 0.283581, no queue/backlog/drop signal, and predicted probability 0.890385 above threshold 0.65. This is an unnecessary low-load action. ML took no action in the other two steady seeds, while fixed/reactive/early warning took none in all three. All steady runs delivered with zero UDP loss. One action is not evidence of a prevented event when there was no sustained load increase.

## Prediction, lead time and latency

Keep the separate untouched prediction test beside networking results: row F1 0.956522 for ramps and 0.811111 for bursty traffic; advance warnings reached 2/3 ramp and 9/25 scorable burst events (26 observed). Twenty-four false episodes included twenty late warnings; five tail episodes were censored. High row F1 alone does not establish actionable prediction.

Nineteen matched actions were applied. CLI command/readback elapsed ranged from 44.234 to 210.673 ms. This includes local command/readback overhead, not packet disruption or exact rule-activation time. Successful held-out warning-run median leads ranged approximately 0.995–1.999 seconds. They are from separate fixed traces and cannot be treated as paired proof of time available for a matched intervention. Full packet-level activation/disruption measurement remains outside this benchmark.

## Measurement and source limits

Mean receiver goodput is over each whole traffic schedule. Reply RTT statistics describe received probes, with loaded-probe loss reported separately; traffic-window probe loss is uncomputed. Queue occupancy is sampled at 250 ms, so sampled maxima are not packet-level maxima. Queue drops include probes/control packets and must not be equated exactly to UDP sequence loss.

Pacing-budget discard reached 0.341809% of planned bits, below the unchanged 5% acquisition limit. Sender-rate spread within a matched cell reached 0.342362%; equal plans do not guarantee identical packet timing. Disclose achieved rates, source diagnostics and CPU variation. One-vCPU wall time and sequential execution remain sources of variation despite the rotated order.

Inference CPU is a subset of policy-thread CPU and is not added again. The one-way/single-action cap makes most of a rerouted run stay on the alternate path; these results do not establish repeated recovery behavior, fairness with other flows, arbitrary cross-traffic, link failure handling, maximum throughput or deployment readiness.

## Supported conclusion

The shared implementation is operational and earlier triggering improves delivery against fixed/reactive baselines in this tested setup. A simple trend rule already captures most of that benefit. These data do not establish added value from the learned tree, and reveal an unnecessary low-load ML action. The contribution should emphasize the controlled comparison, observed limitations and cost measurements rather than claim general ML superiority.
