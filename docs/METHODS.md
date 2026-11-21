# Methods and interpretation

- Four-switch diamond; h1/h2 selected IPv4 pair, including RTT probes. h3/h4 idle.
- Primary bottleneck 10 Mbit/s; both alternate links 20 Mbit/s. Access 100 Mbit/s.
- Calibrated profile: source queue 250 packets; switch queue 50; burst 15,360 B,
  cburst 16,384 B; configured link delay 1 ms. Temporary settings are restored.
- One 1,200-byte UDP payload flow; 60-second steady, ramp and bursty trials.
- All four forward queues sampled at requested 250 ms; actual counter elapsed
  time is used. Missing/stale observations suppress action and break support.
- Target: new 85% utilization onset sustained one second within a two-second
  horizon. Two seconds of history and 3.75 seconds of future label support.
- Tree: depth 3, leaf minimum 25, 15 nodes, score threshold 0.65. Whole-run train
  seeds 11–15, validation 21–23 and fresh test 31–33; ramp/bursty in each partition.
- Shared actor: recent valid selected demand plus measured alternate load must
  fit the 12.72 Mbit/s admission limit. One successful primary-to-alternate move,
  five-second cooldown guard, no in-trial return, primary restored at cleanup.
- Reactive waits one second of observed high utilization. Trend uses utilization
  at least 0.5, positive two-second slope and projected utilization at least 0.85.
  ML uses only the frozen score; all policies share freshness/admission/action.

## Keep these distinctions

Requested schedule scale, achieved sender rate and receiver payload goodput are
different quantities. Source pacing discard is not network loss. Root queue
drops, UDP missing datagrams and endpoint errors are not added together.

The 85% target is a high-utilization warning condition, not universal packet-loss
ground truth. Event onset precedes confirmation. Offline labels use untouched
fixed-primary traces; prevented events in controlled runs are not counted as
false alarms simply because they disappear after intervention.

Probe RTT describes received replies, not one-way application delay. CLI
readback is not packet activation. The separate capture pilot observed first
alternate UDP at 110.117–110.142 ms after decision in one ML ramp. Software tap
timestamps and observed clock envelopes do not establish atomic installation,
receiver delivery, a causal overhead bound or prevented onset.

## Repeatability and limits

The original 36-trial benchmark uses seeds 41–43. Independent runs, rather than
adjacent polling rows, are the comparison unit. Fixed-alternate controls show
that the stronger route already handles these workloads without loss.

Only seed 51 completed an extra four-policy block. The separate 16-cell follow-up
attempted seven cells: six individually valid, one collector-quality failure and
nine unattempted. Partial seed 52 cannot enter a complete four-policy mean. Older
failed cohorts and the four passing diagnostics remain separate. The intermittent
failure cause remains unresolved; no quality rule was weakened.

Current-collector interval optimization, TCP, alternate-path background load,
multiple flows, repeated recovery, switch-back and general deployment performance
were not established. No consistent ML advantage over simple trend early warning
is claimed. Detailed fixed settings, exclusions and paired variation are in
[`results/tables`](../results/tables/).
