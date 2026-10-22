"""Execute expanded development-task admission on frozen sources without a model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent

def main(spec,dll,dotnet):
    catalog=json.loads((spec/'catalog.json').read_text())
    for name,expected in catalog['source_hashes'].items():
        if hashlib.sha256((spec/name).read_bytes()).hexdigest()!=expected:raise ValueError('Snapshot changed: '+name)
    results=[]
    for task in catalog['tasks']:
        taskdir=spec/task['task_id']
        for name,expected in task['files'].items():
            if hashlib.sha256((taskdir/name).read_bytes()).hexdigest()!=expected:raise ValueError('Task material changed')
        original=spec/task['snapshot_original'];variants=dict(original=original,repaired=spec/task['snapshot_repaired'],reference=taskdir/'reference.cs',mutant=taskdir/'mutant.cs')
        scores={}
        for label,path in variants.items():
            result_path=taskdir/(label+'-admission.json')
            result=subprocess.run([dotnet,str(dll),'--probe',str(original),str(path),str(taskdir/'tests.cs'),str(result_path)],capture_output=True,text=True,timeout=60)
            if not result_path.exists():raise RuntimeError('Probe did not produce evidence: '+result.stderr)
            raw=json.loads(result_path.read_text())
            scores[label]=dict(build_passed=raw['build_passed'],
                acceptance_failures=sum(c['acceptance'] and not c['passed'] for c in raw.get('cases',[])) if raw['build_passed'] else None,
                regression_failures=sum(not c['acceptance'] and not c['passed'] for c in raw.get('cases',[])) if raw['build_passed'] else None,
                cases=len(raw.get('cases',[])))
        reasons=[]
        if not all(s['build_passed'] for s in scores.values()):reasons.append('compilation_failure')
        if scores['reference']['acceptance_failures']!=0 or scores['reference']['regression_failures']!=0:reasons.append('reference_fails')
        if not all(scores[a]['acceptance_failures'] is not None and scores[a]['acceptance_failures']>0 for a in ['original','repaired']):reasons.append('requirement_not_missing_on_both_versions')
        if any(scores[a]['regression_failures']!=0 for a in ['original','repaired']):reasons.append('starting_regression_difference')
        if not ((scores['mutant']['acceptance_failures'] or 0)+(scores['mutant']['regression_failures'] or 0)>0):reasons.append('deliberate_defect_not_detected')
        if any(s['cases']!=task['test_cases'] for s in scores.values()):reasons.append('case_inventory_mismatch')
        results.append(dict(task_id=task['task_id'],target_id=task['target_id'],family=task['family'],admitted=not reasons,reasons=reasons,variants=scores))
        print(task['task_id'], 'ADMITTED' if not reasons else ','.join(reasons),flush=True)
    summary=dict(status='development admission; not model performance',catalog_sha256=hashlib.sha256((spec/'catalog.json').read_bytes()).hexdigest(),
                 evaluator_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),tasks=results,admitted=sum(r['admitted'] for r in results),total=len(results),model_calls=0)
    (spec/'admission.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['admitted']==summary['total'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',type=Path,default=ROOT/'generated/expanded-spec-v1');p.add_argument('--evaluator',type=Path,default=ROOT/'reproduction/bin/Debug/net10.0/Replay.dll');p.add_argument('--dotnet',default='dotnet');a=p.parse_args()
    raise SystemExit(main(a.spec.resolve(),a.evaluator.resolve(),a.dotnet))
