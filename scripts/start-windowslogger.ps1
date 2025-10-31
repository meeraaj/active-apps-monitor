param(
    [ValidateSet("active","process","both")]
    [string]$Mode = "active",
    [string]$LogFile = "$env:LOCALAPPDATA\ActiveAppsMonitor\app-usage.log",
    [double]$Interval = 2.0,
    [double]$Heartbeat = 300,
    [switch]$StdOut,
    [switch]$IncludeSystem,
    [switch]$ProcSnapshot,
    [switch]$NoRotate,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

# Ensure log directory exists
$logDir = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($LogFile))
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$scriptRoot = $PSScriptRoot
$loggerPath = Join-Path $scriptRoot "..\windowslogger.py" | Resolve-Path

$argsList = @("`"$($loggerPath.Path)`"", "--mode", $Mode, "--logfile", "`"$LogFile`"", "--interval", $Interval)
if ($Heartbeat -ge 0) { $argsList += @("--heartbeat", $Heartbeat) }
if ($StdOut) { $argsList += @("--stdout") }
if ($IncludeSystem) { $argsList += @("--include-system") }
if ($ProcSnapshot) { $argsList += @("--proc-snapshot") }
if ($NoRotate) { $argsList += @("--no-rotate") }

if (-not $Quiet) { Write-Host "Starting windowslogger: python $($argsList -join ' ')" -ForegroundColor Green }

# Launch hidden in background
$proc = Start-Process -FilePath "python" -ArgumentList $argsList -WorkingDirectory $scriptRoot -WindowStyle Hidden -PassThru
if (-not $Quiet) { Write-Host "Started PID $($proc.Id). Logs at $LogFile" -ForegroundColor Green }
