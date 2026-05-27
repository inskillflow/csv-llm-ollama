# stop.ps1 — arrête l'app Streamlit du port 8504
$port = 8504
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    $pids = $conn.OwningProcess | Sort-Object -Unique
    foreach ($pid in $pids) {
        try {
            $proc = Get-Process -Id $pid -ErrorAction Stop
            Write-Host "Arrêt PID=$pid ($($proc.ProcessName))…" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force
        } catch { }
    }
    Write-Host "Port $port libéré." -ForegroundColor Green
} else {
    Write-Host "Aucun processus n'écoute sur le port $port." -ForegroundColor Cyan
}
