$ErrorActionPreference = 'Stop'

$experiment = $PSScriptRoot
$pipeline = 'Z:\GitHub\hybrid-static-llm-pipeline'
$corpus = 'Z:\GitHub\hybrid-pipeline-corpus'
$cli = Join-Path $pipeline 'src\HybridLens.CLI\HybridLens.CLI.csproj'
$baseline = Join-Path $experiment 'baseline.jsonl'
$target = Join-Path $corpus 'corpus\Corpus.sln'
$output = Join-Path $experiment 'generated-tests'
$targets = Get-Content -Raw (Join-Path $experiment 'preflight\TARGETS.json') | ConvertFrom-Json

if (-not (Test-Path -LiteralPath $baseline)) { throw 'Frozen baseline is missing.' }
if ($targets.Count -ne 26) { throw "Expected 26 targets, found $($targets.Count)." }

foreach ($item in $targets) {
    $alreadyRecorded = Get-ChildItem -LiteralPath $output -Filter '*.json' -File | Where-Object {
        try {
            $artifact = Get-Content -Raw $_.FullName | ConvertFrom-Json
            $artifact.source_file -eq $item.source_file
        }
        catch { $false }
    }
    $arguments = @(
        'run', '--project', $cli, '--', 'generate-characterization-test',
        '--from', $baseline,
        '--target', $target,
        '--source', $item.source_file,
        '--model', 'gpt-5.6-sol',
        '--out', $output,
        '--baseline-runs', '3',
        '--timeout', '180'
    )
    if ($alreadyRecorded) {
        if ($alreadyRecorded.Count -ne 1) { throw "Multiple artefacts exist for $($item.instance_id)." }
        $persisted = Get-Content -Raw $alreadyRecorded.FullName | ConvertFrom-Json
        if ($persisted.admission_status -eq 'parse_failed' -and
            $persisted.generation_call_count -eq 1 -and
            $null -eq $persisted.raw_llm_output) {
            Write-Host "RESUME $($item.instance_id): reuse persisted planning call"
            $arguments += @('--resume-artifact', $alreadyRecorded.FullName)
        }
        else {
            Write-Host "SKIP $($item.instance_id): a terminal persisted artefact already exists"
            continue
        }
    }
    else {
        Write-Host "GENERATE $($item.instance_id): $($item.symbol_name)"
    }

    & dotnet @arguments
    if ($LASTEXITCODE -ne 0) { throw "Generation command failed for $($item.instance_id)." }
}

& python (Join-Path $pipeline 'analysis\prepare_v2_run.py') `
    --corpus $corpus --pipeline $pipeline --out $experiment --refresh
if ($LASTEXITCODE -ne 0) { throw 'Readiness refresh failed.' }
