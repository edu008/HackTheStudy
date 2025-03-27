# PowerShell-Skript zum Einrichten und Testen der PyLint-Integration

# Zum Backend-Verzeichnis wechseln, falls das Skript von einem anderen Verzeichnis aufgerufen wird
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $scriptPath

Write-Host "=== Einrichtung der PyLint-Integration ===" -ForegroundColor Cyan
Write-Host ""

# Prüfen, ob PyLint und autopep8 installiert sind
Write-Host "Prüfe, ob PyLint und autopep8 installiert sind..." -ForegroundColor Yellow
$PYLINT_INSTALLED = pip list | Where-Object { $_ -match "pylint" }
$AUTOPEP8_INSTALLED = pip list | Where-Object { $_ -match "autopep8" }

if (-not $PYLINT_INSTALLED) {
    Write-Host "⚠️ PyLint ist nicht installiert. Installiere es mit:" -ForegroundColor Red
    Write-Host "   pip install pylint==2.17.5" -ForegroundColor Yellow
}
else {
    Write-Host "✅ PyLint ist installiert: $PYLINT_INSTALLED" -ForegroundColor Green
}

if (-not $AUTOPEP8_INSTALLED) {
    Write-Host "⚠️ autopep8 ist nicht installiert. Installiere es mit:" -ForegroundColor Red
    Write-Host "   pip install autopep8==2.0.4" -ForegroundColor Yellow
}
else {
    Write-Host "✅ autopep8 ist installiert: $AUTOPEP8_INSTALLED" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== PyLint-Konfiguration ===" -ForegroundColor Cyan
Write-Host "Die Konfigurationsdatei befindet sich in: $((Get-Location).Path)\pylintrc" -ForegroundColor White
Write-Host ""

Write-Host "=== Test-Linting ===" -ForegroundColor Cyan
Write-Host "Du kannst das Linting-Skript jetzt testen mit:" -ForegroundColor White
Write-Host "  python lint.py" -ForegroundColor Yellow
Write-Host "  python lint.py --path main/app.py" -ForegroundColor Yellow
Write-Host "  python lint.py --fix --path worker/" -ForegroundColor Yellow
Write-Host ""

Write-Host "=== Dokumentation ===" -ForegroundColor Cyan
Write-Host "Eine detaillierte Dokumentation zur Verwendung von PyLint findest du in:" -ForegroundColor White
Write-Host "  $((Get-Location).Path)\LINTING.md" -ForegroundColor Yellow
Write-Host ""

Write-Host "=== Fertig ===" -ForegroundColor Green
Write-Host "Die PyLint-Integration wurde erfolgreich eingerichtet." -ForegroundColor White

# Informationen zur Ausführung von Python-Skripten in PowerShell
Write-Host ""
Write-Host "Hinweis: Falls du Probleme bei der Ausführung von lint.py hast, versuche folgendes:" -ForegroundColor Yellow
Write-Host "  - Stelle sicher, dass die Python-Umgebung aktiviert ist" -ForegroundColor White
Write-Host "  - Verwende python.exe oder python3.exe explizit:" -ForegroundColor White
Write-Host "    python.exe lint.py" -ForegroundColor Yellow
Write-Host "  - Bei Berechtigungsproblemen, starte PowerShell als Administrator" -ForegroundColor White 