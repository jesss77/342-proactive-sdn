# Post-PR4 acquisition counts and decisions

Counts describe distinct registered phases with different purposes; they are
not pooled independent efficacy repetitions. Cancelled idle checks had no
generated traffic and are recorded separately from the trial counts below.
Adverse/no-action outcomes pass when the frozen measurement checks pass.

| Phase | Planned traffic cells | Attempted | Quality-valid individual trials | Quality-invalid trials | Not attempted | Decision / use |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Initial advisor supplement | 18 | 8 | 7 | 1 | 10 | Six accepted fixed-alternate controls; one accepted reactive seed44; early warning seed44 failed collector quality. No complete new four-policy block. |
| Separately registered seed44 recovery | 12 | 1 | 0 | 1 | 11 | First reactive trial failed endpoint UDP-error and collector-quality checks. No complete block. Stopped. |
| Loaded component ladder | 4 | 4 | 4 | 0 | 0 | Source/receiver, collector, fixed loop, reactive loop; diagnostic windows only, not four-policy matched efficacy samples. |
| Activation off/on/off pilot | 3 | 3 | 3 | 0 | 0 | One repeated frozen-ML ramp realization for software forwarding observation and descriptive overhead. Not three fresh efficacy seeds. |
| New reserved bursty follow-up | 16 | 7 | 6 | 1 | 9 | Seed51 complete and independently verified; seed52 partial. Fixed seed52 failed collector quality. Acquisition closed. |

The initial supplement, its recovery and the new follow-up remain closed;
their failed states and every raw reference are retained. A manual cancellation
during recovery idle readiness and another during activation idle readiness
were reviewed separately as pre-acquisition administrative exceptions, not
traffic retries or quality waivers. Their original failed evidence remains
unchanged. The later traffic-quality failures did not use those exceptions.

The original **36/36** matched benchmark predates this table and remains
independently verified. There is **one** additional complete four-policy bursty
block (seed51), not six new matched seeds or sixteen completed follow-up cells.
Seed52's valid reactive and early-warning trials remain descriptive partial
evidence; its failed fixed trial cannot enter accepted paired means and its ML
trial was never run. Seeds53–54 were not acquired.

Evidence:

- [Initial supplement and six alternate controls](../supplement-diagnostics-v1/DIAGNOSIS.md)
- [Loaded recovery failure](../loaded-recovery-diagnostics-v1/DIAGNOSIS.md)
- [Completed four-case component ladder](../component-ladder-v1/RESULTS.md)
- [Completed activation timing pilot](../activation-pilot-v1/RESULTS.md)
- [Final follow-up closure and exact failure](CLOSED.md)
