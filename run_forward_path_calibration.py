from pathlib import Path
from datetime import datetime
import json
import shutil

base = Path("/home/jess/342-proactive-sdn")
folder = base / "results/runs" / (
    datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-forward-cburst"
)
folder.mkdir(parents=True)
shutil.copy2(base / "run_forward_path_calibration.py", folder)

links = [("h1", "h1-eth0", "100mbit"),
         ("s1", "s1-eth3", "100mbit"),
         ("s2", "s2-eth2", "10mbit"),
         ("s4", "s4-eth1", "100mbit")]

def configure(node, interface, rate, value, label):
    command = ["tc", "class", "change", "dev", interface,
               "parent", "5:", "classid", "5:1", "htb",
               "rate", rate, "ceil", rate, "burst", "15360",
               "cburst", str(value)]
    out, err, status = net[node].pexec(command)
    (folder / f"{label}-{interface}.json").write_text(
        json.dumps(dict(command=command, stdout=out,
                        stderr=err, exit=status), indent=2))
    if status:
        raise RuntimeError(f"{interface}: {err}")

try:
    for node, interface, rate in links:
        out, err, status = net[node].pexec(
            ["tc", "-s", "class", "show", "dev", interface])
        (folder / f"before-{interface}.txt").write_text(out + err)
        configure(node, interface, rate, 16384, "apply")
    scope = {"net": net, "requested_bps": globals().get("requested_bps", 12000000)}
    source = base / "run_monitored_trial.py"
    exec(compile(source.read_text(), str(source), "exec"), scope)
    context = dict(cburst_bytes=16384, interfaces=links,
                   protocol_folder=str(folder),
                   monitoring=str(scope["folder"]))
    (scope["trial"] / "calibration-context.json").write_text(
        json.dumps(context, indent=2))
    (folder / "traffic-run.txt").write_text(str(scope["trial"]))
finally:
    failures = []
    for node, interface, rate in links:
        try:
            configure(node, interface, rate, 1600, "restore")
        except Exception as e:
            failures.append(str(e))
    print("Restoration failures:", failures)
    if failures:
        raise RuntimeError("Restoration incomplete")
print("All four cburst settings restored to 1600.")
print("Protocol folder:", folder)
