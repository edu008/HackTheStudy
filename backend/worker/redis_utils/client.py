"""
Redis-Client für den Worker-Microservice
"""
import os
import logging
import socket
import time
from typing import Optional
from config import REDIS_URL, REDIS_HOST, REDIS_FALLBACK_URLS

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Instanz des Redis-Clients
redis_client = None

def initialize_redis_connection() -> bool:
    """
    Initialisiert die Redis-Verbindung mit dem konfigurierten Host.
    
    Implementiert einen robusten Fallback-Mechanismus für DigitalOcean App Platform.
    
    Returns:
        bool: True wenn die Verbindung erfolgreich hergestellt wurde, sonst False
    """
    global redis_client
    
    logger.info("🔄 Redis-Verbindungsinitialisierung wird gestartet")
    
    # Mögliche Redis-Hosts sammeln (in Prioritätsreihenfolge)
    potential_hosts = []
    
    # 1. Haupthost aus Umgebungsvariablen
    if REDIS_HOST:
        potential_hosts.append(REDIS_HOST)
        logger.info(f"✅ REDIS_HOST aus Umgebungsvariable gefunden: {REDIS_HOST}")
    
    # 2. Hosts aus DigitalOcean PRIVATE_URL (wenn verfügbar)
    api_host = os.environ.get('API_HOST', '')
    if api_host:
        potential_hosts.append(api_host)
        logger.info(f"✅ API_HOST aus Umgebungsvariable gefunden: {api_host}")
    
    # 3. Standard-Kubernetes-Service-Namen
    potential_hosts.extend(['api', 'backend-api', 'hackthestudy-backend-api'])
    
    # 4. Lokale Hosts
    potential_hosts.extend(['localhost', '127.0.0.1'])
    
    # 5. Zusätzliche Fallback-URLs (wenn konfiguriert)
    if REDIS_FALLBACK_URLS:
        fallback_hosts = REDIS_FALLBACK_URLS.split(',')
        potential_hosts.extend([h.strip() for h in fallback_hosts])
        logger.info(f"✅ REDIS_FALLBACK_URLS gefunden: {REDIS_FALLBACK_URLS}")
    
    # Deduplizieren und leere Werte entfernen
    potential_hosts = [host for host in dict.fromkeys(potential_hosts) if host]
    
    logger.info(f"🔍 Mögliche Redis-Hosts (in Prioritätsreihenfolge): {', '.join(potential_hosts)}")
    
    # Versuche, jeden möglichen Host zu erreichen
    for host in potential_hosts:
        # Versuche DNS-Auflösung (für Kubernetes-Servicenamen)
        try:
            ip_address = socket.gethostbyname(host)
            logger.info(f"✅ DNS-Auflösung für {host} erfolgreich: {ip_address}")
        except socket.gaierror:
            logger.warning(f"⚠️ DNS-Auflösung für {host} fehlgeschlagen, versuche trotzdem zu verbinden")
            ip_address = host
        
        # Versuche Redis-Verbindung
        redis_url = f"redis://{host}:6379/0"
        logger.info(f"🔄 Versuche Redis-Verbindung zu {redis_url}")
        try:
            import redis as redis_external
            client = redis_external.Redis(host=host, port=6379, db=0, socket_timeout=5)
            ping_result = client.ping()
            
            if ping_result:
                logger.info(f"✅ Erfolgreiche Redis-Verbindung zu {host}:6379")
                # Globale Umgebungsvariablen aktualisieren
                os.environ['REDIS_URL'] = redis_url
                os.environ['REDIS_HOST'] = host
                # Client-Instanz speichern
                redis_client = client
                return True
            else:
                logger.warning(f"⚠️ Redis-Ping zu {host}:6379 fehlgeschlagen")
        except Exception as e:
            logger.warning(f"⚠️ Redis-Verbindung zu {host}:6379 fehlgeschlagen: {str(e)}")
    
    # Wenn alle Verbindungsversuche fehlgeschlagen sind, gib einen Fehler aus
    logger.error("❌ Alle Redis-Verbindungsversuche fehlgeschlagen!")
    logger.error("📝 Bitte überprüfe die REDIS_HOST und REDIS_URL Umgebungsvariablen")
    logger.error("📝 In DigitalOcean: Stelle sicher, dass der Worker-Service Zugriff auf den API-Service hat")
    
    # Letzter Versuch mit einem lokalen Dummy-Redis für Entwicklungszwecke
    try:
        from fakeredis import FakeRedis
        logger.warning("⚠️ Verwende FakeRedis als Fallback (nur für Entwicklung geeignet!)")
        redis_client = FakeRedis()
        return True
    except ImportError:
        logger.error("❌ Auch FakeRedis ist nicht verfügbar. Redis-Verbindung nicht möglich!")
        return False

def get_redis_client():
    """
    Gibt den Redis-Client zurück oder initialisiert ihn, falls noch nicht geschehen.
    
    Returns:
        Eine Redis-Client-Instanz
    """
    global redis_client
    
    if redis_client is None:
        logger.info("Redis-Client wird initialisiert...")
        retry_count = 0
        max_retries = 3
        
        while redis_client is None and retry_count < max_retries:
            if retry_count > 0:
                logger.info(f"Wiederholungsversuch {retry_count}/{max_retries} nach 3 Sekunden...")
                time.sleep(3)
            
            initialize_redis_connection()
            retry_count += 1
        
        if redis_client is None:
            logger.error("❌ Redis-Client konnte nicht initialisiert werden!")
            # Rückgabe eines Dummy-Clients, der alle Operationen protokolliert aber ignoriert
            from fakeredis import FakeStrictRedis
            return FakeStrictRedis()
    
    return redis_client

def is_redis_connected() -> bool:
    """
    Prüft, ob die Redis-Verbindung aktiv ist.
    
    Returns:
        bool: True wenn verbunden, False sonst
    """
    client = get_redis_client()
    try:
        return client.ping()
    except:
        return False

def get_redis_connection_info() -> dict:
    """
    Gibt Informationen zur aktuellen Redis-Verbindung zurück.
    
    Returns:
        dict: Verbindungsinformationen
    """
    client = get_redis_client()
    connected = False
    info = {}
    
    try:
        connected = client.ping()
        if connected:
            info = client.info()
    except:
        pass
    
    return {
        "connected": connected,
        "host": os.environ.get('REDIS_HOST', 'unknown'),
        "url": os.environ.get('REDIS_URL', 'unknown'),
        "info": info
    } 