#!/bin/bash
set -e

echo "Starting Worker container..."

# Entferne alte Socket-Dateien
echo "Removing stale socket files..."
rm -f /tmp/supervisor-worker.sock
rm -f /tmp/supervisord-worker.pid
rm -f /tmp/supervisor.*
sleep 1

# Verzeichnisberechtigungen prüfen
echo "Checking directory permissions..."
mkdir -p /var/run/
chmod 755 /var/run/
chmod 755 /etc/supervisor/conf.d/

# Debug-Informationen anzeigen
echo "=== ENVIRONMENT VARIABLES ==="
echo "REDIS_URL: $REDIS_URL"
echo "REDIS_HOST: $REDIS_HOST"
echo "API_HOST: $API_HOST"
echo "CONTAINER_TYPE: $CONTAINER_TYPE"
echo "RUN_MODE: $RUN_MODE"
echo "============================"

# Hardcoded IP-Adresse des API-Services als Fallback
DEFAULT_API_HOST="10.0.0.3" # Typische IP für DigitalOcean-Container
if [ -z "$API_HOST" ]; then
    API_HOST="$DEFAULT_API_HOST"
    echo "API_HOST nicht gesetzt, verwende Default: $API_HOST"
fi

# Korrigiere Redis-URL falls nötig
if [ -z "$REDIS_URL" ] || [ "$REDIS_URL" == "redis://localhost:6379/0" ]; then
    if [ ! -z "$USE_API_URL" ]; then
        export REDIS_HOST="$USE_API_URL"
        export REDIS_URL="redis://$USE_API_URL:6379/0"
        echo "Überschreibe Redis-URL mit: $REDIS_URL (von USE_API_URL)"
    else
        echo "Verwende API_HOST für Redis-Verbindung: $API_HOST"
        export REDIS_HOST="$API_HOST"
        export REDIS_URL="redis://$API_HOST:6379/0"
        echo "Überschreibe Redis-URL mit: $REDIS_URL"
    fi
fi

# Füge eine Liste von möglichen API-Adressen hinzu, die wir nacheinander versuchen können
API_ADDRESSES=(
    "api"
    "hackthestudy-backend-api"
    "$API_HOST"
    "10.0.0.3"
    "10.0.0.2"
    "localhost"
)

# Warte bis Redis im API-Container verfügbar ist - versuche verschiedene Adressen
echo "Versuche Verbindung zu Redis aufzubauen..."
for api_addr in "${API_ADDRESSES[@]}"; do
    echo "Teste Redis-Verbindung zu $api_addr:6379..."
    if timeout 2 redis-cli -h "$api_addr" -p 6379 ping &>/dev/null; then
        echo "Redis-Server gefunden auf $api_addr:6379!"
        export REDIS_HOST="$api_addr"
        export REDIS_URL="redis://$api_addr:6379/0"
        break
    else
        echo "Redis nicht verfügbar auf $api_addr:6379"
    fi
done

# Stelle sicher, dass die Supervisor-Konfigurationsdatei existiert
echo "Checking supervisor configuration file..."
if [ ! -f /etc/supervisor/conf.d/supervisord.conf ]; then
    echo "ERROR: Supervisor configuration file not found!"
    echo "Contents of /etc/supervisor/conf.d/:"
    ls -la /etc/supervisor/conf.d/
    exit 1
fi

# Starte Supervisor
echo "Starting supervisor..."
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 