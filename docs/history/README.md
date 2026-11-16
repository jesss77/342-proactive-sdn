# CMPS342 - Proactive Congestion Management in SDN

Study whether predicting link congestion allows an SDN controller to reroute traffic early enough to improve goodput, delay and packet loss.

The planned comparison uses fixed routing, reactive rerouting after confirmed congestion, and proactive rerouting using a Decision Tree. Reactive and proactive policies will use the same flow selection, alternate-path checks and cooldown. Traffic scenarios will include steady load, increasing load and bursts.

## Testbed

Mininet hosts and Open vSwitch switches are controlled by OS-Ken over OpenFlow 1.3.

```text
                 100 Mbit/s       10 Mbit/s
             +------------- s2 ------------+
             |                             |
 h1, h3 ---- s1                             s4 ---- h2, h4
             |                             |
             +------------- s3 ------------+
                  20 Mbit/s       20 Mbit/s
```

Host links are 100 Mbit/s. Every link direction has a configured 1 ms delay and a 50-packet netem queue limit. The controller selects the primary path through s2 or the alternate path through s3 at startup.

## What works

- Four-host, four-switch topology and static forwarding rules.
- Primary-path connectivity, with 12/12 directed ping replies.
- Saved traffic outputs, queue counters and timing diagnostics.

Repeatable shaped-path measurements remain unresolved. Two primary-path trials showed severe timing problems and packet loss, including drops at the source interface. They are retained as diagnostics. Alternate-path traffic validation, utilization sampling, reactive control and the predictive model are still pending.

## Run

Follow [SETUP.md](SETUP.md) to install dependencies, start the controller and topology, and record a traffic trial. [Results](results/README.md) lists the observed measurements and how to save new runs.

| File | Purpose |
| --- | --- |
| `topology.py` | Hosts, switches, port numbers and link settings |
| `diamond_controller.py` | Static primary/alternate forwarding rules |
| `run_primary_trial.py` | Record a 3 Mbit/s primary-path UDP trial |
| `requirements.txt` | Python dependency versions from the original environment |
| `SETUP.md` | Installation, commands and shutdown |
| `results/` | Original scripts and raw results, checksums and experiment log |

Next steps are to establish reliable low-load and overload measurements, validate the alternate route, and calibrate 500/250/100 ms sampling. Model evaluation will separate complete runs between training and testing and compare repeated traffic schedules across policies.
