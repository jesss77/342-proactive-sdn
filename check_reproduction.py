"""Offline checks for this repaired V2 checkout; starts no network traffic."""
from pathlib import Path
import ast,hashlib,json,sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def check():
    files=[]
    for folder in ['analysis','control','ml','network','telemetry','traffic']:
        for path in sorted((ROOT/folder).glob('*.py')):
            ast.parse(path.read_text(encoding='utf-8'),filename=str(path));files.append(path.relative_to(ROOT).as_posix())
    from ml.ml_trigger import load_runtime_model
    model,context=load_runtime_model(ROOT)
    expected='63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595'
    assert context['sha256']==expected
    assert hashlib.sha256((ROOT/'ml/build_trace_dataset.py').read_bytes()).hexdigest()==context['feature_source_sha256']
    assert model.threshold==.65 and len(model.nodes)==15
    print(json.dumps(dict(python_sources_parsed=len(files),frozen_model_preflight='passed',model_sha256=context['sha256'],
        feature_sha256=context['feature_source_sha256'],threshold=model.threshold,nodes=len(model.nodes),
        live_Mininet_test_performed=False,original_raw_trials_available=False),indent=2))

if __name__=='__main__':check()
