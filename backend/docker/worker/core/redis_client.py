import os
import redis
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv(override=True, verbose=True)

# Bereinige Redis-URL
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0').strip()

# Initialisiere Redis-Client
redis_client = redis.Redis.from_url(REDIS_URL) 