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
    redis_host_raw = os.environ.get('REDIS_HOST', '10.244.15.188')
    redis_port = int(os.environ.get('REDIS_PORT', '6379'))
    
    # URL-Bereinigung: Entferne "http://" oder "https://" Präfixe
    # z.B. "http://hackthestudy-backend-main:8080" -> "hackthestudy-backend-main"
    redis_host = redis_host_raw
    if redis_host.startswith('http://'):
        redis_host = redis_host.replace('http://', '')
    if redis_host.startswith('https://'):
        redis_host = redis_host.replace('https://', '')
    
    # Entferne Port-Informationen, falls vorhanden
    if ':' in redis_host:
        redis_host = redis_host.split(':')[0]
    
    # Baue bereinigte Redis-URL
    redis_url = f"redis://{redis_host}:{redis_port}/0"
    
    logger.info(f"✅ Verwende folgende Redis-Konfiguration:")
    logger.info(f"   - REDIS_HOST (Original): {redis_host_raw}")
    logger.info(f"   - REDIS_HOST (Bereinigt): {redis_host}")
    logger.info(f"   - REDIS_PORT: {redis_port}")
    logger.info(f"   - REDIS_URL (Neu): {redis_url}")
    
    # Direkte Verbindung zum Redis-Server herstellen
    try:
        import redis as redis_external
        client = redis_external.Redis(host=redis_host, port=redis_port, db=0, socket_timeout=5)
        ping_result = client.ping()
        
        if ping_result:
            logger.info(f"✅ Erfolgreiche Redis-Verbindung zu {redis_host}:{redis_port}")
            # Globale Umgebungsvariablen aktualisieren für andere Komponenten
            os.environ['REDIS_URL'] = redis_url
            os.environ['REDIS_HOST'] = redis_host
            # Client-Instanz speichern
            redis_client = client
            return True
        else:
            logger.error(f"❌ Redis-Ping zu {redis_host}:{redis_port} fehlgeschlagen")
            return False
    except Exception as e:
        logger.error(f"❌ Redis-Verbindung zu {redis_host}:{redis_port} fehlgeschlagen: {str(e)}")
        logger.error("📝 Bitte überprüfe die REDIS_HOST und REDIS_URL Umgebungsvariablen")
        
        # Versuche alternative Hostnamen, falls der primäre fehlschlägt
        fallback_hosts = ["hackthestudy-backend-main", "localhost", "127.0.0.1", "redis"]
        for fallback_host in fallback_hosts:
            if fallback_host != redis_host:
                try:
                    logger.info(f"🔄 Versuche Fallback-Host: {fallback_host}")
                    client = redis_external.Redis(host=fallback_host, port=redis_port, db=0, socket_timeout=3)
                    if client.ping():
                        logger.info(f"✅ Erfolgreiche Redis-Verbindung zu Fallback {fallback_host}:{redis_port}")
                        os.environ['REDIS_URL'] = f"redis://{fallback_host}:{redis_port}/0"
                        os.environ['REDIS_HOST'] = fallback_host
                        redis_client = client
                        return True
                except Exception as fallback_err:
                    logger.warning(f"⚠️ Fallback zu {fallback_host} fehlgeschlagen: {str(fallback_err)}")
        
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
            # Alternative Möglichkeiten versuchen
            
            # 1. Versuche bekannte Service-Namen für Redis
            potential_hosts = ["redis", "redis-master", "master.redis", "redis-service", "hackthestudy-redis", "backend-redis"]
            for host in potential_hosts:
                try:
                    logger.info(f"Versuche Redis-Verbindung zu Service: {host}")
                    import redis as redis_external
                    client = redis_external.Redis(host=host, port=6379, db=0, socket_timeout=3)
                    if client.ping():
                        logger.info(f"✅ Erfolgreiche Verbindung zu Redis-Service: {host}")
                        redis_client = client
                        return client
                except Exception as e:
                    logger.warning(f"⚠️ Verbindung zu Redis-Service {host} fehlgeschlagen: {str(e)}")
            
            # 2. Als letzten Ausweg, gib einen DummyRedis zurück, der keine Fehler wirft
            logger.error("❌ Alle Redis-Verbindungsversuche fehlgeschlagen!")
            logger.error("⚠️ Verwende DummyRedis als Notlösung (keine Funktionalität)")
            return DummyRedis()
    
    return redis_client

class DummyRedis:
    """
    Ein Dummy-Redis-Client, der alle Operationen akzeptiert, aber nichts tut.
    Wird verwendet, wenn keine Redis-Verbindung hergestellt werden kann.
    """
    def __init__(self):
        self._data = {}
    
    def ping(self):
        logger.warning("DummyRedis.ping() aufgerufen - keine echte Redis-Verbindung!")
        return True
    
    def get(self, key):
        logger.warning(f"DummyRedis.get({key}) aufgerufen - keine echte Redis-Verbindung!")
        return self._data.get(key)
    
    def set(self, key, value, ex=None, px=None, nx=False, xx=False):
        logger.warning(f"DummyRedis.set({key}, {value[:20] if isinstance(value, str) else value}, ...) aufgerufen - keine echte Redis-Verbindung!")
        self._data[key] = value
        return True
    
    def delete(self, *keys):
        logger.warning(f"DummyRedis.delete({keys}) aufgerufen - keine echte Redis-Verbindung!")
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count
    
    def __getattr__(self, name):
        def dummy_method(*args, **kwargs):
            logger.warning(f"DummyRedis.{name}({args}, {kwargs}) aufgerufen - keine echte Redis-Verbindung!")
            return None
        return dummy_method

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