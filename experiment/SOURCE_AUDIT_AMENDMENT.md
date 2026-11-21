# Source audit amendment — before fitting or fresh test acquisition

The completed development batch has 16 runtime-screened traces. Its original
dataset builder reused a pilot audit that required **exactly zero** sampled
pacing-budget discard. Runtime acquisition screening instead rejected discard
only above **5%** of planned bits. This inconsistent acceptance policy caused
the dataset build to stop after the two zero-discard seed-11 traces.

Inspection of the verified raw checkpoint found nonzero discard in the other
14 traces: 0.020581%–0.228314% of planned traffic. All source timestamps and
packet counts increased correctly. This is discarded sender pacing credit,
not a socket error or a network-lost datagram. The source limits catch-up bursts
instead of sending arbitrarily large bursts after a scheduling delay.

Amendment `measured-fixed-source-integrity-v1` retains data for prediction from
**measured** fixed-primary counters when endpoint/source/collector/path checks
pass, using the already existing 5% acquisition bound. That bound is not newly
chosen just above these observations. Every run reports native discard,
fraction, sampled increments, unsampled tail discard, sample gaps and native
pacer gaps. Timing/count/budget corruption, send errors and incomplete endpoints
still fail. The original zero-discard auditor remains unchanged, and a legacy
zero-discard flag retains its result for each trace.

This is an explicit offline acceptance amendment, made before model fitting
and while fresh test seeds remain unacquired. It is not evidence of a perfectly
delivered planned workload. Models use actual observed counters; schedules and
pacing diagnostics remain outside the feature allowlist. Final policy results
must report achieved sender rates and pacing quality, rather than claiming
packet-identical traffic from equal seeds alone. Larger deviations require
separate examination under the existing acquisition policy.

The raw archive, all traces, original source snapshots and frozen acquisition
protocol are preserved. Acquisition code, source pacing parameters, labels,
feature calculations and data partitions are unchanged. Only the offline reader
uses the amended audit, and derivative summaries record its full policy and
source hash. No traffic rerun or silent removal of an acquired identity occurs.
