param(
    [Parameter(Mandatory = $true)][string]$PreviousRun,
    [string]$VivadoBat = '',
    [ValidateRange(1,32)][int]$Threads = 4,
    [switch]$SkipDspExport
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $root 'input-sha256.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
    $path = Join-Path $root $entry.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing input: $($entry.Name). Extract the entire ZIP." }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Input hash mismatch: $($entry.Name)" }
}
$previous = (Resolve-Path -LiteralPath $PreviousRun -ErrorAction Stop).Path
$prior = Get-Content -LiteralPath (Join-Path $previous 'run-inputs.json') -Raw | ConvertFrom-Json
if ($prior.milestone -ne 'M53' -or $prior.top -ne 'SpinorVpu' -or $prior.part -notmatch '^xczu15eg-[a-z0-9]+-2-[a-z]$') { throw 'Expected an M53 ZU15EG -2 Spinor run.' }
if ($prior.source_hashes.'rtl/SpinorVpu.sv' -ne $manifest.'rtl/SpinorVpu.sv' -or $prior.provenance.rtl_sha256 -ne $manifest.'rtl/SpinorVpu.sv') { throw 'Previous run RTL does not match this bundle.' }
$checkpoint = (Resolve-Path -LiteralPath (Join-Path $previous 'routed.dcp') -ErrorAction Stop).Path
if (-not $VivadoBat) { $VivadoBat = $prior.vivado_bat }
$vivado = (Resolve-Path -LiteralPath $VivadoBat -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $vivado -PathType Leaf)) { throw 'Pass the installed vivado.bat path.' }
$out = Join-Path $root ('runs\M53_Resume_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $out -Force | Out-Null
$exportDsp = if ($SkipDspExport) { '0' } else { '1' }
[ordered]@{
    milestone='M53';top='SpinorVpu';part=$prior.part;mode='ResumeReports';
    previous_run=$previous;checkpoint=$checkpoint;
    checkpoint_sha256=(Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash.ToLowerInvariant();
    previous_inputs_sha256=(Get-FileHash -LiteralPath (Join-Path $previous 'run-inputs.json') -Algorithm SHA256).Hash.ToLowerInvariant();
    vivado_bat=$vivado;source_hashes=$manifest;prior_run_inputs=$prior;
    implementation_repeated=$false;clock_constraint='Preserve checkpoint clock';export_DSP=($exportDsp -eq '1')
} | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath (Join-Path $out 'run-inputs.json') -Encoding UTF8
$toolExit = 1
Push-Location $out
try {
    & $vivado -mode batch -notrace -source (Join-Path $root 'resume_vivado.tcl') `
        -log (Join-Path $out 'vivado.log') -journal (Join-Path $out 'vivado.jou') `
        -tclargs $checkpoint $out $Threads $prior.part $exportDsp
    $toolExit = $LASTEXITCODE
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $out 'launch-error.txt') -Encoding UTF8
} finally { Pop-Location }
& (Join-Path $root 'pack_results.ps1') -RunDirectory $out
if ($toolExit -ne 0) { throw "Vivado report/export failed (exit $toolExit); upload the report ZIP. Original checkpoint is unchanged." }
Write-Host 'Report/export finished. Original synthesis, placement, routing and clock constraints were preserved.'
