<#
  Removes a FieldTrack Tally Sync Agent Scheduled Task.

    powershell -ExecutionPolicy Bypass -File .\uninstall_agent.ps1                                   # production task, keeps files
    powershell -ExecutionPolicy Bypass -File .\uninstall_agent.ps1 -InstanceName STAGING -RemoveFiles # a named instance
    ... add -WhatIf to print what would happen without changing anything.

  SAFETY GUARANTEES
  * Even with -RemoveFiles, .env and data\sync_agent.db are NEVER deleted: they are copied to a sibling
    "..._preserved_<timestamp>" folder first.
  * A named instance only stops processes running from its own folder, never the production agent, and refuses
    the production task name and any folder under C:\TallyAgent.
  * The default (production) uninstall never stops processes running from a named-instance folder.
#>
param(
    [string]$InstallDir = "C:\TallyAgent\tally_agent_1.1.0\tally_agent_1.1.0",
    [string]$TaskName = "FieldTrack_TallySyncAgent",
    [string]$InstanceName = "",
    [switch]$RemoveFiles,
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"
$DefaultTask = "FieldTrack_TallySyncAgent"
$Named = $false
function Fail([string]$msg) { Write-Error $msg; exit 1 }

if ($InstanceName) {
    $InstanceName = $InstanceName.Trim().ToUpper()
    if ($InstanceName -eq "DEFAULT" -or $InstanceName -notmatch '^[A-Z0-9_]{1,20}$') {
        Fail "InstanceName '$InstanceName' is not allowed: use 1-20 of A-Z, 0-9, _ (not DEFAULT)."
    }
    $Named = $true
    if (-not $PSBoundParameters.ContainsKey("TaskName")) { $TaskName = "${DefaultTask}_$InstanceName" }
    if (-not $PSBoundParameters.ContainsKey("InstallDir")) { $InstallDir = "C:\FieldTrackAgent_$InstanceName" }
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
if ($Named) {
    if ($TaskName -ieq $DefaultTask) { Fail "A named instance must not remove the production task '$DefaultTask'." }
    if ($InstallDir.StartsWith("C:\TallyAgent\", [StringComparison]::OrdinalIgnoreCase) -or $InstallDir -ieq "C:\TallyAgent") {
        Fail "A named instance must not touch the production agent's folder ($InstallDir)."
    }
}

function Get-InstanceProcesses {
    $all = @(Get-CimInstance Win32_Process -Filter "Name='FieldTrackTallyAgent.exe'" -ErrorAction SilentlyContinue)
    if ($Named) {
        $prefix = $InstallDir.TrimEnd('\') + '\'
        return @($all | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
    }
    return @($all | Where-Object { -not ($_.ExecutablePath -match '\\FieldTrackAgent_[A-Za-z0-9_]+\\') })
}

if ($WhatIf) {
    Write-Host "WHATIF - nothing was changed. Plan:" -ForegroundColor Cyan
    Write-Host "  Instance:    $(if ($Named) { $InstanceName } else { 'default (production)' })"
    Write-Host "  Task:        $TaskName (stop + unregister)"
    Write-Host "  Processes:   $(if ($Named) { "only those running from $InstallDir" } else { 'all FieldTrackTallyAgent except named-instance folders' }) - currently $((Get-InstanceProcesses).Count)"
    Write-Host "  Files:       $(if ($RemoveFiles) { "remove $InstallDir after preserving .env and data\" } else { 'kept' })"
    exit 0
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Get-InstanceProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Task '$TaskName' removed."

if ($RemoveFiles -and (Test-Path $InstallDir)) {
    $envPath = Join-Path $InstallDir ".env"
    $dataPath = Join-Path $InstallDir "data"
    $hasEnv = Test-Path $envPath
    $hasData = Test-Path $dataPath
    if ($hasEnv -or $hasData) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $parent = Split-Path -Parent $InstallDir
        $leaf = Split-Path -Leaf $InstallDir
        $preserveDir = Join-Path $parent "${leaf}_preserved_$stamp"
        New-Item -ItemType Directory -Force -Path $preserveDir | Out-Null
        if ($hasEnv) { Copy-Item $envPath (Join-Path $preserveDir ".env") -Force }
        if ($hasData) { Copy-Item $dataPath (Join-Path $preserveDir "data") -Recurse -Force }
        Write-Host "NOT deleted: .env and data\ (checkpoints/retry queue) were copied to $preserveDir first." -ForegroundColor Yellow
    }
    Remove-Item -Recurse -Force $InstallDir
    Write-Host "Deleted $InstallDir (agent credentials and sync state preserved separately, see above)."
} else {
    Write-Host "Files kept in $InstallDir (use -RemoveFiles to remove the folder; .env and data\ are preserved either way)."
}
