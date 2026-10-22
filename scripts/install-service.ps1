# Install Lira as a Windows service through NSSM.
# NSSM is an external prerequisite: https://nssm.cc/
param(
    [string]$ServiceName = "Lira",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "nssm is not in PATH. Install NSSM first, then re-run this script."
}
$uv = (Get-Command uv -ErrorAction Stop).Source
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $root "product"

nssm install $ServiceName $uv "run --directory `"$project`" python -m app.main"
nssm set $ServiceName AppDirectory $root
nssm set $ServiceName AppEnvironmentExtra "LIRA_API_PORT=$Port"
nssm set $ServiceName Start SERVICE_AUTO_START
nssm start $ServiceName

Write-Host "Installed $ServiceName on port $Port."
Write-Host "Set LIRA_PIN in the service environment before exposing it on a LAN."
