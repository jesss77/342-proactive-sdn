# First validation-selected Decision Tree

This model predicts a new operational high-utilization onset within two
seconds, using the same eleven causal counter features. It is not a predictor
of every lost packet, and it has not yet been tested on fresh held-out runs or
used for live rerouting.

Training uses only the ten registered training runs (995 eligible rows).
Validation uses six different whole runs (599 eligible rows). No row-level
random split, validation refit, fresh test collection or feature selection is
performed. Each training run receives equal total sample weight. The full
search plan is saved before fitting: depth 2/3/4, leaf minimum 10/25, class
weights none/balanced, alarm threshold .35/.5/.65. The criterion is validation
positive-class F1 averaged equally over ramp and bursty traffic, with a fixed
preference for simpler trees on ties. These are selected validation estimates.

Selected CART: maximum depth 3, minimum leaf size 25, no class weighting,
15 nodes, probability threshold .65. Leaf frequencies are not calibrated
probabilities. The tree is trained by sklearn 1.9.1 DecisionTreeClassifier;
optional training dependencies are pinned in requirements-ml.txt. Portable JSON
inference/review requires only Python's standard library and existing project
modules. It uses float32 inputs to match sklearn's comparisons and rejects
missing/extra/nonfinite features. No pickled executable model is loaded.

Validation row results:

| Measure | Decision Tree | Existing past-trend formula |
| --- | --- | --- |
| Ramp F1 | 0.958333 | See training report |
| Bursty F1 | 0.807692 | 0 |
| Scenario-average F1 | 0.883013 | 0.441860 |
| Pooled positive-class F1 | 0.825243 | See training report |

The independent offline warning-episode replay is less favorable: 2/3 ramp
events and 10/26 burst events received a warning in the two-second window.
False/late warnings remain, including an alarm more than two seconds early
that is not credited as a true prediction. Replay scores all feature-available
histories, not just future-selected eligible rows. It uses rising-threshold
episodes, a fixed five-second cooldown, explicit tail censoring and observed
event truth only for scoring. It does not simulate route changes or the live
one-action cap. Report this distinction beside row F1.

Bursty schedule regularities may be learned from past counters; this does not
establish universal predictability of abrupt real-network bursts. No test or
QoS advantage is claimed. The source pacing amendment and clustered run/event
limitations remain attached to the dataset.

Export parity was checked on all 3,703 available histories, including those
excluded from row-label scoring: maximum probability error 4.44e-16 and
identical alarm decisions. Model inputs are fingerprinted at actual float32
precision to tolerate irrelevant last-bit libm differences across Windows and
Ubuntu; original file hashes are retained separately. Model, target/profile,
feature-source hash and dataset fingerprint must match during guest review.

The frozen model is selected_tree.json. Reproduce it without fitting in T3:

```bash
python3 review_tree.py --dataset DATASET_DIRECTORY --output NEW_REVIEW_DIRECTORY
```

Next: verify guest reproduction, acquire registered fresh held-out traces
without retuning, evaluate prediction/events, then integrate the frozen model
with the shared live action and run repeated networking comparisons.

Primary documentation:
- https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeClassifier.html
- https://scikit-learn.org/stable/common_pitfalls.html
