param(
    [string]$Output = "..\CnCReloadedRandomizer.exe",
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputPath = if ([IO.Path]::IsPathRooted($Output)) {
    [IO.Path]::GetFullPath($Output)
} else {
    [IO.Path]::GetFullPath((Join-Path $scriptDir $Output))
}
$outputDir = Split-Path -Parent $outputPath
$distDir = Join-Path $scriptDir "dist"
$workDir = Join-Path $scriptDir "build"
$iconPath = Join-Path $scriptDir "reloaded-randomizer.ico"
$staticConfigPath = Join-Path $scriptDir "configs"
$assetPath = Join-Path $scriptDir "Assets"
$apWorldPath = Join-Path $scriptDir "Archipelago\cnc_reloaded.apworld"
$tkRuntimeHook = Join-Path $scriptDir "tools\pyinstaller_tk_runtime.py"
$versionInfoPath = Join-Path ([IO.Path]::GetTempPath()) "CnCReloadedRandomizer-$PID-version.txt"
$configManifestDir = Join-Path ([IO.Path]::GetTempPath()) "CnCReloadedRandomizer-$PID-config"
$configManifestPath = Join-Path $configManifestDir "bundle_manifest.json"

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$requiredPythonVersion = '3.14.6'
$pythonCandidates = @()
if ($PythonExecutable) {
    $pythonCandidates = @($PythonExecutable)
} else {
    $requiredPythonDirectory = 'Python' + (
        ($requiredPythonVersion.Split('.')[0..1]) -join ''
    )
    if ($env:LOCALAPPDATA) {
        $pythonCandidates += Join-Path $env:LOCALAPPDATA (
            "Programs\Python\$requiredPythonDirectory\python.exe"
        )
    }
    $pythonCandidates += @(
        Get-Command python -All -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Source }
    )
}

$discoveredPythonVersions = @()
$selectedPythonExecutable = $null
foreach ($candidate in @($pythonCandidates | Select-Object -Unique)) {
    try {
        $candidateVersion = (
            & $candidate -c "import platform; print(platform.python_version())" 2>$null
        ).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $candidateVersion) {
            continue
        }
        $discoveredPythonVersions += "$candidate ($candidateVersion)"
        if ($candidateVersion -eq $requiredPythonVersion) {
            $selectedPythonExecutable = $candidate
            $pythonVersion = $candidateVersion
            break
        }
    } catch {
        continue
    }
}
if (-not $selectedPythonExecutable) {
    $discoveredText = if ($discoveredPythonVersions.Count -gt 0) {
        $discoveredPythonVersions -join ', '
    } else {
        'none'
    }
    throw (
        "Python $requiredPythonVersion is required for reproducible launcher builds; " +
        "found $discoveredText. Install it or pass -PythonExecutable with its full path."
    )
}
$PythonExecutable = $selectedPythonExecutable
Write-Host "Using Python ${pythonVersion}: $PythonExecutable"
if (-not (& $PythonExecutable -m PyInstaller --version 2>$null)) {
    throw "PyInstaller is required. Install build dependencies with: python -m pip install -r requirements-build.txt"
}
$websocketsVersion = (& $PythonExecutable -c "import websockets; print(websockets.__version__)" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $websocketsVersion -ne '17.0') {
    throw "websockets 17.0 is required. Install build dependencies with: python -m pip install -r requirements-build.txt"
}
$certifiVersion = (& $PythonExecutable -c "import certifi; print(certifi.__version__)" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $certifiVersion -ne '2026.07.22') {
    throw "certifi 2026.07.22 is required. Install build dependencies with: python -m pip install -r requirements-build.txt"
}
if (-not (Test-Path -LiteralPath $iconPath -PathType Leaf)) {
    throw "Launcher icon is missing: $iconPath"
}
if (-not (Test-Path -LiteralPath $staticConfigPath -PathType Container)) {
    throw "Static config directory is missing: $staticConfigPath"
}
$assetArguments = @()
if (Test-Path -LiteralPath $assetPath -PathType Container) {
    $assetArguments = @('--add-data', "$assetPath;Assets")
} else {
    Write-Warning "Launcher asset directory is missing; no custom art will be bundled."
}

