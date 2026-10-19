param(
    [Parameter(Mandatory = $true)][string]$VivadoBat,
    [ValidateRange(0.5,100.0)][double]$PeriodNs = 3.333333,
    [ValidateRange(1,32)][int]$Threads = 4,
    [string]$Part = 'xczu15eg-ffvb1156-2-i',
    [switch]$SkipDspExport
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = $PSScriptRoot
$vivado = (Resolve-Path -LiteralPath $VivadoBat -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $vivado -PathType Leaf)) { throw 'Pass the installed vivado.bat path.' }
if ($Part -notmatch '^xczu15eg-[a-z0-9]+-2-[a-z]$') { throw 'Part must be a complete ZU15EG -2 ordering code.' }
$manifest = Get-Content -LiteralPath (Join-Path $root 'input-sha256.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
    $path = Join-Path $root $entry.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing input: $($entry.Name). Extract the entire ZIP." }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Input hash mismatch: $($entry.Name). Extract a fresh copy."
    }
}
$provenance = Get-Content -LiteralPath (Join-Path $root 'provenance.json') -Raw | ConvertFrom-Json
$out = Join-Path $root ('runs\M53_Timing_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $out -Force | Out-Null
$period = $PeriodNs.ToString('0.000000',[Globalization.CultureInfo]::InvariantCulture)
$exportDsp = if ($SkipDspExport) { '0' } else { '1' }
[ordered]@{
    milestone='M53';top='SpinorVpu';part=$Part;mode='FreshImplement';
    implementation_period_ns=[double]::Parse($period,[Globalization.CultureInfo]::InvariantCulture);
    vivado_bat=$vivado;source_hashes=$manifest;provenance=$provenance;
    timing_scope='Standalone OOC; external IO timing and board clock location unspecified';
    post_route_SDF_simulation='NOT_RUN';export_DSP=($exportDsp -eq '1')
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $out 'run-inputs.json') -Encoding UTF8
$toolExit = 1
Push-Location $out
try {
    & $vivado -mode batch -notrace -source (Join-Path $root 'run_vivado.tcl') `
        -log (Join-Path $out 'vivado.log') -journal (Join-Path $out 'vivado.jou') `
        -tclargs $period $out $Threads $Part $exportDsp
    $toolExit = $LASTEXITCODE
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $out 'launch-error.txt') -Encoding UTF8
} finally { Pop-Location }
& (Join-Path $root 'pack_results.ps1') -RunDirectory $out
if ($toolExit -ne 0) { throw "Vivado failed (exit $toolExit); upload the report ZIP for diagnosis." }
Write-Host 'Finished. Read run-summary.txt and timing_routed.rpt; Vivado exit 0 alone does not mean timing passed.'
