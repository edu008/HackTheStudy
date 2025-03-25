"""
Redis-Client für den Worker-Microservice
"""
import os
import redis
import logging
import socket
from config import REDIS_URL, REDIS_HOST, REDIS_FALLBACK_URLS, USE_API_URL, API_HOST

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Instanz des Redis-Clients
redis_client = None

def initialize_redis_connection():
    """
    Dynamische Suche nach einem funktionierenden Redis-Host mit optimierten Verbindungstests
    """
    global REDIS_URL, REDIS_HOST, redis_client
    logger.info("🔄 Redis-Verbindungsinitialisierung wird gestartet")
    
    # Sammle potenzielle Redis-Hosts
    potential_hosts = []
    
    # Prüfe DigitalOcean-spezifische Umgebungsvariablen
    api_private_url = os.environ.get('api_PRIVATE_URL', '')
    if api_private_url:
        clean_url = api_private_url.replace('https://', '').replace('http://', '')
        if clean_url:
            potential_hosts.append(clean_url)
            logger.info(f"✅ DO-spezifische URL gefunden: {clean_url}")
    
    # Prüfe explizit gesetzte Redis-Host-Variable
    if REDIS_HOST and REDIS_HOST not in potential_hosts:
        potential_hosts.append(REDIS_HOST)
        logger.info(f"✅ REDIS_HOST gefunden: {REDIS_HOST}")
    
    # Prüfe REDIS_FALLBACK_URLS Umgebungsvariable
    if REDIS_FALLBACK_URLS:
        for host in REDIS_FALLBACK_URLS.split(','):
            host = host.strip()
            if host and host not in potential_hosts:
                potential_hosts.append(host)
        logger.info(f"✅ REDIS_FALLBACK_URLS gefunden: {REDIS_FALLBACK_URLS}")
    
    # API_HOST und USE_API_URL prüfen
    if USE_API_URL and USE_API_URL not in potential_hosts:
        potential_hosts.append(USE_API_URL)
    
    if API_HOST and API_HOST not in potential_hosts:
        potential_hosts.append(API_HOST)
    
    # Standard-Hosts hinzufügen
    standard_hosts = ['api', 'hackthestudy-backend-api', 'localhost', '127.0.0.1', '10.0.0.3', '10.0.0.2']
    for host in standard_hosts:
        if host not in potential_hosts:
            potential_hosts.append(host)
    
    logger.info(f"ℹ️ Prüfe {len(potential_hosts)} potenzielle Redis-Hosts: {', '.join(potential_hosts)}")
    
    # Teste jeden Host
    successful_host = None
    failed_hosts = []
    max_failures = 5  # Maximale Anzahl an Fehlern, bevor wir abbrechen
    failures = 0
    
    for host in potential_hosts:
        if failures >= max_failures:
            logger.warning(f"⚠️ Zu viele Redis-Verbindungsfehler, überspringe weitere Tests")
            break
            
        try:
            # Schneller Socket-Test
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            connection_result = s.connect_ex((host, 6379))
            s.close()
            
            if connection_result == 0:
                # Wenn Socket-Verbindung möglich, versuche Redis-Ping
                client = redis.Redis(host=host, port=6379, db=0, socket_timeout=2)
                ping_result = client.ping()
                
                if ping_result:
                    logger.info(f"✅ Erfolgreiche Redis-Verbindung zu {host}:6379")
                    successful_host = host
                    # Aktualisiere globale Variablen
                    REDIS_URL = f"redis://{host}:6379/0"
                    REDIS_HOST = host
                    # Aktualisiere Umgebungsvariablen für andere Prozesse
                    os.environ['REDIS_URL'] = REDIS_URL
                    os.environ['REDIS_HOST'] = REDIS_HOST
                    # Speichere Client-Instanz
                    redis_client = client
                    break
                else:
                    logger.warning(f"⚠️ Socket-Verbindung zu {host}:6379 möglich, aber Redis-Ping fehlgeschlagen")
                    failed_hosts.append(host)
                    failures += 1
            else:
                # Für Logging-Zwecke, nicht jede fehlgeschlagene Verbindung einzeln loggen
                failed_hosts.append(host)
                failures += 1
        except Exception as e:
            failures += 1
            failed_hosts.append(host)
    
    # Ausgabe über fehlgeschlagene Hosts
    if failed_hosts:
        logger.warning(f"⚠️ Verbindung zu folgenden Redis-Hosts fehlgeschlagen: {', '.join(failed_hosts)}")
    
    # Status ausgeben
    if successful_host:
        logger.info(f"✅ Redis-Konfiguration abgeschlossen. Verwende Host: {successful_host}, URL: {REDIS_URL}")
        return True
    else:
        logger.error(f"❌ Keine erfolgreiche Redis-Verbindung hergestellt. Verwende Standard: {REDIS_URL}")
        try:
            # Letzte Chance mit Standard-URL
            redis_client = redis.from_url(REDIS_URL, socket_timeout=5)
            return True
        except Exception as e:
            logger.error(f"❌ Auch Verbindung zur Standard-URL fehlgeschlagen: {str(e)}")
            return False

def get_redis_client():
    """
    Gibt den Redis-Client zurück oder initialisiert ihn, falls noch nicht geschehen.
    
    Returns:
        Eine Redis-Client-Instanz
    """
    global redis_client
    
    if redis_client is None:
        initialize_redis_connection()
        
    return redis_client 