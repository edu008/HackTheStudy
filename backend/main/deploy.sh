#!/bin/bash
# Deployment-Skript für die HackTheStudy Backend API

# Stelle sicher, dass das Skript bei Fehlern abbricht
set -e

# Konfiguration
APP_DIR=$(pwd)
LOG_DIR="/var/log/hackthestudy"
VENV_PATH="${APP_DIR}/venv"
REQUIREMENTS_FILE="${APP_DIR}/requirements.txt"
GUNICORN_CONF="${APP_DIR}/gunicorn.conf.py"
PORT=8080

# Farbige Ausgabe für bessere Lesbarkeit
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Funktion zum Anzeigen von Statusmeldungen
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# Funktion zum Anzeigen von Warnungen
warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNUNG: $1${NC}"
}

# Funktion zum Anzeigen von Fehlern
error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] FEHLER: $1${NC}"
    exit 1
}

# Willkommensnachricht
log "Starte Deployment der HackTheStudy Backend API..."
log "Arbeitsverzeichnis: ${APP_DIR}"

# Erstelle Log-Verzeichnis, falls es nicht existiert
if [ ! -d "$LOG_DIR" ]; then
    log "Erstelle Log-Verzeichnis: ${LOG_DIR}"
    sudo mkdir -p "$LOG_DIR"
    sudo chown -R $(whoami):$(whoami) "$LOG_DIR"
fi

# Prüfe, ob Python 3 installiert ist
if ! command -v python3 &> /dev/null; then
    error "Python 3 ist nicht installiert. Bitte installiere Python 3 und versuche es erneut."
fi

log "Python $(python3 --version) gefunden."

# Prüfe, ob pip installiert ist
if ! command -v pip3 &> /dev/null; then
    error "pip3 ist nicht installiert. Bitte installiere pip und versuche es erneut."
fi

# Erstelle virtuelle Umgebung, falls sie nicht existiert
if [ ! -d "$VENV_PATH" ]; then
    log "Erstelle virtuelle Python-Umgebung in ${VENV_PATH}..."
    python3 -m venv "$VENV_PATH"
else
    log "Virtuelle Python-Umgebung bereits vorhanden."
fi

# Aktiviere virtuelle Umgebung
log "Aktiviere virtuelle Umgebung..."
source "${VENV_PATH}/bin/activate"

# Aktualisiere pip und setuptools
log "Aktualisiere pip und setuptools..."
pip install --upgrade pip setuptools wheel

# Installiere Abhängigkeiten
log "Installiere Python-Abhängigkeiten aus ${REQUIREMENTS_FILE}..."
pip install -r "$REQUIREMENTS_FILE"

# Prüfe, ob Gunicorn installiert ist
if ! pip show gunicorn &> /dev/null; then
    warn "Gunicorn ist nicht installiert. Installiere Gunicorn..."
    pip install gunicorn>=21.2.0 gevent>=23.9.1
fi

# Prüfe, ob Gunicorn-Konfigurationsdatei existiert
if [ ! -f "$GUNICORN_CONF" ]; then
    error "Gunicorn-Konfigurationsdatei nicht gefunden: ${GUNICORN_CONF}"
fi

# Erstelle systemd Service-Datei
SERVICE_NAME="hackthestudy-api"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log "Erstelle systemd Service-Datei in ${SERVICE_FILE}..."

# Erstelle Service-Datei mit sudo
cat << EOF | sudo tee "$SERVICE_FILE" > /dev/null
[Unit]
Description=HackTheStudy Backend API
After=network.target

[Service]
User=$(whoami)
Group=$(whoami)
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_PATH}/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PORT=${PORT}"
Environment="FLASK_APP=app.py"
Environment="PYTHONUNBUFFERED=1"
ExecStart=${VENV_PATH}/bin/gunicorn --config=${GUNICORN_CONF} app:app
Restart=always
RestartSec=5
StandardOutput=append:${LOG_DIR}/api-access.log
StandardError=append:${LOG_DIR}/api-error.log

[Install]
WantedBy=multi-user.target
EOF

# Aktualisiere systemd
log "Aktualisiere systemd..."
sudo systemctl daemon-reload

# Aktiviere und starte den Service
log "Aktiviere den Service ${SERVICE_NAME}..."
sudo systemctl enable "$SERVICE_NAME"

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Starte den Service ${SERVICE_NAME} neu..."
    sudo systemctl restart "$SERVICE_NAME"
else
    log "Starte den Service ${SERVICE_NAME}..."
    sudo systemctl start "$SERVICE_NAME"
fi

# Überprüfe den Status des Services
log "Überprüfe den Status des Services ${SERVICE_NAME}..."
sudo systemctl status "$SERVICE_NAME"

log "Deployment abgeschlossen! Die API sollte jetzt unter http://localhost:${PORT} verfügbar sein."
log "Server-Logs befinden sich in ${LOG_DIR}/api-access.log und ${LOG_DIR}/api-error.log" 