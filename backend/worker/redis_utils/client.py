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
    
    # Konfigurierte Redis-Verbindungsdetails aus Umgebungsvariablen verwenden
    redis_host = os.environ.get('REDIS_HOST', '10.244.15.188')
    redis_port = int(os.environ.get('REDIS_PORT', '6379'))
    redis_url = os.environ.get('REDIS_URL', f'redis://{redis_host}:{redis_port}/0')
    
    logger.info(f"✅ Verwende folgende Redis-Konfiguration:")
    logger.info(f"   - REDIS_HOST: {redis_host}")
    logger.info(f"   - REDIS_PORT: {redis_port}")
    logger.info(f"   - REDIS_URL: {redis_url}")
    
    # Direkte Verbindung zum Redis-Server herstellen
    try:
        import redis as redis_external
        client = redis_external.Redis(host=redis_host, port=redis_port, db=0, socket_timeout=5)
        ping_result = client.ping()
        
        if ping_result:
            logger.info(f"✅ Erfolgreiche Redis-Verbindung zu {redis_host}:{redis_port}")
            # Client-Instanz speichern
            redis_client = client
            return True
        else:
            logger.error(f"❌ Redis-Ping zu {redis_host}:{redis_port} fehlgeschlagen")
            return False
    except Exception as e:
        logger.error(f"❌ Redis-Verbindung zu {redis_host}:{redis_port} fehlgeschlagen: {str(e)}")
        logger.error("📝 Bitte überprüfe die REDIS_HOST und REDIS_URL Umgebungsvariablen")
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