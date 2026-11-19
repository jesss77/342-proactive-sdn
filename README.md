# Proactive Congestion Management in SDN

CMPS342 research project — Youssef Shawwa and Jessy Karamaoun. Updated November 19, 2026.

We test whether a lightweight learned congestion warning adds value when routing, observations and admission constraints are shared. **The registered experiment is complete: 36 matched trials, four policies, three traffic scenarios and three seeds. Earlier triggering helped against fixed/reactive routing; an added benefit from the learned tree over the simple trend rule was not established.**

## Obtained results

Each entry is a whole-run mean over three matched seeds. These are descriptive results from one VM, one selected host pair and at most one successful alternate-path switch per trial.

| Policy | Ramp goodput Mbit/s | Ramp UDP loss % | Bursty goodput Mbit/s | Bursty UDP loss % |
| --- | ---: | ---: | ---: | ---: |
| Fixed | 7.510 | 9.741 | 6.121 | 18.682 |
| Reactive | 8.319 | 0.002 | 7.137 | 5.591 |
| Simple early warning | 8.329 | 0.000 | 7.537 | 0.013 |
| Frozen Decision Tree | 8.329 | 0.000 | 7.521 | 0.195 |

All low-load 3 Mbit/s trials had zero UDP loss. ML unnecessarily switched one of three low-load trials. Reactive burst loss varied from 0.606% to 15.030%, including admission denials; those outcomes remain in the comparison.

The separate, untouched six-run prediction test gave positive-class F1 of 0.957 for ramps and 0.811 for bursts. Useful advance warnings reached 2/3 ramp events and 9/25 scorable burst events. Row F1 alone does not establish useful prediction or a networking benefit.

- [Full networking results and per-trial CSV](results/matched-v1/RESULTS.md)
- [Interpretation and adverse outcomes](results/matched-v1/INTERPRETATION.md)
- [Prediction reference](results/matched-v1/PREDICTION_REFERENCE.md)
- [Mean RTT supplement](results/matched-v1/LATENCY_SUPPLEMENT.md)
- [Additional source, queue and cost metrics](results/matched-v1/ADDITIONAL_METRICS.md)
- [Figures](results/matched-v1/figures/README.md)
- [Proposal/report alignment and remaining validation](results/matched-v1/PROPOSAL_ALIGNMENT.md)

## Implemented system

Mininet and Open vSwitch form a four-switch diamond. OS-Ken installs OpenFlow 1.3 baseline rules. A shared external Python loop observes both paths and applies the selected trigger: fixed, reactive, past-trend early warning or frozen Decision Tree. The action moves only the h1/h2 IPv4 pair, including RTT probes. The h3/h4 pair retains its baseline path.

```text
                100 Mbit/s       10 Mbit/s
             +------------ s2 ------------+
             |                            |
h1, h3 ---- s1                            s4 ---- h2, h4
             |                            |
             +------------ s3 ------------+
                 20 Mbit/s       20 Mbit/s
```

Host links are configured at 100 Mbit/s; link directions have 1 ms delay. Final trials use the recorded dual profile: source queue 250 packets, bottleneck queues 50 packets, burst 15,360 bytes and cburst 16,384 bytes. Each wrapper checks and restores the original settings. Configured rates are not measured payload-service guarantees.

The continuous UDP source uses 1,200-byte payloads and saved pacing diagnostics. A batch collector observes all four forward inter-switch qdiscs at a requested 250 ms interval. Features use past/present observations and actual elapsed time. The target is a new 85%-utilization onset sustained for one second within a two-second horizon; it is not packet-loss ground truth.

Ten fixed-primary traces trained the tree; six validation traces selected it; six fresh traces evaluated it without retuning. The tree has depth 3, minimum leaf size 25, 15 nodes and threshold 0.65. Model SHA-256: `63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595`.

## Reproduce or inspect

- [Setup and offline checks](SETUP.md)
- [Reproduce calibration, development, matched/prediction reports, optional training replay and plots](docs/REPRODUCIBILITY.md)
- [Repeat the live lab in a separate clean workspace](docs/LIVE_REPLAY.md)
- [Exact preserved raw checkpoint and checksum](evidence/raw/)
- [Source publication manifest](evidence/publication-manifest.json)
- [Versioned acquisition protocols](docs/PROTOCOL_INDEX.md)

All 36 final networking trials passed independent source/model/raw-hash, endpoint, collector and restoration checks. Original raw runtime `pending_review` statuses are preserved; derived assessments are separate. The complete checkpoint also retains failed and superseded diagnostics. Source pacing discard reached 0.342% against the inherited 5% screen; achieved rates are reported separately from network loss.

## Limits and remaining work

Only the Decision Tree was trained; an earlier broader classifier objective was narrowed. The polling sweep used steady traffic and an older collector. More high-variance repetitions and current-collector burst/interval validation remain open. Repeated recovery and oscillation are untested. Received-probe RTT is not one-way delay; command/readback elapsed time is not packet-level activation or disruption. No production-controller or general abrupt-burst prediction claim is made.

PR4 was submitted, as confirmed by the authors on November 17. The final IEEE paper and final submission audit remain open. The submitted report PDF is kept separate from this reproducibility publication.
