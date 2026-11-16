import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("output")
p.add_argument("--interval", type=float, default=0.25)
p.add_argument("--duration", type=float, default=60)
a = p.parse_args()
if a.interval <= 0 or a.duration <= 0:
    p.error("Interval and duration must be positive")

interfaces = ["s1-eth3", "s2-eth2", "s4-eth3"]
start = time.monotonic()
deadline = start
sequence = 0

with Path(a.output).open("x") as f:
    while time.monotonic() - start < a.duration:
        time.sleep(max(0, deadline - time.monotonic()))
        t0 = time.monotonic()
        row = {
            "sample": sequence,
            "utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_start": t0,
            "scheduled": deadline,
            "requested_interval": a.interval,
            "interfaces": {}
        }
        for name in interfaces:
            folder = Path("/sys/class/net") / name / "statistics"
            try:
                row["interfaces"][name] = {
                    key: int((folder / key).read_text())
                    for key in ["tx_bytes", "rx_bytes",
                                "tx_packets", "rx_packets"]
                }
            except (OSError, ValueError) as e:
                row["interfaces"][name] = {"error": str(e)}
        try:
            result = subprocess.run(
                ["tc", "-j", "-s", "qdisc", "show",
                 "dev", "s2-eth2"],
                capture_output=True, text=True, timeout=2
            )
            row["tc_exit"] = result.returncode
            row["tc_stdout"] = result.stdout
            row["tc_stderr"] = result.stderr
        except subprocess.TimeoutExpired:
            row["tc_error"] = "query exceeded 2 seconds"
        row["monotonic_end"] = time.monotonic()
        f.write(json.dumps(row) + "\n")
        f.flush()
        sequence += 1
        deadline += a.interval
        if deadline < time.monotonic():
            deadline += (
                int((time.monotonic() - deadline) / a.interval) + 1
            ) * a.interval

print("Saved", sequence, "samples to", a.output)
