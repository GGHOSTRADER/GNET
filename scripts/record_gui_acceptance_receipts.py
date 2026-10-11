"""Record bounded typed reports for the two fabricated GUI validation requests."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
sys.path.insert(0, config['package_root'])
from gnet_jobs.client import Client

client = Client(Path(config['exchange']), Path(config['results']))
jobs = ['job-20261011T052801Z-62139ff8103a4d94b4007777f27c5584',
        'job-20261011T053108Z-5816c5e635d543bbbbb54c8debac011f']
receipt = dict(synthetic_only=True, export_id='acceptance-client-delivery-oct09-fresh-r1',
    broker_release_id=config['broker_release_id'], jobs=[], full_gui_workflow_accepted=False)
for job in jobs:
    result = client.report(job)
    receipt['jobs'].append(dict(job_id=job, result=result))
path = base / '.test_artifacts/gui-acceptance-validation-oct11.json'
path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(dict(receipt=str(path), jobs=len(jobs), full_gui_workflow_accepted=False)))
