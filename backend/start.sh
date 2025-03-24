#!/bin/bash
set -e

echo "Starting All-in-One Backend container..."

# Entferne stale socket Dateien direkt
echo "Removing stale socket files..."
rm -f /var/run/supervisor.sock
rm -f /var/run/supervisord.pid
rm -f /tmp/supervisor.*
sleep 1

# Verzeichnisberechtigungen prüfen
echo "Checking directory permissions..."
mkdir -p /var/run/
chmod 755 /var/run/
chmod 755 /etc/supervisor/conf.d/
chmod 755 /var/run/redis

# Stelle sicher, dass die Supervisor-Konfigurationsdatei existiert
echo "Checking supervisor configuration file..."
if [ ! -f /etc/supervisor/conf.d/supervisord.conf ]; then
    echo "ERROR: Supervisor configuration file not found!"
    echo "Contents of /etc/supervisor/conf.d/:"
    ls -la /etc/supervisor/conf.d/
    exit 1
fi

# Redis-Status überprüfen
echo "Checking Redis configuration..."
if [ -f /etc/redis/redis.conf ]; then
    echo "Redis configuration found."
else
    echo "WARNING: Redis configuration not found!"
    ls -la /etc/redis/
fi

# Zeige die Umgebungsvariablen an
echo "Environment variables:"
echo "REDIS_URL: $REDIS_URL"
echo "REDIS_HOST: $REDIS_HOST"
echo "CONTAINER_TYPE: $CONTAINER_TYPE"
echo "RUN_MODE: $RUN_MODE"

# Start mit explizitem Pfad und direkter Ausführung
echo "Starting supervisor..."
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 