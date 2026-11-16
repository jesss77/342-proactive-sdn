# Matched networking evaluation

Single selected pair; one successful switch per trial; synthetic scenarios and one VM. Received-probe RTT is separate from loaded-probe loss; traffic-window loss remains uncomputed. Inference CPU is already included in policy CPU. Command/readback time is not packet interruption.

Descriptive means, observed ranges and sample standard deviations over three seeds. Rows/windows are not independent trials. No confidence or superiority claim from these summaries alone.

| Scenario | Policy | Goodput mean [range] Mbit/s | UDP loss mean [range] % | Reply RTT p95 mean [range] ms | Actions across 3 runs |
| --- | --- | --- | --- | --- | --- |
| steady | fixed | 2.999 [2.999, 3.000] | 0.000 [0.000, 0.000] | 26.767 [17.200, 44.900] | 0 |
| steady | reactive | 2.999 [2.999, 3.000] | 0.000 [0.000, 0.000] | 15.933 [14.300, 17.300] | 0 |
| steady | early_warning | 3.000 [3.000, 3.000] | 0.000 [0.000, 0.000] | 17.300 [16.900, 17.800] | 0 |
| steady | ml | 2.999 [2.998, 3.000] | 0.000 [0.000, 0.000] | 17.267 [15.800, 19.100] | 1 |
| ramp | fixed | 7.510 [7.493, 7.523] | 9.741 [7.762, 12.317] | 60.000 [58.500, 62.700] | 0 |
| ramp | reactive | 8.319 [8.156, 8.585] | 0.002 [0.000, 0.006] | 19.333 [18.800, 20.300] | 3 |
| ramp | early_warning | 8.329 [8.156, 8.584] | 0.000 [0.000, 0.000] | 18.100 [17.000, 20.000] | 3 |
| ramp | ml | 8.329 [8.158, 8.583] | 0.000 [0.000, 0.000] | 18.267 [17.400, 19.400] | 3 |
| bursty | fixed | 6.121 [5.812, 6.514] | 18.682 [17.702, 20.407] | 61.500 [61.100, 61.800] | 0 |
| bursty | reactive | 7.137 [5.998, 8.141] | 5.591 [0.606, 15.030] | 33.033 [18.200, 61.400] | 3 |
| bursty | early_warning | 7.537 [7.067, 8.190] | 0.013 [0.007, 0.016] | 18.033 [16.200, 19.800] | 3 |
| bursty | ml | 7.521 [7.064, 8.143] | 0.195 [0.000, 0.584] | 16.233 [13.800, 17.800] | 3 |
