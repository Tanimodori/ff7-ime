#Requires -Version 5.1
<#
.SYNOPSIS
  Verify a 魔光键影 installation without changing anything.
#>
[CmdletBinding()]
param(
    [string]$RimeUserDir = (Join-Path $env:APPDATA 'Rime')
)

$ErrorActionPreference = 'Stop'
$SchemaId = 'moguang_jianying'
$ok = $true

function Check([string]$Path, [string]$Label) {
    if (Test-Path -LiteralPath $Path) {
        Write-Host "[OK]   $Label"
    } else {
        Write-Host "[FAIL] $Label ($Path)" -ForegroundColor Red
        $script:ok = $false
    }
}

Check (Join-Path $RimeUserDir "$SchemaId.schema.yaml") 'schema file'
Check (Join-Path $RimeUserDir "$SchemaId.custom.yaml") 'custom config'
Check (Join-Path $RimeUserDir 'lua\mgjy.lua') 'Lua adapter'
Check (Join-Path $RimeUserDir 'lua\mgjy_matcher.lua') 'Lua matcher'
Check (Join-Path $RimeUserDir 'lua\mgjy_data.lua') 'Lua data'
Check (Join-Path $RimeUserDir "build\$SchemaId.schema.yaml") 'deployed build artifact'

$default = Join-Path $RimeUserDir 'default.custom.yaml'
if (Test-Path -LiteralPath $default) {
    $text = Get-Content -LiteralPath $default -Raw -Encoding UTF8
    if ($text -match [regex]::Escape($SchemaId)) {
        Write-Host "[OK]   default.custom.yaml lists $SchemaId"
    } else {
        Write-Host "[FAIL] default.custom.yaml does not list $SchemaId" -ForegroundColor Red
        $ok = $false
    }
} else {
    Write-Host "[FAIL] default.custom.yaml missing" -ForegroundColor Red
    $ok = $false
}

$buildDefault = Join-Path $RimeUserDir 'build\default.yaml'
if (Test-Path -LiteralPath $buildDefault) {
    $bd = Get-Content -LiteralPath $buildDefault -Raw -Encoding UTF8
    if ($bd -match [regex]::Escape($SchemaId)) {
        Write-Host "[OK]   build/default.yaml contains $SchemaId"
    } else {
        Write-Host "[FAIL] build/default.yaml does not contain $SchemaId" -ForegroundColor Red
        $ok = $false
    }
}

if ($ok) {
    Write-Host "`nVerification passed. Press F4 / Ctrl+`` and select 魔光键影." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nVerification failed. Re-run install.ps1 and check %TEMP%\rime.weasel logs." -ForegroundColor Yellow
    exit 1
}
