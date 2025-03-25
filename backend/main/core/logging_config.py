import os
import logging
import sys

# Set ein Flag für Logging-Initialisierung
LOGGING_INITIALIZED = False

# Verbessere die setup_logging-Funktion, um Doppel-Logs zu vermeiden
def setup_logging():
    """
    Konfiguriert das Logging-System für die Anwendung.
    Verhindert Doppel-Logs und stellt sicher, dass alle Logger einheitlich konfiguriert sind.
    
    Returns:
        logging.Logger: Der konfigurierte Logger für die Anwendung
    """
    global LOGGING_INITIALIZED
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
    log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
    
    # Log-Level bestimmen
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # Log-Präfix aus Umgebungsvariable holen
    log_prefix = os.environ.get('LOG_PREFIX', '[APP] ')
    
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
    # Setze auf INFO, unabhängig von der Umgebungsvariable
    api_logger.setLevel(logging.INFO)
    api_logger.propagate = False
    
    # Füge mehrere Handler hinzu, um sicherzustellen, dass Logs überall ankommen
    api_handlers = []
    
    # Standard-Stdout-Handler
    api_stdout_handler = logging.StreamHandler(sys.stdout)
    api_stdout_handler.setFormatter(formatter)
    api_handlers.append(api_stdout_handler)
    
    # Versuch, einen Datei-Handler hinzuzufügen, falls wir Schreibrechte haben
    try:
        api_file_handler = logging.FileHandler('/tmp/api_requests.log')
        api_file_handler.setFormatter(formatter)
        api_handlers.append(api_file_handler)
    except (IOError, PermissionError):
        # Kein Fehler werfen, wenn wir keine Schreibrechte haben
        pass
    
    # Alle Handler zum Logger hinzufügen
    for handler in api_handlers:
        api_logger.addHandler(handler)
    
    # Debug-Info über API-Logging ausgeben
    logging.getLogger('HackTheStudy.app').info(
        f"API-REQUEST-LOGGING konfiguriert: Level={api_logger.level}, Handler={len(api_logger.handlers)}"
    )
    
    # Explicit Log-Meldung wenn API-Logging aktiviert wurde
    if log_api_requests:
        logging.getLogger('HackTheStudy.app').info("API-Anfragen-Logging wurde aktiviert - alle API-Anfragen werden protokolliert")
    
    # Flag setzen
    LOGGING_INITIALIZED = True
    return logger

# Logger für API-Anfragen
api_request_logger = logging.getLogger('api_requests') 