# PyInstaller's Tcl/Tk probe can reject otherwise working Python 3.14 installs.
# Bundle the verified runtime explicitly so windowed builds remain reproducible.
$pythonRoot = (& $PythonExecutable -c "import sys; print(sys.base_prefix)").Trim()
$tkinterBinary = Join-Path $pythonRoot "DLLs\_tkinter.pyd"
$tkinterPackage = Join-Path $pythonRoot "Lib\tkinter"
$tclBinary = Join-Path $pythonRoot "DLLs\tcl86t.dll"
$tkBinary = Join-Path $pythonRoot "DLLs\tk86t.dll"
$tclData = Join-Path $pythonRoot "tcl\tcl8.6"
$tkData = Join-Path $pythonRoot "tcl\tk8.6"
foreach ($tkRuntimePath in @(
    $tkinterBinary, $tkinterPackage, $tclBinary, $tkBinary, $tclData, $tkData,
    $tkRuntimeHook
)) {
    if (-not (Test-Path -LiteralPath $tkRuntimePath)) {
        throw "Required Tcl/Tk runtime path is missing: $tkRuntimePath"
    }
}

& $PythonExecutable -c "from randomizer.config.static import REQUIRED_STATIC_CONFIGS, validate_static_configs; validate_static_configs(REQUIRED_STATIC_CONFIGS); print('Static config preflight passed.')"
if ($LASTEXITCODE -ne 0) {
    throw "Static config preflight failed; EXE was not built."
}
$apWorldBuildScript = Join-Path $scriptDir 'Archipelago\build_apworld.ps1'
& $apWorldBuildScript `
    -OutputDirectory (Split-Path -Parent $apWorldPath) `
    -PythonExecutable $PythonExecutable
if (-not (Test-Path -LiteralPath $apWorldPath -PathType Leaf)) {
    throw "Built C&C Reloaded APWorld is missing: $apWorldPath"
}

$appVersion = (& $PythonExecutable -c "from randomizer.core.version import APP_VERSION; print(APP_VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or $appVersion -notmatch '^\d+\.\d+(\.\d+)?$') {
    throw "Invalid APP_VERSION in randomizer/core/version.py: $appVersion"
}
$versionParts = @($appVersion.Split('.') | ForEach-Object { [int]$_ })
while ($versionParts.Count -lt 4) {
    $versionParts += 0
}
$versionTuple = $versionParts -join ', '
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($versionTuple),
    prodvers=($versionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'C&C Reloaded Randomizer contributors'),
          StringStruct(u'FileDescription', u'C&C Reloaded Randomizer Launcher'),
          StringStruct(u'FileVersion', u'$appVersion'),
          StringStruct(u'InternalName', u'CnCReloadedRandomizer'),
          StringStruct(u'OriginalFilename', u'CnCReloadedRandomizer.exe'),
          StringStruct(u'ProductName', u'C&C Reloaded Randomizer Launcher'),
          StringStruct(u'ProductVersion', u'$appVersion')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
[IO.File]::WriteAllText($versionInfoPath, $versionInfo, [Text.UTF8Encoding]::new($false))

