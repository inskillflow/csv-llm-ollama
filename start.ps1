# start.ps1 — démarre l'app Ollama (port 8504).
# Layout attendu : ce dossier (csv-llm-ollama/) est un sibling de csv-llm-shared/.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$shared = Join-Path (Split-Path $PSScriptRoot -Parent) "csv-llm-shared"
if (-not (Test-Path $shared)) {
    Write-Host "csv-llm-shared introuvable a $shared" -ForegroundColor Red
    Write-Host "Clone https://github.com/.../csv-llm-shared a cote de csv-llm-ollama." -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/3] Verification d'Ollama..." -ForegroundColor Cyan
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
    Write-Host "    Ollama est en marche." -ForegroundColor Green
} catch {
    Write-Host "    Ollama ne repond pas. Lance d'abord : ollama serve" -ForegroundColor Yellow
}

Write-Host "[2/3] Verification du modele llama3.1:8b..." -ForegroundColor Cyan
$tags = ollama list 2>$null
if ($tags -notmatch "llama3\.1:8b") {
    Write-Host "    Telechargement (~4.7 Go, lent la 1re fois)..." -ForegroundColor Yellow
    ollama pull llama3.1:8b
}

Write-Host "[3/3] Lancement Streamlit sur http://127.0.0.1:8504 ..." -ForegroundColor Cyan
streamlit run app.py --server.port 8504 --server.headless true
