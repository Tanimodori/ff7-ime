#Requires -Version 5.1
<#
.SYNOPSIS
  Headless Rime deployment via rime.dll (no WeaselDeployer GUI).
#>
[CmdletBinding()]
param(
    [string]$SharedDataDir = 'C:\Program Files\Rime\weasel-0.17.4\data',
    [string]$UserDataDir = (Join-Path $env:APPDATA 'Rime'),
    [string]$LogDir = (Join-Path $env:TEMP 'rime.weasel')
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $SharedDataDir 'default.yaml'))) {
    throw "Invalid shared data dir: $SharedDataDir"
}
if (-not (Test-Path -LiteralPath $UserDataDir)) {
    New-Item -ItemType Directory -Force -Path $UserDataDir | Out-Null
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$code = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class RimeDeploy
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
    public static extern void RimeSetup(ref RimeTraits traits);
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeInitialize(ref RimeTraits traits);
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern int RimeStartMaintenance(int full_check);
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeJoinMaintenanceThread();
    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeFinalize();

    static IntPtr Utf8(string s)
    {
        if (s == null) return IntPtr.Zero;
        byte[] b = Encoding.UTF8.GetBytes(s);
        IntPtr p = Marshal.AllocHGlobal(b.Length + 1);
        Marshal.Copy(b, 0, p, b.Length);
        Marshal.WriteByte(p, b.Length, 0);
        return p;
    }

    public static int Deploy(string sharedDir, string userDir, string logDir)
    {
        RimeTraits t = new RimeTraits();
        t.data_size = Marshal.SizeOf(typeof(RimeTraits)) - 4;
        t.shared_data_dir = Utf8(sharedDir);
        t.user_data_dir = Utf8(userDir);
        t.distribution_name = Utf8("Rime");
        t.distribution_code_name = Utf8("weasel");
        t.distribution_version = Utf8("0.17.4");
        t.app_name = Utf8("rime.mgjy_deploy");
        t.modules = IntPtr.Zero;
        t.min_log_level = 2;
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
            IntPtr[] ptrs = new IntPtr[] {
                t.shared_data_dir, t.user_data_dir, t.distribution_name,
                t.distribution_code_name, t.distribution_version,
                t.app_name, t.log_dir
            };
            foreach (IntPtr p in ptrs)
            {
                if (p != IntPtr.Zero) Marshal.FreeHGlobal(p);
            }
        }
    }
}
'@

Add-Type -TypeDefinition $code -Language CSharp
$dllDir = Split-Path -Parent $SharedDataDir
$oldPath = $env:PATH
$env:PATH = "$dllDir;$env:PATH"
try {
    $started = [RimeDeploy]::Deploy($SharedDataDir, $UserDataDir, $LogDir)
    Write-Host "[MGJY] rime maintenance started=$started"
} finally {
    $env:PATH = $oldPath
}
