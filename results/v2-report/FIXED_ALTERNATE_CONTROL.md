# Fixed-Alternate Control Check (`h1 -> h2` permanently on `s3`, `s3 BG = 14 Mbit/s`)

| Scenario | Seed | `h1->h2` Goodput (Mbit/s) | `h1->h2` Loss (%) | RTT `p95` (ms) | `s1-eth4` Drops | `s3-eth2` Drops | `h3->h4` BG Goodput (Mbit/s) | `h3->h4` BG Loss (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ramp | 41 | 6.972 | 14.264 | 42.4 | 14889 | 0 | 12.157 | 10.354 |
| bursty | 41 | 5.795 | 17.952 | 36.8 | 15555 | 0 | 12.362 | 10.220 |
