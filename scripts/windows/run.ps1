param(
    [Parameter(Mandatory = $true)]
    [string]$VivadoBat,
    [ValidateRange(0.5, 100.0)]
    [double]$PeriodNs = 3.333,
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$RunName = '300MHz',
    [ValidateRange(1, 32)]
    [int]$Threads = 4,
    [string]$Checkpoint = ''
)

$ErrorActionPreference = 'Stop'
$bundleRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath $VivadoBat -PathType Leaf)) {
    throw "vivado.bat not found: $VivadoBat. Pass its full installed path."
}
$vivadoExe = (Resolve-Path -LiteralPath $VivadoBat).Path
$checkpointArg = '-'
$checkpointHash = $null
$checkpointTop = $null
$checkpointPart = $null
if ($Checkpoint) {
    if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) {
        throw "Routed checkpoint not found: $Checkpoint"
    }
    $checkpointArg = (Resolve-Path -LiteralPath $Checkpoint).Path
    $checkpointHash = (Get-FileHash -LiteralPath $checkpointArg -Algorithm SHA256).Hash.ToLowerInvariant()
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $dcpZip = [System.IO.Compression.ZipFile]::OpenRead($checkpointArg)
    try {
        $xmlEntry = $dcpZip.GetEntry('dcp.xml')
        if (-not $xmlEntry) { throw 'Checkpoint has no dcp.xml metadata.' }
        $xmlStream = $xmlEntry.Open()
        $xmlReader = $null
        try {
            $xmlSettings = New-Object System.Xml.XmlReaderSettings
            $xmlSettings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
            $xmlSettings.XmlResolver = $null
            $xmlReader = [System.Xml.XmlReader]::Create($xmlStream, $xmlSettings)
            $dcpMetadata = New-Object System.Xml.XmlDocument
            $dcpMetadata.XmlResolver = $null
            $dcpMetadata.Load($xmlReader)
            $checkpointTop = $dcpMetadata.Checkpoint.Top.GetAttribute('Name')
            $checkpointPart = $dcpMetadata.Checkpoint.Part.GetAttribute('Name')
        } finally {
            if ($xmlReader) { $xmlReader.Dispose() }
            $xmlStream.Dispose()
        }
    } finally {
        $dcpZip.Dispose()
    }
    if ($checkpointTop -cne 'RamVectorFp') { throw "Checkpoint metadata Top mismatch: $checkpointTop" }
    if ($checkpointPart -ne 'xczu15eg-ffvb1156-2-i') { throw "Checkpoint metadata Part mismatch: $checkpointPart" }
    Write-Host "Checkpoint metadata: Top=$checkpointTop Part=$checkpointPart"
}
$flowScript = Join-Path $bundleRoot 'run_vivado.tcl'
$rtlFile = Join-Path $bundleRoot 'rtl\RamVectorFp.sv'
$dumpScript = Join-Path $bundleRoot 'dump_all_dsp_delay.tcl'
$manifestFile = Join-Path $bundleRoot 'input-sha256.json'
foreach ($requiredFile in @($flowScript, $rtlFile, $dumpScript, $manifestFile)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Missing bundle file: $requiredFile. Extract the entire ZIP first."
    }
}
$expectedHashes = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
foreach ($entry in $expectedHashes.PSObject.Properties) {
    $inputFile = Join-Path $bundleRoot $entry.Name
    $actualHash = (Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $entry.Value) {
        throw "Bundle input changed: $($entry.Name). Use the unchanged evaluation bundle."
    }
}
if ($Checkpoint) {
    $originReceipt = Join-Path (Split-Path -Parent $checkpointArg) 'run-inputs.json'
    if (-not (Test-Path -LiteralPath $originReceipt -PathType Leaf)) {
        throw 'Resume requires the run-inputs.json beside the DCP to identify its RTL revision.'
    }
    $originInputs = Get-Content -LiteralPath $originReceipt -Raw | ConvertFrom-Json
    if ($originInputs.source_hashes.'rtl/RamVectorFp.sv' -ne $expectedHashes.'rtl/RamVectorFp.sv') {
        throw 'This DCP was built from different RTL. Run M5 without -Checkpoint; an M4 checkpoint cannot evaluate M5.'
    }
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$runDir = Join-Path $bundleRoot ("runs\{0}_{1}" -f $RunName, $stamp)
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$periodText = $PeriodNs.ToString('0.000000', [Globalization.CultureInfo]::InvariantCulture)
$runMetadata = [ordered]@{
    target = 'xczu15eg-ffvb1156-2-i'
    top = 'RamVectorFp'
    period_ns = $PeriodNs
    label = $RunName
    vivado_bat = $vivadoExe
    scope = 'Standalone out-of-context implementation; host and board IO timing excluded'
    source_hashes = $expectedHashes
    resume_checkpoint = $checkpointArg
    resume_checkpoint_sha256 = $checkpointHash
    resume_checkpoint_top = $checkpointTop
    resume_checkpoint_part = $checkpointPart
}
$runMetadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDir 'run-inputs.json') -Encoding UTF8

$vivadoExit = 1
$launchFailure = $null
Push-Location $runDir
try {
    & $vivadoExe -mode batch -notrace -source $flowScript `
        -log (Join-Path $runDir 'vivado.log') `
        -journal (Join-Path $runDir 'vivado.jou') `
        -tclargs $periodText $runDir $Threads $checkpointArg
    $vivadoExit = $LASTEXITCODE
} catch {
    $launchFailure = $_.Exception.Message
    $launchFailure | Set-Content -LiteralPath (Join-Path $runDir 'launch-error.txt') -Encoding UTF8
} finally {
    Pop-Location
}

# Package reports and checkpoints even if Vivado failed; omit its .Xil cache.
$returnFiles = @(Get-ChildItem -LiteralPath $runDir -File)
$dspDir = Join-Path $runDir 'dsp_delay'
if (Test-Path -LiteralPath $dspDir -PathType Container) {
    $returnFiles += @(Get-ChildItem -LiteralPath $dspDir -File -Recurse)
}
$resultHashes = [ordered]@{}
foreach ($resultFile in $returnFiles) {
    $relativeName = $resultFile.FullName.Substring($runDir.Length + 1).Replace('\', '/')
    $resultHashes[$relativeName] = (Get-FileHash -LiteralPath $resultFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$resultHashes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir 'output-sha256.json') -Encoding UTF8
$packItems = @(Get-ChildItem -LiteralPath $runDir -File | ForEach-Object { $_.FullName })
if (Test-Path -LiteralPath $dspDir -PathType Container) { $packItems += $dspDir }
$returnZip = Join-Path $bundleRoot ("vpu_results_{0}_{1}.zip" -f $RunName, $stamp)
Compress-Archive -LiteralPath $packItems -DestinationPath $returnZip -CompressionLevel Optimal
Write-Host ""
Write-Host "Result folder: $runDir"
Write-Host "Upload this ZIP: $returnZip"
if (($vivadoExit -ne 0) -or $launchFailure) {
    throw "Vivado did not complete successfully (exit $vivadoExit). Upload the result ZIP for diagnosis."
}
Write-Host 'Implementation/export finished. Read run-summary.txt; tool success alone does not mean timing passed.'
