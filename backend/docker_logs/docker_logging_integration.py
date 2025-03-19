"""
Docker Logging Integration
-------------------------
Dieses Modul integriert verbessertes Logging für Docker-Container und API-Anfragen.
Es wird automatisch beim Start des Containers geladen.
"""

import os
import sys
import logging
import json
import time
from functools import wraps
from datetime import datetime
from flask import Flask, request, g
import traceback

# Importiere Formatter-Module
try:
    from .docker_data_formatter import (
        format_dict_summary, 
        format_list_summary, 
        summarize_data, 
        print_progress,
        BLUE, GREEN, YELLOW, RED, CYAN, MAGENTA, BOLD, NC
    )
except ImportError:
    # Fallback für fehlende Docker-Data-Formatter
    BLUE = GREEN = YELLOW = RED = CYAN = MAGENTA = BOLD = NC = ''
    def format_dict_summary(data, max_keys=3):
        return f"Dict mit {len(data)} Schlüsseln"
    def format_list_summary(data, max_items=3):
        return f"Liste mit {len(data)} Elementen"
    def summarize_data(data, context=None):
        prefix = f"{context}: " if context else ""
        if isinstance(data, dict):
            return f"{prefix}Dict mit {len(data)} Schlüsseln"
        elif isinstance(data, list):
            return f"{prefix}Liste mit {len(data)} Elementen"
        else:
            return f"{prefix}{str(data)}"
    def print_progress(message, progress, emoji="⏱️"):
        bar_length = 30
        filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        percent = int(progress * 100)
        sys.stdout.write(f"\r{emoji} {message} [{bar}] {percent}%")
        sys.stdout.flush()
        if progress >= 1.0:
            print()

# Emoji-Icons für verschiedene API-Endpunkte
API_EMOJIS = {
    'GET': '🔍',
    'POST': '📝',
    'PUT': '📤',
    'DELETE': '🗑️',
    'PATCH': '🔧',
    '/api/v1/upload': '📤',
    '/api/v1/results': '📊',
    '/api/v1/topics': '📋',
    '/api/v1/generate': '🤖',
    '/api/v1/generate-more-flashcards': '📇',
    '/api/v1/generate-more-questions': '❓',
    '/api/v1/auth': '🔐',
    '/api/v1/user': '👤',
    '/api/v1/session': '🔄',
    '/api/v1/payment': '💳',
    'error': '❌',
    'success': '✅',
    'warning': '⚠️',
    'info': '📢'
}

# Bestimme Emoji basierend auf Endpunkt
def get_endpoint_emoji(path, method='GET'):
    # Exakte Pfade prüfen
    if path in API_EMOJIS:
        return API_EMOJIS[path]
    
    # Methode prüfen
    if method in API_EMOJIS:
        return API_EMOJIS[method]
    
    # Teilpfade prüfen
    for key in API_EMOJIS:
        if key.startswith('/') and path.startswith(key):
            return API_EMOJIS[key]
    
    # Standardemoji für unbekannte Endpunkte
    return '🌐'

class DockerFormatter(logging.Formatter):
    """
    Formatter für farbiges Logging mit Emojis in Docker-Containern
    """
    
    def __init__(self):
        super().__init__()
        self.datefmt = '%H:%M:%S'
    
    def format(self, record):
        timestamp = self.formatTime(record, self.datefmt)
        
        # Bestimme Farbe basierend auf Log-Level
        if record.levelno >= logging.ERROR:
            level_color = RED
            icon = '❌'
        elif record.levelno >= logging.WARNING:
            level_color = YELLOW
            icon = '⚠️'
        elif record.levelno >= logging.INFO:
            level_color = GREEN
            icon = 'ℹ️'
        else:
            level_color = BLUE
            icon = '🔍'
        
        # Überprüfen auf benutzerdefinierte Attribute
        if hasattr(record, 'emoji') and record.emoji:
            icon = record.emoji
        
        # Komponente aus dem Logger-Namen extrahieren
        component = record.name.split('.')[-1].upper()
        
        # Basis-Log-Nachricht
        base_message = f"{BLUE}[{timestamp}]{NC} {icon} {CYAN}[{component}]{NC} {level_color}{record.getMessage()}{NC}"
        
        # Zusätzliche Daten formatieren
        if hasattr(record, 'data') and record.data is not None:
            try:
                # Daten-Zusammenfassung hinzufügen
                data_summary = ""
                data = record.data
                
                if isinstance(data, dict):
                    data_summary = format_dict_summary(data)
                elif isinstance(data, list):
                    data_summary = format_list_summary(data)
                else:
                    data_summary = str(data)
                
                base_message += f"\n    {data_summary}"
            except Exception:
                # Wenn etwas schief geht, füge die Daten im Standard-Format hinzu
                base_message += f"\n    Daten: {str(record.data)}"
        
        # Stacktrace für Fehler hinzufügen
        if record.exc_info:
            base_message += f"\n{YELLOW}{''.join(traceback.format_exception(*record.exc_info))}{NC}"
        
        return base_message

