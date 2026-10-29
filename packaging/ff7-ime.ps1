#Requires -Version 5.1
<#
.SYNOPSIS
  魔光键影（ff7-ime）Rime 方案安装器 / 卸载器 / 校验器。

.DESCRIPTION
  自包含安装器，不依赖 rime/plum、不依赖 bash、不依赖 PowerShell 7。
  它只做一件事：把 packaging\manifest.txt 列出的运行时文件写进 Rime 用户目录，
  然后触发一次重新部署。

  明确不做的事：
    * 不改写 default.custom.yaml（方案是否启用由「方案选单设定」的勾选决定）；
    * 不覆盖用户的 ff7-ime.custom.yaml；
    * 不安装 data/、tools/、tests/、docs/；
    * 不联网。

  安装是幂等的：内容相同的文件跳过，内容不同的文件先备份到
  <用户目录>\_backup\ff7-ime-<时间戳>\ 再覆盖。

.PARAMETER Action
  install（默认）/ uninstall / verify。verify 只读，不写任何文件。

.PARAMETER RimeUserDir
  Rime 用户目录。不指定时按
  注册表 HKCU\SOFTWARE\Rime\Weasel\RimeUserDir → %APPDATA%\Rime 的顺序探测。

.PARAMETER WeaselDir
  小狼毫安装目录（需要其中的 WeaselDeployer.exe / rime.dll / data\default.yaml）。
  不指定时依次从注册表、运行中的进程、卸载项、常见安装位置探测。

.PARAMETER NoDeploy
  只复制 / 删除文件，不触发重新部署。

.PARAMETER DryRun
  只探测并打印将要执行的动作，不写任何文件。

.PARAMETER PruneSchemaList
  仅卸载时有效：额外从 default.custom.yaml 的 schema_list 里移除 ff7-ime 条目
  （先备份）。默认关闭，因为默认策略是不碰 default.custom.yaml。

.PARAMETER PurgeBackups
  仅卸载时有效：删除 _backup\ff7-ime-* 备份目录。

.PARAMETER Json
  机器可读模式：抑制人类可读输出，最后在 stdout 输出一行
  `FF7IME-JSON {…}`（前缀是为了和 librime 自己的诊断输出区分开）。

.EXAMPLE
  .\packaging\ff7-ime.ps1 -Action install -DryRun

.EXAMPLE
  .\packaging\ff7-ime.ps1 -Action install -RimeUserDir D:\rime-user -NoDeploy

.EXAMPLE
  .\packaging\ff7-ime.ps1 -Action uninstall -PruneSchemaList
#>
[CmdletBinding()]
param(
    [ValidateSet('install', 'uninstall', 'verify')]
    [string]$Action = 'install',
    [string]$RimeUserDir = '',
    [string]$WeaselDir = '',
    [switch]$NoDeploy,
    [switch]$DryRun,
    [switch]$PruneSchemaList,
    [switch]$PurgeBackups,
    [switch]$Json,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- 常量与状态
$script:SchemaId = 'ff7-ime'
$script:SchemaName = '魔光键影'
$script:ExitCode = 0
$script:JsonMode = [bool]$Json
$script:Warnings = New-Object System.Collections.ArrayList
$script:Errors = New-Object System.Collections.ArrayList
$script:Actions = New-Object System.Collections.ArrayList
$script:Backups = New-Object System.Collections.ArrayList
$script:WeaselCandidates = New-Object System.Collections.ArrayList
$script:WeaselVersionHint = ''
$script:Version = ''

# ---------------------------------------------------------------- 输出工具
function Say {
    param([string]$Text = '', [string]$Color = '')
    if ($script:JsonMode) { return }
    if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text }
}
function SayStep {
    param([string]$Text)
    Say ''
    Say "== $Text" 'Cyan'
}
function SayItem {
    param([string]$Label, [string]$Value, [string]$Color = '')
    if ($script:JsonMode) { return }
    $pad = 18 - ([string]$Label).Length
    if ($pad -lt 1) { $pad = 1 }
    Say ("  " + $Label + (' ' * $pad) + $Value) $Color
}
function SayOk {
    param([string]$Text)
    Say "  [OK]   $Text" 'Green'
}
function SayWarn {
    param([string]$Text)
    [void]$script:Warnings.Add($Text)
    Say "  [注意] $Text" 'Yellow'
}
function SayFail {
    param([string]$Text)
    [void]$script:Errors.Add($Text)
    Say "  [失败] $Text" 'Red'
}

function Fail {
    param([string]$Message, [int]$Code = 1)
    $ex = New-Object System.Exception($Message)
    $ex.Data['Ff7ImeExitCode'] = $Code
    throw $ex
}

# ---------------------------------------------------------------- 基础工具
function Get-FullPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    try { return [System.IO.Path]::GetFullPath($expanded) } catch { return $expanded }
}

