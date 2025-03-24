#!/bin/bash
set -e

echo "Starting Worker container..."

# Entferne stale socket Dateien direkt
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
echo "DEBUG_INFO: $DEBUG_INFO"
echo "USE_API_URL: $USE_API_URL"
echo "CONTAINER_TYPE: $CONTAINER_TYPE"
echo "RUN_MODE: $RUN_MODE"
echo "============================"

# Hardcoded IP-Adresse des API-Services als Fallback
API_HOST="10.0.0.3" # Diese IP-Adresse sollte dem DigitalOcean API-Container entsprechen
echo "Hardcoded API-Host: $API_HOST"

# Korrigiere Redis-URL falls nötig
if [ -z "$REDIS_URL" ] || [ "$REDIS_URL" == "redis://localhost:6379/0" ]; then
    if [ ! -z "$USE_API_URL" ]; then
        export REDIS_HOST="$USE_API_URL"
        export REDIS_URL="redis://$USE_API_URL:6379/0"
        echo "Überschreibe Redis-URL mit: $REDIS_URL"
    else
        echo "WARNUNG: Lokale Redis-URL wird verwendet. Versuche API_HOST=$API_HOST"
        export REDIS_HOST="$API_HOST"
        export REDIS_URL="redis://$API_HOST:6379/0"
        echo "Überschreibe Redis-URL mit Fallback: $REDIS_URL"
    fi
fi

# Prüfe, ob die Redis-URL eine interne URL ist (erwartet bei DigitalOcean)
if [[ "$REDIS_URL" != *"PRIVATE_URL"* ]] && [[ "$REDIS_URL" != *"redis://"* ]]; then
    # Füge "redis://" hinzu, falls es fehlt
    export REDIS_URL="redis://$REDIS_URL"
    echo "Korrigierte Redis URL: $REDIS_URL"
fi

# Füge eine Liste von möglichen API-Adressen hinzu, die wir nacheinander versuchen können
API_ADDRESSES=(
    "localhost"
    "$API_HOST" 
    "api"
    "hackthestudy-backend-api"
    "10.0.0.2"
    "10.0.0.3"
    "10.0.0.4"
)

# Warte bis Redis im API-Container verfügbar ist - versuche verschiedene Adressen
for api_addr in "${API_ADDRESSES[@]}"; do
    echo "Versuche Redis-Verbindung zu $api_addr:6379..."
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

# Start mit explizitem Pfad und direkter Ausführung
echo "Starting supervisor..."
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 