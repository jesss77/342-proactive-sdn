# V2 checkout repair and evidence boundary

This branch repairs checkout defects found during the final-paper asset audit.
It descends from `512cafc5f48748b741bb2961fa9a644b8333d4a5`. That original commit,
all reported results, trigger settings, the learned tree and its threshold are
preserved as historical evidence.

## Repairs

1. The original Git model and feature blobs used LF line endings, while their
   runtime fingerprints require the original CRLF bytes. A Windows checkout or
   archive with automatic conversion masked the mismatch; a Linux checkout did
   not. Restore the two pinned files to the bytes already required by the loader
   and add `.gitattributes` to preserve them across platforms. Do not weaken or
   change the fingerprints.
2. Correct indentation in `control/run_routing_smoke.py` so it parses.
3. Remove the accidental PowerShell wrapper from `.gitignore`.
4. Add `python check_reproduction.py` to parse the sources and run the frozen
   model/feature preflight without Mininet, traffic or new measurements.

The model SHA-256 is
`63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595`.
The feature SHA-256 is
`2654567afd5e77285fdbf8ca0077e733389c07b4b63d7003ed6afff66649c291`.
Model parameters and feature logic are unchanged. The repairs are not evidence
that a new live network experiment has been performed.

## Fresh acquisition

Use the Linux/Mininet commands in the README after the offline check. The
committed `results/v2-batch.json` and `results/v2-steady-control.json` are the
historical records. Copy them to a separate evidence location and keep a new
acquisition's state and raw output separate; otherwise the batch sees its
existing completed state and performs no new trials. Never overwrite the
historical summaries with a fresh run.

## Audit the paper

The default branch contains the canonical paper-asset generators and pinned
summary inputs. Start at its `docs/PAPER_ASSETS.md` and `results/paper/`.
These rebuild all four figures and six tables. V1 has raw-backed replay; V2
original raw trial logs are unavailable. This repaired source branch enables
offline preflight and supplies acquisition code, but does not fill that gap.