function Test-SamePath {
    param([string]$A, [string]$B)
    if ([string]::IsNullOrWhiteSpace($A) -or [string]::IsNullOrWhiteSpace($B)) { return $false }
    $fa = (Get-FullPath $A).TrimEnd('\')
    $fb = (Get-FullPath $B).TrimEnd('\')
    return [string]::Equals($fa, $fb, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-Hash {
    param([string]$Path)
    try { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash }
    catch { return $null }
}

function Set-FreshTimestamp {
    # Copy-Item 会把源文件的修改时间一起带过来，而 Rime 的部署签名是「路径 + 秒级 mtime +
    # 大小」的哈希。写成「当前时间」可以确保这次安装一定被 Rime 认成「有变化」。
    param([string]$Path)
    try { (Get-Item -LiteralPath $Path -Force).LastWriteTime = (Get-Date) } catch { }
}

function Get-RegString {
    param([string]$KeyPath, [string]$Name)
    try {
        $item = Get-ItemProperty -LiteralPath $KeyPath -Name $Name -ErrorAction Stop
        $value = $item.$Name
        if ($null -eq $value) { return $null }
        return [string]$value
    } catch { return $null }
}

function ConvertTo-DirPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    $p = $Path.Trim()
    $p = $p.Trim('"')
    $p = $p -replace ',\s*\d+\s*$', ''
    if ($p -match '(?i)\.(exe|dll|ico)$') { $p = Split-Path -Parent $p }
    $p = $p.TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($p)) { return '' }
    return (Get-FullPath $p)
}

function Test-Elevated {
    try {
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

function Get-DirVersion {
    param([string]$Path)
    $name = Split-Path -Leaf $Path
    $m = [regex]::Match($name, '\d+(\.\d+)+')
    if (-not $m.Success) { return $null }
    try { return [version]$m.Value } catch { return $null }
}

function Get-FileVersionString {
    param([string]$Path)
    try {
        $vi = (Get-Item -LiteralPath $Path -ErrorAction Stop).VersionInfo
        if ($vi.FileVersion) { return [string]$vi.FileVersion }
        if ($vi.ProductVersion) { return [string]$vi.ProductVersion }
        return ''
    } catch { return '' }
}

function Get-SchemaVersion {
    param([string]$SchemaPath)
    try { $text = [System.IO.File]::ReadAllText($SchemaPath, [System.Text.Encoding]::UTF8) }
    catch { return '' }
    $m = [regex]::Match($text, '(?m)^\s*version\s*:\s*"?([0-9][^"\r\n]*?)"?\s*$')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ''
}

# ---------------------------------------------------------------- 包自检
function Get-Manifest {
    param([string]$Root)
    $manifestPath = Join-Path $Root 'packaging\manifest.txt'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Fail "包不完整：找不到运行时清单 $manifestPath" 2
    }
    $entries = New-Object System.Collections.ArrayList
    foreach ($line in [System.IO.File]::ReadAllLines($manifestPath)) {
        $t = $line.Trim()
        if ($t.Length -eq 0) { continue }
        if ($t.StartsWith('#')) { continue }
        [void]$entries.Add(($t -replace '/', '\'))
    }
    if ($entries.Count -eq 0) { Fail "包不完整：运行时清单为空 $manifestPath" 2 }
    return , $entries.ToArray()
}

function Test-PackageComplete {
    param([string]$Root, [string[]]$Entries)
    $problems = New-Object System.Collections.ArrayList
    foreach ($rel in $Entries) {
        $p = Join-Path $Root $rel
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
            [void]$problems.Add("$rel（缺失）")
            continue
        }
        if ((Get-Item -LiteralPath $p).Length -eq 0) {
            [void]$problems.Add("$rel（空文件）")
        }
    }
    return , $problems.ToArray()
}

function Test-SchemaContents {
    param([string]$SchemaPath)
    $problems = New-Object System.Collections.ArrayList
    try { $text = [System.IO.File]::ReadAllText($SchemaPath, [System.Text.Encoding]::UTF8) }
    catch {
        [void]$problems.Add("无法读取 $SchemaPath：$($_.Exception.Message)")
        return , $problems.ToArray()
    }
    $id = [regex]::Escape($script:SchemaId)
    if ($text -notmatch "schema_id\s*:\s*$id") { [void]$problems.Add("缺少 schema_id: $($script:SchemaId)") }
    if ($text -notmatch "lua_translator@\*$id") { [void]$problems.Add("缺少 lua_translator@*$($script:SchemaId)") }
    if ($text -notmatch "lua_processor@\*${id}_filter") { [void]$problems.Add("缺少 lua_processor@*$($script:SchemaId)_filter") }
    return , $problems.ToArray()
}

# ---------------------------------------------------------------- 路径探测
function Resolve-RimeUserDir {
    param([string]$Explicit)

    $candidates = New-Object System.Collections.ArrayList
    $explicitGiven = -not [string]::IsNullOrWhiteSpace($Explicit)
    if ($explicitGiven) {
        [void]$candidates.Add([pscustomobject]@{
            Path = (Get-FullPath $Explicit); Source = '参数 -RimeUserDir'
        })
    }
    $regValue = Get-RegString 'HKCU:\SOFTWARE\Rime\Weasel' 'RimeUserDir'
    if (-not [string]::IsNullOrWhiteSpace($regValue)) {
        [void]$candidates.Add([pscustomobject]@{
            Path = (Get-FullPath $regValue); Source = '注册表 HKCU\SOFTWARE\Rime\Weasel\RimeUserDir'
        })
    }
    $defaultDir = ''
    if (-not [string]::IsNullOrWhiteSpace($env:APPDATA)) {
        $defaultDir = Get-FullPath (Join-Path $env:APPDATA 'Rime')
        [void]$candidates.Add([pscustomobject]@{
            Path = $defaultDir; Source = '默认 %APPDATA%\Rime'
        })
    }
    if ($candidates.Count -eq 0) {
        Fail '无法确定 Rime 用户目录：%APPDATA% 未定义，且未提供 -RimeUserDir。' 5
    }

    # 显式指定的目录无条件优先（哪怕它还不存在——那正是要创建的目标）。
    # 否则优先取第一个「已经存在」的候选，避免注册表里残留的旧路径把安装引到空目录。
    $selected = $candidates[0]
    if (-not $explicitGiven) {
        foreach ($c in $candidates) {
            if (Test-Path -LiteralPath $c.Path) { $selected = $c; break }
        }
    }

    # 小狼毫自己会用的目录（用于判断能否走 WeaselDeployer）。
    $configured = ''
    if (-not [string]::IsNullOrWhiteSpace($regValue)) { $configured = Get-FullPath $regValue }
    elseif (-not [string]::IsNullOrWhiteSpace($defaultDir)) { $configured = $defaultDir }

    return [pscustomobject]@{
        Path = $selected.Path
        Source = $selected.Source
        Candidates = $candidates
        Configured = $configured
    }
}

function Add-WeaselCandidate {
    param([string]$Path, [string]$Source)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $dir = ConvertTo-DirPath $Path
    if ([string]::IsNullOrWhiteSpace($dir)) { return }
    foreach ($c in $script:WeaselCandidates) {
        if (Test-SamePath $c.Path $dir) { return }
    }
    [void]$script:WeaselCandidates.Add([pscustomobject]@{ Path = $dir; Source = $Source })
}

function Test-WeaselDir {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Path 'WeaselDeployer.exe') -PathType Leaf)
}

function Resolve-WeaselDir {
    param([string]$Explicit)

    $script:WeaselCandidates = New-Object System.Collections.ArrayList

    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        Add-WeaselCandidate $Explicit '参数 -WeaselDir'
    }

    foreach ($key in @(
            'HKCU:\SOFTWARE\Rime\Weasel',
            'HKLM:\SOFTWARE\Rime\Weasel',
            'HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel')) {
        foreach ($name in @('WeaselRoot', 'InstallDir', 'InstallPath')) {
            $v = Get-RegString $key $name
            if (-not [string]::IsNullOrWhiteSpace($v)) { Add-WeaselCandidate $v "注册表 $key\$name" }
        }
    }

    try {
        foreach ($proc in @(Get-Process -Name 'WeaselServer', 'WeaselDeployer' -ErrorAction SilentlyContinue)) {
            $p = $null
            try { $p = $proc.Path } catch { $p = $null }
            if (-not [string]::IsNullOrWhiteSpace($p)) { Add-WeaselCandidate $p '正在运行的小狼毫进程' }
        }
    } catch { }

    foreach ($root in @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')) {
        $subs = @()
        try { $subs = @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue) } catch { $subs = @() }
        foreach ($sub in $subs) {
            $props = $null
            try { $props = Get-ItemProperty -LiteralPath $sub.PSPath -ErrorAction SilentlyContinue } catch { $props = $null }
            if ($null -eq $props) { continue }
            $display = ''
            if ($props.PSObject.Properties['DisplayName']) { $display = [string]$props.DisplayName }
            if ($display -notmatch '(?i)weasel|小狼毫') { continue }
            if ($props.PSObject.Properties['DisplayVersion']) {
                $dv = [string]$props.DisplayVersion
                if (-not [string]::IsNullOrWhiteSpace($dv) -and [string]::IsNullOrWhiteSpace($script:WeaselVersionHint)) {
                    $script:WeaselVersionHint = $dv.Trim()
                }
            }
            if ($props.PSObject.Properties['InstallLocation']) {
                Add-WeaselCandidate ([string]$props.InstallLocation) "卸载项 $($sub.PSChildName)"
            }
            if ($props.PSObject.Properties['DisplayIcon']) {
                Add-WeaselCandidate ([string]$props.DisplayIcon) "卸载项 $($sub.PSChildName) 的 DisplayIcon"
            }
        }
    }

    $roots = New-Object System.Collections.ArrayList
    if ($env:ProgramFiles) { [void]$roots.Add($env:ProgramFiles) }
    if (${env:ProgramFiles(x86)}) { [void]$roots.Add(${env:ProgramFiles(x86)}) }
    if ($env:LOCALAPPDATA) { [void]$roots.Add((Join-Path $env:LOCALAPPDATA 'Programs')) }
    if ($env:SystemDrive) { [void]$roots.Add(($env:SystemDrive.TrimEnd('\') + '\')) }

    $searchRoots = New-Object System.Collections.ArrayList
    foreach ($r in $roots) {
        [void]$searchRoots.Add($r)
        $rimeRoot = Join-Path $r 'Rime'
        if (Test-Path -LiteralPath $rimeRoot) { [void]$searchRoots.Add($rimeRoot) }
    }
    foreach ($r in $searchRoots) {
        if (-not (Test-Path -LiteralPath $r)) { continue }
        $dirs = @()
        try { $dirs = @(Get-ChildItem -LiteralPath $r -Directory -ErrorAction SilentlyContinue) } catch { $dirs = @() }
        foreach ($d in $dirs) {
            if ($d.Name -notmatch '(?i)^weasel') { continue }
            if (Test-WeaselDir $d.FullName) { Add-WeaselCandidate $d.FullName "扫描 $r" }
        }
    }

    $valid = @($script:WeaselCandidates | Where-Object { Test-WeaselDir $_.Path })
    $selected = $null
    if ($valid.Count -gt 0) {
        $selected = $valid[0]
        $bestVersion = Get-DirVersion $selected.Path
        foreach ($c in $valid) {
            $v = Get-DirVersion $c.Path
            if ($null -ne $v -and ($null -eq $bestVersion -or $v -gt $bestVersion)) {
                $selected = $c
                $bestVersion = $v
            }
        }
    }

    $selectedPath = ''
    $selectedSource = ''
    if ($null -ne $selected) {
        $selectedPath = $selected.Path
        $selectedSource = $selected.Source
    }
    return [pscustomobject]@{
        Path = $selectedPath
        Source = $selectedSource
        Candidates = $script:WeaselCandidates
        Valid = $valid
    }
}

# ---------------------------------------------------------------- 部署
function Invoke-HeadlessDeploy {
    param(
        [string]$WeaselRoot,
        [string]$UserDataDir,
        [string]$LogDir,
        [string]$DistributionVersion
    )

    $sharedDataDir = Join-Path $WeaselRoot 'data'
    $dllPath = Join-Path $WeaselRoot 'rime.dll'
    if (-not (Test-Path -LiteralPath (Join-Path $sharedDataDir 'default.yaml') -PathType Leaf)) {
        Fail "无法无头部署：共享数据目录无效（缺少 default.yaml）$sharedDataDir" 4
    }
    if (-not (Test-Path -LiteralPath $dllPath -PathType Leaf)) {
        Fail "无法无头部署：找不到 $dllPath" 4
    }

    if (-not ('Ff7ImeRimeDeploy' -as [type])) {
        $code = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class Ff7ImeRimeDeploy
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeTraits
    {
        public int data_size;
        public IntPtr shared_data_dir;
        public IntPtr user_data_dir;
        public IntPtr distribution_name;
        public IntPtr distribution_code_name;
        public IntPtr distribution_version;
        public IntPtr app_name;
        public IntPtr modules;
        public int min_log_level;
        public IntPtr log_dir;
        public IntPtr prebuilt_data_dir;
        public IntPtr staging_dir;
    }

    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void RimeSetup(ref RimeTraits traits);
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void RimeInitialize(ref RimeTraits traits);
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int RimeStartMaintenance(int full_check);
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void RimeJoinMaintenanceThread();
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void RimeFinalize();

    private static IntPtr Utf8(string s)
    {
        if (s == null) return IntPtr.Zero;
        byte[] b = Encoding.UTF8.GetBytes(s);
        IntPtr p = Marshal.AllocHGlobal(b.Length + 1);
        Marshal.Copy(b, 0, p, b.Length);
        Marshal.WriteByte(p, b.Length, 0);
        return p;
    }

    public static int Deploy(string sharedDir, string userDir, string logDir, string version, int logLevel)
    {
        RimeTraits t = new RimeTraits();
        t.data_size = Marshal.SizeOf(typeof(RimeTraits));
        t.shared_data_dir = Utf8(sharedDir);
        t.user_data_dir = Utf8(userDir);
        t.distribution_name = Utf8("Rime");
        t.distribution_code_name = Utf8("weasel");
        t.distribution_version = Utf8(version);
        t.app_name = Utf8("rime.ff7_ime_deploy");
        t.modules = IntPtr.Zero;
        t.min_log_level = logLevel;
        t.log_dir = Utf8(logDir);
        t.prebuilt_data_dir = IntPtr.Zero;
        t.staging_dir = IntPtr.Zero;
        try
        {
            RimeSetup(ref t);
            RimeInitialize(ref t);
            int started = RimeStartMaintenance(1);
            RimeJoinMaintenanceThread();
            RimeFinalize();
            return started;
        }
        finally
        {
            IntPtr[] ptrs = new IntPtr[] { t.shared_data_dir, t.user_data_dir, t.distribution_name,
                t.distribution_code_name, t.distribution_version, t.app_name, t.log_dir };
            foreach (IntPtr p in ptrs) { if (p != IntPtr.Zero) Marshal.FreeHGlobal(p); }
        }
    }
}
'@
        Add-Type -TypeDefinition $code -Language CSharp -ErrorAction Stop
    }

    if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

    $oldPath = $env:PATH
    $env:PATH = "$WeaselRoot;$oldPath"
    try {
        $started = [Ff7ImeRimeDeploy]::Deploy($sharedDataDir, $UserDataDir, $LogDir, $DistributionVersion, 2)
    } catch {
        Fail "无头部署失败（rime.dll）：$($_.Exception.Message)" 4
    } finally {
        $env:PATH = $oldPath
    }
    return [pscustomobject]@{ Method = 'rime.dll 无头部署'; Started = $started; ExitCode = $null }
}

function Invoke-Deploy {
    param($Probe)

    if ($DryRun) {
        SayItem '部署方式' '跳过（-DryRun 预演不执行部署）'
        return [pscustomobject]@{ Attempted = $false; Method = '跳过（-DryRun）'; ExitCode = $null; Started = $null }
    }

    if ($NoDeploy) {
        SayWarn '已指定 -NoDeploy：跳过重新部署。文件已就位，请手动「重新部署」或重启 WeaselServer。'
        return [pscustomobject]@{ Attempted = $false; Method = '跳过（-NoDeploy）'; ExitCode = $null; Started = $null }
    }

    $weaselRoot = $Probe.WeaselDir
    if ([string]::IsNullOrWhiteSpace($weaselRoot)) {
        SayWarn '未找到小狼毫安装目录，无法自动部署。请手动「重新部署」，或用 -WeaselDir 指定安装目录。'
        return [pscustomobject]@{ Attempted = $false; Method = '跳过（未找到小狼毫）'; ExitCode = $null; Started = $null }
    }

    # Rime 的部署签名精确到秒，刚写完的文件需要等一秒以上才不会被判为「未变化」。
    if (-not $DryRun) { Start-Sleep -Seconds 2 }

    # 一律走 rime.dll 无头部署，不用 WeaselDeployer.exe：
    #   * WeaselDeployer.exe /deploy 虽然被它自己的 /? 列为「Update workspace」，
    #     但在 0.17.4 上实测会打开「方案选单设定」窗口并一直等在那里，安装会卡死；
    #   * 它只认注册表里的用户目录，-RimeUserDir 指向别处时会部署错地方；
    #   * 无头部署能显式传 shared_data_dir / user_data_dir，行为确定。
    $sameDir = Test-SamePath $Probe.RimeUserDir $Probe.WeaselConfigured
    $serverPath = Join-Path $weaselRoot 'WeaselServer.exe'
    $restartServer = $false

    if ($sameDir -and (Test-Path -LiteralPath $serverPath -PathType Leaf)) {
        $running = @(Get-Process -Name 'WeaselServer' -ErrorAction SilentlyContinue)
        if ($running.Count -gt 0) {
            # 服务正在使用同一个用户目录，它 mmap 了 build/ 产物；先停再部署，避免写冲突。
            SayItem '暂停服务' 'WeaselServer（部署期间需要停一下，结束后自动拉起）'
            try { Stop-Process -Name 'WeaselServer' -Force -ErrorAction Stop } catch { }
            Start-Sleep -Seconds 2
            $restartServer = $true
        }
    }

    SayItem '部署方式' 'rime.dll 无头部署'
    $logDir = Join-Path $env:TEMP 'rime.weasel'
    try {
        $result = Invoke-HeadlessDeploy -WeaselRoot $weaselRoot -UserDataDir $Probe.RimeUserDir -LogDir $logDir -DistributionVersion $Probe.DistributionVersion
    } finally {
        if ($restartServer) {
            try {
                Start-Process -FilePath $serverPath -WorkingDirectory $weaselRoot | Out-Null
                Start-Sleep -Seconds 2
                SayItem '恢复服务' 'WeaselServer 已重新启动'
            } catch {
                SayWarn "WeaselServer 未能自动重启，请手动运行 $serverPath"
            }
        }
    }
    return [pscustomobject]@{ Attempted = $true; Method = $result.Method; ExitCode = $result.ExitCode; Started = $result.Started }
}

# ---------------------------------------------------------------- 备份
function New-BackupStamp {
    return (Get-Date -Format 'yyyyMMdd-HHmmss')
}

function Backup-File {
    param([string]$SourcePath, [string]$BackupDir, [string]$RelativePath)
    $target = Join-Path $BackupDir $RelativePath
    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    Copy-Item -LiteralPath $SourcePath -Destination $target -Force
    [void]$script:Backups.Add($target)
    return $target
}

# ---------------------------------------------------------------- 安装
function Invoke-Install {
    param($Probe)

    $userDir = $Probe.RimeUserDir
    $backupDir = Join-Path (Join-Path $userDir '_backup') ("ff7-ime-" + (New-BackupStamp))

    SayStep '复制运行时文件'

    $added = 0
    $unchanged = 0
    $updated = 0

    foreach ($rel in $Probe.Manifest) {
        $src = Join-Path $Probe.PackageRoot $rel
        $dst = Join-Path $userDir $rel
        $srcHash = Get-Hash $src

        if (-not (Test-Path -LiteralPath $dst -PathType Leaf)) {
            [void]$script:Actions.Add("新增 $rel")
            if (-not $DryRun) {
                $parent = Split-Path -Parent $dst
                if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
                Copy-Item -LiteralPath $src -Destination $dst -Force
                Set-FreshTimestamp -Path $dst
            }
            $added++
            SayOk "新增 $rel"
            continue
        }

        $dstHash = Get-Hash $dst
        if ($srcHash -eq $dstHash) {
            [void]$script:Actions.Add("已是最新 $rel")
            $unchanged++
            SayOk "已是最新 $rel"
            continue
        }

        [void]$script:Actions.Add("更新 $rel（旧文件已备份）")
        if (-not $DryRun) {
            [void](Backup-File -SourcePath $dst -BackupDir $backupDir -RelativePath $rel)
            Copy-Item -LiteralPath $src -Destination $dst -Force
            Set-FreshTimestamp -Path $dst
        }
        $updated++
        SayOk "更新 $rel（旧文件已备份）"
    }

    if ($DryRun) {
        SayWarn '预演模式：没有写入任何文件。'
    } elseif ($script:Backups.Count -gt 0) {
        SayItem '备份目录' $backupDir
    }

    SayItem '结果' "新增 $added 个，更新 $updated 个，已是最新 $unchanged 个"

    SayStep '重新部署'
    $deploy = Invoke-Deploy -Probe $Probe

    SayStep '检查部署产物'
    $buildSchema = Join-Path $userDir ("build\$($script:SchemaId).schema.yaml")
    $buildExists = Test-Path -LiteralPath $buildSchema -PathType Leaf
    if ($buildExists) {
        SayOk "build\$($script:SchemaId).schema.yaml 已生成"
    } elseif ($Probe.HadBuildArtifact) {
        SayFail "build\$($script:SchemaId).schema.yaml 在部署后消失了"
        $script:ExitCode = 4
    } else {
        SayWarn "build\$($script:SchemaId).schema.yaml 还没有生成：首次安装时这是正常的，librime 只编译已勾选的方案。"
        SayWarn "请打开「方案选单设定」勾选「$($script:SchemaName)」并保存，然后重新部署。"
    }

    if (Test-Path -LiteralPath (Join-Path $userDir "$($script:SchemaId).custom.yaml") -PathType Leaf) {
        SayItem '用户配置' "$($script:SchemaId).custom.yaml 已存在，本工具不会修改它"
    }

    SayStep '下一步'
    Say "  1. 右键小狼毫托盘图标 → 方案选单设定"
    Say "  2. 在列表里勾选「$($script:SchemaName)」，点击「中」保存"
    Say "  3. 若候选没有立即生效：右键托盘 → 重新部署，或重启 WeaselServer"
    Say "  4. 测试：输入 shenluo 应出现「神罗」，输入 lkcc 应出现「我们会立刻彻底铲除你们！」"

    return [pscustomobject]@{ Added = $added; Updated = $updated; Unchanged = $unchanged; Deploy = $deploy }
}

# ---------------------------------------------------------------- 卸载
function Remove-SchemaListEntry {
    param([string]$DefaultCustomPath, [string]$BackupDir)

    if (-not (Test-Path -LiteralPath $DefaultCustomPath -PathType Leaf)) {
        return 'default.custom.yaml 不存在，无需清理'
    }
    $bytes = [System.IO.File]::ReadAllBytes($DefaultCustomPath)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $raw = [System.IO.File]::ReadAllText($DefaultCustomPath, [System.Text.Encoding]::UTF8)
    $eol = "`n"
    if ($raw.Contains("`r`n")) { $eol = "`r`n" }

    $kept = New-Object System.Collections.ArrayList
    $removed = 0
    foreach ($line in ($raw -split "`r?`n")) {
        $trimmed = $line.Trim()
        if (-not $trimmed.StartsWith('#') -and $trimmed -match "schema\s*:\s*$($script:SchemaId)\b") {
            $removed++
            continue
        }
        [void]$kept.Add($line)
    }
    if ($removed -eq 0) { return 'default.custom.yaml 里没有 ff7-ime 条目' }

    if (-not $DryRun) {
        [void](Backup-File -SourcePath $DefaultCustomPath -BackupDir $BackupDir -RelativePath 'default.custom.yaml')
        $encoding = New-Object System.Text.UTF8Encoding($hasBom)
        [System.IO.File]::WriteAllText($DefaultCustomPath, ($kept -join $eol), $encoding)
    }
    return "已从 default.custom.yaml 移除 $removed 行 ff7-ime 条目（原文件已备份）"
}

function Invoke-Uninstall {
    param($Probe)

    $userDir = $Probe.RimeUserDir
    $backupDir = Join-Path (Join-Path $userDir '_backup') ("ff7-ime-" + (New-BackupStamp))

    SayStep '删除运行时文件'
    $removed = 0
    $absent = 0
    foreach ($rel in $Probe.Manifest) {
        $src = Join-Path $Probe.PackageRoot $rel
        $dst = Join-Path $userDir $rel
        if (-not (Test-Path -LiteralPath $dst -PathType Leaf)) {
            [void]$script:Actions.Add("跳过 $rel（不存在）")
            $absent++
            continue
        }
        $changed = ((Get-Hash $dst) -ne (Get-Hash $src))
        if (-not $DryRun) {
            if ($changed) { [void](Backup-File -SourcePath $dst -BackupDir $backupDir -RelativePath $rel) }
            Remove-Item -LiteralPath $dst -Force
        }
        if ($changed) {
            [void]$script:Actions.Add("删除 $rel（与包内不同，已备份）")
            SayOk "删除 $rel（与包内不同，已备份）"
        } else {
            [void]$script:Actions.Add("删除 $rel")
            SayOk "删除 $rel"
        }
        $removed++
    }
    SayItem '结果' "删除 $removed 个，本来就不存在 $absent 个"

    SayStep '清理构建产物'
    $buildDir = Join-Path $userDir 'build'
    $artifacts = @()
    if (Test-Path -LiteralPath $buildDir) {
        try { $artifacts = @(Get-ChildItem -LiteralPath $buildDir -Filter "$($script:SchemaId)*" -File -ErrorAction SilentlyContinue) }
        catch { $artifacts = @() }
    }
    if ($artifacts.Count -eq 0) {
        SayOk "build\ 下没有 $($script:SchemaId)* 产物"
    } else {
        foreach ($a in $artifacts) {
            if (-not $DryRun) { Remove-Item -LiteralPath $a.FullName -Force }
            SayOk "删除 build\$($a.Name)"
        }
    }

    $pruneMessage = ''
    if ($PruneSchemaList) {
        SayStep '清理 default.custom.yaml（-PruneSchemaList）'
        $pruneMessage = Remove-SchemaListEntry -DefaultCustomPath (Join-Path $userDir 'default.custom.yaml') -BackupDir $backupDir
        SayOk $pruneMessage
    } else {
        SayWarn '没有改动 default.custom.yaml。如果你之前在方案选单里勾选过本方案，请在那里取消勾选并保存；或下次用 -PruneSchemaList 自动清理。'
    }

    if ($PurgeBackups) {
        SayStep '清理备份目录（-PurgeBackups）'
        $backupRoot = Join-Path $userDir '_backup'
        if (Test-Path -LiteralPath $backupRoot) {
            $dirs = @(Get-ChildItem -LiteralPath $backupRoot -Directory -Filter 'ff7-ime-*' -ErrorAction SilentlyContinue)
            if ($dirs.Count -eq 0) {
                SayOk '_backup 下没有 ff7-ime-* 备份'
            } else {
                foreach ($d in $dirs) {
                    if (-not $DryRun) { Remove-Item -LiteralPath $d.FullName -Recurse -Force }
                    SayOk "删除 $($d.FullName)"
                }
            }
        }
    }

    SayStep '重新部署'
    $deploy = Invoke-Deploy -Probe $Probe

    SayStep '说明'
    Say "  * 本工具只删除 $($script:SchemaId) 自己的文件，没有触碰 luna_pinyin_simp 等其他方案。"
    if (-not $PruneSchemaList) {
        Say "  * default.custom.yaml 未被修改；如仍残留勾选，请在「方案选单设定」里取消勾选。"
    }

    return [pscustomobject]@{ Removed = $removed; Absent = $absent; Prune = $pruneMessage; Deploy = $deploy }
}

# ---------------------------------------------------------------- 校验
function Invoke-Verify {
    param($Probe)

    $userDir = $Probe.RimeUserDir
    $ok = $true

    SayStep '运行时文件'
    foreach ($rel in $Probe.Manifest) {
        $src = Join-Path $Probe.PackageRoot $rel
        $dst = Join-Path $userDir $rel
        if (-not (Test-Path -LiteralPath $dst -PathType Leaf)) {
            SayFail "$rel 不存在"
            $ok = $false
            continue
        }
        if ((Get-Hash $dst) -ne (Get-Hash $src)) {
            SayFail "$rel 与包内版本不一致"
            $ok = $false
            continue
        }
        SayOk $rel
    }

    SayStep '构建产物'
    $buildSchema = Join-Path $userDir ("build\$($script:SchemaId).schema.yaml")
    if (Test-Path -LiteralPath $buildSchema -PathType Leaf) {
        SayOk "build\$($script:SchemaId).schema.yaml 存在"
    } else {
        SayWarn "build\$($script:SchemaId).schema.yaml 不存在（尚未在方案选单中勾选，或还没重新部署）"
    }

    SayStep '其它'
    if (Test-Path -LiteralPath (Join-Path $userDir "$($script:SchemaId).custom.yaml") -PathType Leaf) {
        SayOk "$($script:SchemaId).custom.yaml 存在（用户配置，本工具不修改）"
    } else {
        Say "  $($script:SchemaId).custom.yaml 不存在（可选文件，方案自带全部默认值）"
    }
    $backupRoot = Join-Path $userDir '_backup'
    if (Test-Path -LiteralPath $backupRoot) {
        $dirs = @(Get-ChildItem -LiteralPath $backupRoot -Directory -Filter 'ff7-ime-*' -ErrorAction SilentlyContinue)
        Say "  _backup 下 ff7-ime-* 备份目录：$($dirs.Count) 个"
    }

    return $ok
}

# ================================================================ 主流程
try {
    try {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [Console]::OutputEncoding = $utf8
        $OutputEncoding = $utf8
    } catch { }

    # ---- 包位置与完整性
    $scriptDir = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptDir)) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $packageRoot = Get-FullPath (Join-Path $scriptDir '..')

    $manifest = Get-Manifest -Root $packageRoot
    $packageProblems = Test-PackageComplete -Root $packageRoot -Entries $manifest
    if ($packageProblems.Count -gt 0) {
        Fail ("包不完整，缺少这些文件：" + ($packageProblems -join '、') + "。请重新解压完整的发布包。") 2
    }
    $schemaPath = Join-Path $packageRoot "$($script:SchemaId).schema.yaml"
    $schemaProblems = Test-SchemaContents -SchemaPath $schemaPath
    if ($schemaProblems.Count -gt 0) {
        Fail ("包内方案文件异常：" + ($schemaProblems -join '；')) 2
    }
    $script:Version = Get-SchemaVersion -SchemaPath $schemaPath
    if ([string]::IsNullOrWhiteSpace($script:Version)) { $script:Version = '0.0.0' }

    # ---- 探测
    $userProbe = Resolve-RimeUserDir -Explicit $RimeUserDir
    $weaselProbe = Resolve-WeaselDir -Explicit $WeaselDir

    # 显式指定的 -WeaselDir 必须有效，否则直接失败：静默换用别的目录会让用户以为装对了。
    # -NoDeploy 时根本不会用到它，所以不校验。
    if (-not $NoDeploy -and -not [string]::IsNullOrWhiteSpace($WeaselDir)) {
        $explicitWeasel = ConvertTo-DirPath $WeaselDir
        if (-not (Test-WeaselDir $explicitWeasel)) {
            Fail "指定的 -WeaselDir 无效（其中没有 WeaselDeployer.exe）：$explicitWeasel" 3
        }
        $weaselProbe = [pscustomobject]@{
            Path = $explicitWeasel
            Source = '参数 -WeaselDir'
            Candidates = $weaselProbe.Candidates
            Valid = $weaselProbe.Valid
        }
    }

    $weaselVersion = ''
    $rimeDllVersion = ''
    $weaselVersionSource = ''
    if (-not [string]::IsNullOrWhiteSpace($weaselProbe.Path)) {
        # 小狼毫的 exe/dll 不带版本资源，所以要按 版本资源 → 卸载项 DisplayVersion
        # → 安装目录名 的顺序退让。
        $weaselVersion = Get-FileVersionString (Join-Path $weaselProbe.Path 'WeaselDeployer.exe')
        if (-not [string]::IsNullOrWhiteSpace($weaselVersion)) {
            $weaselVersionSource = 'WeaselDeployer.exe 版本资源'
        }
        if ([string]::IsNullOrWhiteSpace($weaselVersion) -and -not [string]::IsNullOrWhiteSpace($script:WeaselVersionHint)) {
            $weaselVersion = $script:WeaselVersionHint
            $weaselVersionSource = '卸载项 DisplayVersion'
        }
        if ([string]::IsNullOrWhiteSpace($weaselVersion)) {
            $dirVersion = Get-DirVersion $weaselProbe.Path
            if ($null -ne $dirVersion) {
                $weaselVersion = $dirVersion.ToString()
                $weaselVersionSource = '安装目录名'
            }
        }
        $rimeDllVersion = Get-FileVersionString (Join-Path $weaselProbe.Path 'rime.dll')
    }
    $distributionVersion = $weaselVersion
    if ([string]::IsNullOrWhiteSpace($distributionVersion)) { $distributionVersion = '0.0.0' }

    $logDir = Join-Path $env:TEMP 'rime.weasel'
    $elevated = Test-Elevated
    $userDirExists = Test-Path -LiteralPath $userProbe.Path
    $buildSchemaPath = Join-Path $userProbe.Path ("build\$($script:SchemaId).schema.yaml")
    $hadBuildArtifact = Test-Path -LiteralPath $buildSchemaPath -PathType Leaf

    $probe = [pscustomobject]@{
        PackageRoot = $packageRoot
        Manifest = $manifest
        RimeUserDir = $userProbe.Path
        RimeUserDirSource = $userProbe.Source
        RimeUserDirCandidates = $userProbe.Candidates
        WeaselConfigured = $userProbe.Configured
        WeaselDir = $weaselProbe.Path
        WeaselDirSource = $weaselProbe.Source
        WeaselDirCandidates = $weaselProbe.Candidates
        WeaselVersion = $weaselVersion
        RimeDllVersion = $rimeDllVersion
        DistributionVersion = $distributionVersion
        LogDir = $logDir
        Elevated = $elevated
        HadBuildArtifact = $hadBuildArtifact
    }

    Say "$($script:SchemaName) · $($script:SchemaId) 安装器 $($script:Version)"
    Say ("动作：" + $Action + "    模式：" + $(if ($DryRun) { '预演（不写文件）' } else { '正式执行' }))
    Say ("PowerShell：" + $PSVersionTable.PSVersion.ToString() + "    管理员：" + $(if ($elevated) { '是' } else { '否（不需要）' }))

    SayStep '探测结果'
    SayItem '包目录' "$packageRoot（脚本所在位置）"
    SayItem '运行时清单' "packaging\manifest.txt（$($manifest.Count) 项）"
    SayItem 'Rime 用户目录' "$($userProbe.Path)（$($userProbe.Source)$(if ($userDirExists) { '' } else { '，尚不存在，将创建' })）"
    foreach ($c in $userProbe.Candidates) {
        if (-not (Test-SamePath $c.Path $userProbe.Path)) { SayItem '  备选' "$($c.Path)（$($c.Source)）" }
    }
    if (-not [string]::IsNullOrWhiteSpace($weaselProbe.Path)) {
        SayItem '小狼毫目录' "$($weaselProbe.Path)（$($weaselProbe.Source)）"
        $verText = '未知'
        if (-not [string]::IsNullOrWhiteSpace($weaselVersion)) { $verText = "$weaselVersion（$weaselVersionSource）" }
        $dllText = '无版本信息'
        if (-not [string]::IsNullOrWhiteSpace($rimeDllVersion)) { $dllText = $rimeDllVersion }
        SayItem '小狼毫版本' "$verText；rime.dll：$dllText"
    } else {
        SayItem '小狼毫目录' '未找到（无法自动部署；可用 -WeaselDir 指定，或加 -NoDeploy）' 'Yellow'
        foreach ($c in $weaselProbe.Candidates) { SayItem '  候选' "$($c.Path)（$($c.Source)，不含 WeaselDeployer.exe）" }
    }
    SayItem '日志目录' $logDir

    $installedCount = 0
    foreach ($rel in $manifest) {
        if (Test-Path -LiteralPath (Join-Path $userProbe.Path $rel) -PathType Leaf) { $installedCount++ }
    }
    SayItem '已安装状态' "$installedCount / $($manifest.Count) 个运行时文件存在"

    # 需要部署但找不到小狼毫时，直接失败，避免用户以为装好了。
    if (-not $NoDeploy -and [string]::IsNullOrWhiteSpace($weaselProbe.Path) -and $Action -ne 'verify') {
        Fail '找不到小狼毫安装目录，无法自动部署。请用 -WeaselDir 指定安装目录（含 WeaselDeployer.exe），或加 -NoDeploy 只复制文件。' 3
    }

    # ---- 确保用户目录可写
    if (-not $DryRun -and -not (Test-Path -LiteralPath $userProbe.Path)) {
        try { New-Item -ItemType Directory -Force -Path $userProbe.Path | Out-Null }
        catch { Fail "无法创建 Rime 用户目录 $($userProbe.Path)：$($_.Exception.Message)" 5 }
    }
    if (-not $DryRun) {
        $probeFile = Join-Path $userProbe.Path '.ff7-ime-write-test.tmp'
        try {
            Set-Content -LiteralPath $probeFile -Value 'ok' -Encoding ASCII -ErrorAction Stop
            Remove-Item -LiteralPath $probeFile -Force -ErrorAction SilentlyContinue
        } catch {
            Fail "Rime 用户目录不可写：$($userProbe.Path)（$($_.Exception.Message)）" 5
        }
    }

    # ---- 执行
    $installResult = $null
    $uninstallResult = $null
    $verifyOk = $null

    switch ($Action) {
        'install' { $installResult = Invoke-Install -Probe $probe }
        'uninstall' { $uninstallResult = Invoke-Uninstall -Probe $probe }
        'verify' {
            $verifyOk = Invoke-Verify -Probe $probe
            if (-not $verifyOk) { $script:ExitCode = 1 }
        }
    }

    if ($DryRun) { Say ''; Say '（预演结束：没有写入任何文件）' 'Yellow' }

    $result = [ordered]@{
        ok = ($script:ExitCode -eq 0)
        action = $Action
        dry_run = [bool]$DryRun
        schema = $script:SchemaId
        schema_name = $script:SchemaName
        version = $script:Version
        package_root = $packageRoot
        manifest = @($manifest)
        rime_user_dir = $userProbe.Path
        rime_user_dir_source = $userProbe.Source
        rime_user_dir_exists = $userDirExists
        rime_user_dir_candidates = @($userProbe.Candidates | ForEach-Object { "$($_.Path) [$($_.Source)]" })
        weasel_dir = $weaselProbe.Path
        weasel_dir_source = $weaselProbe.Source
        weasel_dir_candidates = @($weaselProbe.Candidates | ForEach-Object { "$($_.Path) [$($_.Source)]" })
        weasel_version = $weaselVersion
        weasel_version_source = $weaselVersionSource
        rime_dll_version = $rimeDllVersion
        log_dir = $logDir
        elevated = $elevated
        no_deploy = [bool]$NoDeploy
        installed_files_present = $installedCount
        build_artifact = (Test-Path -LiteralPath $buildSchemaPath -PathType Leaf)
        build_artifact_before = $hadBuildArtifact
        actions = @($script:Actions)
        backups = @($script:Backups)
        warnings = @($script:Warnings)
        errors = @($script:Errors)
        install = $installResult
        uninstall = $uninstallResult
        verify_ok = $verifyOk
    }

    if ($script:JsonMode) {
        # librime 会把自己的诊断直接写到 stderr（glog 默认把 ERROR 复制到 stderr），
        # 调用方一旦把 2>&1 合并，JSON 就会被污染。所以机器模式用固定前缀标记，
        # 取这一行、去掉前缀就是完整 JSON。
        Write-Output ("FF7IME-JSON " + ($result | ConvertTo-Json -Depth 6 -Compress))
    } else {
        Say ''
        if ($script:ExitCode -eq 0) { Say "完成（退出码 0）。" 'Green' } else { Say "结束，退出码 $($script:ExitCode)。" 'Yellow' }
    }
    exit $script:ExitCode
} catch {
    $code = 1
    if ($_.Exception.Data.Contains('Ff7ImeExitCode')) { $code = [int]$_.Exception.Data['Ff7ImeExitCode'] }
    if (-not $script:JsonMode) {
        Say ''
        Say "错误：$($_.Exception.Message)" 'Red'
        if ($code -eq 2) { Say '提示：请从完整的发布包 / 仓库副本运行安装器。' 'Yellow' }
        if ($code -eq 3) { Say '提示：-WeaselDir 指向小狼毫安装目录（含 WeaselDeployer.exe），或加 -NoDeploy 只复制文件。' 'Yellow' }
        if ($code -eq 5) { Say '提示：检查目录权限；Rime 用户目录不需要管理员权限，除非被安全软件拦截。' 'Yellow' }
    } else {
        [void]$script:Errors.Add($_.Exception.Message)
        $failResult = [ordered]@{
            ok = $false
            action = $Action
            error = $_.Exception.Message
            exit_code = $code
            warnings = @($script:Warnings)
            errors = @($script:Errors)
            actions = @($script:Actions)
        }
        Write-Output ("FF7IME-JSON " + ($failResult | ConvertTo-Json -Depth 6 -Compress))
    }
    exit $code
}
