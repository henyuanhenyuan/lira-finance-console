# Lira 2.0 一键启动（Windows PowerShell）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[1/3] 启动 PostgreSQL (pgvector)" -ForegroundColor Cyan
docker compose -f "$root\docker-compose.yml" up -d

Write-Host "[2/3] 构建前端" -ForegroundColor Cyan
if (-not (Test-Path "$root\frontend\node_modules")) {
  npm --prefix "$root\frontend" install
}
npm --prefix "$root\frontend" run build

Write-Host "[3/3] 启动后端 http://localhost:8012" -ForegroundColor Cyan
& "$root\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "$root\backend" --host 127.0.0.1 --port 8012
