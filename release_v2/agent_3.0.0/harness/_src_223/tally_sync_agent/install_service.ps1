param(
    [string]$TaskName = "FieldTrack_TallySyncAgent",
    [string]$PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
)

if (-not $PythonExe) {
    Write-Error "Python executable not found in system PATH. Please specify -PythonExe <path>."
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkingDir = Split-Path -Parent $ScriptDir
$ServiceRunnerScript = Join-Path $ScriptDir "service_runner.py"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Installing FieldTrack Pro Tally Sync Agent Service" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Task Name:    $TaskName"
Write-Host "Python:       $PythonExe"
Write-Host "Working Dir:  $WorkingDir"
Write-Host "Script:       $ServiceRunnerScript"

$ArgumentString = '"' + $ServiceRunnerScript + '"'
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $ArgumentString -WorkingDirectory $WorkingDir
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $TriggerLogon -Settings $Settings -Description "FieldTrack Pro - Tally Sync Bridge Agent Service" -ErrorAction Stop

    Write-Host ""
    Write-Host "SUCCESS: Background Service Task registered successfully!" -ForegroundColor Green
    Write-Host "To start the task immediately, run:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName $TaskName" -ForegroundColor White
    Write-Host "To stop the task, run:" -ForegroundColor Yellow
    Write-Host "  Stop-ScheduledTask -TaskName $TaskName" -ForegroundColor White
} catch {
    Write-Error $_
}
