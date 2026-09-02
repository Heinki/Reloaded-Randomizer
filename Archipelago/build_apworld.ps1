param(
    [string]$OutputDirectory = $PSScriptRoot,
    [string]$PythonExecutable = 'python',
    [switch]$AllowIncompleteCatalogue
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$moduleName = 'cnc_reloaded'
$sourceDirectory = Join-Path $PSScriptRoot "APWorld\$moduleName"
$cataloguePath = Join-Path $sourceDirectory 'catalogue.json'
$manifestPath = Join-Path $sourceDirectory 'archipelago.json'

& $PythonExecutable -m Archipelago.audit | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'C&C Reloaded APWorld source validation failed.'
}

$catalogue = Get-Content -LiteralPath $cataloguePath -Raw | ConvertFrom-Json
if (-not $catalogue.review_complete -and -not $AllowIncompleteCatalogue) {
    throw (
        'APWorld catalogue is review-gated. Use -AllowIncompleteCatalogue ' +
        'only for structural developer builds.'
    )
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$outputPath = Join-Path $OutputDirectory "$moduleName.apworld"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$manifest | Add-Member -NotePropertyName 'compatible_version' -NotePropertyValue 7 -Force
$manifest | Add-Member -NotePropertyName 'version' -NotePropertyValue 7 -Force
$manifestJson = $manifest | ConvertTo-Json -Depth 20 -Compress

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$fixedTimestamp = [DateTimeOffset]::new(
    2000, 1, 1, 0, 0, 0, [TimeSpan]::Zero
)

function Add-ArchiveBytes {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryName,
        [byte[]]$Bytes
    )
    $entry = $Archive.CreateEntry(
        $EntryName,
        [System.IO.Compression.CompressionLevel]::Optimal
    )
    $entry.LastWriteTime = $fixedTimestamp
    $stream = $entry.Open()
    try {
        $stream.Write($Bytes, 0, $Bytes.Length)
    }
    finally {
        $stream.Dispose()
    }
}

if (Test-Path -LiteralPath $outputPath -PathType Leaf) {
    Remove-Item -LiteralPath $outputPath -Force
}
$archive = [System.IO.Compression.ZipFile]::Open(
    $outputPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    $sourcePrefix = $sourceDirectory.TrimEnd('\', '/') + '\'
    $files = Get-ChildItem -LiteralPath $sourceDirectory -File -Recurse |
        Where-Object {
            $_.Name -ne 'archipelago.json' -and
            $_.Extension -ne '.pyc' -and
            $_.FullName -notmatch '[\\/]__pycache__[\\/]'
        } |
        Sort-Object {
            $_.FullName.Substring($sourcePrefix.Length).Replace('\', '/')
        }
    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring(
            $sourcePrefix.Length
        ).Replace('\', '/')
        Add-ArchiveBytes `
            -Archive $archive `
            -EntryName "$moduleName/$relativePath" `
            -Bytes ([IO.File]::ReadAllBytes($file.FullName))
    }
    Add-ArchiveBytes `
        -Archive $archive `
        -EntryName "$moduleName/archipelago.json" `
        -Bytes ([Text.UTF8Encoding]::new($false).GetBytes($manifestJson))
}
finally {
    $archive.Dispose()
}

Write-Output $outputPath