def setup_docker_logging():
    """
    Richtet verbessertes Logging für Docker-Container ein
    """
    # Root-Logger konfigurieren
    root_logger = logging.getLogger()
    
    # Bestehende Handler entfernen
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Standard-Handler für Konsolenausgabe
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(DockerFormatter())
    
    # Log-Level aus Umgebungsvariable lesen oder Standard verwenden
    log_level_name = os.environ.get('LOG_LEVEL', 'INFO')
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Spezifische Logger für verschiedene Komponenten erstellen
    loggers = {
        'api': logging.getLogger('docker.api'),
        'db': logging.getLogger('docker.db'),
        'worker': logging.getLogger('docker.worker'),
        'auth': logging.getLogger('docker.auth'),
        'app': logging.getLogger('docker.app'),
    }
    
    for logger in loggers.values():
        logger.setLevel(log_level)
    
    # Standardlogger als Fallback
    default_logger = logging.getLogger('docker')
    default_logger.setLevel(log_level)
    
    return loggers

def integrate_flask_logging(app, loggers=None):
    """
    Integriert verbessertes Logging in eine Flask-App
    """
    if loggers is None:
        loggers = {'api': logging.getLogger('docker.api')}
    
    api_logger = loggers.get('api', logging.getLogger('docker.api'))
    
    # Request-Start-Zeit speichern
    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.request_id = f"{int(time.time())}-{id(request)}"
    
    # API-Anfragen loggen
    @app.after_request
    def after_request(response):
        # Berechne Dauer
        duration = time.time() - g.start_time
        duration_text = f"{duration:.3f}s"
        
        # Bestimme Status-Farbe
        if response.status_code >= 500:
            status_color = RED
            status_emoji = "❌"
        elif response.status_code >= 400:
            status_color = YELLOW
            status_emoji = "⚠️"
        elif response.status_code >= 300:
            status_color = CYAN
            status_emoji = "↪️"
        else:
            status_color = GREEN
            status_emoji = "✅"
        
        # Endpoint-Emoji ermitteln
        endpoint_emoji = get_endpoint_emoji(request.path, request.method)
        
        # Request-Daten zusammenfassen
        request_data = None
        if request.method in ('POST', 'PUT', 'PATCH') and request.is_json:
            try:
                request_data = request.get_json()
            except:
                request_data = {"error": "Konnte JSON nicht parsen"}
        
        # Response-Daten zusammenfassen (begrenzt auf Header-Info)
        response_data = {
            "status_code": response.status_code,
            "content_type": response.content_type,
            "content_length": response.content_length,
        }
        
        # Log-Nachricht erstellen
        log_message = (
            f"{endpoint_emoji} {request.method} {request.path} → "
            f"{status_emoji} {status_color}{response.status_code}{NC} in {MAGENTA}{duration_text}{NC}"
        )
        
        # Bei JSON-Anfragen zusätzliche Informationen loggen
        if request_data:
            api_logger.info(log_message, extra={
                'data': {
                    'request': request_data,
                    'response': response_data,
                    'duration': duration
                },
                'emoji': endpoint_emoji
            })
        else:
            api_logger.info(log_message, extra={
                'data': response_data,
                'emoji': endpoint_emoji
            })
        
        return response
    
    # Fehlerbehandlung
    @app.errorhandler(Exception)
    def handle_exception(e):
        api_logger.error(f"Fehler bei {request.method} {request.path}: {str(e)}", 
                         exc_info=True,
                         extra={'emoji': '❌'})
        return {"error": str(e)}, 500

