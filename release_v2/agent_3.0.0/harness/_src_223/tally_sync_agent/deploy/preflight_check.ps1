<#
  Read-only pre-flight for the machine that runs TallyPrime. Changes nothing, sends no business data.
    powershell -ExecutionPolicy Bypass -File .\preflight_check.ps1 [-BackendUrl https://51-79-158-138.sslip.io]
#>
param([string]$BackendUrl = "https://51-79-158-138.sslip.io", [string]$TallyHost = "127.0.0.1", [int]$TallyPort = 9000)

function Row($name, $ok, $detail) {
    $mark = if ($ok) { "PASS" } else { "FAIL" }
    $color = if ($ok) { "Green" } else { "Red" }
    Write-Host ("[{0}] {1}  {2}" -f $mark, $name.PadRight(42), $detail) -ForegroundColor $color
}

$os = (Get-CimInstance Win32_OperatingSystem)
Row "Windows" $true "$($os.Caption) $($os.Version), $([math]::Round($os.TotalVisibleMemorySize/1MB,1)) GB RAM"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Row "Running as Administrator" $isAdmin "(needed to install)"
$free = [math]::Round((Get-PSDrive C).Free/1GB,1)
Row "Free space on C:" ($free -gt 1) "$free GB"

$tallyProc = Get-Process | Where-Object { $_.ProcessName -match "tally" } | Select-Object -First 1
Row "TallyPrime process running" ($null -ne $tallyProc) $(if ($tallyProc) { $tallyProc.ProcessName } else { "not found" })

$tcp = $false
try { $c = New-Object Net.Sockets.TcpClient; $iar = $c.BeginConnect($TallyHost, $TallyPort, $null, $null); $tcp = $iar.AsyncWaitHandle.WaitOne(2000) -and $c.Connected; $c.Close() } catch {}
Row "Tally XML port ${TallyHost}:${TallyPort} open" $tcp $(if ($tcp) { "" } else { "enable: F1 Help > Settings > Connectivity > Client/Server configuration" })

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $r = Invoke-WebRequest -UseBasicParsing -Uri "$BackendUrl/health" -TimeoutSec 20
    Row "FieldTrack API reachable (HTTPS)" ($r.StatusCode -eq 200) "$($r.StatusCode) $($r.Content)"
} catch { Row "FieldTrack API reachable (HTTPS)" $false $_.Exception.Message }

$exe = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "FieldTrackTallyAgent.exe"
if (Test-Path $exe) {
    Write-Host ""; Write-Host "Agent says about Tally:" -ForegroundColor Cyan
    & $exe test-tally 2>&1 | Select-Object -Last 6
}
