<#
  FieldTrack Pro - Tally Sync Agent installer (run as Administrator on the machine that runs TallyPrime).

    powershell -ExecutionPolicy Bypass -File .\install_agent.ps1                         # the production agent
    powershell -ExecutionPolicy Bypass -File .\install_agent.ps1 -InstanceName STAGING   # a separate, named instance
    ... add -WhatIf to validate everything and print the plan WITHOUT changing anything.

  Default instance (no -InstanceName) - unchanged behaviour since 1.2.2:
    task FieldTrack_TallySyncAgent, folder C:\TallyAgent\tally_agent_1.1.0\tally_agent_1.1.0 (the existing install).

  Named instance (-InstanceName NAME, 1-20 of A-Z 0-9 _ , not DEFAULT) - for an acceptance/staging agent that must
  run BESIDE the production agent without touching it:
    task FieldTrack_TallySyncAgent_NAME, folder C:\FieldTrackAgent_NAME (or -InstallDir).
    Refuses: the production task name, any folder under C:\TallyAgent, a .env whose AGENT_INSTANCE_NAME is not NAME,
    and a .env pointing at the production backend. Only stops agent processes running FROM ITS OWN FOLDER.

  What it does:
    1. Validates parameters and the .env that will be used (and stops here with -WhatIf).
    2. Stops this instance's Scheduled Task, then this instance's agent processes:
         default instance: every FieldTrackTallyAgent process EXCEPT those running from a named-instance folder
                           (C:\...\FieldTrackAgent_<NAME>\...), as before (reaches orphaned onefile children);
         named instance:   only processes whose executable is inside -InstallDir.
    3. Polls up to 30 s until none remain; otherwise ABORTS without replacing, backing up or restarting anything.
    4. Backs up the existing .env, data\ and exe to _pre_install_backup_<timestamp> (quiescent copy).
    5. Copies FieldTrackTallyAgent.exe into -InstallDir.
    6. Never overwrites an existing .env; never touches data\sync_agent.db (checkpoints, retry queue).
    7. Restricts .env (agent key) to SYSTEM and Administrators.
    8. Registers / starts the Scheduled Task (at startup, SYSTEM, restart 999 x 1 min, IgnoreNew) and reports state.

  Read-only towards Tally: agent 2.x performs no write-back.
