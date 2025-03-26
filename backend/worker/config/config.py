"""
Zentrale Konfigurationsdatei für den Worker-Microservice
"""
import os
import logging
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv(override=True, verbose=True)

# Logging-Konfiguration
LOG_LEVEL_STR = os.environ.get('LOG_LEVEL', 'INFO')
LOG_PREFIX = os.environ.get('LOG_PREFIX', '[WORKER] ')
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR.upper(), logging.INFO)
LOG_API_REQUESTS = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'

# Redis-Konfiguration
REDIS_URL = os.getenv('REDIS_URL', 'redis://10.244.15.188:6379/0').strip()
REDIS_HOST = os.getenv('REDIS_HOST', '10.244.15.188').strip()
REDIS_TTL_DEFAULT = 14400  # 4 Stunden Standard-TTL für Redis-Einträge
REDIS_TTL_SHORT = 3600    # 1 Stunde für kurzlebige Einträge
REDIS_FALLBACK_URLS = os.getenv('REDIS_FALLBACK_URLS', '').strip()

# Sicherstellen, dass REDIS_URL konsistent ist
if 'localhost' in REDIS_URL and REDIS_HOST != 'localhost':
    REDIS_URL = f"redis://{REDIS_HOST}:6379/0"
    os.environ['REDIS_URL'] = REDIS_URL

# API-Konfiguration
USE_API_URL = os.getenv('USE_API_URL', '').strip()
API_HOST = os.getenv('API_HOST', '').strip()

# Celery-Konfiguration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)

# Health-Check-Konfiguration
HEALTH_PORT = int(os.environ.get('HEALTH_PORT', 8080))

# Deployment-Informationen
DO_APP_PLATFORM = os.getenv('DO_APP_PLATFORM', 'false').lower() == 'true'
DIGITAL_OCEAN_DEPLOYMENT = os.getenv('DIGITAL_OCEAN_DEPLOYMENT', 'false').lower() == 'true'
CONTAINER_TYPE = os.getenv('CONTAINER_TYPE', 'worker')
RUN_MODE = os.getenv('RUN_MODE', 'production')

# OpenAI-Konfiguration
OPENAI_LOG = os.environ.get('OPENAI_LOG', 'debug')
os.environ['OPENAI_LOG'] = OPENAI_LOG

# Wenn wir in einer DigitalOcean-Umgebung sind, logge wichtige Umgebungsvariablen
if DO_APP_PLATFORM or DIGITAL_OCEAN_DEPLOYMENT:
    import sys
    logger = logging.getLogger("worker")
    logger.info("=== DigitalOcean App Platform erkannt ===")
    logger.info(f"REDIS_HOST: {REDIS_HOST}")
    logger.info(f"API_HOST: {API_HOST}")
    logger.info(f"REDIS_FALLBACK_URLS: {REDIS_FALLBACK_URLS}")
    
    # Wenn API_HOST nicht gesetzt ist, versuche ${api.PRIVATE_URL} zu lesen
    # (wird von DigitalOcean ersetzt)
    if not API_HOST or API_HOST.startswith("${api."):
        logger.warning("API_HOST nicht oder als Template gesetzt, verwende Fallback-Strategie")
        # Versuche, die API-Adresse anders zu ermitteln 