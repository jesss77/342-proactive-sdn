# Mean RTT supplement

Derived from original timestamped ping replies restricted to each actual source window. Counts and nearest-observation quantiles match the existing reviewed statistics in every trial. No censored <1 ms replies occurred. Means and p95 values below are averages of within-run statistics, not pooled packet statistics. RTT is not one-way delay, and missing replies are not assigned invented delays.

| Scenario | Policy | Mean reply RTT ms across three runs | Mean within-run reply RTT p95 ms |
| --- | --- | --- | --- |
| steady | fixed | 12.836 | 26.767 |
| steady | reactive | 11.213 | 15.933 |
| steady | early_warning | 11.477 | 17.300 |
| steady | ml | 11.429 | 17.267 |
| ramp | fixed | 28.080 | 60.000 |
| ramp | reactive | 13.081 | 19.333 |
| ramp | early_warning | 12.183 | 18.100 |
| ramp | ml | 12.363 | 18.267 |
| bursty | fixed | 31.056 | 61.500 |
| bursty | reactive | 16.512 | 33.033 |
| bursty | early_warning | 12.174 | 18.033 |
| bursty | ml | 10.909 | 16.233 |