#>
param(
    [string]$InstallDir = "C:\TallyAgent\tally_agent_1.1.0\tally_agent_1.1.0",
    [string]$TaskName = "FieldTrack_TallySyncAgent",
    [string]$InstanceName = "",
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"

$DefaultTask = "FieldTrack_TallySyncAgent"
$ProductionDir = "C:\TallyAgent\tally_agent_1.1.0\tally_agent_1.1.0"
$ProductionBackend = "https://51-79-158-138.sslip.io"
$Named = $false

function Fail([string]$msg) { Write-Error $msg; exit 1 }
function Read-EnvValue([string]$path, [string]$key) {
    if (-not (Test-Path $path)) { return $null }
    foreach ($line in Get-Content $path) {
        $t = $line.Trim()
        if ($t -and -not $t.StartsWith("#") -and $t -match "^\s*$key\s*=(.*)$") { return $Matches[1].Trim().Trim('"').Trim("'") }
    }
    return $null
}

# ---------------------------------------------------------------------------
# 1. Parameters and instance guards
# ---------------------------------------------------------------------------
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
    if ($TaskName -ieq $DefaultTask) { Fail "A named instance must not use the production task name '$DefaultTask'." }
    if ($InstallDir.TrimEnd('\') -ieq [IO.Path]::GetFullPath($ProductionDir).TrimEnd('\') -or
        $InstallDir.StartsWith("C:\TallyAgent\", [StringComparison]::OrdinalIgnoreCase) -or $InstallDir -ieq "C:\TallyAgent") {
        Fail "A named instance must not be installed into the production agent's folder ($InstallDir)."
    }
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exeSrc = Join-Path $here "FieldTrackTallyAgent.exe"
if (-not (Test-Path $exeSrc)) {
    if ($WhatIf) { Write-Warning "FieldTrackTallyAgent.exe not found next to this script (required for a real install)." }
    else { Fail "FieldTrackTallyAgent.exe not found next to this script." }
}

$envDst = Join-Path $InstallDir ".env"
$dataDst = Join-Path $InstallDir "data"
$targetEnvExists = Test-Path $envDst
$envSrc = Join-Path $here ".env"
$templateSrc = Join-Path $here "env.template"
$envToUse = if ($targetEnvExists) { $envDst } elseif (Test-Path $envSrc) { $envSrc } elseif (Test-Path $templateSrc) { $templateSrc } else { $null }
if (-not $envToUse) { Fail "No .env or env.template found next to this script, and no existing .env at target." }

$envInstance = (Read-EnvValue $envToUse "AGENT_INSTANCE_NAME")
$envInstance = if ($envInstance) { $envInstance.ToUpper() } else { "" }
$envBackend = Read-EnvValue $envToUse "BACKEND_URL"
$usingTemplate = ($envToUse -eq $templateSrc)
if ($Named) {
    if (-not $usingTemplate -and $envInstance -ne $InstanceName) {
        Fail "The .env to be used ($envToUse) has AGENT_INSTANCE_NAME='$envInstance', expected '$InstanceName'. Set it first."
    }
    $allowProd = (Read-EnvValue $envToUse "ALLOW_NAMED_INSTANCE_ON_PRODUCTION")
    if (-not $usingTemplate -and $envBackend -and $envBackend.TrimEnd('/') -ieq $ProductionBackend -and $allowProd -notmatch '^(1|true|yes|on)$') {
        Fail "The .env for named instance '$InstanceName' points at the production backend ($ProductionBackend). Refusing."
    }
} else {
    if ($envInstance) {
        Fail "The .env to be used ($envToUse) sets AGENT_INSTANCE_NAME='$envInstance'; install it with -InstanceName $envInstance."
    }
}

# Placeholder check on SETTING lines only (comment lines may mention placeholders). Done here, so -WhatIf catches it too.
function Get-PlaceholderLines([string]$path) {
    return @(Get-Content $path | Where-Object { $_.Trim() -and -not $_.TrimStart().StartsWith("#") -and $_ -match "REPLACE_ME|your-agent|your-organization" })
}
if (-not $targetEnvExists -and $envToUse -eq $envSrc) {
    $ph = Get-PlaceholderLines $envSrc
    if ($ph.Count -gt 0) {
        Fail (".env next to this script still has $($ph.Count) placeholder value(s): " + (($ph | ForEach-Object { ($_ -split "=", 2)[0].Trim() }) -join ", ") + ". Fill them in first.")
    }
}

$plan = @(
    "Instance:      $(if ($Named) { $InstanceName } else { 'default (production)' })",
    "Task:          $TaskName",
    "Install dir:   $InstallDir",
    ".env used:     $envToUse $(if ($targetEnvExists) { '(existing at target - kept)' } else { '(copied to target)' })",
    "Backend (env): $envBackend",
    "Processes:     $(if ($Named) { "only FieldTrackTallyAgent processes running from $InstallDir" } else { 'all FieldTrackTallyAgent processes except named-instance folders' })"
)
if ($WhatIf) {
    Write-Host "WHATIF - validation passed. Nothing was stopped, copied or registered. Plan:" -ForegroundColor Cyan
    $plan | ForEach-Object { Write-Host "  $_" }
    exit 0
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Run this script as Administrator (right-click PowerShell > Run as administrator)."
}
$plan | ForEach-Object { Write-Host $_ }

# Agent processes that belong to THIS instance (see header).
function Get-InstanceProcesses {
    $all = @(Get-CimInstance Win32_Process -Filter "Name='FieldTrackTallyAgent.exe'" -ErrorAction SilentlyContinue)
    if ($Named) {
        $prefix = $InstallDir.TrimEnd('\') + '\'
        return @($all | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
    }
    return @($all | Where-Object { -not ($_.ExecutablePath -match '\\FieldTrackAgent_[A-Za-z0-9_]+\\') })
}
function Stop-InstanceProcesses { Get-InstanceProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }

# ---------------------------------------------------------------------------
# 2-3. Stop this instance's task and processes; poll until none remain (30 s) or abort untouched.
# ---------------------------------------------------------------------------
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Stop-InstanceProcesses
$maxWaitSeconds = 30
$elapsed = 0
$remaining = Get-InstanceProcesses
while ($remaining.Count -gt 0 -and $elapsed -lt $maxWaitSeconds) {
    Start-Sleep -Seconds 1
    $elapsed += 1
    Stop-InstanceProcesses
    $remaining = Get-InstanceProcesses
}
if ($remaining.Count -gt 0) {
    $survivingPids = ($remaining | Select-Object -ExpandProperty ProcessId) -join ", "
    Fail ("Timed out after ${maxWaitSeconds}s waiting for this instance's FieldTrackTallyAgent process(es) to exit " +
        "(still running: PID $survivingPids). Aborting - the existing EXE was NOT replaced, nothing was " +
        "backed up, and the Scheduled Task was NOT restarted.")
}
Write-Host "Confirmed zero agent processes of this instance remain (waited ${elapsed}s)." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Back up what is there (quiescent: only after confirmed termination).
# ---------------------------------------------------------------------------
if (Test-Path $InstallDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $InstallDir "_pre_install_backup_$stamp"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    if ($targetEnvExists) { Copy-Item $envDst (Join-Path $backupDir ".env") -Force }
    if (Test-Path $dataDst) { Copy-Item $dataDst (Join-Path $backupDir "data") -Recurse -Force }
    $oldExe = Join-Path $InstallDir "FieldTrackTallyAgent.exe"
    if (Test-Path $oldExe) { Copy-Item $oldExe (Join-Path $backupDir "FieldTrackTallyAgent.exe") -Force }
    Write-Host "Backed up existing .env / data / exe to $backupDir" -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item $exeSrc (Join-Path $InstallDir "FieldTrackTallyAgent.exe") -Force

# ---------------------------------------------------------------------------
# 5. .env: NEVER overwrite an existing one.
# ---------------------------------------------------------------------------
if ($targetEnvExists) {
    Write-Host "Existing .env found at $envDst - left untouched (existing agent credentials preserved)." -ForegroundColor Green
} elseif ($envToUse -eq $envSrc) {
    if ((Get-PlaceholderLines $envSrc).Count -gt 0) {
        Fail ".env next to this script still contains placeholder values. Fill it in first."
    }
    Copy-Item $envSrc $envDst -Force
    Write-Host "No existing .env at target - installed the one provided next to this script." -ForegroundColor Yellow
} else {
    Copy-Item $templateSrc $envDst -Force
    if ($Named) { Add-Content -Path $envDst -Value "`r`nAGENT_INSTANCE_NAME=$InstanceName" }
    Write-Warning "No existing .env at target and none provided - copied env.template to $envDst as a placeholder."
    Write-Warning "Edit $envDst (AGENT_ID / AGENT_KEY / ORGANIZATION_ID$(if ($Named) { ', BACKEND_URL of the non-production backend' })) before the agent will work, then: Restart-ScheduledTask -TaskName $TaskName"
}
icacls $envDst /inheritance:r /grant:r "SYSTEM:(R)" "BUILTIN\Administrators:(F)" | Out-Null

if (Test-Path (Join-Path $dataDst "sync_agent.db")) {
    Write-Host "Existing checkpoint database found at $dataDst\sync_agent.db - left untouched (sync resumes)." -ForegroundColor Green
} else {
    Write-Host "No existing checkpoint database - the agent creates one and performs the first full load." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 6. Register and start this instance's Scheduled Task.
# ---------------------------------------------------------------------------
$exe = Join-Path $InstallDir "FieldTrackTallyAgent.exe"
$action = New-ScheduledTaskAction -Execute $exe -Argument "daemon" -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "FieldTrack Pro - Tally Sync Agent$(if ($Named) { " ($InstanceName)" }) (starts at boot, read-only towards Tally)" | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

$t = Get-ScheduledTask -TaskName $TaskName
$finalProcs = Get-InstanceProcesses
Write-Host ""
Write-Host "Installed to $InstallDir" -ForegroundColor Green
Write-Host "Task '$TaskName' state: $($t.State)   (starts automatically at boot, runs as SYSTEM)"
if ($t.State -ne "Running") {
    Write-Warning "Task state is '$($t.State)', not 'Running'. Check: Get-ScheduledTaskInfo -TaskName '$TaskName', and $InstallDir\data\sync_agent.log"
}
Write-Host "Agent processes of this instance: $($finalProcs.Count)   (expect 2 - bootloader + child)"
Write-Host "Check status any time:   & '$exe' status"
Write-Host "Log file:                $InstallDir\data\sync_agent.log"
Write-Host "Stop / remove:           Stop-ScheduledTask -TaskName $TaskName   |   .\uninstall_agent.ps1$(if ($Named) { " -InstanceName $InstanceName" })"
