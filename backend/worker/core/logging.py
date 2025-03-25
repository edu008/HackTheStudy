"""
Zentrale Logging-Konfiguration für den Worker-Microservice
"""
import os
import sys
import logging
from config import LOG_LEVEL, LOG_PREFIX, LOG_API_REQUESTS

def setup_logging():
    """
    Richtet das Logging für den Worker ein.
    Konfiguriert verschiedene Logger für unterschiedliche Komponenten.
    """
    # VERBESSERTE LOGGING-KONFIGURATION FÜR DIGITAL OCEAN
    # Umfassende Logging-Konfiguration
    logging.basicConfig(
        level=LOG_LEVEL,
        # Optimiertes Format für DigitalOcean App Platform Logs - konsistent mit Flask
        format=f'{LOG_PREFIX}[%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)  # Explizit stdout verwenden für DigitalOcean
        ],
        force=True  # Überschreibe alle bestehenden Konfigurationen
    )

    # Worker-Logging aktivieren (Celery-Kernkomponenten)
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(LOG_LEVEL)
    celery_logger.info("🚀 Celery-Worker-Logger aktiviert - Sollte in DigitalOcean Runtime-Logs sichtbar sein")

    # Worker-Task-Logging aktivieren
    task_logger = logging.getLogger('celery.task')
    task_logger.setLevel(LOG_LEVEL)
    task_logger.info("📋 Celery-Task-Logger aktiviert")

    # Hauptlogger für den Worker
    logger = logging.getLogger('worker')
    logger.setLevel(LOG_LEVEL)
    logger.info("📝 Worker-Hauptlogger aktiviert")

    # API-Request-Logger
    api_request_logger = logging.getLogger('api_requests')
    api_request_logger.setLevel(LOG_LEVEL if LOG_API_REQUESTS else logging.WARNING)
    if LOG_API_REQUESTS:
        api_request_logger.info("🌐 API-Request-Logger aktiviert")
    
    # Spezielle Logger für OpenAI API-Anfragen und -Antworten
    openai_logger = logging.getLogger('openai_api')
    openai_logger.setLevel(logging.DEBUG)
    openai_logger.addHandler(logging.StreamHandler(sys.stdout))
    
    # Konfiguriere auch den api.openai_client-Logger im Worker-Prozess
    api_openai_logger = logging.getLogger('api.openai_client')
    api_openai_logger.setLevel(logging.DEBUG)
    api_openai_logger.addHandler(logging.StreamHandler(sys.stdout))
    
    # Aktiviere auch den Haupt-OpenAI-Logger
    openai_lib_logger = logging.getLogger('openai')
    openai_lib_logger.setLevel(logging.DEBUG)
    openai_lib_logger.addHandler(logging.StreamHandler(sys.stdout))
    
    # Explizites OpenAI-Debugging aktivieren
    os.environ['OPENAI_LOG'] = 'debug'
    
    return logger

def log_environment_variables():
    """
    Protokolliert wichtige Umgebungsvariablen beim Start des Workers.
    """
    logger = logging.getLogger('worker')
    
    important_vars = [
        "REDIS_URL", "REDIS_HOST", "REDIS_FALLBACK_URLS",
        "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND",
        "API_HOST", "API_URL", 
        "DO_APP_PLATFORM", "DIGITAL_OCEAN_DEPLOYMENT",
        "CONTAINER_TYPE", "RUN_MODE", "HEALTH_PORT"
    ]
    
    logger.info("=== Worker-Service Umgebungsvariablen ===")
    for var in important_vars:
        value = os.environ.get(var, "NICHT GESETZT")
        # Wenn es ein Passwort enthält, dann zensieren
        if var.lower().find("password") >= 0 or var.lower().find("secret") >= 0:
            value = "******" if value != "NICHT GESETZT" else "NICHT GESETZT"
        logger.info(f"{var}: {value}")
    
    # Redis-spezifische Konfiguration anzeigen
    logger.info("=== Celery & Redis-Konfiguration ===")
    broker_url = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "NICHT GESETZT"))
    result_backend = os.environ.get("CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "NICHT GESETZT"))
    logger.info(f"Effektive Broker-URL: {broker_url}")
    logger.info(f"Effektives Result-Backend: {result_backend}")
    
    # IP und DNS-Auflösung testen
    logger.info("=== Netzwerk-Diagnose ===")
    try:
        import socket
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        api_host = os.environ.get("API_HOST", "localhost")
        
        try:
            redis_ip = socket.gethostbyname(redis_host)
            logger.info(f"DNS-Auflösung für REDIS_HOST ({redis_host}): {redis_ip}")
        except socket.gaierror:
            logger.error(f"DNS-Auflösung für REDIS_HOST ({redis_host}) fehlgeschlagen")
        
        try:
            api_ip = socket.gethostbyname(api_host)
            logger.info(f"DNS-Auflösung für API_HOST ({api_host}): {api_ip}")
        except socket.gaierror:
            logger.error(f"DNS-Auflösung für API_HOST ({api_host}) fehlgeschlagen")
    except Exception as e:
        logger.error(f"Fehler bei Netzwerkdiagnose: {str(e)}")
    
    logger.info("========================") 