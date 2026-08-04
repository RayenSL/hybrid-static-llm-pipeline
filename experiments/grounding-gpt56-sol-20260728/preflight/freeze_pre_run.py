#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SKIP = {"bin", "obj", ".git", ".vs", ".idea"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_ledger(path: Path, files: list[Path], relative_to: Path) -> None:
    lines=[]
    for item in sorted(set(files), key=lambda p: p.relative_to(relative_to).as_posix()):
        lines.append(f"{sha(item)}  {item.relative_to(relative_to).as_posix()}")
    path.write_text("\n".join(lines)+"\n", encoding="utf-8", newline="\n")


def main() -> None:
    script=Path(__file__).resolve()
    experiment=script.parent.parent
    repo=experiment.parent.parent
    corpus_repo=Path('/mnt/z/GitHub/hybrid-pipeline-corpus')
    corpus=corpus_repo/'corpus'
    manifest_path=experiment/'grounding-manifest.json'
    baseline_path=experiment/'grounding-baseline.jsonl'
    output=experiment/'PRE_RUN_AUDIT.json'
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing pre-run audit: {output}")
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    baseline=[json.loads(line) for line in baseline_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    if len(baseline)!=30 or Counter(row['anti_pattern_type'] for row in baseline)!=Counter({'god_class':10,'long_method':10,'obsolete_api_usage':10}):
        raise ValueError('unexpected 30-target baseline')
    assignments=manifest['assignments']
    if len(assignments)!=120 or len({row['assignment_id'] for row in assignments})!=120:
        raise ValueError('unexpected assignment dimensions')
    blocks={row['block_id'] for row in assignments}
    if len(blocks)!=30:
        raise ValueError('unexpected block count')
    expected={'minimal','structural','relational','full'}
    for block in blocks:
        levels={row['context_level'] for row in assignments if row['block_id']==block}
        if levels!=expected:
            raise ValueError(f'incomplete context block: {block}')
    if any((experiment/'campaign').iterdir()):
        raise ValueError('campaign output exists before pre-run freeze')

    pipeline_files=[
        repo/'src/HybridLens.CLI/Commands/GroundingCampaignCommand.cs',
        repo/'src/HybridLens.CLI/Commands/AnalyseCommand.cs',
        repo/'src/HybridLens.CLI/Program.cs',
        repo/'src/HybridLens.ContextBuilder/ContextBuilder.cs',
        repo/'src/HybridLens.ContextBuilder/PromptTemplate.cs',
        repo/'src/HybridLens.Pipeline/AnalysisPipeline.cs',
        repo/'src/HybridLens.Pipeline/RepairApplier.cs',
        repo/'src/HybridLens.Pipeline/RepairVerifier.cs',
        repo/'src/HybridLens.Core/Models/RunRecord.cs',
        repo/'src/HybridLens.CLI/appsettings.json',
    ]
    write_ledger(experiment/'preflight/PIPELINE_SHA256SUMS.txt', pipeline_files, repo)
    binary_files=sorted((repo/'src').glob('HybridLens.*/bin/Debug/net10.0/HybridLens*.dll'))
    if not binary_files:
        raise ValueError('no built HybridLens binaries found')
    write_ledger(experiment/'preflight/BINARY_SHA256SUMS.txt', binary_files, repo)
    corpus_files=[p for p in corpus.rglob('*') if p.is_file() and not any(part in SKIP for part in p.relative_to(corpus).parts)]
    write_ledger(experiment/'preflight/CORPUS_SHA256SUMS.txt', corpus_files, corpus_repo)
    truth_files=[p for p in (corpus_repo/'ground-truth').rglob('*') if p.is_file()]
    write_ledger(experiment/'preflight/GROUND_TRUTH_SHA256SUMS.txt', truth_files, corpus_repo)
    experiment_inputs=[
        experiment/'PROTOCOL.md',
        manifest_path,
        baseline_path,
        experiment/'preflight/static-output.json',
        experiment/'preflight/create_grounding_manifest.py',
        experiment/'preflight/model-config-snapshot.json',
        script,
    ]
    write_ledger(experiment/'preflight/EXPERIMENT_INPUT_SHA256SUMS.txt', experiment_inputs, experiment)
    credentials=[
        re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
        re.compile(r'(?i)authorization\s*:\s*bearer\s+\S+'),
        re.compile(r'(?i)(api[_ -]?key|access[_ -]?token)\s*[=:]\s*[A-Za-z0-9_./+-]{20,}'),
    ]
    hits=[]
    for item in experiment_inputs:
        text=item.read_text(encoding='utf-8-sig',errors='ignore')
        if any(pattern.search(text) for pattern in credentials):
            hits.append(item.relative_to(experiment).as_posix())
    if hits:
        raise ValueError(f'credential-shaped value found: {hits}')
    ledgers=[
        experiment/'preflight/PIPELINE_SHA256SUMS.txt',
        experiment/'preflight/BINARY_SHA256SUMS.txt',
        experiment/'preflight/CORPUS_SHA256SUMS.txt',
        experiment/'preflight/GROUND_TRUTH_SHA256SUMS.txt',
        experiment/'preflight/EXPERIMENT_INPUT_SHA256SUMS.txt',
    ]
    audit={
        'status':'pre_run_frozen',
        'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'campaign_id':manifest['campaign_id'],
        'manifest_sha256':sha(manifest_path),
        'baseline_sha256':sha(baseline_path),
        'targets':30,
        'assignments':120,
        'repetitions':1,
        'anti_pattern_targets':{'god_class':10,'long_method':10,'obsolete_api_usage':10},
        'context_levels':['minimal','structural','relational','full'],
        'evaluated_model':manifest['model_name'],
        'applier_model':manifest['applier_model'],
        'prompt_version':manifest['prompt_version'],
        'applier_prompt_version':manifest['applier_prompt_version'],
        'randomization_seed':manifest['randomization_seed'],
        'campaign_output_empty':True,
        'credential_shaped_value_scan':{'pass':True,'matching_files':[]},
        'ledger_sha256':{p.name:sha(p) for p in ledgers},
    }
    output.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8',newline='\n')
    freeze_files=experiment_inputs+ledgers+[output]
    write_ledger(experiment/'PRE_RUN_SHA256SUMS.txt',freeze_files,experiment)
    print(json.dumps(audit,sort_keys=True))

if __name__=='__main__':
    main()
