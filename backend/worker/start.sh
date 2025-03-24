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

# Prüfe, ob die Redis-URL korrekt gesetzt ist
echo "Redis URL: $REDIS_URL"
echo "Redis Host: $REDIS_HOST"

# Prüfe, ob die Redis-URL eine interne URL ist (erwartet bei DigitalOcean)
if [[ "$REDIS_URL" != *"PRIVATE_URL"* ]] && [[ "$REDIS_URL" != *"redis://"* ]]; then
    # Füge "redis://" hinzu, falls es fehlt
    export REDIS_URL="redis://$REDIS_URL"
    echo "Korrigierte Redis URL: $REDIS_URL"
fi

# Warte bis Redis im API-Container verfügbar ist
echo "Waiting for Redis to become available..."
attempt=0
max_attempts=30

until redis-cli -h $REDIS_HOST -p 6379 ping 2>/dev/null || [ $attempt -eq $max_attempts ]; do
    attempt=$((attempt+1))
    echo "Waiting for Redis (Attempt $attempt/$max_attempts)..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "WARNING: Redis server not responding after $max_attempts attempts. Continuing anyway..."
else
    echo "Redis server is available!"
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