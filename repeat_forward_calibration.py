from pathlib import Path
from datetime import datetime
import json
import shutil
import subprocess

base = Path("/home/jess/342-proactive-sdn")
group = base / "results/runs" / (
    datetime.now().strftime("%Y%m%d-%H%M%S-%f") + f"-calibration-{globals().get('requested_bps', 12000000)}bps"
)
group.mkdir(parents=True)
for name in ["repeat_forward_calibration.py", "inspect_trial.py"]:
    shutil.copy2(base / name, group)

def source_limit(value, label):
    command = ["tc", "qdisc", "change", "dev", "h1-eth0",
               "parent", "5:1", "handle", "10:", "netem",
               "delay", "1ms", "limit", str(value)]
    out, err, status = net["h1"].pexec(command)
    (group / f"{label}.json").write_text(json.dumps(
        dict(command=command, stdout=out, stderr=err, exit=status),
        indent=2))
    if status:
        raise RuntimeError(err)

try:
    source_limit(250, "apply-source-limit")
    for repetition in globals().get("repetitions", [2, 3]):
        print("Calibration repetition", repetition, "at bit/s", globals().get("requested_bps", 12000000), flush=True)
        namespace = {"net": net, "requested_bps": globals().get("requested_bps", 12000000)}
        source = base / "run_forward_path_calibration.py"
        exec(compile(source.read_text(), str(source), "exec"), namespace)
        trial = namespace["scope"]["trial"]
        monitor = namespace["scope"]["folder"]
        context = dict(repetition=repetition, source_queue_limit=250,
                       group=str(group))
        (trial / "repetition-context.json").write_text(
            json.dumps(context, indent=2))
        result = subprocess.run(
            ["/usr/bin/python3", str(base / "inspect_trial.py"),
             trial.name, monitor.name],
            cwd=base, capture_output=True, text=True)
        (group / f"inspection-{repetition}.json").write_text(result.stdout)
        (group / f"inspection-{repetition}.err").write_text(result.stderr)
        result.check_returncode()
        report = json.loads(result.stdout)
        print("Inspection:", json.dumps({
            "run": trial.name,
            "sender": report["client"]["summary"],
            "receiver": report["server"]["summary"],
            "queue_drops": report["queue_drop_deltas"],
            "udp_errors": report["udp_error_deltas"],
            "metadata": report["metadata"],
            "max_resource_gap_s": report["max_resource_gap_s"],
            "collector": report.get("collector")
        }), flush=True)
finally:
    source_limit(50, "restore-source-limit")
    print("Source queue restored to 50 packets.", flush=True)

print("Repetition records:", group)
