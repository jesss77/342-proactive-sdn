# Generated paper tables

Values are rounded only for display. Exact cells and source selectors are in table-provenance.json.

## Table 1: Common trigger and action settings; V2 adds measured alternate-path background load.

| Setting | Value |

| --- | --- |

| Foreground | 1,200-byte UDP payload; 60 s; primary initially |

| Queues / delay | Source 250 packets; switch 50 packets; 1 ms/link |

| Sampling / history | 250 ms; at least 2 s contiguous history |

| Event / forecast | Utilization >= 0.85 for 1 s; new onset within 2 s |

| Label future support | 3.75 s (horizon + confirmation + read guard) |

| Reactive trigger | Observed high utilization sustained for 1 s |

| Trend trigger | u >= 0.5; slope > 0; u + 2 slope >= 0.85 |

| Frozen tree | Depth 3; minimum leaf 25; 15 nodes; score >= 0.65 |

| Freshness checks | Live pre-action 0.5 s; actor entry 2 s |

| Admission | Current demand + alternate load <= 12.72 Mbit/s |

| Action limit | One successful switch; primary restored at cleanup |

## Table 2: Whole-run partitions and mutually exclusive row exclusions. Invalid-sample exclusions are zero in all accepted partitions.

| Split | Runs | All rows | Eligible | Positive | Short history | Event active | Short future |

| --- | --- | --- | --- | --- | --- | --- | --- |

| Train | 10 | 2390 | 995 | 352 | 75 | 1213 | 107 |

| Validation | 6 | 1434 | 599 | 207 | 46 | 719 | 70 |

| Test | 6 | 1434 | 642 | 206 | 45 | 670 | 77 |

## Table 3: V1 measurement and path validation. Rates are received UDP payload; overload rows show means.

| Control | Runs | Goodput Mbit/s | Loss % |

| --- | --- | --- | --- |

| Primary, 3 Mbit/s | 3 | 2.9990-2.9995 | 0 |

| Primary, ramp | 3 | 7.510 | 9.741 |

| Primary, bursty | 3 | 6.121 | 18.682 |

| Alternate, 12 Mbit/s | 3 | 11.994-11.997 | 0 |

| Alternate, 16 Mbit/s | 3 | 15.993-15.996 | 0 |

| Alternate, variable | 6 | All sent datagrams delivered | 0 |

## Table 4: V1: means of three run outcomes per policy/scenario. RTT is mean within-run traffic-window probe p95.

| Policy | Ramp goodput Mbit/s | Ramp loss % | Ramp RTT p95 ms | Burst goodput Mbit/s | Burst loss % | Burst RTT p95 ms |

| --- | --- | --- | --- | --- | --- | --- |

| Fixed primary | 7.510 | 9.741 | 60.0 | 6.121 | 18.682 | 61.5 |

| Reactive | 8.319 | 0.002 | 19.3 | 7.137 | 5.591 | 33.0 |

| Trend | 8.329 | 0.000 | 18.1 | 7.537 | 0.013 | 18.0 |

| ML | 8.329 | 0.000 | 18.3 | 7.521 | 0.195 | 16.2 |

All twelve steady trials had zero UDP sequence loss. Individual paired differences, rather than pooled polling samples, show variation.

## Table 5: Held-out row-level prediction scores on fixed-primary traces.

| Method / scenario | Rows | Precision | Recall | F1 |

| --- | --- | --- | --- | --- |

| ML / ramp | 289 | 0.957 | 0.957 | 0.957 |

| ML / bursty | 353 | 0.825 | 0.798 | 0.811 |

| trend / ramp | 289 | 0.792 | 0.826 | 0.809 |

| trend / bursty | 353 | 0.000 | 0.000 | 0.000 |

## Table 6: V2 exploratory summaries: mean foreground UDP loss (%) over three seeds per cell.

| Scenario | BG Mbit/s | Fixed | Reactive | Trend | ML |

| --- | --- | --- | --- | --- | --- |

| Ramp | 0 | 9.642 | 0.000 | 0.000 | 0.000 |

| Ramp | 4 | 9.573 | 8.893 | 0.000 | 0.000 |

| Ramp | 14 | 8.516 | 7.995 | 8.669 | 9.108 |

| Bursty | 0 | 18.568 | 5.404 | 0.093 | 0.000 |

| Bursty | 4 | 18.327 | 18.246 | 9.564 | 0.587 |

| Bursty | 14 | 17.530 | 15.719 | 16.327 | 17.219 |

Includes V2’s three quality-tolerance exceptions, all at 14 Mbit/s background. At that load no intervention policy switched. Raw trial logs were unavailable for independent verification.
