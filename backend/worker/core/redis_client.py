import os
import redis
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Lade Umgebungsvariablen
load_dotenv(override=True, verbose=True)

# Bereinige Redis-URL
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0').strip()
logger.info(f"Redis-Client verwendet URL: {REDIS_URL}")

# Initialisiere Redis-Client mit verbesserten Verbindungsparametern
redis_client = redis.Redis.from_url(
    REDIS_URL,
    socket_timeout=30.0,           # Timeout für Socket-Operationen
    socket_connect_timeout=30.0,   # Timeout für Verbindungsaufbau
    socket_keepalive=True,         # Keep-Alive aktivieren
    health_check_interval=15,      # Regelmäßige Verbindungsprüfung
    retry_on_timeout=True,         # Bei Timeout erneut versuchen
    decode_responses=False,        # Keine automatische Dekodierung
    max_connections=10             # Maximale Verbindungen im Pool
) 