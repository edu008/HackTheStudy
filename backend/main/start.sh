#!/bin/bash
set -e

echo "Starting API container..."

# Entferne stale socket Dateien direkt
echo "Removing stale socket files..."
rm -f /tmp/supervisor-api.sock
rm -f /tmp/supervisord-api.pid
rm -f /tmp/supervisor.*
sleep 1

# Verzeichnisberechtigungen prüfen
echo "Checking directory permissions..."
mkdir -p /var/run/
chmod 755 /var/run/
chmod 755 /etc/supervisor/conf.d/

# Prüfe und erstelle Redis-Verzeichnisse falls nötig
echo "Setting up Redis directories..."
if [ ! -d "/var/run/redis" ]; then
    mkdir -p /var/run/redis
    echo "Created /var/run/redis directory"
fi
if [ ! -d "/var/lib/redis" ]; then
    mkdir -p /var/lib/redis
    echo "Created /var/lib/redis directory"
fi
if [ ! -d "/var/log/redis" ]; then
    mkdir -p /var/log/redis
    echo "Created /var/log/redis directory"
fi

chmod 755 /var/run/redis
chown -R root:root /var/run/redis /var/lib/redis /var/log/redis || true

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

# Start mit explizitem Pfad und direkter Ausführung
echo "Starting supervisor..."
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 