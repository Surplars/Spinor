param(
    [Parameter(Mandatory = $true)][string]$RunDirectory,
    [string]$DestinationZip = ''
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 requires both assemblies explicitly, before enum use.
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$out = (Resolve-Path -LiteralPath $RunDirectory -ErrorAction Stop).Path.TrimEnd([char[]]@('\','/'))
$inputsPath = Join-Path $out 'run-inputs.json'
$inputs = Get-Content -LiteralPath $inputsPath -Raw | ConvertFrom-Json
if ($inputs.top -ne 'SpinorVpu' -or $inputs.milestone -ne 'M31') {
    throw 'Expected an M31 SpinorVpu run directory containing run-inputs.json.'
}
if (-not $DestinationZip) {
    $bundleRoot = Split-Path -Parent (Split-Path -Parent $out)
    $label = Split-Path -Leaf $out
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    $DestinationZip = Join-Path $bundleRoot ("spinor_results_{0}_packed_{1}.zip" -f $label,$stamp)
}
$zip = [System.IO.Path]::GetFullPath($DestinationZip)
if ($zip.StartsWith($out+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination ZIP must be outside the run directory.'
}
if (Test-Path -LiteralPath $zip) { throw "Destination already exists: $zip" }
$files = @(Get-ChildItem -LiteralPath $out -File -Recurse | Where-Object {
    $_.FullName -notmatch '[\\/]\.Xil[\\/]' -and
    $_.FullName -notmatch '[\\/]xsim\.dir[\\/]' -and
    $_.FullName -ne (Join-Path $out 'output-sha256.json')
})
# Exclude an earlier output-sha256.json: it cannot hash itself and must appear
# exactly once in a repacked ZIP, including when a previous packing failed.
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
