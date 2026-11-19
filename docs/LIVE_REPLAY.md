# Replay the live experiment in a new lab

Use this for **new measurements**. For the exact historical results, use [saved-data reproduction](REPRODUCIBILITY.md). VM scheduling, kernel shaping and wall-clock timings vary; a fresh live run is not expected to reproduce identical loss/RTT numbers.

## Environment and clean workspace

Use a separate clone in a dedicated Ubuntu 24.04.5 VirtualBox guest, one vCPU, 6 GiB RAM and the recorded controller dependencies. Start with [SETUP.md](../SETUP.md). The accepted guest used Python 3.12.3, Mininet 2.3.0, Open vSwitch 3.3.9, iperf3 3.16 and OS-Ken 3.1.1. `requirements.txt` records the controller Python packages; `requirements-ml.txt` records the separate historical Windows training environment. No training packages are needed for the frozen-tree live loop.

The original topology starts with 50-packet queues and cburst 1600 bytes. Wrappers check this baseline, apply the frozen dual profile during a trial, and restore it. Do not pre-apply the final profile: the preflight deliberately refuses unexpected settings. See [operating bounds](../operating_bounds.json), [dual profile](../dual_path_profile.py) and [matched protocol](../matched_protocol.json).

Record the new machine's actual configuration before collection:

```bash
mkdir -p results/environment
uname -a > results/environment/kernel.txt
python3 --version > results/environment/python.txt
mn --version > results/environment/mininet.txt 2>&1
ovs-vsctl --version > results/environment/ovs.txt
iperf3 --version > results/environment/iperf.txt 2>&1
.venv/bin/osken-manager --version > results/environment/osken.txt 2>&1
.venv/bin/python -m pip freeze > results/environment/controller-packages.txt
lscpu > results/environment/cpu.txt
free -b > results/environment/memory.txt
cat /sys/devices/system/clocksource/clocksource0/current_clocksource > results/environment/clocksource.txt
git rev-parse HEAD > results/environment/git-commit.txt
```

The source records the clock before/after each run; it does not change the clock. Do not attribute the stabilized protocol to a universal clock fix. A VirtualBox disk image and host machine are not included; software/configuration records and raw evidence are included. Do not relax hash, shaping or quality checks to conceal environment drift.

Do **not** extract the historical checkpoint over this active clone's `results/runs`. Historical extraction contains completed batch registries. Keep it under the reproduction output directory. The live clone must begin without an old matched registry or seed-41/42/43 trials. Never delete a registry to force a second batch in the same study.

## Start the network

Terminal A, from the clone:

```bash
SDN_PATH=primary .venv/bin/osken-manager --ofp-tcp-listen-port 6653 diamond_controller.py
```

Terminal B, from the same clone, only when no other lab is active:

```bash
sudo mn -c
sudo mn --custom topology.py --topo diamond --link tc --arp --controller remote,ip=127.0.0.1,port=6653 --switch ovs,protocols=OpenFlow13 --wait
```

At `mininet>`, require `pingall` to give 12/12 replies. Record original flow/class/qdisc readbacks. Run commands below from this repository's working directory; relative `__file__` paths are resolved by the existing wrappers.

## Validate restoration and alternate-path operation

At `mininet>`:

```text
py exec(compile(open('run_routing_smoke.py').read(), 'run_routing_smoke.py', 'exec'), {'net': net, '__file__': 'run_routing_smoke.py'})
```

Then the existing fixed path control (repeat three times at 12 Mbit/s and three times at 16 Mbit/s, preserving every output):

```text
py exec(compile(open('run_path_control.py').read(), 'run_path_control.py', 'exec'), {'net': net, '__file__': 'run_path_control.py', 'route': 'alternate', 'requested_bps': 12000000, 'duration': 20})
```

Use `requested_bps: 16000000` for the higher controls. Inspect the printed `control_screen_failures`, active/inactive path counters, receiver rate, root drops, UDP errors and both restoration records. A completed process is not itself acceptance. Historical primary low/overload controls can be reconstructed from the included checkpoint; the versioned [calibration instructions](../EXPERIMENTS.md) and source wrappers are also preserved.

## Establish the frozen-model in-traffic pilot

At `mininet>`:

```text
py exec(compile(open('run_policy_experiment.py').read(), 'run_policy_experiment.py', 'exec'), {'net': net, '__file__': 'run_policy_experiment.py', 'policy': 'ml', 'scenario': 'ramp', 'requested_bps': 11500000, 'duration': 60, 'seed': 1})
```

The original matched runner requires an accepted seed-1 ML pilot with the same frozen source/model and in-traffic path proof. Preserve its evidence. It refuses collection if the gate fails. Other pilot modes can be selected with `policy` equal to `fixed`, `reactive` or `early_warning`. At most one primary-to-alternate action is allowed; cleanup returns to primary after traffic.

## Replay the 36-cell workload matrix

At `mininet>`, in the new live clone:

```text
py exec(compile(open('run_matched_batch.py').read(), 'run_matched_batch.py', 'exec'), {'net': net, '__file__': 'run_matched_batch.py', 'limit': 4})
```

Inspect the four completed steady seed-41 results. If accepted, resume the exact recorded batch:

```text
py __import__('run_matched_batch').run(net, limit=32, resume=__import__('pathlib').Path('results/runs/active-matched-batch.txt').read_text().strip())
```

The pinned plan provides all four policies, three scenarios and seeds 41-43, with 60-second trials, steady 3 Mbit/s and variable scale 11.5 Mbit/s. Scenario/policy order, actual traffic schedules, measurements, freshness/admission checks and quality criteria are in `matched_protocol.json` and the source. Low-load switches, denied actions and no-action runs remain valid outcomes; a QoS benefit is not required for acceptance. Source or model changes block acquisition/resumption. Failed attempts stop the batch and retain their raw references.

After completion, from a normal terminal:

```bash
python3 tools/analyze_matched.py --repo . --output ../new-live-analysis
python3 tools/plot_matched.py --report ../new-live-analysis/matched-report.json --output ../new-live-plots
```

Use the separate plotting environment described in [reproduction instructions](REPRODUCIBILITY.md). Fresh outputs get new run identifiers; preserve them separately from the November 16 historical results. Do not require an exact match to historical timing metrics or replace adverse runs.

## Rebuild or replay predictor development

All original training/validation/fresh-test selections, feature/label rules, source audits and input traces are in the raw checkpoint. The offline reproduction workflow rebuilds them. `--refit` replays only the original development search into a new directory and checks the resulting tree against the frozen model; it never installs that replayed model or retunes on test data.

For genuinely new training acquisitions, `run_dataset_batch.py` and `fixed_trace_dataset.py` retain the original 16-trace workflow. Fresh prediction collection uses `run_heldout_batch.py`, which requires matching guest development reproduction and a model frozen **before** test acquisition. Changing the workload, target, model or seeds defines a new registered study. It is not a correction to the saved benchmark. The original held-out seeds are no longer unseen data.
