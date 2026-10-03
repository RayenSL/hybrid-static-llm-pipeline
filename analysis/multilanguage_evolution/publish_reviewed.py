"""Publish descriptive, explicitly provisional measurements with replay evidence."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
CASES={'odoo__odoo':('Odoo','python'),'jenkinsci__jenkins':('Jenkins','java'),'apache__tomcat':('Apache Tomcat','java')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--campaign',type=Path,required=True);ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--plot-packages',type=Path,required=True);a=ap.parse_args()
    sys.path.insert(0,str(a.packages.resolve()));sys.path.insert(0,str(HERE/'ingest'))
    from validate import validate
    rows=[];evidence=[]
    for repo,(title,lang) in CASES.items():
        hist=json.loads((HERE/'selection/histories'/f'{repo}.json').read_text())
        for obs in hist['observations']:
            name=f"{repo}-{obs['label']}-{lang}.json";paths=[a.campaign/p/name for p in ['A','B','offline']]
            hashes=[sha(p) for p in paths]
            if len(set(hashes))!=1:raise ValueError('Replay differs: '+name)
            d=json.loads(paths[0].read_text());validate(d)
            if d['commit']!=obs['commit']:raise ValueError('Commit mismatch')
            s=d['summary'];ok=d['status']['syntax']=='complete'
            language_counts=obs['inventory']['tracked_language_files']
            row={'repository':title,'language':lang,'label':obs['label'],'year':int(obs['label'][-4:]),'commit':d['commit'],'actual_commit_date':obs['committer_date'],'syntax':d['status']['syntax'],'scientific_admission':False,'eligible_files':s['eligible_files'],'parsed_files':s['parsed_files'],'physical_lines':s['physical_lines'],'eligible_definitions':s['definition_count'] if ok else None,'flagged_gt10':s['finding_count'] if ok else None,'prevalence_pct_gt10':100*s['prevalence'] if ok and s['prevalence'] is not None else None,'prevalence_pct_gt15':100*s['sensitivity_counts']['15']/s['definition_count'] if ok and s['definition_count'] else None,'prevalence_pct_gt20':100*s['sensitivity_counts']['20']/s['definition_count'] if ok and s['definition_count'] else None,'tracked_files_in_language':language_counts.get(lang,0),'tracked_other_recognised_language_files':sum(v for k,v in language_counts.items() if k not in [lang,'other']),'scope_sha256':d['scope_sha256'],'result_sha256':hashes[0],'replay_identical':True}
            rows.append(row);evidence.append({'file':name,'hashes':dict(zip(['A','B','offline'],hashes)),'diagnostics':d['diagnostics'],'archive_sha256':d['archive_sha256'],'adapter':d['tool']})
    out=HERE/'results';out.mkdir(exist_ok=True)
    with (out/'annual-measurements.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out/'replay-evidence.json').write_text(json.dumps({'status':'All three passes identical','observations':len(rows),'method':'Same sealed source archives copied to separate input paths; each pass recalculates and validates all findings. Python sockets blocked. This establishes computational repeatability, not an independent implementation or a fresh Git export.','records':evidence},indent=2)+'\n')
    sys.path.insert(0,str(a.plot_packages.resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.hashsalt':'cross-language-evolution-v1','pdf.fonttype':42})
    fig,axes=plt.subplots(4,3,figsize=(11.5,9),sharex=True,layout='constrained')
    colours=['#0072B2','#D55E00','#009E73']
    keys=['prevalence_pct_gt10','flagged_gt10','eligible_definitions','physical_lines']
    labels=['Flagged definitions (%)','Flagged definitions (count)','Eligible definitions (count)','Eligible source (kPLOC)']
    for col,(repo,(title,lang)) in enumerate(CASES.items()):
        rr=[r for r in rows if r['repository']==title];xx=[r['year'] for r in rr]
        axes[0,col].set_title(f'{title} ({lang.title()})')
        for i,key in enumerate(keys):
            ax=axes[i,col];yy=[r[key] if r[key] is not None else np.nan for r in rr]
            if i==3:yy=[v/1000 for v in yy]
            ax.plot(xx,yy,color=colours[0],marker='o',markersize=2.8,linewidth=1.3,label='CC > 10' if i==0 else None)
            if i==0:
                for threshold,colour,style in [(15,colours[1],'--'),(20,colours[2],':')]:
                    ax.plot(xx,[r[f'prevalence_pct_gt{threshold}'] if r[f'prevalence_pct_gt{threshold}'] is not None else np.nan for r in rr],color=colour,linestyle=style,linewidth=1,label=f'CC > {threshold}')
            for r in rr:
                if r['syntax']!='complete':ax.axvspan(r['year']-.22,r['year']+.22,color='grey',alpha=.15)
            ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
            ax.ticklabel_format(axis='y',style='plain');ax.set_xticks([2006,2010,2015,2020,2026]);ax.set_xlim(2005.5,2026.5)
            if col==0:ax.set_ylabel(labels[i])
        axes[3,col].set_xlabel('Snapshot year')
    upper=max(ax.get_ylim()[1] for ax in axes[0]);
    for ax in axes[0]:ax.set_ylim(0,upper)
    axes[0,0].legend(fontsize=8,frameon=False)
    fig.suptitle('Annual complexity trajectories — provisional detector measurements',fontsize=13)
    fig.supxlabel('Grey bands: incomplete parsing; no finding count or prevalence reported. 2026 is a partial-year endpoint.',fontsize=8)
    figures=HERE/'figures';figures.mkdir(exist_ok=True)
    for extension in ['pdf','svg','png']:
        metadata={'CreationDate':None,'ModDate':None} if extension=='pdf' else {'Date':None} if extension=='svg' else None
        fig.savefig(figures/f'three_codebases_annual_timeline.{extension}',dpi=180,metadata=metadata)
    lines=['# Three-codebase annual analysis','', '**Status: provisional, not yet admitted as thesis evidence.**', '', 'The reviewed campaign covers 21 snapshots per case: the earliest source state in 2006, annual selections for 2007–2025, and the fixed September 2026 endpoint. All 63 outputs are byte-identical across A, B and socket-blocked replay.', '', '| Case | Complete snapshots | Earliest: flagged / eligible (%) | Latest complete: flagged / eligible (%) | Latest complete year |','|---|---:|---:|---:|---:|']
    for _,(title,_) in CASES.items():
        rr=[r for r in rows if r['repository']==title];valid=[r for r in rr if r['syntax']=='complete'];first,last=valid[0],valid[-1]
        def value(r):return f"{r['flagged_gt10']:,} / {r['eligible_definitions']:,} ({r['prevalence_pct_gt10']:.2f}%)"
        lines.append(f"| {title} | {len(valid)}/{len(rr)} | {value(first)} | {value(last)} | {last['year']} |")
    lines+=['','## Meaning of the measurements','','Prevalence is 100 × named definitions with CC > 10 / all eligible named definitions with bodies. Python functions and Java methods/constructors are the units. Abstract declarations and anonymous functions are excluded. This is a complexity-based condition, not a God Class detector. No combined anti-pattern total is calculated.','','Physical lines of eligible source (PLOC, including comments and blank lines) indicate the size of the analysed language layer. Eligible-definition counts provide the actual prevalence denominator. Raw finding counts and size use separate axes; prevalence uses the same scale in all three columns. The figure retains missing observations without interpolation.','','The > 15 and > 20 curves show threshold sensitivity. No trajectory establishes that the same problematic definitions survived between snapshots, that defects were confirmed, or that one project or language is better than another. Odoo covers Python; Jenkins and Tomcat cover Java. Tracked-language file counts in the CSV expose unanalysed recognised languages but are not a percentage of all production code.','','## Scope review','','Reviewed exclusions remove known bundled libraries, framework test add-ons, packaging files and documentation examples. Odoo account_test is retained because its manifest describes user-facing accounting-consistency checks. This is a targeted single-reviewer provenance audit, not an exhaustive ownership assessment. Exact scopes are in protocols/; source-header evidence is in scope-review-evidence.json. Earlier feasibility outputs remain unchanged.','','## Reproduction and outstanding validation','','All findings are recalculated for each pass; no aggregate is copied from another pass. The source archives are the same sealed Git exports, copied to distinct paths. The replay therefore demonstrates computational repeatability, not independent Git acquisition or independent algorithm agreement. Full outputs are in ignored tmp/multilanguage-evolution/reviewed-campaign-v1; hashes and the plotted CSV are retained here.','','The original feasibility contract remains admitted=false. Empirical Java rule validation, legacy-Python validation, exhaustive scope review and current source build/runtime checks remain incomplete. No Java runtime was found and neither the WSL nor Windows Docker endpoint was usable during this run. These limitations do not make syntax counts zero; they prevent final case admission under the agreed protocol. Consult python-ast-validation.json for the separate modern-Python comparison when present.','','No thesis subsection has been replaced with these provisional results.']
    (out/'ANALYSIS.md').write_text('\n'.join(lines)+'\n')
    print('Published',len(rows),'replayed observations',flush=True)
if __name__=='__main__':main()
