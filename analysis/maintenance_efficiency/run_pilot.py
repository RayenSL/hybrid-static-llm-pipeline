"""Bounded Azure-compatible maintenance pilot. No automatic retries or hidden-test feedback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from accounting import summarize_run, validate_call

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
SYSTEM='''You are implementing a specified maintenance requirement in a C# 12 / .NET 8 project. Standard SDK implicit usings are enabled. Return ONLY the complete replacement contents of PricingRules.cs, without Markdown or explanations. Preserve the required public API. You may add helpers inside that file. Do not access files, environment variables, processes, networks, reflection, test internals or external services in generated code. Supporting files are read-only. Compiler feedback may be supplied, but no hidden test feedback will be given. Implement the requirement, not a guessed test case.'''

def digest(data):return hashlib.sha256(data).hexdigest()
def dump(path,data):path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def prompt_reserve(messages):
    # Deliberately conservative UTF-8-byte bound plus framing reserve, not a token estimate.
    # Validate on every returned usage record; cease execution if the assumption fails.
    return len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))+512

def extract_source(text):
    text=text.strip()
    if text.startswith('```'):
        match=re.fullmatch(r'```(?:csharp|cs)?\s*\n(.*?)\n```',text,re.S)
        if not match:raise ValueError('Invalid fenced response')
        text=match.group(1)
    if not text or '\x00' in text:raise ValueError('Empty or invalid source')
    return text+'\n'

def provider_call(messages,max_output,config):
    base=config['BaseUrl'].rstrip('/')
    deployment=urllib.parse.quote(config['Model'],safe='')
    url=f'{base}/openai/deployments/{deployment}/chat/completions?api-version=2024-10-21'
    body=dict(messages=messages,temperature=config.get('Temperature',1),max_completion_tokens=max_output)
    request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','api-key':config['ApiKey']},method='POST')
    started=time.monotonic()
    with urllib.request.urlopen(request,timeout=180) as response:
        data=json.loads(response.read())
    return data,time.monotonic()-started,body

def evaluate(original,candidate,output,task_id=None):
    dotnet='dotnet' if os.name=='nt' else '/mnt/c/Program Files/dotnet/dotnet.exe'
    dll=REPO/'src/HybridLens.MaintenancePilot/bin/Debug/net10.0/HybridLens.MaintenancePilot.dll'
    cmd=[dotnet,str(dll),'--compile' if task_id is None else '--evaluate',str(original),str(candidate),str(output)]
    if task_id is not None:cmd += [str(ROOT/'tasks.json'),task_id]
    subprocess.run(cmd,check=True,capture_output=True,timeout=60)
    return json.loads(output.read_text(encoding='utf-8-sig'))

def main(output):
    settings=json.loads((ROOT/'pilot_config.json').read_text())
    if not settings['live_execution_enabled']:raise ValueError('Live execution disabled')
    if not settings['token_only_limit_confirmed']:raise ValueError('Token ceiling must be explicitly selected')
    campaign=json.loads((ROOT/'generated/campaign.json').read_text())
    if campaign['settings_sha256']!=digest((ROOT/'pilot_config.json').read_bytes()):raise ValueError('Settings changed')
    if campaign['tasks_sha256']!=digest((ROOT/'tasks.json').read_bytes()):raise ValueError('Tasks changed')
    admission=json.loads((ROOT/'generated/admission.json').read_text())
    if admission['failed_admissions'] or admission['campaign_sha256']!=digest((ROOT/'generated/campaign.json').read_bytes()):raise ValueError('Task admission does not match campaign')
    if output.exists():raise ValueError('Output exists: no implicit overwrite or retry of paid calls')
    output.mkdir(parents=True)
    local=json.loads((REPO/'src/HybridLens.CLI/appsettings.local.json').read_text(encoding='utf-8-sig'))['Llm']
    model={**{k:v for k,v in local.items() if k!='Models'},**local['Models'][settings['model_key']]}
    if not model.get('ApiKey'):raise ValueError('Existing API key unavailable')
    pairs={p['target_id']:p for p in campaign['pairs']}
    tasks={t['task_id']:t for t in json.loads((ROOT/'tasks.json').read_text())['tasks']}
    protected={ROOT/'tasks.json':campaign['tasks_sha256']}
    evidence_path=ROOT.parent/'repair_design_quality/generated/manifest.json'
    if digest(evidence_path.read_bytes())!=campaign['evidence_manifest_sha256']:raise ValueError('Evidence manifest changed')
    evidence=json.loads(evidence_path.read_text())
    for relative,expected in evidence['baseline_files'].items():
        protected[(evidence_path.parent/'baseline'/relative).resolve()]=expected
    for pair in pairs.values():
        for pathfield,hashfield in [('baseline_path','baseline_sha256'),('repaired_path','repair_sha256')]:
            protected[(ROOT/pair[pathfield]).resolve()]=pair[hashfield]
    def verify():
        for path,expected in protected.items():
            if digest(path.read_bytes())!=expected:raise ValueError('Protected evidence changed')
    verify()
    frozen=dict(settings=settings,campaign_sha256=digest((ROOT/'generated/campaign.json').read_bytes()),
                tasks_sha256=campaign['tasks_sha256'],runner_sha256=digest(Path(__file__).read_bytes()),
                evaluator_sha256=digest((REPO/'src/HybridLens.MaintenancePilot/bin/Debug/net10.0/HybridLens.MaintenancePilot.dll').read_bytes()),
                system_prompt=SYSTEM,provider='azure-compatible',api_version='2024-10-21',
                token_admission='UTF-8 serialised-message bytes + 512 framing reserve; actual provider counts checked after each call',
                price_schedule=None,scope='two synthetic development tasks; compiler-only feedback; hidden final evaluation')
    dump(output/'execution-freeze.json',frozen)
    global_tokens=0;halt=None;results=[]
    for index,planned in enumerate(campaign['pilot_runs']):
        row={**planned,'calls':[],'acceptance_passed':None,'regression_passed':None,'edit_scope_passed':True,
             'integrity_passed':True,'termination_reason':None}
        if halt:
            row['termination_reason']='not_executed_after_campaign_stop';row['integrity_passed']=None
            results.append(row);continue
        pair=pairs[row['target_id']];task=tasks[row['task_id']]
        original=(ROOT/pair['baseline_path']).resolve()
        initial=(ROOT/pair['baseline_path' if row['arm']=='original' else 'repaired_path']).resolve()
        run_dir=output/row['run_id'];run_dir.mkdir()
        support='\n\n'.join(f'READ-ONLY {name}\n'+(original.parent/name).read_text(encoding='utf-8-sig') for name in ['Order.cs','Customer.cs'])
        prompt=f"REQUIREMENT\n{task['requirement']}\n\nREAD-ONLY PROJECT CONTEXT\n{support}\n\nEDITABLE PricingRules.cs\n{initial.read_text(encoding='utf-8-sig')}"
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}]
        started=time.monotonic();run_tokens=0;candidate=None
        for number in range(settings['maximum_calls_per_run']):
            if time.monotonic()-started>=settings['maximum_wall_seconds_per_run']:
                row['termination_reason']='wall_timeout';break
            reserve=prompt_reserve(messages)
            allowed=min(4096,row['token_budget']-run_tokens-reserve,settings['pilot_recorded_token_ceiling']-global_tokens-reserve)
            if allowed<128:
                row['termination_reason']='conservative_budget_stop';break
            call_id=f"{row['run_id']}-{number+1}"
            call=dict(call_id=call_id,model=settings['model_key'],outcome='failed',input_tokens=None,output_tokens=None,
                      cached_input_tokens=None,reasoning_output_tokens=None,prompt_token_reserve=reserve,max_completion_tokens=allowed)
            dump(run_dir/(call_id+'-request.json'),dict(messages=messages,max_completion_tokens=allowed))
            # Write an intent before sending: an interrupted call cannot be silently forgotten.
            dump(run_dir/(call_id+'-intent.json'),dict(status='sending',call_id=call_id,reserved_total_tokens=reserve+allowed))
            try:
                raw,elapsed,_=provider_call(messages,allowed,model)
                dump(run_dir/(call_id+'-response.json'),raw)
                usage=raw.get('usage') or {}
                call.update(outcome='completed',elapsed_seconds=elapsed,
                    input_tokens=usage.get('prompt_tokens'),output_tokens=usage.get('completion_tokens'),
                    cached_input_tokens=(usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
                    reasoning_output_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                    returned_model=raw.get('model'),raw_usage_ref=f'{row["run_id"]}/{call_id}-response.json')
                inp,out,_,_=validate_call(call)
                if inp is None or out is None:raise ValueError('Provider omitted usage')
                run_tokens+=inp+out;global_tokens+=inp+out
                if inp>reserve or out>allowed or run_tokens>row['token_budget'] or global_tokens>settings['pilot_recorded_token_ceiling']:
                    raise ValueError('Provider count exceeded reserved budget')
                choice=raw['choices'][0]
                text=choice['message'].get('content') or ''
                call['finish_reason']=choice.get('finish_reason')
                row['calls'].append(call);dump(run_dir/(call_id+'-usage.json'),call)
                if choice.get('finish_reason') not in ['stop',None]:
                    row['termination_reason']='provider_output_limit';break
                try:source=extract_source(text)
                except ValueError:
                    messages += [{'role':'assistant','content':text},{'role':'user','content':'Invalid response format. Return only the complete C# file.'}]
                    row['termination_reason']='invalid_response';continue
                candidate=run_dir/'candidate.cs';candidate.write_text(source,encoding='utf-8')
                compile_result=evaluate(original,candidate,run_dir/'compile.json')
                if compile_result['build_passed']:
                    row['termination_reason']='submitted_building_candidate';break
                messages += [{'role':'assistant','content':text},{'role':'user','content':'Compiler errors:\n'+'\n'.join(compile_result['diagnostics'])[:8000]+'\nReturn the corrected full file.'}]
                row['termination_reason']='compiler_failure'
            except Exception as error:
                if isinstance(error,urllib.error.HTTPError):
                    call['http_status']=error.code
                    detail=error.read(65536).decode('utf-8',errors='replace')
                    detail=detail.replace(model['ApiKey'],'[REDACTED]').replace(model['BaseUrl'],'[ENDPOINT]')
                    (run_dir/(call_id+'-provider-error.txt')).write_text(detail,encoding='utf-8')
                # No retry when a request may have consumed unreported tokens.
                if not row['calls'] or row['calls'][-1]['call_id']!=call_id:row['calls'].append(call)
                dump(run_dir/(call_id+'-usage.json'),call)
                row['termination_reason']='provider_or_instrument_error';row['integrity_passed']=False
                halt=dict(run_id=row['run_id'],error_type=type(error).__name__,reason='Stop after uncertain usage, reservation violation or instrument failure; inspect protected raw evidence before any resumption.')
                break
        if candidate is not None and halt is None:
            try:
                final=evaluate(original,candidate,run_dir/'hidden-evaluation.json',task['task_id'])
                row.update(acceptance_passed=final['acceptance_passed'],regression_passed=final['regression_passed'])
                verify()
            except Exception as error:
                row['integrity_passed']=False;row['termination_reason']='evaluation_error'
                halt=dict(run_id=row['run_id'],error_type=type(error).__name__,reason='Evaluation or evidence-integrity failure')
        elif halt is None:
            row.update(acceptance_passed=False,regression_passed=False)
        row['elapsed_seconds']=time.monotonic()-started
        row['accounting']=summarize_run(row)
        dump(run_dir/'result.json',row);results.append(row)
        with (output/'results.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps(dict(completed=index+1,total=len(campaign['pilot_runs']),arm=row['arm'],task=row['task_id'],budget=row['token_budget'],tokens=run_tokens,
                              success=row['accounting']['correct_within_budget'],termination=row['termination_reason'],campaign_tokens=global_tokens)),flush=True)
    # Include every planned assignment, even if execution stopped early.
    (output/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in results),encoding='utf-8')
    dump(output/'execution-summary.json',dict(planned_runs=len(results),recorded_tokens=global_tokens,halt=halt,prices_available=False))
    return 1 if halt else 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    raise SystemExit(main(args.output.resolve()))
