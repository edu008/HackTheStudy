"""
Logging-Konfiguration für die Anwendung.
"""

import os
import sys
import logging
from typing import Optional

# Flag für Logging-Initialisierung
LOGGING_INITIALIZED = False

def setup_logging() -> logging.Logger:
    """
    Konfiguriert das Logging-System für die Anwendung.
    
    Returns:
        Logger-Instanz
    """
    global LOGGING_INITIALIZED
    
    # Vermeidet mehrfache Initialisierung
    if LOGGING_INITIALIZED:
        return logging.getLogger('HackTheStudy.app')
    
    # Deaktiviere Pufferung für stdout und stderr
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(line_buffering=True)
    
    # Umgebungsvariablen für Logging-Konfiguration prüfen
    run_mode = os.environ.get('RUN_MODE', 'app')
    log_level_str = os.environ.get('LOG_LEVEL', 'INFO')
    
    # API-Request-Logging standardmäßig aktivieren
    log_api_requests = os.environ.get('LOG_API_REQUESTS', 'true').lower() == 'true'
    
    # Log-Level bestimmen
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # Log-Präfix aus Umgebungsvariable holen
    log_prefix = os.environ.get('LOG_PREFIX', '[API] ')
    
    # Entferne alle bestehenden Handler
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Angepasstes Logformat mit Präfix
    log_format = f'{log_prefix}[%(levelname)s] %(name)s: %(message)s'
    
    # Konfiguriere das Logging-System mit verbessertem Format
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ],
        force=True
    )
    
    # Logger mit Modul-Namen erstellen
    logger = logging.getLogger('HackTheStudy.app')
    logger.setLevel(log_level)
    
    # Verhindere Weiterleitung der Logs an den Root-Logger
    logger.propagate = False
    
    # Spezifische Logger konfigurieren mit gleicher Formatierung
    special_loggers = [
        'openai', 'api.openai_client', 'celery', 'celery.task',
        'werkzeug', 'flask', 'gunicorn', 'gunicorn.error', 'gunicorn.access',
        'openai_api'  # Logger für OpenAI API Anfragen und Antworten
    ]
    
    # Benutzeranpassbare Filterlogik basierend auf RUN_MODE
    if run_mode == 'worker':
        # Im Worker-Modus nur Worker-relevante Logger aktivieren
        active_loggers = ['celery', 'celery.task', 'api.openai_client']
        if log_api_requests:
            active_loggers.append('api_requests')  # Für API-Anfragen im Worker
        
        for logger_name in special_loggers:
            custom_logger = logging.getLogger(logger_name)
            if logger_name in active_loggers:
                custom_logger.setLevel(log_level)
            else:
                custom_logger.setLevel(logging.WARNING)  # Andere Logger stumm schalten
    else:
        # Im App-Modus normale Konfiguration
        for logger_name in special_loggers:
            custom_logger = logging.getLogger(logger_name)
            custom_logger.setLevel(log_level)
    
    # Gemeinsamer Handler mit einheitlicher Formatierung
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    
    for logger_name in special_loggers:
        custom_logger = logging.getLogger(logger_name)
        
        # Entferne bestehende Handler
        if custom_logger.handlers:
            for h in custom_logger.handlers[:]:
                custom_logger.removeHandler(h)
        
        # Verhindere Weiterleitung an den Root-Logger
        custom_logger.propagate = False
        
        # Füge einheitlichen Handler hinzu
        custom_logger.addHandler(handler)
    
    # API-Request-Logger erstellen
    api_logger = logging.getLogger('api_requests')
    api_logger.setLevel(log_level if log_api_requests else logging.WARNING)
    api_logger.propagate = False
    api_handler = logging.StreamHandler(sys.stdout)
    api_handler.setFormatter(formatter)
    api_logger.addHandler(api_handler)
    
    # Flag setzen
    LOGGING_INITIALIZED = True
    
    logger.info("Logging-System erfolgreich initialisiert")
    return logger

def force_flush_handlers():
    """
    Erzwingt das Leeren aller Log-Handler-Puffer.
    Nützlich vor einem geordneten Shutdown.
    """
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            for handler in logger.handlers:
                if hasattr(handler, 'flush'):
                    try:
                        handler.flush()
                    except:
                        pass
    
    # Auch die Handler des Root-Loggers leeren
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            try:
                handler.flush()
            except:
                pass 