def patch_flask_app():
    """
    Patcht die Flask-App-Klasse, um verbessertes Logging zu integrieren
    """
    original_init = Flask.__init__
    
    @wraps(original_init)
    def patched_init(self, *args, **kwargs):
        # Ursprüngliche Initialisierung aufrufen
        original_init(self, *args, **kwargs)
        
        # Loggers einrichten
        loggers = setup_docker_logging()
        
        # Flask-Logging integrieren
        integrate_flask_logging(self, loggers)
        
        # Banner anzeigen
        app_logger = loggers.get('app', logging.getLogger('docker.app'))
        app_logger.info(f"Flask-App '{self.name}' gestartet mit verbessertem Docker-Logging", 
                       extra={'emoji': '🚀'})
    
    Flask.__init__ = patched_init

# Initialisiere das verbesserte Logging bei Import
loggers = setup_docker_logging()
patch_flask_app()

# Einfacher Zugriff auf die Logger
api_logger = loggers['api']
db_logger = loggers['db']
worker_logger = loggers['worker']
auth_logger = loggers['auth']
app_logger = loggers['app']

# Exportiere Hilfsfunktionen für einfaches Logging
def log_request_start(path, method, data=None):
    emoji = get_endpoint_emoji(path, method)
    api_logger.info(f"{emoji} {method} {path} gestartet", extra={'data': data, 'emoji': emoji})

def log_request_end(path, method, status_code, duration, data=None):
    emoji = get_endpoint_emoji(path, method)
    status_emoji = "✅" if status_code < 400 else "❌"
    api_logger.info(f"{emoji} {method} {path} → {status_emoji} {status_code} in {duration:.3f}s", 
                   extra={'data': data, 'emoji': emoji})

def log_db_query(query, params=None, duration=None):
    query_summary = ' '.join(query.split()[:5]) + "..." if len(query.split()) > 5 else query
    duration_text = f" in {duration:.3f}s" if duration is not None else ""
    db_logger.debug(f"SQL: {query_summary}{duration_text}", 
                   extra={'data': {'query': query, 'params': params}, 'emoji': '🗃️'})

def log_auth_event(event_type, user_id=None, details=None):
    auth_logger.info(f"{event_type} für Benutzer {user_id}", 
                    extra={'data': details, 'emoji': '🔐'})

def log_worker_task(task_name, task_id=None, args=None):
    worker_logger.info(f"Task {task_name} gestartet", 
                      extra={'data': {'id': task_id, 'args': args}, 'emoji': '📝'})

def log_worker_result(task_name, task_id=None, result=None, duration=None):
    duration_text = f" in {duration:.3f}s" if duration is not None else ""
    worker_logger.info(f"Task {task_name} abgeschlossen{duration_text}", 
                      extra={'data': {'id': task_id, 'result': result}, 'emoji': '✅'})

def log_app_event(event_name, details=None):
    app_logger.info(event_name, extra={'data': details, 'emoji': 'ℹ️'})

# Wenn das Modul direkt ausgeführt wird, führe eine Demo aus
if __name__ == "__main__":
    # Demo-Funktion, um das verbesserte Logging zu testen
    app_logger.info("Docker-Logging-Integration gestartet", extra={'emoji': '🚀'})
    
    # API-Anfrage simulieren
    api_logger.info("GET /api/v1/results/12345", extra={
        'data': {'params': {'session_id': '12345'}},
        'emoji': '🔍'
    })
    
    # DB-Abfrage simulieren
    db_logger.info("SELECT * FROM users WHERE id = ?", extra={
        'data': {'params': [1], 'rows_affected': 1, 'duration': 0.015},
        'emoji': '🗃️'
    })
    
    # Worker-Task simulieren
    worker_logger.info("process_pdf Task gestartet", extra={
        'data': {'task_id': 'abc123', 'file': 'document.pdf', 'pages': 5},
        'emoji': '📝'
    })
    
    # Fehler simulieren
    api_logger.error("Fehler bei API-Anfrage", extra={
        'data': {'error_code': 500, 'path': '/api/v1/upload', 'reason': 'Datenbank nicht erreichbar'},
        'emoji': '❌'
    })
    
    # Erfolgsmeldung
    app_logger.info("Demo abgeschlossen", extra={'emoji': '✅'}) 