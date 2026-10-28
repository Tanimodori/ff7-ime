#Requires -Version 5.1
<#
.SYNOPSIS
  Uninstall the 魔光键影 (Moguang Jianying) Rime schema.

.DESCRIPTION
  Removes the schema files and the schema_list entry, then redeploys.
  Other schemas (e.g. luna_pinyin_simp) are left untouched.

.PARAMETER RimeUserDir
  Rime user data directory.  Default: %APPDATA%\Rime

.PARAMETER WeaselDir
  Weasel installation directory.  Default: C:\Program Files\Rime\weasel-0.17.4

.PARAMETER RestoreBackup
  Restore the newest default.custom.yaml.mgjy-backup-* instead of editing it.
#>
[CmdletBinding()]
param(
    [string]$RimeUserDir = (Join-Path $env:APPDATA 'Rime'),
    [string]$WeaselDir = 'C:\Program Files\Rime\weasel-0.17.4',
    [switch]$RestoreBackup,
    [switch]$NoDeploy
)

$ErrorActionPreference = 'Stop'
$SchemaId = 'moguang_jianying'

function Write-Step([string]$Text) {
    Write-Host "[MGJY] $Text" -ForegroundColor Cyan
}

Write-Step "Rime user dir: $RimeUserDir"

$files = @(
    (Join-Path $RimeUserDir 'moguang_jianying.schema.yaml'),
    (Join-Path $RimeUserDir 'moguang_jianying.custom.yaml'),
    (Join-Path $RimeUserDir 'lua\mgjy.lua'),
    (Join-Path $RimeUserDir 'lua\mgjy_matcher.lua'),
    (Join-Path $RimeUserDir 'lua\mgjy_data.lua')
)
foreach ($f in $files) {
    if (Test-Path -LiteralPath $f) {
        Remove-Item -LiteralPath $f -Force
        Write-Step "Removed $f"
    }
}

$default = Join-Path $RimeUserDir 'default.custom.yaml'
if ($RestoreBackup -and (Test-Path -LiteralPath $default)) {
    $backup = Get-ChildItem -LiteralPath $RimeUserDir -Filter 'default.custom.yaml.mgjy-backup-*' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($backup) {
        Copy-Item -LiteralPath $backup.FullName -Destination $default -Force
        Write-Step "Restored $($backup.Name)"
    } else {
        Write-Warning "No mgjy backup found; editing default.custom.yaml instead."
    }
}

if (Test-Path -LiteralPath $default) {
    $lines = New-Object System.Collections.ArrayList
    foreach ($line in (Get-Content -LiteralPath $default -Encoding UTF8)) {
        if ($line -notmatch [regex]::Escape($SchemaId)) {
            [void]$lines.Add($line)
        }
    }
    # Drop an empty schema_list/+ block left behind.
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        if ($lines[$i] -match '^\s*schema_list/\+:\s*$') {
            $hasItem = $false
            for ($j = $i + 1; $j -lt $lines.Count; $j++) {
                if ($lines[$j].Trim() -eq '') { continue }
                if ($lines[$j] -match '^\s*-\s') { $hasItem = $true }
                break
            }
            if (-not $hasItem) { $lines.RemoveAt($i) }
        }
    }
    $out = ($lines -join "`r`n")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($default, $out, $utf8NoBom)
    Write-Step "Removed $SchemaId from default.custom.yaml."
}

if ($NoDeploy) {
    Write-Step "NoDeploy set; skipping WeaselDeployer."
    exit 0
}

$deployer = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'deploy-rime.ps1'
if (Test-Path -LiteralPath $deployer) {
    Start-Sleep -Seconds 2
    Write-Step "Deploying via rime.dll (headless) ..."
    $hadServer = @(Get-Process WeaselServer -ErrorAction SilentlyContinue).Count -gt 0
    if ($hadServer) {
        Stop-Process -Name WeaselServer -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    try {
        & $deployer -SharedDataDir (Join-Path $WeaselDir 'data') -UserDataDir $RimeUserDir -LogDir (Join-Path $env:TEMP 'rime.weasel')
    } finally {
        if ($hadServer) {
            Start-Process -FilePath (Join-Path $WeaselDir 'WeaselServer.exe') | Out-Null
            Start-Sleep -Seconds 2
        }
    }
    Write-Step "Redeployed. Other schemas remain available."
} else {
    Write-Warning "deploy-rime.ps1 not found; run WeaselDeployer manually if needed."
}
