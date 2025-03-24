#!/bin/bash
set -e

echo "Starting Worker container..."

# Entferne stale socket Dateien direkt
echo "Removing stale socket files..."
rm -f /var/run/supervisor-worker.sock
rm -f /var/run/supervisord-worker.pid
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

# Korrigiere Redis-URL falls nötig
if [ -z "$REDIS_URL" ] || [ "$REDIS_URL" == "redis://localhost:6379/0" ]; then
    if [ ! -z "$USE_API_URL" ]; then
        export REDIS_HOST="$USE_API_URL"
        export REDIS_URL="redis://$USE_API_URL:6379/0"
        echo "Überschreibe Redis-URL mit: $REDIS_URL"
    else
        echo "WARNUNG: Lokale Redis-URL wird verwendet und USE_API_URL ist nicht gesetzt!"
    fi
fi

# Prüfe, ob die Redis-URL eine interne URL ist (erwartet bei DigitalOcean)
if [[ "$REDIS_URL" != *"PRIVATE_URL"* ]] && [[ "$REDIS_URL" != *"redis://"* ]]; then
    # Füge "redis://" hinzu, falls es fehlt
    export REDIS_URL="redis://$REDIS_URL"
    echo "Korrigierte Redis URL: $REDIS_URL"
fi

# Warte bis Redis im API-Container verfügbar ist
echo "Waiting for Redis to become available at $REDIS_HOST:6379..."
attempt=0
max_attempts=30

# Erster Timeout: Kürzere Abstände für schnellere Services
until timeout 2 redis-cli -h $REDIS_HOST -p 6379 ping 2>/dev/null || [ $attempt -eq 5 ]; do
    attempt=$((attempt+1))
    echo "Erstes Warten auf Redis (Attempt $attempt/5)..."
    sleep 2
done

# Wenn der erste Versuch fehlschlägt, warte länger zwischen den Versuchen
if [ $attempt -eq 5 ]; then
    echo "Erstes Warten fehlgeschlagen, längere Wartezeit..."
    attempt=0
    until timeout 5 redis-cli -h $REDIS_HOST -p 6379 ping 2>/dev/null || [ $attempt -eq $max_attempts ]; do
        attempt=$((attempt+1))
        echo "Zweites Warten auf Redis (Attempt $attempt/$max_attempts)..."
        sleep 5
    done
fi

if [ $attempt -eq $max_attempts ]; then
    echo "WARNUNG: Redis-Server antwortet nicht nach $max_attempts Versuchen."
    echo "Versuche, dennoch fortzufahren..."
else
    echo "Redis-Server ist verfügbar!"
fi

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