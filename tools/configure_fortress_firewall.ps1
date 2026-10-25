#Requires -RunAsAdministrator
param(
    [string]$GameRoot = (Split-Path -Parent $PSScriptRoot | Split-Path -Parent)
)

$ErrorActionPreference = 'Stop'
$launcher = Join-Path $GameRoot 'CnCReloadedRandomizer.exe'
$game = Join-Path $GameRoot 'gamemd.exe'
if (!(Test-Path -LiteralPath $launcher) -or !(Test-Path -LiteralPath $game)) {
    throw 'Choose the installed Reloaded game directory.'
}

foreach ($name in @('Reloaded Final Fortress Lobby', 'Reloaded Final Fortress Game')) {
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
New-NetFirewallRule -DisplayName 'Reloaded Final Fortress Lobby' -Direction Inbound `
    -Action Allow -Profile Private -Protocol TCP -LocalPort 19420 -Program $launcher
New-NetFirewallRule -DisplayName 'Reloaded Final Fortress Game' -Direction Inbound `
    -Action Allow -Profile Private -Protocol UDP -LocalPort 1234,1235,1236 -Program $game
