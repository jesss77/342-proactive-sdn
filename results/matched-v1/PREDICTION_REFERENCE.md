# Separate frozen-model prediction reference

These are the six untouched fixed-primary traces, seeds 31–33, not the 36 intervened networking trials. The model, threshold and feature code were frozen before fresh collection. Full row and warning metrics reproduced exactly from raw data.

| Scenario | Eligible rows | Precision | Recall | Positive F1 |
| --- | --- | --- | --- | --- |
| ramp | 289 | 0.956522 | 0.956522 | 0.956522 |
| bursty | 353 | 0.824859 | 0.797814 | 0.811111 |

Advance warnings reached 2/3 observed ramp events and 9/25 scorable burst events (26 observed). Twenty-four false episodes included twenty late episodes; five tail episodes were censored. Successful-run median leads ranged approximately 0.995–1.999 seconds; do not average those medians into a pooled lead time.

Compare these qualified timing results with matched command/readback measurements, not with unmeasured packet disruption. A route intervention censors primary-path congestion, so primary event labels are not reconstructed from ML-rerouted runs. No model refit or threshold change was performed.
