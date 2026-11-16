from pathlib import Path
from datetime import datetime
import json
import shutil

base = Path("/home/jess/342-proactive-sdn")
group = base / "results/runs" / (
    datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-cburst-repeats"
)
group.mkdir(parents=True)
shutil.copy2(base / "repeat_cburst_calibration.py", group)
(group / "first-trial.txt").write_text(
    "20261114-164912-874512-primary-3M\n"
)

def change(value, label):
    command = ["tc", "class", "change", "dev", "s2-eth2",
               "parent", "5:", "classid", "5:1", "htb",
               "rate", "10mbit", "ceil", "10mbit",
               "burst", "15360", "cburst", str(value)]
    out, err, status = net["s2"].pexec(command)
    (group / (label + ".json")).write_text(json.dumps(
        dict(command=command, stdout=out, stderr=err, exit=status),
        indent=2))
    if status:
        raise RuntimeError(err)

try:
    change(16384, "apply")
    for repetition in [2, 3]:
        print("Low-load repetition", repetition, "of 3", flush=True)
        scope = {"net": net}
        source = base / "run_monitored_trial.py"
        exec(compile(source.read_text(), str(source), "exec"), scope)
        context = dict(repetition=repetition, cburst_bytes=16384,
                       group=str(group), monitoring=str(scope["folder"]))
        trial = scope["trial"]
        (trial / "calibration-context.json").write_text(
            json.dumps(context, indent=2))
        (group / f"repetition-{repetition}.txt").write_text(str(trial))
        metadata = json.loads((trial / "metadata.json").read_text())
        if metadata["outcome"] != "completed":
            raise RuntimeError("Trial failed; stopping repetitions")
finally:
    change(1600, "restore")
    out, err, status = net["s2"].pexec(
        ["tc", "-s", "class", "show", "dev", "s2-eth2"])
    (group / "restored-class.txt").write_text(out + err)
    print("Restored class:\n" + out, flush=True)

print("Repetition records:", group)
