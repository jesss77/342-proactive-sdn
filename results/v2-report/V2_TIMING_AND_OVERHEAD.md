# Version 2 Switch Timing, Useful Warning, and Control Overhead

## Applied Route-Switch Timing Summary

- Total applied switches across 72 trials: **29**
- Observation-to-action age (`started − observed_at`): mean **0.164 s** [0.084, 0.221]
- OpenFlow modify + readback latency (`command_and_readback_elapsed_s`): mean **0.170 s** [0.080, 0.280]
- Switches completing with **zero** `s2-eth2` packet drops: **20/29**

| Policy | Switches | Zero-Drop Switches | Mean Trigger Time (s) | Mean Demand at Switch (Mbit/s) | Mean Switch+Readback (s) | Collector CPU (%) | Policy Thread CPU (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | 0 | 0/0 | n/a | n/a | n/a | 8.79 | 2.81 |
| reactive | 6 | 3/6 | 16.59 | 10.81 | 0.174 | 8.85 | 3.44 |
| early_warning | 11 | 6/11 | 10.87 | 8.34 | 0.171 | 9.05 | 3.19 |
| ml | 12 | 11/12 | 7.41 | 5.39 | 0.167 | 8.66 | 3.03 |

## ML Decision-Tree Inference CPU Latency (15-node CART, across 18 ML trials)
- Median per-call CPU time: **53.8 µs** [range 33.1–65.9 µs]
- p95 per-call CPU time: **138.9 µs** [max observed 872.0 µs]
