"""Compare independent CST implementations on legacy files both parsers accept."""
import argparse,json,sys,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--results',type=Path,required=True);a=ap.parse_args()
    sys.path.insert(0,str(a.packages.resolve()));sys.path.insert(0,str(HERE/'detectors'))
    from syntax_probe import analyse
    from legacy_python import analyse as legacy_analyse
    from tree_sitter import Language,Parser
    import tree_sitter_python
    parser=Parser(Language(tree_sitter_python.language()));report={'status':'Legacy/modern CST overlap only; not validation of unsupported legacy syntax','snapshots':[]}
    for label in ['earliest-2006','2010','2016','2017']:
        name='odoo__odoo-'+label;d=json.loads((a.results/(name+'-python.json')).read_text());parsed=set();observed={};failures=[];fresh=[]
        with tarfile.open(a.sources/(name+'.tar')) as tar:
            for item in d['inventory']:
                path=item['path'];data=tar.extractfile(path).read();defs,errors=analyse(data,path,'python',parser)
                if errors:failures.append(path);continue
                parsed.add(path)
                legacy,legacy_errors=legacy_analyse(data,path,python3_mode=label=='2017')
                if legacy_errors:raise ValueError('Legacy parser regression: '+path)
                fresh.extend(legacy)
                for x in defs:observed[(path,x['span']['line_start'],x['symbol'].split('.')[-1])]=x['metrics']['cyclomatic_complexity']
        expected={(x['path'],x['span']['line_start'],x['symbol'].split('.')[-1]):x['metrics']['cyclomatic_complexity'] for x in fresh if x['path'] in parsed}
        mismatches=[{'path':k[0],'line':k[1],'name':k[2],'legacy':expected.get(k),'modern':observed.get(k)} for k in sorted(expected.keys()|observed.keys()) if expected.get(k)!=observed.get(k)]
        report['snapshots'].append({'label':label,'eligible_files':len(d['inventory']),'overlap_files':len(parsed),'compared_definitions':len(expected),'matching':sum(expected.get(k)==v for k,v in observed.items()),'mismatches':mismatches,'unsupported_by_modern_parser':failures})
        print(label,len(expected),len(mismatches),len(failures),flush=True)
    (HERE/'results/legacy-overlap-validation.json').write_text(json.dumps(report,indent=2)+'\n')
