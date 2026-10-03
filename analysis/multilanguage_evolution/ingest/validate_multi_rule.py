"""Validate modular three-rule results before admitting them to aggregation."""
import argparse,hashlib,json,math
from pathlib import Path,PurePosixPath
RULES={'LongMethod','GodClass','ObsoleteApiUsage'}
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
def digest(x):return hashlib.sha256(x).hexdigest()
def validate(d):
    import jsonschema
    schema=Path(__file__).resolve().parents[1]/"contracts/multi-rule.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema.read_text())).validate(d)
    def check(ok,msg):
        if not ok:raise ValueError(msg)
    check(d['schema_version']=='evolution.multi-rule/0.2' and d['admitted'] is False,'Unsupported or prematurely admitted result')
    check(len(d['commit'])==40 and all(c in '0123456789abcdef' for c in d['commit']),'Invalid commit')
    check(d['scope_sha256']==digest(canonical(d['scope'])),'Scope seal mismatch')
    inv={x['path']:x for x in d['inventory']};check(len(inv)==len(d['inventory']),'Duplicate sources')
    for path in inv:
        check(not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts and '\\' not in path and ':' not in path,'Unsafe source path')
    check(len(d['rules'])==3 and {r['rule'] for r in d['rules']}==RULES,'Three distinct rules required')
    for r in d['rules']:
        check(r['status'] in {'complete','partial','unavailable'},'Invalid rule coverage')
        check(r['observed_finding_count']==len(r['findings']),'Observed count mismatch')
        check(r['finding_count']==(len(r['findings']) if r['status']=='complete' else None),'Missing data must not become zero')
        check(r['status']=='complete' or bool(r['limitations']),'Incomplete rule needs explanation')
        check(r['eligible_count'] is None or (isinstance(r['eligible_count'],int) and r['eligible_count']>=0),'Invalid denominator')
        check(isinstance(r['assessed_count'],int) and r['assessed_count']>=0,'Invalid coverage numerator')
        check(r['eligible_count'] is None or r['assessed_count']<=r['eligible_count'],'Coverage exceeds denominator')
        ids=set();api=set()
        for f in r['findings']+r['candidates']:
            check(f['rule']==r['rule'] and f['path'] in inv,'Finding outside rule/scope')
            check(f['source_sha256']==inv[f['path']]['sha256'],'Finding source mismatch')
            check(isinstance(f['line'],int) and 1<=f['line']<=inv[f['path']]['physical_lines'],'Invalid finding line')
            check(f['id']==digest(canonical([f['rule'],f['path'],f['line'],f['symbol']])),'Finding identity mismatch')
            check(f['id'] not in ids,'Duplicate finding');ids.add(f['id'])
            m=f['metrics']
            check(all(isinstance(v,(int,float)) and math.isfinite(v) for v in m.values()),'Non-finite metric')
            if r['rule']=='LongMethod':check(m['CC']>10,'Long Method threshold mismatch')
            if r['rule']=='GodClass':check(m['ATFD']>4 and m['WMC']>=47 and 0<=m['TCC']<1/3,'God Class conjunction mismatch')
            if r['rule']=='ObsoleteApiUsage':
                key=(f['path'],f['symbol']);check(key not in api,'API usage must be deduplicated per file/symbol');api.add(key)
                check(f['declaration_path'] in inv,'Source deprecation declaration outside inventory')
    return {r['rule']:{'status':r['status'],'count':r['finding_count'],'observed':r['observed_finding_count']} for r in d['rules']}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('files',type=Path,nargs='+')
    for p in ap.parse_args().files:print(p.name,json.dumps(validate(json.loads(p.read_text()))))
