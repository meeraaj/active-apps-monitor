param(
    [string]$TaskName = "ActiveAppsMonitor",
    [ValidateSet("active","process","both")]
    [string]$Mode = "active",
    [string]$LogFile = "$env:LOCALAPPDATA\ActiveAppsMonitor\app-usage.log",
    [double]$Interval = 2.0,
    [double]$Heartbeat = 300
)

$ErrorActionPreference = 'Stop'

$scriptRoot = $PSScriptRoot
$startScript = Join-Path $scriptRoot 'start-windowslogger.ps1' | Resolve-Path

$psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$($startScript.Path)`" -Mode $Mode -LogFile `"$LogFile`" -Interval $Interval -Heartbeat $Heartbeat"

Write-Host "Registering logon task '$TaskName' to run: powershell.exe $psArgs" -ForegroundColor Yellow

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6)

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Active/Process app monitor" -Force | Out-Null
    Write-Host "Task '$TaskName' registered. It will run at logon." -ForegroundColor Green
} catch {
    Write-Warning "Failed to register via Register-ScheduledTask. Trying schtasks.exe..."
    $schtasksCmd = "schtasks /Create /TN `"$TaskName`" /TR `"powershell.exe $psArgs`" /SC ONLOGON /RL LIMITED /F"
    Write-Host $schtasksCmd
    cmd.exe /c $schtasksCmd | Write-Output
}
