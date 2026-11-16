# Figure captions

All figures use the complete independently checked 36-trial batch. Each point
represents a whole run; marker shape identifies seeds 41, 42 and 43. Horizontal
bars indicate the three-run mean and vertical lines the observed range, not a
confidence interval. Policies are gray fixed, blue reactive, orange early
warning and purple ML. Scenarios are analyzed separately. PNG and editable
vector SVG versions are supplied.

1. **Networking outcomes.** Whole-run receiver payload goodput, UDP sequence
   loss and within-run received-probe RTT p95. The displayed mean RTT p95 is
   the average of three within-run p95 values, not a pooled packet quantile.
   Loaded-probe loss is reported separately in the trial CSV; traffic-window
   probe loss remains uncomputed. The different column scales are explicit.
   Tiny nonzero loss can be difficult to see on the shared conceptual scale;
   retain the numeric table alongside the figure.

2. **Computation costs.** Collector process/children CPU and policy-thread CPU
   as percentages of one core over their recorded measurement windows. These
   are separate components, not total system overhead. ML inference CPU is
   already included in policy-thread CPU. First-block CPU and jitter are
   visibly higher for all four modes; rotating order does not remove VM
   scheduling variation.

3. **Routing and inference.** Counts of trials with an applied route change
   out of three, individual command/readback times for applied actions, and
   within-run ML inference wall p95 values. Each trial permits at most one
   successful switch; a low-load switch is unnecessary. CLI readback includes
   command overhead and does not measure packet interruption or exact rule
   activation. Inference runs until a switch or trial end, so call counts and
   the measured observation periods differ across runs.

4. **Queues and drop localization.** Sampled maximum queue occupancy at the
   primary bottleneck, primary root-drop deltas and alternate root-drop deltas.
   Sampling at 250 ms does not capture every packet-level maximum. The two
   alternate interfaces are distinct queues; their independent root counters
   are summed only for the alternate-drop figure. Across all trials, 49,700
   primary bottleneck drops and four alternate first-link drops were recorded;
   access, primary-upstream and final egress drops were zero. Counters include
   probes and control packets, so keep them separate from UDP sequence loss.

The complete methodology, source comparability and adverse outcomes are in
`../INTERPRETATION.md`; direct ML-versus-comparator differences are in
`../analysis-details.json`.
