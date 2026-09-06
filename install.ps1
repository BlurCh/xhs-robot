# Install/update xhs-robot skill into DSH skill roots.
# Usage: .\install.ps1              -> project root .agents\skills (current session)
#        .\install.ps1 -DshHome     -> also into $env:DSH_HOME\skills (all sessions)
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads ps1 as ANSI).
[CmdletBinding()]
param([switch]$DshHome)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot            # ...\xhs-robot (skill\ lives here)
$ProjectRoot = Split-Path -Parent $ScriptDir
$Name = 'xhs-robot'

$Targets = @()
if ($DshHome) {
    $dshHomeDir = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
    $Targets += Join-Path $dshHomeDir 'skills'
}
$Targets += Join-Path $ProjectRoot '.agents\skills'

foreach ($t in $Targets) {
    $dst = Join-Path $t $Name
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item -Force -Recurse (Join-Path $ScriptDir 'skill\*') $dst
    Write-Output "installed -> $dst"
}
Write-Output 'Done. The skill appears after the session catalog refreshes (next step or a new session).'
