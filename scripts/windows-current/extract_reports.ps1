param(
    [Parameter(Mandatory = $true)][string]$ResultZip,
    [string]$DestinationZip = ''
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$sourcePath = (Resolve-Path -LiteralPath $ResultZip -ErrorAction Stop).Path
if (-not $DestinationZip) {
    $parent = Split-Path -Parent $sourcePath
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($sourcePath)
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    $DestinationZip = Join-Path $parent ("{0}_reports_{1}.zip" -f $baseName,$stamp)
}
$targetPath = [System.IO.Path]::GetFullPath($DestinationZip)
if (Test-Path -LiteralPath $targetPath) { throw "Destination already exists: $targetPath" }
$source = [System.IO.Compression.ZipFile]::OpenRead($sourcePath)
$target = $null
$count = 0
try {
    $target = [System.IO.Compression.ZipFile]::Open($targetPath,[System.IO.Compression.ZipArchiveMode]::Create)
    foreach ($entry in $source.Entries) {
        $name = $entry.FullName.Replace('\','/')
        if ($name -match '(^|/)(\.Xil|xsim\.dir)(/|$)') { continue }
        $rootReport = $name -notmatch '/' -and $name -match '\.(rpt|txt|json|xdc|log|jou)$'
        $simulationLog = $name -match '^simulation/' -and $name -match '(\.log$|/(simulation-logs|result)\.txt$)'
        if (-not ($rootReport -or $simulationLog)) { continue }
        $copy = $target.CreateEntry($name,[System.IO.Compression.CompressionLevel]::Optimal)
        $inputStream = $entry.Open()
        $outputStream = $null
        try {
            $outputStream = $copy.Open()
            $inputStream.CopyTo($outputStream)
        } finally {
            if ($outputStream) { $outputStream.Dispose() }
            $inputStream.Dispose()
        }
        $count++
    }
} finally {
    if ($target) { $target.Dispose() }
    $source.Dispose()
}
$bytes = (Get-Item -LiteralPath $targetPath).Length
Write-Host "Copied $count report/log entries. RTL, checkpoints, EDIF, waveforms and DSP arc tables are omitted."
Write-Host "Report ZIP: $targetPath"
Write-Host ("Size: {0:N2} MiB" -f ($bytes/1MB))
if ($bytes -gt 32MB) { throw 'Report ZIP still exceeds 32MiB. Upload run-summary.txt and timing_routed.rpt separately.' }
