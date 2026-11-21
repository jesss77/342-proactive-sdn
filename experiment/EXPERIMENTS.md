# Recorded path experiments

This entry point prepares C2 (alternate validation) and C3 (measurement calibration).
It has local contract tests. Guest Mininet acceptance tests are still required.
It does not implement reactive routing, early-warning routing, ML, or training labels.

## Validated evidence and profile

The November 14 checkpoint contains three low-load and three overload primary
calibration runs under one vCPU and 6144 MB RAM. The original topology file remains
unchanged: its initial netem limits are 50 and HTB cburst is 1600 bytes.

For each new recorded path trial, the wrapper explicitly applies profile
`forward-cburst16k-source250-v1`: cburst 16384 bytes and burst 15360 bytes on the
four forward-path interfaces, source netem limit 250, other netem limits 50,
rate/ceil and 1 ms delays retained. The alternate route uses 100/20/20/100 Mbit/s
forward classes, rather than the primary route's 100/100/10/100.

The original class and source queue values are restored in finally blocks. The
wrapper refuses an unexpected initial profile, a wrong controller route or an
unshaped topology. Inspect `profile-commands.json` and `restoration.json` after
every attempt. No automatic Windows/clock/security changes are made.

## Start the alternate path

Stop the old Mininet CLI with `exit`; then stop its controller using Ctrl+C.
Create a fresh session directory and record controller/Mininet terminal logs as
before. Start the controller with `SDN_PATH=alternate`, and Mininet with the
existing topology and `--link tc --arp` options. Check `pingall` before traffic.

