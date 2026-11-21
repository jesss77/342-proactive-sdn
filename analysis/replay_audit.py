"""Run a curated-input audit and compare its scientific outputs with the saved reference."""
from pathlib import Path
import argparse,importlib,json
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['components','activation','followup']);p.add_argument('--repo',required=True);p.add_argument('--published',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    modules={'components':('audit_component_ladder','component-ladder-v1/audit.json','cases'),
             'activation':('audit_activation_pilot','activation-pilot-v1/audit.json','steps'),
             'followup':('audit_closed_bursty_followup','bursty-followup-v1/closed-audit.json','attempts')}
    module,ref,key=modules[a.stage];actual=importlib.import_module(module).audit(a.repo,a.published,a.output)
    expected=read(Path(a.published)/'results'/ref)
    assert actual[key]==expected[key],a.stage+' detailed outcomes differ'
    if a.stage!='components':assert actual['summary']==expected['summary']
    assert actual['original_action_audit']==expected['original_action_audit']
    print(json.dumps(dict(stage=a.stage,outcomes=len(actual[key]),scientific_outputs_exactly_match=True)))
