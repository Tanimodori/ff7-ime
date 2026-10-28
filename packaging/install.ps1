#Requires -Version 5.1
<#
.SYNOPSIS
  Install the 魔光键影 (Moguang Jianying) Rime schema into Weasel.

.DESCRIPTION
  Copies the schema, user config and Lua runtime into %APPDATA%\Rime,
  adds the schema to default.custom.yaml, and runs WeaselDeployer.exe /deploy.
  The existing schemas are preserved.  A timestamped backup of
  default.custom.yaml is created before it is modified.

.PARAMETER RimeUserDir
  Rime user data directory.  Default: %APPDATA%\Rime

.PARAMETER WeaselDir
  Weasel installation directory.  Default: C:\Program Files\Rime\weasel-0.17.4

.PARAMETER NoDeploy
  Copy files and patch config, but do not run WeaselDeployer.
#>
[CmdletBinding()]
param(
    [string]$RimeUserDir = (Join-Path $env:APPDATA 'Rime'),
    [string]$WeaselDir = 'C:\Program Files\Rime\weasel-0.17.4',
    [switch]$NoDeploy
)

$ErrorActionPreference = 'Stop'
$SchemaId = 'moguang_jianying'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $Here 'rime'

function Write-Step([string]$Text) {
    Write-Host "[MGJY] $Text" -ForegroundColor Cyan
}

function Add-SchemaEntry {
    param(
        [string]$Path,
        [string]$Id
    )

    $text = ''
    if (Test-Path -LiteralPath $Path) {
        $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    }
    if ($text -match [regex]::Escape($Id)) {
        Write-Step "default.custom.yaml already contains $Id; skip patch."
        return $false
    }

    $lines = New-Object System.Collections.ArrayList
    if ($text.Length -gt 0) {
        foreach ($line in ($text -split "`r?`n")) { [void]$lines.Add($line) }
    }

    $entry = "- {schema: $Id}"
    $schemaIdx = -1
    $baseIndent = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^(\s*)schema_list\s*:\s*$') {
            $schemaIdx = $i
            $baseIndent = $matches[1].Length
            break
        }
    }

    if ($schemaIdx -ge 0) {
        $last = $schemaIdx
        for ($j = $schemaIdx + 1; $j -lt $lines.Count; $j++) {
            $line = $lines[$j]
            if ($line.Trim() -eq '') { continue }
            $indent = ($line -replace '^(\s*).*$', '$1').Length
            if ($line -match '^\s*-\s' -and $indent -gt $baseIndent) {
                $last = $j
            } elseif ($indent -le $baseIndent) {
                break
            }
        }
        $indentStr = ' ' * ($baseIndent + 2)
        $lines.Insert($last + 1, "$indentStr$entry")
        Write-Step "Inserted $Id into existing schema_list."
    } else {
        $patchIdx = -1
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '^patch\s*:\s*$') {
                $patchIdx = $i
                break
            }
        }
        if ($patchIdx -ge 0) {
            $lines.Insert($patchIdx + 1, "  schema_list/+:")
            $lines.Insert($patchIdx + 2, "    $entry")
            Write-Step "Added schema_list/+ entry for $Id."
        } else {
            if ($lines.Count -gt 0 -and $lines[$lines.Count - 1].Trim() -ne '') {
                [void]$lines.Add('')
            }
            [void]$lines.Add('patch:')
            [void]$lines.Add('  schema_list/+:')
            [void]$lines.Add("    $entry")
            Write-Step "Created patch/schema_list/+ for $Id."
        }
    }

    $out = ($lines -join "`r`n")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $out, $utf8NoBom)
    return $true
}

if (-not (Test-Path -LiteralPath $Src)) {
    throw "Package is incomplete: missing $Src"
}
if (-not (Test-Path -LiteralPath (Join-Path $Src 'lua\mgjy_data.lua'))) {
    throw "Package is incomplete: missing rime/lua/mgjy_data.lua"
}

Write-Step "Rime user dir: $RimeUserDir"
Write-Step "Weasel dir:    $WeaselDir"
New-Item -ItemType Directory -Force -Path $RimeUserDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RimeUserDir 'lua') | Out-Null

$default = Join-Path $RimeUserDir 'default.custom.yaml'
if (Test-Path -LiteralPath $default) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "$default.mgjy-backup-$stamp"
    Copy-Item -LiteralPath $default -Destination $backup -Force
    Write-Step "Backup: $backup"
}

Copy-Item -LiteralPath (Join-Path $Src 'moguang_jianying.schema.yaml') -Destination $RimeUserDir -Force
Copy-Item -LiteralPath (Join-Path $Src 'moguang_jianying.custom.yaml') -Destination $RimeUserDir -Force
Copy-Item -Path (Join-Path $Src 'lua\*.lua') -Destination (Join-Path $RimeUserDir 'lua') -Force
Write-Step "Copied schema, custom config and Lua runtime."

[void](Add-SchemaEntry -Path $default -Id $SchemaId)

if ($NoDeploy) {
    Write-Step "NoDeploy set; skipping WeaselDeployer."
    Write-Host "Next: run WeaselDeployer.exe /deploy manually, then press F4 / Ctrl+`` to select 魔光键影."
    exit 0
}

$deployer = Join-Path $Here 'deploy-rime.ps1'
if (-not (Test-Path -LiteralPath $deployer)) {
    throw "Package is incomplete: missing deploy-rime.ps1"
}

# Rime's deployment signature is second-resolution; wait so a just-copied file
# is not considered "unchanged".
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
Start-Sleep -Seconds 1

$buildSchema = Join-Path $RimeUserDir 'build\moguang_jianying.schema.yaml'
$buildDefault = Join-Path $RimeUserDir 'build\default.yaml'
if (-not (Test-Path -LiteralPath $buildSchema)) {
    Write-Warning "Deployment artifact not found: $buildSchema"
    Write-Warning "Check %TEMP%\rime.weasel logs and run WeaselDeployer.exe /deploy again."
    exit 2
}
if (Test-Path -LiteralPath $buildDefault) {
    $bd = Get-Content -LiteralPath $buildDefault -Raw -Encoding UTF8
    if ($bd -notmatch [regex]::Escape($SchemaId)) {
        Write-Warning "build/default.yaml does not list $SchemaId; check schema_list patch."
        exit 3
    }
}

Write-Step "Installed. Press F4 or Ctrl+`` and select 魔光键影."
Write-Host "Input examples: shenluo -> 神罗, lkcc -> 我们会立刻彻底铲除你们！, leinuo/lienuo/leino/leiknuo -> 雷诺"
