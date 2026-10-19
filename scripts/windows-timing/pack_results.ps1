param(
    [Parameter(Mandatory = $true)][string]$RunDirectory,
    [string]$DestinationZip = '',
    [switch]$Full
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$out = (Resolve-Path -LiteralPath $RunDirectory -ErrorAction Stop).Path.TrimEnd([char[]]@('\','/'))
$inputs = Get-Content -LiteralPath (Join-Path $out 'run-inputs.json') -Raw | ConvertFrom-Json
if ($inputs.milestone -ne 'M53' -or $inputs.top -ne 'SpinorVpu') { throw 'Expected an M53 SpinorVpu timing run.' }
if (-not $DestinationZip) {
    $bundleRoot = Split-Path -Parent (Split-Path -Parent $out)
    $kind = if ($Full) { 'full' } else { 'reports' }
    $DestinationZip = Join-Path $bundleRoot ('spinor_results_'+(Split-Path -Leaf $out)+'_'+$kind+'_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')+'.zip')
}
$zip = [System.IO.Path]::GetFullPath($DestinationZip)
if ($zip.StartsWith($out+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Destination must be outside the run directory.' }
if (Test-Path -LiteralPath $zip) { throw "Destination already exists: $zip" }
$files = @(Get-ChildItem -LiteralPath $out -File -Recurse | Where-Object {
    $_.FullName -notmatch '[\\/]\.Xil[\\/]' -and
    $_.FullName -ne (Join-Path $out 'output-sha256.json') -and
    ($Full -or ($_.DirectoryName -eq $out -and $_.Extension -match '^\.(rpt|txt|json|xdc|log|jou)$'))
})
$hashes = [ordered]@{}
foreach ($file in $files) {
    $relative = $file.FullName.Substring($out.Length+1).Replace('\','/')
    $hashes[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashPath = Join-Path $out 'output-sha256.json'
$hashes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $hashPath -Encoding UTF8
$files += Get-Item -LiteralPath $hashPath
$archive = [System.IO.Compression.ZipFile]::Open($zip,[System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($out.Length+1).Replace('\','/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,$relative,[System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally { $archive.Dispose() }
Write-Host "Result folder: $out"
Write-Host "Upload this ZIP: $zip"
if (-not $Full -and (Get-Item -LiteralPath $zip).Length -gt 32MB) { Write-Warning 'Report ZIP exceeds 32MiB; send run-summary.txt and timing_routed.rpt first.' }
