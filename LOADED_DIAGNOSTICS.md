# Bounded loaded component diagnostic

This is a prospective diagnostic after the November-20 loaded recovery failed.
It does not reopen either failed batch, change the frozen study or collect a
replacement policy-benefit matrix. The full failed checkpoint and diagnosis are
preserved separately. A passing idle check did not establish loaded stability.

## Registered ladder

| Step | Added component | Held constant |
| --- | --- | --- |
| 1 — source_receiver | Source/receiver, probes, resource log; no continuous collector or decision loop | Primary path, dual profile, default sockets, 1,200-byte UDP, bursty seed 44, scale 11.5 Mbit/s, 60 s |
| 2 — collector | Frozen all-four-queue collector at 250 ms | Same source, path, profile, probes and resource log as step 1 |
| 3 — fixed_loop | Frozen fixed-policy observation/decision loop | Original full policy runner; no rerouting request |
| 4 — reactive_loop | Frozen reactive trigger and shared action | Same full runner; at most one admitted alternate switch |

Step 1 still has startup/final queue and UDP snapshots, passive rule checks,
one-second vmstat, source/receiver samples and RTT probes. “No collector” means
no continuous `tc` polling, not an uninstrumented or loopback test. Missing
collector metrics are marked inapplicable, never fabricated as zero failures.
Step 2 uses the same component wrapper, adding only continuous polling.
Steps 3–4 reuse the unchanged policy runner; those comparisons include its
thread/queue/tailing orchestration, not only the trigger's arithmetic cost.

The fixed order, one attempt per case and concurrent host workload cannot
establish a statistical causal effect. This ladder localizes an observed
failure to the smallest tested configuration. A pass does not prove the earlier
fault is fixed or justify pooling these rows with the original matched study.
Seed 44 is already observed; these are diagnostics, not fresh prediction tests.

## Conditions and limits

Jess reported: laptop plugged in, other work must remain running. Record that
condition honestly. Do not claim an otherwise-idle host or attribute the prior
failure to a specific app. Keep the same host work as consistent as practical
across these four short cases; report any change before the next one.

The guest remains one vCPU, six GiB, `tsc`, the original dual profile and default
socket buffers. The runner records kernel/Python/OVS/tc/vmstat versions, guest
load/memory, actual source behavior, raw endpoint/queue counters and restoration.
No new host process sampler is introduced inside the timed window.

The first call includes the existing 60-second idle readiness check; subsequent
calls retain the original per-trial idle guard. Readiness failure starts no
traffic. The first loaded source lasts 60 seconds; initial setup/readiness and
drain mean the command takes more than two minutes overall.

Run one case per explicit call and inspect its evidence before adding a
component. Any execution, endpoint, source, collector, identity or restoration
failure stops this registration. All attempts and new raw folder references
are saved. A failed or interrupted diagnostic cannot be reset, resumed or
silently replaced. Expected primary bottleneck loss is an outcome; it is not
by itself a rejection criterion. No ML-benefit or action-success requirement
is added. Strict original quality thresholds remain in force wherever the
instrument is present. No automatic extra repetitions or model fitting.

## Install and first call

In T3, mount the existing `SDNUpdate` share and run
`loaded-diagnostics-v1/install_loaded_diagnostics.py` with the guest repository
path. The installer verifies all 72 current frozen files and adds only four
new files. It starts no traffic and edits no previous raw result.

In the existing T2 Mininet CLI:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_loaded_diagnostics.py').read(), '/home/jess/342-proactive-sdn/run_loaded_diagnostics.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_loaded_diagnostics.py', 'case': 'source_receiver'})
```

Send the result before the next case. Later case names, in order, are
`collector`, `fixed_loop`, `reactive_loop`; the registry enforces this order.
Do not run the old supplement or recovery commands.

## Interpretation and next decision

- Failure in step 1: investigate endpoints/source/shaped path and resources
  without blaming the absent collector or policy loop.
- First failure in step 2: continuous monitoring is present when the failure
  appears; compare timing/resources with step 1. One ordered pair alone does
  not prove it caused the failure.
- First failure in step 3: investigate full-loop orchestration/tailing and
  runtime contention before any trigger comparison.
- First failure in step 4: inspect decision freshness, baseline verification,
  admission/denials and action command timing. Keep actual readback distinct
  from first-packet forwarding activation.
- All pass: the earlier failure was not reproduced in this short window.
  Do not call it a fix; review evidence and time budget before any new protocol.

Any actual fix must be a separately versioned variant with new calibration.
Do not silently increase buffers/vCPUs, change clock/poll interval, relax
collector screens, retune thresholds or replace the model. The existing
36-trial study and six alternate controls remain the main accepted evidence.
If loaded stability cannot be established promptly, retain the supplemental
failure as a limitation and finish the paper from the accepted evidence.
