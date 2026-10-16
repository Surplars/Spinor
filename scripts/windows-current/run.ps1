param(
    [Parameter(Mandatory = $true)][string]$VivadoBat,
    [ValidateSet('All','Rtl','Implement')][string]$Mode = 'All',
    [ValidateRange(0.5,100.0)][double]$PeriodNs = 3.333333,
    [ValidateRange(1,32)][int]$Threads = 4
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$vivado = (Resolve-Path -LiteralPath $VivadoBat -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $vivado -PathType Leaf)) { throw 'Pass the installed vivado.bat path.' }
$manifest = Get-Content -LiteralPath (Join-Path $root 'input-sha256.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
    $path = Join-Path $root $entry.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing input: $($entry.Name). Extract the entire ZIP." }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) { throw "Input hash mismatch: $($entry.Name). Extract a fresh copy." }
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$out = Join-Path $root ("runs\M31_{0}_{1}" -f $Mode,$stamp)
New-Item -ItemType Directory -Path $out -Force | Out-Null
$period = $PeriodNs.ToString('0.000000',[Globalization.CultureInfo]::InvariantCulture)
[ordered]@{
    milestone='M31';top='SpinorVpu';part='xczu15eg-ffvb1156-2-i';mode=$Mode;
    implementation_period_ns=$PeriodNs;vivado_bat=$vivado;source_hashes=$manifest;
    simulation_scope='Functional self-checks; TB clock is not a 300MHz timing proof';
    timing_scope='Fresh standalone OOC; host IO delays and board clock location unspecified'
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'run-inputs.json') -Encoding UTF8
$toolExit = 1
Push-Location $out
try {
    & $vivado -mode batch -notrace -source (Join-Path $root 'run_vivado.tcl') `
        -log (Join-Path $out 'vivado.log') -journal (Join-Path $out 'vivado.jou') `
        -tclargs $Mode $period $out $Threads
    $toolExit = $LASTEXITCODE
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $out 'launch-error.txt') -Encoding UTF8
} finally {
    Pop-Location
}
# Include nested XSim logs/TBs, WDB and DSP data; omit only tool working caches.
$files = @(Get-ChildItem -LiteralPath $out -File -Recurse | Where-Object {
    $_.FullName -notmatch '[\\/]\.Xil[\\/]' -and $_.FullName -notmatch '[\\/]xsim\.dir[\\/]'
})
$hashes = [ordered]@{}
foreach ($file in $files) {
    $relative = $file.FullName.Substring($out.Length+1).Replace('\','/')
    $hashes[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'output-sha256.json') -Encoding UTF8
$files += Get-Item -LiteralPath (Join-Path $out 'output-sha256.json')
$zip = Join-Path $root ("spinor_results_M31_{0}_{1}.zip" -f $Mode,$stamp)
# ZipArchive streams files, supports >2GB and preserves relative paths.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open($zip,[System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($out.Length+1).Replace('\','/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,$relative,[System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally { $archive.Dispose() }
Write-Host "Result folder: $out"
Write-Host "Upload this ZIP: $zip"
if ($toolExit -ne 0) { throw "Vivado failed (exit $toolExit); upload the result ZIP for diagnosis." }
Write-Host 'Flow finished. Check run-summary.txt and timing_routed.rpt; tool success does not mean timing passed.'
