# CMPS342 — Fixed-path controls before automatic policy trials

The accepted idle routing smoke does not establish alternate service capacity.
This wrapper keeps the primary OS-Ken controller and uses the same owned h1/h2
IPv4 action to hold the selected pair on the requested path for one continuous
steady UDP trial. It sends no automatic reactive or ML-triggered reroutes.

Both forward paths receive profile `dual-forward-cburst16k-source250-v1`: cburst
16,384 bytes on six forward egresses, rate/ceil and delay unchanged, source queue
250 packets, all other queues 50. Both paths use this same profile in every
control, preparing a common configuration for later policy comparisons. This
is a new recorded profile; do not silently pool it with single-path calibration.
Every setting is checked before/after application and after restoration.

Four inter-switch qdiscs are observed by one tc JSON dump per 250 ms cycle,
collector schema 6 / coverage `all`. Default older route-only collection stays
schema 5. Stored query timing and process overhead remain explicit. No OVS
statistics-refresh setting or Windows/VM security setting changes.

The manual alternate action is admitted while idle, using a conservative small
smoke budget. The subsequent requested UDP rate is deliberately offered for
capacity characterization and may exceed that idle admission budget. It is not
a production admission decision, automatic-policy result or a certified 20 Mbit/s
service rate. Inspect achieved source/receiver delivery, pacing, all limiting
queue drops, UDP errors and timing before setting a later policy budget.

The continuous recorder has an explicit owned-hostpair route-verification hook,
with metadata identifying this mode. Its normal passive route verification
remains the default; no global bypass or baseline-rule rewrite is used.
The wrapper records all four queue streams, actual selected-pair readbacks,
active/inactive link counters, loaded/idle RTT and source snapshots. It stops
traffic/monitoring, removes only its owned rules, and restores the six classes
and original source queue. Failures are retained, not discarded.

After installing, at idle primary `mininet>`:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_path_control.py').read(), '/home/jess/342-proactive-sdn/run_path_control.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_path_control.py', 'route': 'alternate', 'requested_bps': 12000000, 'duration': 20})
```

The wrapper saves its full inspection under `results/derived` and prints it.
Do not proceed to repeated higher-rate controls after nonempty screening or
restoration failures. A clean control is evidence for that tested offered rate,
not a guarantee of all future burst peaks. Live policy integration and matched
policy evaluation remain subsequent implementation work.
