# Current results — November 16, 2026

The completed 36-trial benchmark is in [matched-v1/RESULTS.md](matched-v1/RESULTS.md). Read [interpretation](matched-v1/INTERPRETATION.md), [proposal alignment](matched-v1/PROPOSAL_ALIGNMENT.md) and [reproduction instructions](../docs/REPRODUCIBILITY.md). The complete checkpoint is in [evidence/raw](../evidence/raw/). The diagnostic results below are historical and remain unchanged.

---

# Experiment log

Measurements collected October 29–November 2, 2026. Source files and raw outputs are preserved unchanged in `archive/`.

All paths below are relative to [the original project snapshot](archive/results/). Preserve failed runs alongside successful ones.

| Record | Observation | Interpretation |
| --- | --- | --- |
| Initial setup / S02 | Four-host diamond passed 12/12 pings; primary rules installed on all four switches | Connectivity verified; performance and alternate-path traffic still pending |
| P01-primary-3M | UDP requested 3 Mbit/s for 20 s; sender ran 25.22 s; receiver about 455 Kbit/s with 76% loss; bottleneck queue drop delta 202 | Invalid as a normal-load reference; severe timing/traffic anomalies |
| D01-loopback-20261101-232429 | Receiver 2.87 Mbit/s; 70/3107 lost (2.3%); later cumulative UDP receive-buffer errors 70 | Host-side loopback can also lose packets; cumulative counter lacks a paired before reading |
| D02-buffers-20261101-233405 | Default buffers passed 3 Mbit/s, 10 s, zero loss. Larger-buffer trial timed out; client/server exit 124 | Failed trial cannot support a buffer-size comparison |
| D03-timing-20261101-234655 | Thirty one-second waits took 30.112 s; longest 1.011 s | Timing clean in this idle window only |
| D04-loopback-repeat-20261101-234916 | First repetition timed out; next two passed 3 Mbit/s, 10 s, zero loss | Intermittent failure persists with default buffers |
| D05-clockcheck-20261101-235412 | TSC active; kernel reported long watchdog readout intervals | Supports investigating timing; does not prove TSC is the cause |
| D06-kvm-clock-20261101-235818/traffic-20261102-000046 | Three 10 s loopback trials at 3 Mbit/s; 0/3125 loss each; exit statuses 0; UDP error deltas 0; clock restored to TSC | Successful short loopback series under temporary kvm-clock; no lasting fix demonstrated |
| S02-primary-20261102-000443 | Network recovered after terminal closure; again 12/12 pings | Connectivity restored, logs retained |
| P02-primary-3M-20261102-002024 | Requested 3 Mbit/s, 20 s; client wait timed out after 40 s; empty client/server JSON; h1 queue drops +2592; bottleneck drops +184; vmstat gaps of 7 and 24 s | Invalid performance trial under kvm-clock; source-side impairment and timing remain unresolved |

## Interpretation rules

- Empty final JSON is missing evidence, not zero throughput or zero loss.
- P02's h1 UDP send-buffer error delta 2592 and qdisc drop delta 2592 may describe the same failed transmissions. Do not add them.
- Do not add parent HTB and child netem counters as independent packet losses.
- P01 probe timing did not establish a fully aligned loaded interval, so its entire average RTT is not a clean under-load metric.
- Guest CPU idle percentages do not rule out host scheduling delays.
- Hypervisor/scheduling and traffic-pacing effects remain hypotheses. A temporary clock change was insufficient.
- P01 and P02 are diagnostic evidence and excluded from model training and QoS-effect estimates.

## Next experiment

Three repeatable low-load and three overload runs with complete outputs and no unexplained timing gaps. Define acceptance criteria before running them. Then validate alternate-path forwarding and implement the sampling collector. Retain failed runs and their exclusion reasons.


## Files and integrity

`archive/` contains the original topology, controller, diagnostic scripts and raw outputs. Its directory structure preserves the historical protocols and source hash manifests. Those scripts contain the original machine paths and clock assumptions. Use the current root-level scripts and setup instructions for new runs.

Verify all 179 original files from the repository root:

```bash
sha256sum -c results/SHA256SUMS
```

The current portable runner is derived from the archived P02 protocol. It records timeouts and exit statuses, attempts a graceful endpoint shutdown, and records the active clock without changing it. No new network performance result is associated with this revision.

## Record a new run

Use one directory per attempt under `results/runs/`. The runner creates a unique timestamped directory and metadata automatically. Record software versions and VM resources alongside it, then add an `assessment.md` explaining the purpose, validity decision, observed results and any exclusions. Keep raw outputs unchanged. Record a seed for randomized scenarios and all schedule parameters when traffic generation is extended.

Commit code before running it. The runner saves its code commit, working-tree status and copies/hashes of the experiment scripts. New runs are ignored until reviewed. To publish one:

```bash
git add -f results/runs/<run-id>
git commit -m "Record <run-id> and validity assessment"
git push origin main
```

Keep incomplete JSON as missing output. Record failed attempts as well as successful ones. Put derived plots and summaries in separate files.
