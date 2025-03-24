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

# Initialisiere Redis-Client
redis_client = redis.Redis.from_url(REDIS_URL) 