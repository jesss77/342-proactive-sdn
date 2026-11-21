# CMPS342 — Shared routing action

This is a control-plane prototype and idle connectivity smoke test. It is not a
completed policy experiment, measured QoS improvement or admission-capacity
calibration. The original topology and OS-Ken controller are unchanged.

## Action and scope

The selected traffic is the IPv4 h1/h2 host pair in both directions, including
UDP and ICMP RTT probes. h3/h4 stays on the primary baseline. Static ARP traffic
keeps the original MAC rules. Both transit paths already have destination rules.

The action adds one priority-200 IPv4 rule at s1 and one at s4, using reserved
cookie `0x3420000000000001`, selecting output port 4. Original priority-100 MAC
rules are verified on all four switches before and after. Cleanup deletes only
that exact cookie on the two edge switches. Unknown rules, a prior owner or a
different controller baseline cause refusal before mutation.

Every command, result, readback and decision is logged. OpenFlow 1.3 is explicit.
OVS uses barriers after ordinary flow-mod commands by default; no OpenFlow 1.4
bundles are used. The two switches are updated sequentially, not atomically.
Readback verifies match and output, and the smoke test additionally requires
packet increments in the selected rules and the expected path. CLI execution
plus verification elapsed time includes process startup and readbacks; it is
not a direct measure of hardware rule activation or end-to-end disruption.

After the five alternate probes, rule statistics are polled on both edges at
100 ms spacing for up to three seconds, plus any bounded in-flight command
completion. Both rules must still match the selected pair and reach five packets.
Every read and count is logged; a missing/wrong rule fails immediately and stale
counts that never catch up still fail with cleanup. No extra pings or OVS
revalidator changes are made. The observation wait is reported separately from
action/readback time. This corrects the first guest test, whose path counters
proved five alternate packets while OpenFlow reported only one after 0.467 s.

OVS revalidation/statistics propagation is asynchronous; the database manual
describes the revalidator interval. It does not establish an exact refresh time
for this VM: [OVS configuration reference](https://www.openvswitch.org/support/dist-docs/ovs-vswitchd.conf.db.5.html).

Reference: [OVS ovs-ofctl manual](https://www.openvswitch.org/support/dist-docs/ovs-ofctl.8.html).

## Guards and cleanup

Admission requires finite nonnegative demand/background rates, live alternate
links, explicitly identified budget evidence, observation age at most two
seconds, and demand plus background at most 80% of the supplied admission budget.
A five-second cooldown and one successful action per trial are the initial
constraints. A trigger is marked fired only after an applied action. Production
admission must obtain route-specific current measurements and a justified
service budget; nominal 20 Mbit/s is not established spare payload capacity.

The idle smoke reads source/alternate counters for one second and refuses more
than 100 kbit/s background/source activity. It uses a conservative 3 Mbit/s
smoke-only admission budget for a few pings, not a certificate for later ramp
rerouting. It does not change queue settings or run a throughput test.

A partial failed action attempts removal on both edges and verifies primary
restoration. Cleanup bypasses policy action limits and cooldown. Cleanup failure
is a failed/unknown state and must be inspected before any next experiment. The
smoke's finally block attempts cleanup after exceptions. Abrupt process/VM death
cannot run finally: a later attempt refuses a leftover reserved cookie instead
of silently taking it over. Preserve logs before explicit recovery.

## Non-ML decisions

`Trigger` supplies pure fixed/reactive/early-warning logic, not a live experiment
loop. Fixed never switches. Reactive requires observed utilization at least 85%
for one second; late/invalid/nonmonotonic observations reset that timer. Early
warning requires utilization at least 50%, positive measured two-second trend,
and a linear two-second forecast reaching 85%. These are provisional parameters,
not validation-selected thresholds. Both policies must call the same admission
and action path. A Decision Tree trigger and live matched-policy integration
remain to implement.

## Idle guest acceptance

Keep the primary OS-Ken controller and shaped Mininet session open, with no trial
running. After installation, at `mininet>`:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_routing_smoke.py').read(), '/home/jess/342-proactive-sdn/run_routing_smoke.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_routing_smoke.py'})
```

It verifies primary h1/h2 connectivity, alternate h1/h2 connectivity, unchanged
primary h3/h4 forwarding, then restored primary forwarding for both pairs. All
five probes must receive five replies and show the expected path increments.
Expected final output is `Routing smoke: completed`, restoration verified true,
and a saved evidence folder. Until this passes in the VM, action is locally
tested only. Existing fixed experiment preflight rejects higher-priority routing
overlays, preventing a mixed route from being mislabeled as a passive baseline.
