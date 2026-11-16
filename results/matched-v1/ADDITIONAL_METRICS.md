# Additional matched metrics

Each bracket gives the observed three-seed range, not a confidence interval. CPU components use recorded windows and are not total system cost. Inference is included in policy CPU. Loaded probe loss covers the complete loaded-probe window; traffic-only probe loss remains uncomputed.

## Source and probe observations

| Scenario | Policy | Achieved sender Mbit/s mean [range] | Loaded probe loss % mean [range] | Pacing discard % mean [range] |
| --- | --- | --- | --- | --- |
| steady | fixed | 3.000 [3.000, 3.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| steady | reactive | 3.000 [3.000, 3.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| steady | early_warning | 3.000 [3.000, 3.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| steady | ml | 2.999 [2.999, 3.000] | 0.000 [0.000, 0.000] | 0.012 [0.000, 0.036] |
| ramp | fixed | 8.326 [8.158, 8.573] | 5.207 [3.822, 6.688] | 0.046 [0.000, 0.137] |
| ramp | reactive | 8.321 [8.159, 8.585] | 0.000 [0.000, 0.000] | 0.114 [0.000, 0.342] |
| ramp | early_warning | 8.330 [8.159, 8.585] | 0.000 [0.000, 0.000] | 0.002 [0.000, 0.006] |
| ramp | ml | 8.330 [8.159, 8.585] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| bursty | fixed | 7.539 [7.068, 8.190] | 7.006 [4.777, 8.599] | 0.003 [0.000, 0.009] |
| bursty | reactive | 7.536 [7.060, 8.191] | 1.805 [0.318, 4.140] | 0.040 [0.000, 0.119] |
| bursty | early_warning | 7.538 [7.068, 8.191] | 0.106 [0.000, 0.318] | 0.009 [0.000, 0.027] |
| bursty | ml | 7.538 [7.064, 8.191] | 0.212 [0.000, 0.637] | 0.021 [0.000, 0.062] |

## Computation costs

| Scenario | Policy | Collector CPU % one core mean [range] | Policy CPU % one core mean [range] | ML within-run p95 wall µs mean [range] |
| --- | --- | --- | --- | --- |
| steady | fixed | 4.319 [2.991, 6.651] | 1.212 [0.795, 2.019] | n/a |
| steady | reactive | 4.097 [2.854, 6.300] | 1.216 [0.837, 1.951] | n/a |
| steady | early_warning | 4.022 [2.627, 5.920] | 1.172 [0.822, 1.848] | n/a |
| steady | ml | 4.286 [2.797, 7.111] | 1.175 [0.765, 1.937] | 108.822 [27.669, 258.432] |
| ramp | fixed | 3.583 [2.796, 4.619] | 0.852 [0.796, 0.935] | n/a |
| ramp | reactive | 3.923 [3.651, 4.445] | 0.919 [0.761, 1.086] | n/a |
| ramp | early_warning | 3.425 [3.248, 3.681] | 0.857 [0.814, 0.909] | n/a |
| ramp | ml | 3.499 [3.201, 3.739] | 0.834 [0.755, 0.969] | 30.297 [24.567, 39.622] |
| bursty | fixed | 3.588 [3.474, 3.803] | 0.854 [0.795, 0.902] | n/a |
| bursty | reactive | 3.069 [2.965, 3.260] | 0.952 [0.877, 1.007] | n/a |
| bursty | early_warning | 3.420 [2.535, 4.019] | 0.825 [0.787, 0.861] | n/a |
| bursty | ml | 2.781 [2.447, 3.235] | 0.839 [0.802, 0.877] | 20.380 [19.073, 22.612] |

## Queue localization

Sampled maxima are not packet-level maxima. Drop deltas include probes/control packets; they are separate from UDP sequence loss.

| Scenario | Policy | Primary sampled max queue packets mean [range] | Primary bottleneck drop total | Alternate drop total |
| --- | --- | --- | --- | --- |
| steady | fixed | 5.667 [3.000, 9.000] | 0 | 0 |
| steady | reactive | 6.333 [3.000, 13.000] | 0 | 0 |
| steady | early_warning | 3.000 [3.000, 3.000] | 0 | 0 |
| steady | ml | 3.333 [3.000, 4.000] | 0 | 0 |
| ramp | fixed | 50.000 [50.000, 50.000] | 15319 | 0 |
| ramp | reactive | 11.333 [6.000, 21.000] | 0 | 3 |
| ramp | early_warning | 4.333 [4.000, 5.000] | 0 | 0 |
| ramp | ml | 5.667 [4.000, 7.000] | 0 | 0 |
| bursty | fixed | 50.000 [50.000, 50.000] | 26580 | 0 |
| bursty | reactive | 49.333 [48.000, 50.000] | 7482 | 0 |
| bursty | early_warning | 32.000 [21.000, 39.000] | 18 | 1 |
| bursty | ml | 17.000 [2.000, 47.000] | 301 | 0 |

## Individual applied actions

Source elapsed is measured from each run’s own source start. It is not event lead time or packet interruption. No-action runs are retained in trials.csv.

| Scenario | Policy | Seed | Switch source elapsed s | Command/readback ms | Denials before applied switch |
| --- | --- | --- | --- | --- | --- |
| steady | ml | 41 | 30.088 | 210.673 | 0 |
| ramp | reactive | 41 | 14.758 | 78.968 | 0 |
| ramp | early_warning | 41 | 11.077 | 75.118 | 0 |
| ramp | ml | 41 | 11.278 | 124.596 | 0 |
| bursty | early_warning | 41 | 3.364 | 75.955 | 0 |
| bursty | ml | 41 | 2.375 | 149.189 | 0 |
| bursty | reactive | 41 | 5.534 | 150.277 | 4 |
| ramp | ml | 42 | 11.805 | 113.015 | 0 |
| ramp | early_warning | 42 | 12.115 | 148.030 | 0 |
| ramp | reactive | 42 | 15.387 | 87.838 | 0 |
| bursty | reactive | 42 | 47.611 | 61.646 | 40 |
| bursty | ml | 42 | 2.064 | 52.260 | 0 |
| bursty | early_warning | 42 | 4.144 | 60.343 | 0 |
| bursty | early_warning | 43 | 2.374 | 76.153 | 0 |
| bursty | ml | 43 | 3.633 | 56.949 | 0 |
| bursty | reactive | 43 | 3.671 | 57.080 | 0 |
| ramp | reactive | 43 | 13.695 | 92.373 | 0 |
| ramp | ml | 43 | 10.877 | 44.234 | 0 |
| ramp | early_warning | 43 | 10.298 | 116.202 | 0 |
