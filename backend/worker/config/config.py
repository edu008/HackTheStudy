"""
Zentrale Konfigurationsdatei für den Worker-Microservice
"""
import os
import logging
import re
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv(override=True, verbose=True)

# Logging-Konfiguration
LOG_LEVEL_STR = os.environ.get('LOG_LEVEL', 'INFO')
LOG_PREFIX = os.environ.get('LOG_PREFIX', '[WORKER] ')
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR.upper(), logging.INFO)
LOG_API_REQUESTS = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'

# Redis-Konfiguration
REDIS_URL_RAW = os.getenv('REDIS_URL', 'redis://localhost:6379/0').strip()
REDIS_HOST_RAW = os.getenv('REDIS_HOST', 'localhost').strip()

# Bereinige Redis-Host - kann durch DigitalOcean falsch gesetzt sein
REDIS_HOST = REDIS_HOST_RAW
if REDIS_HOST.startswith('http://'):
    REDIS_HOST = REDIS_HOST.replace('http://', '')
if REDIS_HOST.startswith('https://'):
    REDIS_HOST = REDIS_HOST.replace('https://', '')
# Entferne Port-Informationen
if ':' in REDIS_HOST:
    REDIS_HOST = REDIS_HOST.split(':')[0]

# Bereinige Redis-URL
REDIS_URL = REDIS_URL_RAW
if 'redis://http://' in REDIS_URL:
    # Extrahiere Hostnamen
    host_match = re.search(r'redis://http://([^:/]+)(:\d+)?', REDIS_URL)
    if host_match:
        hostname = host_match.group(1)
        REDIS_URL = f"redis://{hostname}:6379/0"

# Weitere Prüfung für ungültiges Redis-URL-Format
if ':' in REDIS_URL and not REDIS_URL.startswith('redis://'):
    # Wenn URL wie "hackthestudy-backend-main:8080:6379/0" aussieht
    parts = REDIS_URL.split(':')
    if len(parts) >= 3:  # Format hostname:port1:port2/db
        hostname = parts[0]
        # Nehme immer den port vor dem slash als Redis-Port
        redis_port = parts[-1].split('/')[0] if '/' in parts[-1] else parts[-1]
        # Wenn port2 ist 6379, benutze das
        redis_port = parts[-2] if parts[-2] == '6379' else redis_port
        db = parts[-1].split('/')[1] if '/' in parts[-1] else '0'
        REDIS_URL = f"redis://{hostname}:{redis_port}/{db}"
        
# Schreibe Debug-Logs
print(f"REDIS_URL nach Bereinigung: {REDIS_URL}")

# Bereinige auch die Celery-spezifischen Umgebungsvariablen
CELERY_BROKER_URL_RAW = os.getenv('CELERY_BROKER_URL', REDIS_URL).strip()
CELERY_RESULT_BACKEND_RAW = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL).strip()

# Wende die gleiche Reinigungslogik auf Celery-URLs an
def clean_redis_url(url):
    if 'redis://http://' in url:
        host_match = re.search(r'redis://http://([^:/]+)(:\d+)?', url)
        if host_match:
            hostname = host_match.group(1)
            return f"redis://{hostname}:6379/0"
    
    if ':' in url and not url.startswith('redis://'):
        parts = url.split(':')
        if len(parts) >= 3:
            hostname = parts[0]
            redis_port = parts[-1].split('/')[0] if '/' in parts[-1] else parts[-1]
            redis_port = parts[-2] if parts[-2] == '6379' else redis_port
            db = parts[-1].split('/')[1] if '/' in parts[-1] else '0'
            return f"redis://{hostname}:{redis_port}/{db}"
    
    return url

CELERY_BROKER_URL = clean_redis_url(CELERY_BROKER_URL_RAW)
CELERY_RESULT_BACKEND = clean_redis_url(CELERY_RESULT_BACKEND_RAW)

# Setze die bereinigten Werte in die Umgebungsvariablen zurück
os.environ['REDIS_HOST'] = REDIS_HOST
os.environ['REDIS_URL'] = REDIS_URL
os.environ['CELERY_BROKER_URL'] = CELERY_BROKER_URL
os.environ['CELERY_RESULT_BACKEND'] = CELERY_RESULT_BACKEND

# Schreibe weitere Debug-Logs
print(f"CELERY_BROKER_URL nach Bereinigung: {CELERY_BROKER_URL}")
print(f"CELERY_RESULT_BACKEND nach Bereinigung: {CELERY_RESULT_BACKEND}")

REDIS_TTL_DEFAULT = 14400  # 4 Stunden Standard-TTL für Redis-Einträge
REDIS_TTL_SHORT = 3600    # 1 Stunde für kurzlebige Einträge
REDIS_FALLBACK_URLS = os.getenv('REDIS_FALLBACK_URLS', '').strip()

# API-Konfiguration
USE_API_URL = os.getenv('USE_API_URL', '').strip()
API_HOST = os.getenv('API_HOST', '').strip()

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
    logger.info(f"REDIS_HOST (Original): {REDIS_HOST_RAW}")
    logger.info(f"REDIS_HOST (Bereinigt): {REDIS_HOST}")
    logger.info(f"REDIS_URL (Original): {REDIS_URL_RAW}")
    logger.info(f"REDIS_URL (Bereinigt): {REDIS_URL}")
    logger.info(f"API_HOST: {API_HOST}")
    logger.info(f"REDIS_FALLBACK_URLS: {REDIS_FALLBACK_URLS}")
    
    # Wenn API_HOST nicht gesetzt ist, versuche ${api.PRIVATE_URL} zu lesen
    # (wird von DigitalOcean ersetzt)
    if not API_HOST or API_HOST.startswith("${api."):
        logger.warning("API_HOST nicht oder als Template gesetzt, verwende Fallback-Strategie") 