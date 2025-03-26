import os
from redis import Redis
from fakeredis import FakeRedis
import logging

logger = logging.getLogger(__name__)

def get_redis_client():
    """Erstellt und konfiguriert einen Redis-Client."""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Redis-URL korrigieren
    if redis_url.startswith('redis://http://'):
        redis_url = redis_url.replace('redis://http://', 'redis://')
    if redis_url.startswith('redis://https://'):
        redis_url = redis_url.replace('redis://https://', 'redis://')
    
    # Redis-Host extrahieren
    redis_host = redis_url.split('://')[1].split(':')[0]
    
    logger.info(f"Redis-URL: {redis_url}")
    logger.info(f"Redis-Host: {redis_host}")
    
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        client.ping()  # Teste die Verbindung
        logger.info(f"Redis-Verbindung erfolgreich hergestellt: {redis_url}")
        return client
    except Exception as e:
        logger.error(f"Redis-Verbindungsfehler: {str(e)}")
        logger.error(f"Redis-URL: {redis_url}")
        logger.warning("Verwende FakeRedis als Fallback")
        return FakeRedis(decode_responses=True) 