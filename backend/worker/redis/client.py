"""
Redis-Client für den Worker-Microservice
"""
import os
import logging
from config import REDIS_URL, REDIS_HOST

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Instanz des Redis-Clients
redis_client = None

def initialize_redis_connection():
    """
    Initialisiert die Redis-Verbindung mit dem konfigurierten Host
    """
    global REDIS_URL, REDIS_HOST, redis_client
    logger.info("🔄 Redis-Verbindungsinitialisierung wird gestartet")
    
    # Redis-Host aus Umgebungsvariablen holen, mit Fallback
    redis_host = REDIS_HOST or "hackthestudy-backend-main.hackthestudy-backend.svc.cluster.local"
    redis_port = 6379
    redis_db = 0
    
    logger.info(f"✅ REDIS_HOST gefunden: {redis_host}")
    
    # Redis-URL basierend auf Host konstruieren
    redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
    
    try:
        # Richtige Redis-Klasse importieren - von der externen Bibliothek
        import redis.client as redis_external
        client = redis_external.Redis(host=redis_host, port=redis_port, db=redis_db, socket_timeout=5)
        # Test-Ping, um die Verbindung zu überprüfen
        ping_result = client.ping()
        
        if ping_result:
            logger.info(f"✅ Erfolgreiche Redis-Verbindung zu {redis_host}:{redis_port}")
            # Globale Variablen aktualisieren
            REDIS_URL = redis_url
            REDIS_HOST = redis_host
            # Umgebungsvariablen für andere Prozesse aktualisieren
            os.environ['REDIS_URL'] = REDIS_URL
            os.environ['REDIS_HOST'] = REDIS_HOST
            # Client-Instanz speichern
            redis_client = client
            return True
        else:
            logger.error(f"❌ Redis-Ping zu {redis_host}:{redis_port} fehlgeschlagen")
    except Exception as e:
        logger.error(f"❌ Redis-Verbindung zu {redis_host}:{redis_port} fehlgeschlagen: {str(e)}")
    
    # Fallback: Versuche es mit einer alternativen Methode
    try:
        logger.info(f"⚙️ Versuche Fallback zur Standard-URL: {REDIS_URL}")
        import redis.client as redis_external
        # Direkter Import der Redis-Klasse aus dem externen redis Paket
        fallback_host = redis_host
        redis_client = redis_external.StrictRedis(host=fallback_host, port=redis_port, db=redis_db, socket_timeout=5)
        redis_client.ping()  # Test
        logger.info(f"✅ Fallback-Verbindung zu {fallback_host} erfolgreich")
        return True
    except Exception as e:
        logger.error(f"❌ Auch Fallback-Verbindung fehlgeschlagen: {str(e)}")
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