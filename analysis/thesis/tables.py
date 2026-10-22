"""Export the quantitative tables in the 22 October 2026 thesis as CSV.

Reads retained evidence only. Private industrial context counts are a labelled
transcription of Table 5.9; --industrial-summary replaces it with a regenerated
industrial summary. Conceptual/literature tables are manually authored.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / 'data'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def write(out, name, rows):
    if not rows:
        raise ValueError(f'No data for {name}')
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (out / f'{name}.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def factorial_tables(base, out):
    attempts = read(base/'results/factorial-summary/attempts.json')
    groups = defaultdict(list)
    for row in attempts:
        groups[(row['control_structure'], row['grounding_enabled'], row['visible_tests_enabled'])].append(row)
    outcomes, resources = [], []
    for (control, grounding, tests), rows in sorted(groups.items(), key=lambda pair: (pair[0][0] == 'iterative', *pair[0][1:])):
        identity = dict(grounding=grounding, control=control, visible_tests=tests, assignments=len(rows))
        outcomes.append({**identity, 'built': sum(r['build_passed'] is True for r in rows),
                         'resolved': sum(r['metric_resolved'] is True for r in rows),
                         'private_pass': sum(r['private_test_passed'] is True for r in rows),
                         'strict_success': sum(r['strict_success'] is True for r in rows)})
        observed = [r for r in rows if r.get('total_tokens') is not None]
        resources.append({**identity, 'token_observed': len(observed),
                          'mean_tokens': sum(r['total_tokens'] for r in observed)/len(observed) if observed else None,
                          'mean_calls': sum(r['llm_calls'] for r in rows)/len(rows)})
    write(out, 'table_5_4_factorial_outcomes', outcomes)
    write(out, 'table_C_2_factorial_resources', resources)
    quality = jsonl(base/'quality-results/layer2-quality.jsonl')
    quality_rows = []
    for label, key in [('Study detectors', 'smell_total'), ('Default analyser view', 'ca_headline'), ('All analyser view', 'ca_all')]:
        values = [r[key+'_after']-r[key+'_before'] for r in quality
                  if r.get(key+'_before') is not None and r.get(key+'_after') is not None]
        quality_rows.append(dict(instrument=label, states=len(values), decreased=sum(v<0 for v in values),
                                 unchanged=sum(v==0 for v in values), increased=sum(v>0 for v in values),
                                 mean_change=sum(values)/len(values)))
    write(out, 'table_5_5_whole_solution_quality', quality_rows)
    with (base/'results/statistical-analysis/paired_risk_differences.csv').open(encoding='utf-8-sig', newline='') as handle:
        contrasts = [r for r in csv.DictReader(handle) if r['contrast'] in ('grounding_main','iteration_main','visible_test_main')]
    write(out, 'table_5_6_paired_factorial_effects', contrasts)


def context_tables(summary, industrial, out):
    levels = read(summary)['levels']
    write(out, 'table_5_8_corpus_context', [{
        'context': r['level'], 'assigned': r['n'], 'built': r['n']-r['build_fails'],
        'resolved': r['resolved'], 'oracle_pass': r['layer3_pass'],
        'resolved_and_oracle_pass': r['detector_resolved_and_layer3_pass'],
    } for r in levels])
    write(out, 'table_C_3_context_diagnostics', [{
        'context': r['level'], 'scored': r['quality_scored_n'],
        'study_detectors': r['smell_delta_mean'], 'default_view': r['ca_headline_delta_mean'],
        'all_view': r['ca_all_delta_mean'],
    } for r in levels])
    if industrial:
        # Preserve the source summary's native columns and descriptive denominator.
        write(out, 'table_5_9_industrial_context', read(industrial)['levels'])
    else:
        with (DATA/'industrial_context_reported.csv').open(newline='') as handle:
            write(out, 'table_5_9_industrial_context', list(csv.DictReader(handle)))


def contrast_row(label, r):
    return dict(comparison=label, mean=r['mean'], ci90_low=r['ci90'][0], ci90_high=r['ci90'][1],
                implemented_margin=r['sesoi'], equivalent=r['equivalent'])


def maintenance_tables(aggregates, out):
    d = read(aggregates)['results']
    write(out, 'table_5_10_starting_states', [
        contrast_row('v0.3 corpus', d['corpus_introductions']['R_minus_O_new_findings']),
        *[contrast_row(label, d[key]['secondary']['replication']['N_RN_minus_ON'])
          for key,label in [('gpt','v0.4 gpt-5.6-sol'),('opus','v0.6 Opus')]]])
    rows = []
    sensitivities = []
    for key, model in [('gpt','gpt-5.6-sol'),('opus','Claude Opus 5.5')]:
        study = d[key]
        for arm, values in study['secondary']['new_findings_per_arm'].items():
            rows.append(dict(model=model, arm=arm, mean_findings=values['mean'],
                             affected_targets=values['targets_with_new'], targets=len(study['corpus_plot_data']),
                             completed_steps=study['derived']['completed_steps'][arm],
                             assigned_steps=study['derived']['assigned_steps_per_arm'],
                             tokens_per_step=study['secondary']['tokens_per_completed_step'][arm]))
        for name, value in study['sensitivity'].items():
            families = value.items() if name == '3_by_type' else [(name,value)]
            for family, contrasts in families:
                for contrast in ('H3','H4'):
                    r = contrasts[contrast]
                    sensitivities.append(dict(model=model, sensitivity=family, contrast=contrast, mean=r['mean'],
                                              ci95_low=r['ci95'][0], ci95_high=r['ci95'][1],
                                              p_holm=r['p_holm'], supported=r['supported']))
    write(out, 'table_5_12_maintenance_outcomes', rows)
    write(out, 'table_C_5_maintenance_sensitivities', sensitivities)
    write(out, 'table_5_13_introduction_gate_passage', [dict(population=key, successes=d['shadow'][key]['successes'],
          units=d['shadow'][key]['n'], ci95_low=d['shadow'][key]['ci95'][0], ci95_high=d['shadow'][key]['ci95'][1])
          for key in ('primary_oracle_units','static_only_units','all_eligible')])
    write(out, 'table_C_4_industrial_replay', [contrast_row(name, r)
          for section in ('confirmatory','secondary') for name,r in d['industrial_replay'][section].items()])


def qualitative_tables(out):
    d = read(DATA/'qualitative/evidence.json')
    write(out, 'table_5_7_slotfinder', [r for r in d['initial_repair_attempts'] if r['control_structure']=='single_shot'])
    write(out, 'table_5_11_allocate_complexity', [dict(state=f'S{i}', original=o, repaired=r)
          for i,(o,r) in enumerate(zip(d['rq3_allocate_cc']['original'], d['rq3_allocate_cc']['repaired']))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--section', choices=['all','factorial','context','maintenance'], default='all')
    parser.add_argument('--factorial', type=Path, default=ROOT/'experiments/confirmatory-v2-gpt56-sol-20260812')
    parser.add_argument('--corpus-summary', type=Path, default=ROOT/'experiments/context-ladder-corpus-v2-20260816/analysis-results/summary.json')
    parser.add_argument('--industrial-summary', type=Path)
    parser.add_argument('--maintenance-data', type=Path, default=DATA/'maintenance_aggregates.json')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = []
    if args.section in ('all','factorial'):
        factorial_tables(args.factorial, args.out)
        sources += [args.factorial/rel for rel in ['results/factorial-summary/attempts.json',
                    'quality-results/layer2-quality.jsonl','results/statistical-analysis/paired_risk_differences.csv']]
    if args.section in ('all','context'):
        context_tables(args.corpus_summary, args.industrial_summary, args.out)
        sources += [args.corpus_summary, args.industrial_summary or DATA/'industrial_context_reported.csv']
    if args.section in ('all','maintenance'):
        maintenance_tables(args.maintenance_data, args.out)
        sources.append(args.maintenance_data)
    if args.section == 'all':
        qualitative_tables(args.out)
        sources.append(DATA/'qualitative/evidence.json')
    (args.out/'provenance.json').write_text(json.dumps({
        'sources': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
        'industrial_context': 'Recomputed summary' if args.industrial_summary else 'Reported Table 5.9 transcription; private raw records required for independent recomputation',
        'factorial_effect_units': 'Proportions; multiply estimates and confidence bounds by 100 for percentage points',
    },indent=2)+'\n')
    print(f'Exported {len(list(args.out.glob("*.csv")))} thesis tables to {args.out}')


if __name__ == '__main__':
    main()
