from pathlib import Path
from datetime import datetime
import json, re, sys

root = Path("results/runs")
p = root / sys.argv[1]
m = json.loads((p / "metadata.json").read_text())
report = {"run": p.name}
report["metadata"] = {k:m.get(k) for k in [
    "requested_bps", "requested_seconds", "client_elapsed_s", "exits",
    "clock_before", "clock_after", "outcome", "error", "snapshot_error"]}

for name, key in [("client", "sum_sent"), ("server", "sum_received")]:
    d = json.loads((p / f"{name}.json").read_text())
    report[name] = {"error": d.get("error"),
                    "summary": d.get("end", {}).get(key)}

report["queue_drop_deltas"] = {}
for interface in ["h1-eth0", "s1-eth3", "s2-eth2", "s4-eth1"]:
    values = []
    for phase in ["before", "after"]:
        text = (p / f"{phase}-{interface}-queue.txt").read_text()
        match = re.search(r"dropped (\d+)", text)
        values.append(int(match[1]) if match else None)
    report["queue_drop_deltas"][interface] = (
        values[1]-values[0] if None not in values else None)

report["udp_error_deltas"] = {}
for host in ["h1", "h2"]:
    counts = []
    for phase in ["before", "after"]:
        text = (p / f"{phase}-{host}-udp.txt").read_text()
        counts.append({k:int(v) for k,v in re.findall(
            r"^(Udp\w+)\s+(\d+)", text, re.M)})
    report["udp_error_deltas"][host] = {
        k:counts[1][k]-v if k in counts[1] else None
        for k,v in counts[0].items()}

text = (p / "vmstat.txt").read_text()
times = [datetime.fromisoformat(t) for t in re.findall(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text)]
report["resource_samples"] = len(times)
report["max_resource_gap_s"] = max(
    ((b-a).total_seconds() for a,b in zip(times,times[1:])), default=None)

if len(sys.argv) > 2:
    rows = [json.loads(x) for x in
            (root / sys.argv[2] / "samples.jsonl").read_text().splitlines()]
    report["collector"] = {
        "samples": len(rows),
        "failed_queries": sum(r.get("tc_exit") != 0 for r in rows),
        "max_interval_s": max(
            (b["monotonic_start"]-a["monotonic_start"]
             for a,b in zip(rows,rows[1:])), default=None)}
print(json.dumps(report, indent=2))
