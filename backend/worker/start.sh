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

# DigitalOcean App Platform spezifische Variablen prüfen
if [ -n "$DIGITALOCEAN_INTERNAL_API_URL" ]; then
    echo "Gefundene DO-interne API-URL: $DIGITALOCEAN_INTERNAL_API_URL"
    API_HOST=$(echo $DIGITALOCEAN_INTERNAL_API_URL | sed 's|https\?://||' | cut -d':' -f1)
    echo "Extrahierte API-HOST aus DIGITALOCEAN_INTERNAL_API_URL: $API_HOST"
elif [ -n "$API_PRIVATE_URL" ]; then
    echo "Gefundene API_PRIVATE_URL: $API_PRIVATE_URL"
    API_HOST=$(echo $API_PRIVATE_URL | sed 's|https\?://||' | cut -d':' -f1)
    echo "Extrahierte API-HOST aus API_PRIVATE_URL: $API_HOST"
elif [ -n "$api_PRIVATE_URL" ]; then
    echo "Gefundene api_PRIVATE_URL: $api_PRIVATE_URL"
    API_HOST=$(echo $api_PRIVATE_URL | sed 's|https\?://||' | cut -d':' -f1)
    echo "Extrahierte API-HOST aus api_PRIVATE_URL: $API_HOST"
fi

# Hardcoded IP-Adresse des API-Services als Fallback
DEFAULT_API_HOST="10.0.0.3" # Typische IP für DigitalOcean-Container
if [ -z "$API_HOST" ]; then
    API_HOST="$DEFAULT_API_HOST"
    echo "API_HOST nicht gesetzt, verwende Default: $API_HOST"
fi

# Korrigiere Redis-URL falls nötig
if [ -z "$REDIS_URL" ] || [ "$REDIS_URL" == "redis://localhost:6379/0" ]; then
    echo "Verwende API_HOST für Redis-Verbindung: $API_HOST"
    export REDIS_HOST="$API_HOST"
    export REDIS_URL="redis://$API_HOST:6379/0"
    echo "Überschreibe Redis-URL mit: $REDIS_URL"
fi

# Lese REDIS_FALLBACK_URLS aus der Umgebung oder nutze DigitalOcean Netzwerk-Erkennungstechnik
if [ -n "$REDIS_FALLBACK_URLS" ]; then
    IFS=',' read -ra API_ADDRESSES <<< "$REDIS_FALLBACK_URLS"
    echo "Verwende REDIS_FALLBACK_URLS: ${API_ADDRESSES[*]}"
else
    # DNSLookup für bekannte Domainnamen im DigitalOcean-Netzwerk
    API_ADDRESSES=()
    
    # Versuche die API über den Kubernetes-Service zu finden (Digital Ocean intern)
    SERVICE_HOSTS=("api" "hackthestudy-backend-api" "$API_HOST")
    for host in "${SERVICE_HOSTS[@]}"; do
        if host "$host" >/dev/null 2>&1; then
            echo "DNS-Lookup für $host erfolgreich"
            resolved_ip=$(host "$host" | grep "has address" | head -1 | awk '{print $4}')
            if [ -n "$resolved_ip" ]; then
                echo "Aufgelöste IP für $host: $resolved_ip"
                API_ADDRESSES+=("$host" "$resolved_ip")
            else
                API_ADDRESSES+=("$host")
            fi
        else
            API_ADDRESSES+=("$host")
        fi
    done
    
    # Füge Standard-IPs hinzu
    API_ADDRESSES+=("10.0.0.3" "10.0.0.2" "localhost" "127.0.0.1")
    
    echo "Generierte API-Adressen-Liste: ${API_ADDRESSES[*]}"
fi

# Suche Netzwerkschnittstellen für weitere potenzielle IPs
echo "Netzwerkschnittstellen-Informationen:"
# Verwende einen Befehl, der immer existiert, statt 'ip'
ifconfig 2>/dev/null || netstat -i 2>/dev/null || echo "Netzwerk-Tools nicht verfügbar"

# Starte einen einfachen TCP-Listener für Health-Checks im Hintergrund
echo "Starting simple TCP health check server on port 8080..."
(
  while true; do
    # Starte netcat-Listener, der jede Verbindung sofort mit Erfolg beantwortet und schließt
    nc -l -p 8080 -k >/dev/null 2>&1 || echo "Netcat-Fehler, versuche erneut..."
    sleep 1
  done
) &

# Erhöhe die Timeout-Zeit für zuverlässigere Verbindungen
# Warte bis Redis im API-Container verfügbar ist - versuche verschiedene Adressen
echo "Versuche Verbindung zu Redis aufzubauen..."
redis_found=false
for api_addr in "${API_ADDRESSES[@]}"; do
    echo "Teste Redis-Verbindung zu $api_addr:6379..."
    if timeout 5 redis-cli -h "$api_addr" -p 6379 ping &>/dev/null; then
        echo "Redis-Server gefunden auf $api_addr:6379!"
        export REDIS_HOST="$api_addr"
        export REDIS_URL="redis://$api_addr:6379/0"
        
        # Setze auch die Umgebungsvariablen für die Supervisor-Prozesse
        echo "export REDIS_HOST=$api_addr" >> /etc/environment
        echo "export REDIS_URL=redis://$api_addr:6379/0" >> /etc/environment
        
        redis_found=true
        break
    else
        echo "Redis nicht verfügbar auf $api_addr:6379"
    fi
done

# Wenn keine Redis-Verbindung gefunden wurde, starten wir trotzdem - vielleicht funktioniert es später
if [ "$redis_found" = false ]; then
    echo "WARNUNG: Keine Redis-Verbindung konnte hergestellt werden. Der Worker startet trotzdem, wird aber möglicherweise nicht funktionieren."
    echo "Versuche es mit: REDIS_URL=$REDIS_URL, REDIS_HOST=$REDIS_HOST"
fi

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