From the Mininet CLI (the full path assumes this user's current checkout):

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_experiment.py').read(), '/home/jess/342-proactive-sdn/run_experiment.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_experiment.py', 'route': 'alternate', 'requested_bps': 12000000, 'interval': 0.25})
```

This first alternate check offers 12 Mbit/s, below its nominal 20 Mbit/s capacity.
It records idle/loaded RTT probes, numeric-port forwarding evidence, selected and
unused route counters, qdisc/UDP snapshots, endpoints, actual timing and profile
restoration. It should not be called a passed path validation until inspected.

Inspect from a normal terminal; raw files are readable and not rewritten:

```bash
python3 inspect_experiment.py results/runs/EXPERIMENT_FOLDER
```

Check route proof on ports 4 of s1/s4, increases on s1-eth4/s3-eth2/s4-eth4 and
negligible inactive-path data. Below-capacity tests require achieved rates near
the request and zero source/queue/UDP errors. Under overload, require loss to be
localized and explain packet accounting. New ping probes share those queues, so
qdisc counters include ICMP/control packets as well as UDP.

Obtain three accepted alternate 12 Mbit/s trials in total, then characterize
its overload service with 24 Mbit/s offered load. Watch for access shaping loss
again; nominal capacity is not measured payload goodput.

The alternate path has two equally limiting 20 Mbit/s interfaces: s1-eth4 and
s3-eth2. Overload drops may legitimately occur at either or both; source and
destination access drops still fail the isolation screen. Below-capacity tests
require zero drops on every checked interface.

## Native interval tests and overhead

Measurement-v5 replaces two child commands per cycle with one read-only
`tc -j -s qdisc show` dump, then selects roots by exact device name. Both queues
remain observed; the raw dump is retained in `tc_batch`. Their query bounds are
shared and the kernel entries are sequential, not an atomic snapshot. Do not
count per-interface flags as independent missed cycles. Earlier v3 interval/CPU
results remain historical; repeat the same traffic to measure this optimization.
Traffic generation, source pacing cap, class rates and queues are unchanged.

Path-v3 queries both forward inter-switch qdiscs, with independent query timing,
capacity normalization and failure continuity. Inspect `collector.qdiscs` for
both interfaces; old runs are not retrospectively assigned an upstream queue
measurement. Two queries add cost, so compare intervals using this version
consistently rather than treating v2 and v3 CPU percentages as matched trials.

Use the same scenario/seed with `interval` set to 0.5, 0.25 or 0.1. These are actual
native runs, not resampling one trace. Each record includes individual interface
read times and TC request start/end, scheduled/actual times and skipped deadlines.
`samples.jsonl.stats.json` reports collector and child CPU time separately from
query wall duration. Counter meaning/freshness must still be checked against
traffic and alternate-path counters before selecting the interval.

After a v3 smoke test, `run_interval_sweep.py` runs steady-load native polling at
500, 250 and 100 ms, with three repetitions per interval and rotated block order.
It keeps route, traffic, probes and profile fixed, writes full inspections plus
`summary.csv`, and retains failed delivery screens. Experiment or restoration
errors stop the sweep. Use `repetitions=1` for an exploratory three-run block.
This sweep measures timing/overhead and steady-load effects; controlled burst
resolution and counter freshness still need separate validation.

The loaded probe adds five ICMP requests per second. RTT and new monitoring can
change measured results; do not treat this updated wrapper as byte-identical to
the older no-probe experiments. Compare repeated matched runs.

## Pilot traffic schedules

`scenario='steady'` is one continuous iperf trial at `requested_bps` for `duration`
seconds (defaults 3 Mbit/s and 20 s). `ramp` provides increasing/decreasing pilot
segments; `bursty` provides seeded alternating low/high pilot segments. Record
`seed` and the full schedule. Each segment currently starts a new iperf endpoint,
so startup gaps exist and actual call boundaries are recorded. These are segmented
pilots, not seamless changing-rate flows. Do not produce future-event labels over
unvalidated gaps or call C4 complete based on schedule generation alone.

## Persistent-flow traffic (continuous-v4; guest calibration pending)

`run_experiment(..., engine='continuous')` uses one custom UDP sender and receiver
for the whole schedule. The `iperf` engine remains the default reference. First
compare a steady 3 Mbit/s continuous trial against a same-route iperf control;
do not pool the two engines or claim the new source is calibrated in advance.

Continuous scenarios are steady, a seeded linear up/down ramp, and seeded abrupt
low/high bursts. Requested rate is the base scale for variable schedules; the
full plan and its weighted average are recorded. No iperf process starts between
segments. Abrupt bursts may be intrinsically difficult to predict before onset;
do not add future schedule values to model features or use planned load as a
congestion label.

Pacing uses a 5 ms requested tick and caps each catch-up batch at 32 datagrams.
Discarded sending budget and skipped ticks are recorded, separately from packet
loss. If more than 5% of the planned budget is discarded, the source screen fails;
per-window artifacts still need review even below that whole-run threshold.
Achieved rates and sender/receiver counts remain authoritative.

UDP payload stays 1200 bytes including the measurement header. Packet IDs,
continuous sequence numbers and shared-guest monotonic send timestamps support
unique-packet accounting. Default socket buffers are retained and their actual
sizes recorded. Port 5202 separates the custom source from iperf's 5201. Native
endpoint JSON and 250 ms source/receiver reports are preserved. Canonical summary
JSON is a derived compatibility view, explicitly marked with its engine and loss
definition. End-to-end goodput is normalized through sender end or the final
received packet, whichever is later, using the shared Mininet guest clock.

Receiver shutdown follows a recorded 0.5 s drain period. Report process and traffic
timing separately. Queue counters also include RTT/control traffic. A mixed ramp
is not classified as a constant low-load run based on its average; it needs
per-window event labeling. No training labels, model or rerouting are implemented
by this source update. Repeat reference baselines using the new engine before any
policy evaluation, and assess controller/model benefits with the same generator.

## Local verification and primary evidence

```bash
python3 -m unittest -v test_experiment
python3 summarize_calibration.py --output results/derived/primary-calibration-20261114
```

The summary reproduces the verified six-run CSV, descriptive statistics and raw
source hashes. It keeps sender-based loss distinct from receiver sequence-based
loss. Existing outputs are not overwritten. Unit tests cover route mismatch,
rollback after failure, actual-dt rate calculation, counter resets, failed-query
gaps and deterministic schedules; they do not substitute for a guest experiment.
