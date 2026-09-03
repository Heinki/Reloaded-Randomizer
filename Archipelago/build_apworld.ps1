param(
    [string]$OutputDirectory = $PSScriptRoot,
    [string]$PythonExecutable = 'python',
    [switch]$AllowIncompleteCatalogue
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$arguments = @(
    (Join-Path $PSScriptRoot 'build_apworld.py'),
    '--output-directory',
    $OutputDirectory
)
if ($AllowIncompleteCatalogue) {
    $arguments += '--allow-incomplete-catalogue'
}

& $PythonExecutable @arguments
if ($LASTEXITCODE -ne 0) {
    throw "C&C Reloaded APWorld build failed with exit code $LASTEXITCODE."
}
