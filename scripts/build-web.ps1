$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location (Join-Path $root "product\web")
npm ci
npm run build
Write-Host "Built product/web/dist"
