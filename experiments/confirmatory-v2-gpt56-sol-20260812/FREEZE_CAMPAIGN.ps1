$ErrorActionPreference = 'Stop'

$experiment = $PSScriptRoot
$pipeline = 'Z:\GitHub\hybrid-static-llm-pipeline'
$corpus = 'Z:\GitHub\hybrid-pipeline-corpus'
$cli = Join-Path $pipeline 'src\HybridLens.CLI\HybridLens.CLI.csproj'
$readinessPath = Join-Path $experiment 'RUN_READINESS.json'
$manifestPath = Join-Path $experiment 'factorial-manifest.json'

& python (Join-Path $pipeline 'analysis\prepare_v2_run.py') `
    --corpus $corpus --pipeline $pipeline --out $experiment --refresh
if ($LASTEXITCODE -ne 0) { throw 'Readiness refresh failed.' }

$readiness = Get-Content -Raw $readinessPath | ConvertFrom-Json
$failedStructural = @($readiness.gates.PSObject.Properties | Where-Object { -not $_.Value })
if ($failedStructural.Count -gt 0) {
    throw "Release gates are still closed: $($failedStructural.Name -join ', ')"
}
if (-not $readiness.preparation_gates.baseline_frozen) { throw 'The 26-target baseline is not frozen.' }
if (-not $readiness.preparation_gates.visible_test_generation_complete) {
    throw 'Exactly 26 visible-test generation artefacts are required.'
}
if (Test-Path -LiteralPath $manifestPath) { throw 'Refusing to overwrite an existing factorial manifest.' }

& dotnet run --project $cli -- factorial-manifest `
    --from (Join-Path $experiment 'baseline.jsonl') `
    --target (Join-Path $corpus 'corpus\Corpus.sln') `
    --visible-tests (Join-Path $experiment 'generated-tests') `
    --model 'gpt-5.6-sol' `
    --code-revision '62955d325db8abb43d5d71c093cf8580f795b44c' `
    --runs 3 `
    --budget 6 `
    --build-timeout 180 `
    --max-input-tokens 120000 `
    --seed 20260812 `
    --out $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'Factorial manifest creation failed.' }

$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
if ($manifest.assignments.Count -ne 624) {
    throw "Expected 624 assignments, found $($manifest.assignments.Count)."
}

& python (Join-Path $pipeline 'analysis\prepare_v2_run.py') `
    --corpus $corpus --pipeline $pipeline --out $experiment --refresh
if ($LASTEXITCODE -ne 0) { throw 'Final readiness refresh failed.' }

Write-Host 'Campaign manifest frozen. No repair assignment has been launched.'
