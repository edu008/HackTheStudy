#!/bin/bash
set -e

echo "Starting Worker container..."

# Suche und entferne alle Supervisor-Prozesse
echo "Killing any existing supervisor processes..."
pkill -f supervisord || true
sleep 1

# Stelle sicher, dass keine alten Socket-Dateien existieren
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

# Überprüfe, ob wir die private URL verwenden (DigitalOcean App Platform)
if [[ "$REDIS_URL" == *"localhost"* ]]; then
    echo "WARNUNG: Redis URL enthält 'localhost'. Möglicherweise werden die Umgebungsvariablen von DigitalOcean nicht korrekt übergeben."
    echo "Erwartete URL sollte '${api.PRIVATE_URL}' enthalten."
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