$manifestFiles = [ordered]@{}
$staticConfigPrefix = [IO.Path]::GetFullPath($staticConfigPath).TrimEnd('\') + '\'
Get-ChildItem -LiteralPath $staticConfigPath -Recurse -File |
    Where-Object {
        ($_.Extension -eq '.json' -or $_.Name -like 'Randomizer*.ini') -and
        $_.FullName -notlike "$staticConfigPath\player\*"
    } |
    Sort-Object FullName |
    ForEach-Object {
        $fullConfigPath = [IO.Path]::GetFullPath($_.FullName)
        if (-not $fullConfigPath.StartsWith(
            $staticConfigPrefix,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Refusing config outside source root: $fullConfigPath"
        }
        $relativePath = $fullConfigPath.Substring(
            $staticConfigPrefix.Length
        ).Replace('\', '/')
        $manifestFiles[$relativePath] = (
            Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        ).Hash.ToLowerInvariant()
    }
$configManifest = [ordered]@{
    format = 1
    files = $manifestFiles
} | ConvertTo-Json -Depth 4
New-Item -ItemType Directory -Path $configManifestDir -Force | Out-Null
[IO.File]::WriteAllText(
    $configManifestPath,
    $configManifest,
    [Text.UTF8Encoding]::new($false)
)

# Archipelago uses compressed ws/wss connections. Keep SSL, HTTP, email, and
# the maintained certifi CA bundle available for the handshake implementation.
try {
    & $PythonExecutable -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --noupx `
        --optimize 1 `
        --windowed `
        --icon $iconPath `
        --version-file $versionInfoPath `
        --add-data "$iconPath;." `
        --add-data "$staticConfigPath\*.json;configs" `
        --add-data "$staticConfigPath\README.md;configs" `
        --add-data "$staticConfigPath\rewards;configs\rewards" `
        --add-data "$scriptDir\Archipelago\APWorld\cnc_reloaded;Archipelago\APWorld\cnc_reloaded" `
        --add-data "$configManifestPath;configs" `
        @assetArguments `
        --add-binary "$tkinterBinary;." `
        --add-data "$tkinterPackage;tkinter" `
        --add-binary "$tclBinary;." `
        --add-binary "$tkBinary;." `
        --add-data "$tclData;_tcl_data" `
        --add-data "$tkData;_tk_data" `
        --runtime-hook $tkRuntimeHook `
        --exclude-module logging.handlers `
        --exclude-module ftplib `
        --exclude-module smtplib `
        --hidden-import Archipelago.client `
        --hidden-import Archipelago.run_manifest `
        --hidden-import Archipelago.yaml_config `
        --name CnCReloadedRandomizer `
        --distpath $distDir `
        --workpath $workDir `
        --specpath $workDir `
        (Join-Path $scriptDir "launcher_gui.py")

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }
} finally {
    Remove-Item -LiteralPath $versionInfoPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $configManifestPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $configManifestDir -Force -ErrorAction SilentlyContinue
}

$builtExe = Join-Path $distDir "CnCReloadedRandomizer.exe"
$archiveListing = @(
    & $PythonExecutable -m PyInstaller.utils.cliutils.archive_viewer -l $builtExe 2>&1
)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect built PyInstaller archive: $builtExe"
}
$archiveText = $archiveListing -join "`n"
$requiredArchiveEntries = @(
    "'reloaded-randomizer.ico'",
    "'_tkinter.pyd'",
    "'tcl86t.dll'",
    "'tk86t.dll'",
    "'_tcl_data\\init.tcl'",
    "'_tk_data\\tk.tcl'"
)
$missingArchiveEntries = @(
    $requiredArchiveEntries | Where-Object { -not $archiveText.Contains($_) }
)
if ($missingArchiveEntries.Count -gt 0) {
    throw (
        "Built launcher is missing required Tcl/Tk archive entries: " +
        ($missingArchiveEntries -join ', ')
    )
}
Copy-Item -Force $builtExe $outputPath
$publishedApWorld = Join-Path $outputDir 'cnc_reloaded.apworld'
Copy-Item -Force $apWorldPath $publishedApWorld

# ReloadedRandomizerData is persistent player data. Rebuilding the executable
# must never remove seeds, settings, logs, or cached review evidence.
Write-Host (
    "Built single-file launcher v$appVersion with Python $pythonVersion " +
    "and verified Tcl/Tk runtime: $outputPath"
)
Write-Host "Published matching Archipelago world: $publishedApWorld"
