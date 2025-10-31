param(
    [string]$TaskName = "ActiveAppsMonitor-HourlySummary",
    [string]$LogFile = "$PSScriptRoot\..\app-usage.log",
    [string]$OutLog = "$PSScriptRoot\..\usage-hourly.log",
    [string]$State = "$PSScriptRoot\..\.simple_hourly_state.json",
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$scriptRoot = $PSScriptRoot
$summaryPath = (Join-Path $scriptRoot '..\simple_hourly.py' | Resolve-Path).Path

# Create a tiny wrapper script to keep scheduled task command short
$wrapperPath = Join-Path $scriptRoot 'run-hourly-summary.ps1'
$wrapperContent = @"
param(
    [string]
    $LogFile = "$LogFile",
    [string]
    $OutLog = "$OutLog",
    [string]
    $State = "$State"
)
python "$summaryPath" --logfile "$LogFile" --out-log "$OutLog" --append --state "$State"
"@
Set-Content -LiteralPath $wrapperPath -Value $wrapperContent -Encoding UTF8

if (-not $Quiet) { Write-Host "Registering hourly summary task to run wrapper: $wrapperPath" -ForegroundColor Yellow }

# Create a trigger that repeats every hour indefinitely
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperPath`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
    Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action -Settings $settings -Description "Append hourly grouped active logs" -Force | Out-Null
    if (-not $Quiet) { Write-Host "Task '$TaskName' registered (runs hourly)." -ForegroundColor Green }
} catch {
    if (-not $Quiet) { Write-Warning "Falling back to schtasks.exe..." }
    $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$wrapperPath`""
    $schtasks = "schtasks /Create /TN `"$TaskName`" /TR `"$tr`" /SC HOURLY /MO 1 /F"
    cmd.exe /c $schtasks | Write-Output
}
