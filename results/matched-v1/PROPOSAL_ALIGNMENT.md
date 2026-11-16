# Alignment with the proposal and previous reports

Checked the actual PR1, PR2 and PR3 PDFs plus the submitted presentation. The central research question and controlled four-policy design remain aligned. The project has not changed topic. Some implementation and validation scope is narrower than the early descriptions, so the final paper must state those changes explicitly.

## What was delivered

- Controlled Mininet/OVS/OpenFlow diamond and alternate path
- Steady, ramp and bursty matched trials under common frozen control/action
- Causal future-onset labels and whole-run train/validation/fresh-test partitions
- Decision Tree selection without test tuning; runtime JSON model verified
- Four policies, three seeds per scenario, 36 verified trials
- Goodput, UDP loss, received-probe mean/median/p95 RTT, queue/drop, actions, inference/control costs
- False/late warnings, unnecessary low-load action and admission-denial outcomes retained

## Changes and unclosed promises

| Topic | Actual scope | Reporting requirement |
| --- | --- | --- |
| Classifier breadth | Later presentation and PR3 focus on Decision Tree; no LR/RF models were trained or compared | Document the narrowing; do not claim the earlier multi-classifier objective was completed |
| Polling design | Nine native steady-load interval trials used an older collector; current collector runs at 250 ms with actual-time windows and disclosed resolution limits | Preserve the one-second duration in seconds; current full-collector burst-resolution/interval ablation is not established |
| Control loop scope | A shared cooldown/action guard exists, but each trial permits one alternate switch followed by cleanup | Repeated recovery, switch-back and oscillation behavior are not evaluated |
| Delay and installation | Mean/median/p95 received-probe RTT is now fully derived; CLI command/readback time is measured | Do not claim one-way delay, packet-level activation or disruption measurements |
| Repetition under variability | Three different matched seeds per policy/scenario; reactive burst loss varies 0.606%–15.030%; no expanded repetitions completed | Explain admission-denial mechanisms and qualify generalization; additional repetitions remain needed for a stronger stability claim |
| Calibration/profile | Recorded dual calibration uses source queue 250, bottleneck queues 50 and cburst 16 KiB, identically across all final policies | Disclose calibrated replacements rather than implying the initial unstable configuration was used unchanged |
| Runtime location | OS-Ken establishes baseline rules; a shared external Python decision/action loop drives OpenFlow CLI updates | Describe this control-plane prototype accurately; no native in-controller ML module or production deployment is claimed |

## Interpretation

A negative result for added ML value is compatible with PR2/PR3: the objective was to test whether prediction justifies the added ML step, not to guarantee it wins.

92/100 is the fixed, narrowed execution checklist. It is not a statement that every original proposal sentence was implemented.

PR4 already states one switch per trial and that packet interruption was not measured. It should not claim completion of every original objective or an optimal polling interval. The final-paper plan must either close the broader validation items or explicitly justify its narrower scope. Original submitted reports are preserved unchanged.

Mean received-probe RTT was an easy remaining metric to complete offline: all 36 logs have now been parsed, with counts and medians cross-checked against the existing review. See LATENCY_SUPPLEMENT.md and latency-supplement.csv. No new traffic, fitting, threshold changes or raw edits were required.
