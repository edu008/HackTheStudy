# Gevent-Monkey-Patch vor anderen Imports ausführen
# Dies verhindert SSL-Rekursionsfehler
import gevent.monkey
gevent.monkey.patch_all()

import os
import logging
import sys
import socket
import re
import time

# Setze die ENVIRONMENT-Variable direkt am Anfang, bevor etwas anderes geladen wird
os.environ['ENVIRONMENT'] = os.environ.get('ENVIRONMENT', 'production')
is_development = os.environ['ENVIRONMENT'].lower() == 'development'

from dotenv import load_dotenv
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from core.models import db
from prometheus_flask_exporter import PrometheusMetrics
from api.error_handler import setup_error_handlers
from werkzeug.middleware.proxy_fix import ProxyFix
from config.env_handler import load_env, setup_cors_origins
from datetime import datetime
import traceback
import json
from werkzeug.exceptions import HTTPException
# Importiere das neue Logging-Modul
from core.logging_config import setup_logging, api_request_logger

# Direkt am Anfang - Umfassendes Monkey-Patching für billiard
try:
    import billiard
    import billiard.connection
    from billiard.connection import Connection
    
    # Sichere die Original-Funktionen
    original_module_poll = billiard.connection._poll
    if hasattr(Connection, '_poll'):
        original_class_poll = Connection._poll
    
    # Patch für die billiard.connection._poll Funktion auf Modulebene
    def patched_module_poll(object_list, timeout):
        try:
            return original_module_poll(object_list, timeout)
        except ValueError as e:
            if "invalid file descriptor" in str(e):
                import logging
                logging.getLogger('billiard_patch').warning(
                    f"Caught invalid file descriptor error in module-level _poll, returning empty list."
                )
                return []
            raise
    
    # Patch für die Connection._poll Methode
    def patched_class_poll(self, timeout):
        try:
            if hasattr(Connection, '_original_poll'):
                return Connection._original_poll(self, timeout)
            elif hasattr(self, '_original_poll'):
                return self._original_poll(timeout)
            else:
                try:
                    result = []
                    if hasattr(self, 'fileno'):
                        fd = self.fileno()
                        if fd < 0:
                            import logging
                            logging.getLogger('billiard_patch').warning(
                                f"Negative file descriptor detected: {fd}, returning empty list."
                            )
                            return []
                    return original_module_poll([self], timeout)
                except Exception as inner_e:
                    import logging
                    logging.getLogger('billiard_patch').warning(
                        f"Error in fallback poll method: {inner_e}, returning empty list."
                    )
                    return []
        except ValueError as e:
            if "invalid file descriptor" in str(e):
                import logging
                logging.getLogger('billiard_patch').warning(
                    f"Caught invalid file descriptor error in class-level _poll, returning empty list. FD: {getattr(self, 'fileno', lambda: 'unknown')()}"
                )
                return []
            raise
    
    # Patch auf Modulebene
    billiard.connection._poll = patched_module_poll
    
    # Patch auf Klassenebene
    if hasattr(Connection, '_poll'):
        Connection._original_poll = Connection._poll
        Connection._poll = patched_class_poll
    
    # Direkter Monkey-Patch für wait Funktion
    original_wait = billiard.connection.wait
    def patched_wait(object_list, timeout=None):
        try:
            return original_wait(object_list, timeout)
        except ValueError as e:
            if "invalid file descriptor" in str(e):
                import logging
                logging.getLogger('billiard_patch').warning(
                    f"Caught invalid file descriptor error in wait, returning empty list."
                )
                return []
            raise
    
    billiard.connection.wait = patched_wait
    
    print("Billiard _poll and wait functions patched successfully at module level")
except Exception as e:
    print(f"Could not patch billiard module: {e}")

# Setze auch Socket-Timeout auf einen höheren Wert
import socket
socket.setdefaulttimeout(300)  # 5 Minuten Timeout

# Gevent patch für multithreading
try:
    from gevent import monkey
    if not monkey.is_module_patched('threading'):
        monkey.patch_all(thread=True, socket=True)
        print("Gevent monkey patching applied for thread and socket")
except ImportError:
    print("Gevent not available for monkey patching")

# Setze Umgebungsvariable für Celery Pool-Typ
os.environ['CELERY_POOL'] = 'solo'

# Set ein Flag für Logging-Initialisierung
LOGGING_INITIALIZED = False

# Verbessere die setup_logging-Funktion, um Doppel-Logs zu vermeiden
def setup_logging():
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
    api_logger.setLevel(log_level if log_api_requests else logging.WARNING)
    api_logger.propagate = False
    api_handler = logging.StreamHandler(sys.stdout)
    api_handler.setFormatter(formatter)
    api_logger.addHandler(api_handler)
    
    # Flag setzen
    LOGGING_INITIALIZED = True
    return logger

# Neue Funktion, die Umgebungsvariablen ausgibt
def log_environment_variables():
    """Gibt alle relevanten Umgebungsvariablen aus, um die Konfiguration zu überprüfen"""
    run_mode = os.environ.get('RUN_MODE', 'app')
    container_type = os.environ.get('CONTAINER_TYPE', 'unknown')
    
    log_step("Umgebungsvariablen", "START", f"Prüfe Konfiguration für {container_type.upper()}")
    
    # Prüfen, ob wir in einer Entwicklungsumgebung sind
    is_dev = os.environ.get('FLASK_ENV') == 'development' or os.environ.get('FLASK_DEBUG') == '1'
    
    # .env-Datei nur in Entwicklungsumgebungen laden
    if is_dev:
        try:
            from dotenv import load_dotenv
            dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
            if os.path.exists(dotenv_path):
                log_step("Umgebungsvariablen", "INFO", f".env-Datei gefunden: {dotenv_path}")
                load_dotenv(dotenv_path)
            else:
                log_step("Umgebungsvariablen", "INFO", "Keine .env-Datei gefunden in Entwicklungsumgebung")
        except ImportError:
            log_step("Umgebungsvariablen", "WARNING", "python-dotenv nicht installiert")
    else:
        # In Produktion verwenden wir direkt die DigitalOcean-Umgebungsvariablen
        log_step("Umgebungsvariablen", "INFO", "Produktionsumgebung erkannt, verwende System-Umgebungsvariablen")
    
    # Wichtige Variablen, die angezeigt werden sollen
    important_vars = [
        'RUN_MODE', 'CONTAINER_TYPE', 'PORT', 'FLASK_DEBUG', 
        'REDIS_URL', 'REDIS_HOST', 'API_HOST',
        'DATABASE_URL', 'CELERY_BROKER_URL', 'LOG_LEVEL',
        'API_URL', 'CORS_ORIGINS', 'FLASK_APP',
        'DO_APP_PLATFORM', 'DIGITAL_OCEAN_DEPLOYMENT'
    ]
    
    # Sammle alle verfügbaren kritischen Variablen
    critical_vars = {}
    for var in important_vars:
        if var in os.environ:
            # Verberge vertrauliche Informationen
            value = os.environ.get(var)
            if var in ['DATABASE_URL'] and value:
                # Maskiere Passwörter in URLs
                value = re.sub(r'(://[^:]+:)([^@]+)(@)', r'\1*****\3', value)
            critical_vars[var] = value
    
    # Logge kritische Variablen in Gruppen
    log_step("Netzwerkkonfiguration", "INFO", 
             f"PORT={critical_vars.get('PORT', 'nicht gesetzt')}")
    
    # Redis-Konfiguration zusammenfassen
    redis_info = (f"REDIS_HOST={critical_vars.get('REDIS_HOST', 'nicht gesetzt')}, "
                 f"REDIS_URL={critical_vars.get('REDIS_URL', 'nicht gesetzt')}")
    log_step("Redis-Konfiguration", "INFO", redis_info)
    
    # Datenbank-Konfiguration überprüfen
    if 'DATABASE_URL' in critical_vars:
        log_step("Datenbank-Konfiguration", "INFO", "DATABASE_URL gefunden (maskiert)")
    else:
        log_step("Datenbank-Konfiguration", "WARNING", "DATABASE_URL nicht gefunden", "warning")
    
    # Alle möglichen Redis-Hosts zum Verbinden erstellen
    redis_hosts = []
    # Explizite Hosts
    if 'REDIS_HOST' in os.environ and os.environ.get('REDIS_HOST'):
        redis_hosts.append(os.environ.get('REDIS_HOST'))
    
    # Standardhosts für DigitalOcean App Platform
    standard_hosts = ['api', 'localhost', '127.0.0.1', 'hackthestudy-backend-main']
    for host in standard_hosts:
        if host not in redis_hosts:
            redis_hosts.append(host)
    
    log_step("Redis-Verbindungen", "INFO", f"Mögliche Hosts: {', '.join(redis_hosts)}")
    
    # Logging einrichten, um Umgebungsvariablen anzuzeigen
    logger = logging.getLogger("app_startup")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[API] %(levelname)s: %(message)s'))
    logger.addHandler(handler)

    # Wichtige Umgebungsvariablen ausgeben
    logger.info("=== API-Service Umgebungsvariablen ===")
    for var in important_vars:
        value = os.environ.get(var, "NICHT GESETZT")
        # Wenn es ein Passwort enthält, dann zensieren
        if var.lower().find("password") >= 0 or var.lower().find("secret") >= 0:
            value = "******" if value != "NICHT GESETZT" else "NICHT GESETZT"
        logger.info(f"{var}: {value}")
    
    # Redis-spezifische Konfiguration
    logger.info("=== Redis-Konfiguration ===")
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    redis_port = os.environ.get("REDIS_PORT", "6379")
    redis_url = os.environ.get("REDIS_URL", f"redis://{redis_host}:{redis_port}/0")
    logger.info(f"Effektive Redis-URL: {redis_url}")
    logger.info("========================")
    
    return redis_hosts

# Konfiguriere Logging
logger = setup_logging()

# Explizites Debug-Logging von OpenAI ermöglichen
os.environ['OPENAI_LOG'] = 'debug'

# Lade die Umgebungsvariablen - Nur in Entwicklung, nicht in Produktion
if is_development:
    # Nur in Entwicklung .env-Datei laden
    load_dotenv(override=True, verbose=True)
    print("Entwicklungsumgebung: .env-Datei wird geladen")
else:
    # In Produktion nur Digital Ocean Umgebungsvariablen verwenden
    print("Produktionsumgebung: Verwende Digital Ocean Umgebungsvariablen")

def force_flush_handlers():
    """Flusht alle Logger-Handler, um sicherzustellen, dass Logs geschrieben werden"""
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()

# Verbesserte, strukturierte Logging-Funktion
def log_step(step_name, status="START", details=None, level="INFO"):
    """
    Strukturiertes Logging mit klaren Schritt-Namen und Status
    
    :param step_name: Name des Schritts (z.B. "Redis-Verbindung")
    :param status: Status (START, SUCCESS, ERROR, WARNING, INFO)
    :param details: Zusätzliche Details (optional)
    :param level: Log-Level (INFO, WARNING, ERROR, DEBUG)
    """
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Status-Emojis für bessere visuelle Unterscheidung
    status_emojis = {
        "START": "🔄",
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "INFO": "ℹ️"
    }
    
    emoji = status_emojis.get(status, "")
    message = f"{emoji} [{status}] {step_name}"
    
    if details:
        message += f": {details}"
    
    log_func(message)
    # Sofortiges Flushen für Echtzeit-Logs
    force_flush_handlers()

# Dynamische Funktion zum Testen von Redis-Verbindungen
def test_redis_connections(redis_hosts, port=6379, db=0):
    """
    Testet Redis-Verbindungen zu verschiedenen Hosts und gibt den ersten erfolgreichen Host zurück.
    Reduziertes Logging für klarere Ausgabe.
    """
    from redis import Redis
    import time
    
    # Wenn keine Hosts angegeben sind, Standard-Hosts verwenden
    if not redis_hosts:
        redis_hosts = ['localhost', '127.0.0.1', 'api', 'redis']
    
    log_step("Redis-Verbindungstests", "START", f"Teste {len(redis_hosts)} mögliche Hosts")
    
    failed_hosts = []
    # Jeden Host testen
    for host in redis_hosts:
        redis_url = f"redis://{host}:{port}/{db}"
        try:
            # Verbindung mit Timeout testen
            client = Redis.from_url(redis_url, socket_timeout=5)
            client.ping()
            # Nur erfolgreiche Verbindungen werden ausführlich geloggt
            log_step("Redis-Verbindung", "SUCCESS", f"Host: {host}, Port: {port}")
            # Erfolgreiche Verbindung zurückgeben
            return host, redis_url
        except Exception as e:
            # Fehler sammeln, aber nicht einzeln loggen
            failed_hosts.append(host)
            continue
    
    # Fehlgeschlagene Verbindungen werden zusammengefasst
    if failed_hosts:
        log_step("Redis-Verbindungstests", "ERROR", 
                f"Verbindungen fehlgeschlagen für: {', '.join(failed_hosts)}", "ERROR")
    
    # Wenn keine Verbindung erfolgreich war, None zurückgeben
    return None, None

def log_startup_info():
    """Gibt wichtige Informationen beim Start der Anwendung aus"""
    container_type = os.environ.get('CONTAINER_TYPE', 'unbekannt')
    run_mode = os.environ.get('RUN_MODE', 'app')
    
    log_step("Anwendungsstart", "START", f"Container: {container_type}, Modus: {run_mode}")
    log_step("System-Info", "INFO", f"PID: {os.getpid()}, Hostname: {socket.gethostname()}")
    
    # Server-Umgebung ermitteln
    if 'gunicorn' in os.environ.get('SERVER_SOFTWARE', ''):
        log_step("Server", "INFO", "Läuft unter Gunicorn")
    else:
        log_step("Server", "INFO", "Läuft im Flask-Entwicklungsmodus")
    
    # DigitalOcean-spezifische Informationen
    if 'DIGITAL_OCEAN_APP_NAME' in os.environ:
        log_step("Plattform", "INFO", f"DigitalOcean App: {os.environ.get('DIGITAL_OCEAN_APP_NAME')}")
    
    # Netzwerk-Informationen
    try:
        ip_addresses = socket.gethostbyname_ex(socket.gethostname())
        log_step("Netzwerk", "INFO", f"IP-Adressen: {ip_addresses[2]}")
    except:
        log_step("Netzwerk", "WARNING", "IP-Adressen konnten nicht ermittelt werden")
    
    force_flush_handlers()

# Funktion zum Initialisieren der Anwendung
def init_app(run_mode=None):
    # Globale logger-Variable verwenden
    global logger
    
    # Bestimme Ausführungsmodus (Standard, Worker oder Payment)
    if run_mode is None:
        run_mode = os.environ.get('RUN_MODE', 'app')
    
    # Erzwinge Umgebungsvariable für andere Module
    os.environ['RUN_MODE'] = run_mode
    
    # Stelle sicher, dass der Worker-Container einen anderen Port verwendet als der API-Container
    if run_mode == 'worker' and os.environ.get('PORT') == '8080':
        log_step("Port-Konfiguration", "WARNING", "Worker und API haben den gleichen Port. Ändere Worker-Port auf 8081...")
        os.environ['PORT'] = '8081'
    
    # Umgebungsvariablen protokollieren - für ALLE Modi
    redis_hosts = log_environment_variables()
    
    # Worker- oder Payment-Service Modi
    if run_mode in ['worker', 'payment']:
        # Konfiguriere Logging für den Prozess
        logger = setup_logging()
        log_step("Service", "START", f"Starte im {run_mode.upper()}-Modus")
        
        # Überprüfe, ob API-Anfragen protokolliert werden sollen
        log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
        if log_api_requests:
            log_step("Logging", "INFO", "API-Anfragen-Protokollierung aktiviert")
        
        # Worker-Modus: Starte Celery-Worker
        if run_mode == 'worker':
            from celery import Celery
            
            # Dynamisch Redis-Verbindung testen und beste URL finden
            redis_host, redis_url = test_redis_connections(redis_hosts)
            
            if not redis_url:
                # Wenn keine Verbindung erfolgreich war, Standard-URL verwenden
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0').strip()
                log_step("Redis", "WARNING", f"Keine Verbindung hergestellt. Standard-URL: {redis_url}", "warning")
            else:
                # Erfolgreiche Redis-URL verwenden und in Umgebungsvariablen speichern
                log_step("Redis", "SUCCESS", f"Verbindung hergestellt: {redis_url}")
                os.environ['REDIS_URL'] = redis_url
                os.environ['REDIS_HOST'] = redis_host
                
            # Konfiguriere Celery-Worker direkt
            log_step("Celery", "START", "Initialisiere Celery-Worker")
            celery_app = Celery('worker', broker=redis_url, backend=redis_url)
            
            # Setze Celery-Konfigurationen basierend auf Umgebungsvariablen
            celery_config = {
                'broker_url': redis_url,
                'result_backend': redis_url,
                'task_serializer': 'json',
                'accept_content': ['json'],
                'result_serializer': 'json',
                'enable_utc': True,
                'worker_concurrency': int(os.environ.get('CELERY_WORKER_CONCURRENCY', '2')),
                'worker_max_tasks_per_child': int(os.environ.get('CELERY_MAX_TASKS_PER_CHILD', '100')),
                'broker_connection_retry': True,
                'broker_connection_retry_on_startup': True,
                'broker_connection_max_retries': 10,
            }
            
            # Anwenden der Konfiguration
            celery_app.conf.update(celery_config)
            log_step("Celery", "SUCCESS", "Konfiguration angewendet")
            
            # Setze Logging für den Celery-Worker
            log_step("Celery", "INFO", f"Worker bereit mit Redis-URL: {redis_url}")
            
            # Beende die App-Initialisierung hier, da wir nur den Worker starten wollen
            return None  # Worker hat keine Flask-App
        
        # Payment-Service: Starte speziellen Server
        if run_mode == 'payment':
            from services.payment_service import create_payment_app
            log_step("Payment-Service", "INFO", "Starte Payment-Service")
            return create_payment_app()
    
    # Standard-App-Modus für API und Web-Funktionen
    log_step("API-Server", "START", "Initialisiere Flask-Anwendung")
    app = Flask(__name__)
    
    # Protokolliere wichtige Startinformationen
    log_startup_info()
    
    # Konfiguriere Secret Key für Sessions
    secret_key = os.environ.get('FLASK_SECRET_KEY')
    if not secret_key:
        # Generiere einen zufälligen Schlüssel, wenn keiner gesetzt ist
        import secrets
        secret_key = secrets.token_hex(32)
        log_step("Sicherheit", "WARNING", "Kein FLASK_SECRET_KEY gefunden. Verwende zufälligen Schlüssel für diese Sitzung.", "warning")
    
    app.secret_key = secret_key
    log_step("Sicherheit", "SUCCESS", "Secret Key für Sessions konfiguriert")
    
    # Versuche, die beste Redis-Verbindung zu finden
    redis_host, redis_url = test_redis_connections(redis_hosts)
    if redis_url:
        log_step("Redis", "SUCCESS", f"API-Server: Erfolgreiche Redis-Verbindung zu {redis_host}: {redis_url}")
        # Setze die erfolgreiche Verbindung in Umgebungsvariablen
        os.environ['REDIS_URL'] = redis_url
        os.environ['REDIS_HOST'] = redis_host
    else:
        log_step("Redis", "WARNING", "API-Server: Konnte keine Redis-Verbindung herstellen!")
    
    # Konfiguriere App-Logger mit einheitlicher Formatierung
    app.logger.setLevel(logging.INFO)
    # Entferne alle bestehenden Handler
    for handler in app.logger.handlers:
        app.logger.removeHandler(handler)
    # Verwende die einheitliche Formatierung
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'))
    app.logger.addHandler(handler)
    # Verhindere doppelte Logs
    app.logger.propagate = False
    
    # OAuth Konfiguration - Verbessert mit Fehlerbehandlung
    try:
        from api.auth import setup_oauth
        setup_oauth(app)
        log_step("OAuth", "SUCCESS", "OAuth erfolgreich initialisiert und in Flask-App eingebunden")
    except Exception as e:
        log_step("OAuth", "ERROR", f"Fehler bei der OAuth-Konfiguration: {str(e)}")
        log_step("OAuth", "ERROR", traceback.format_exc())
    
    # Konfiguriere CORS
    cors_origins = setup_cors_origins()
    log_step("CORS", "INFO", f"Finale CORS-Origins: %s", ", ".join(cors_origins))
    
    # Initialisiere CORS mit den erlaubten Origins
    CORS(app, 
         resources={r"/*": {
             "origins": cors_origins,
             "supports_credentials": True,
             "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin", "X-CSRF-Token", "Cache-Control"],
             "expose_headers": ["Content-Type", "Authorization"],
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
             "max_age": 3600,
             "vary_header": True
         }},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin", "X-CSRF-Token", "Cache-Control"],
         expose_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
         max_age=3600)
    
    # Konfiguriere ProxyFix für korrekte Client-IPs hinter Proxies
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
        x_prefix=1
    )
    
    # Konfiguriere die Datenbank
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialisiere die Datenbank
    db.init_app(app)
    
    # Registriere Blueprints
    from api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    
    # Registriere Payment Blueprint
    from api.payment import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/api/v1/payment')
    
    # Debug-Endpoint für Worker-Status
    @app.route('/api/v1/debug/worker', methods=['GET'])
    def worker_status():
        """
        Debug-Endpoint, um den Status der Worker-Prozesse zu überprüfen.
        """
        from redis import Redis
        import json
        
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        redis_client = Redis.from_url(redis_url)
        
        # Versuche, Informationen über laufende Tasks zu sammeln
        active_tasks = []
        try:
            # Prüfe redis keys mit task_id Präfix
            task_keys = redis_client.keys('task_id:*')
            for key in task_keys:
                session_id = key.decode('utf-8').split(':')[1]
                task_id = redis_client.get(key)
                if task_id:
                    task_id = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
                    # Versuche, Task-Status aus Redis zu bekommen
                    status_key = f"task_status:{task_id}"
                    status = redis_client.get(status_key)
                    status = status.decode('utf-8') if status else "unknown"
                    
                    # Sammle Informationen
                    active_tasks.append({
                        "session_id": session_id,
                        "task_id": task_id,
                        "status": status
                    })
        except Exception as e:
            app.logger.error(f"Fehler beim Abrufen der Task-Informationen: {str(e)}")
            active_tasks.append({"error": str(e)})
        
        # Prüfe, ob Celery-Worker vorhanden sind
        worker_info = {"status": "unknown"}
        try:
            # Optional: wenn celery-Inspektion verfügbar ist
            from celery.task.control import inspect
            i = inspect()
            stats = i.stats()
            if stats:
                worker_info = {
                    "status": "active",
                    "workers": len(stats),
                    "stats": stats
                }
            else:
                worker_info = {"status": "no workers found"}
        except Exception as e:
            app.logger.error(f"Fehler beim Prüfen der Celery-Worker: {str(e)}")
            worker_info = {"status": "error", "message": str(e)}
        
        # Redis-Gesundheitsprüfung
        redis_status = "unavailable"
        try:
            if redis_client.ping():
                redis_status = "available"
        except Exception as e:
            redis_status = f"error: {str(e)}"
        
        return jsonify({
            "redis_status": redis_status,
            "worker_info": worker_info,
            "active_tasks": active_tasks,
            "timestamp": datetime.now().isoformat()
        }), 200
    
    # Erweiterter Health-Check-Endpunkt für Status-Überwachung
    @app.route('/api/v1/health', methods=['GET'])
    def health_check():
        """Erweiterter Health-Check für Container-Status und Systemgesundheit"""
        # Parameter auslesen
        skip_db = request.args.get('skip_db', 'false').lower() == 'true'
        simple = request.args.get('simple', 'false').lower() == 'true'
        
        log_step("Health-Check", "START", f"Health-Check angefordert von {request.remote_addr}")
        
        # Einfacher Health-Check ohne detaillierte Prüfungen
        if simple:
            return jsonify({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
                "environment": os.environ.get('FLASK_ENV', 'production'),
                "uptime": int(time.time() - START_TIME)
            }), 200
        
        # Health-Check ohne Datenbank-Prüfung
        if skip_db:
            return jsonify({
                "status": "healthy",
                "message": "DB-Prüfung übersprungen auf Anfrage",
                "timestamp": datetime.now().isoformat(),
                "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
                "version": "1.0.0"
            }), 200
        
        health_status = {"status": "healthy", "checks": {}}
        
        try:
            # Systematischer Check aller Komponenten
            
            # 1. Datenbank prüfen
            db_status = check_database_health()
            health_status["checks"]["database"] = db_status
            if db_status["status"] == "healthy":
                log_step("Health-Check", "SUCCESS", "Datenbankverbindung OK")
            else:
                log_step("Health-Check", "ERROR", f"Datenbankproblem: {db_status.get('message', 'Unbekannter Fehler')}")
            
            # 2. Redis prüfen
            redis_status = test_redis_connection_health()
            health_status["checks"]["redis"] = redis_status
            if redis_status["status"] == "healthy":
                log_step("Health-Check", "SUCCESS", "Redis-Verbindung OK")
            else:
                log_step("Health-Check", "ERROR", f"Redis-Problem: {len(redis_status.get('checks', [])) - sum(1 for c in redis_status.get('checks', []) if c.get('status') == 'connected')} fehlgeschlagene Verbindungen")
            
            # 3. Celery-Worker prüfen
            celery_status = check_celery_workers()
            health_status["checks"]["celery"] = celery_status
            if celery_status["status"] == "healthy":
                log_step("Health-Check", "SUCCESS", f"{celery_status.get('worker_count', 0)} aktive Worker gefunden")
            else:
                log_step("Health-Check", "WARNING", f"Celery-Problem: {celery_status.get('message', 'Keine aktiven Worker')}")
            
            # 4. Systemressourcen prüfen
            system_status = check_system_health()
            health_status["checks"]["system"] = system_status
            if system_status["status"] == "healthy":
                log_step("Health-Check", "INFO", f"System gesund: CPU {system_status.get('cpu_percent', 0)}%, RAM {system_status.get('memory_percent', 0)}%")
            else:
                log_step("Health-Check", "WARNING", f"Systemressourcen knapp: CPU {system_status.get('cpu_percent', 0)}%, RAM {system_status.get('memory_percent', 0)}%")
            
            # Gesamtstatus basierend auf allen Checks bestimmen
            component_status = [check["status"] for check in health_status["checks"].values()]
            
            if "error" in component_status:
                health_status["status"] = "unhealthy"
            elif "critical" in component_status:
                health_status["status"] = "critical"
            elif "degraded" in component_status:
                health_status["status"] = "degraded"
            
            # Metadaten hinzufügen
            health_status["timestamp"] = datetime.now().isoformat()
            health_status["container_type"] = os.environ.get('CONTAINER_TYPE', 'unknown')
            health_status["version"] = "1.0.0"
            health_status["uptime"] = int(time.time() - START_TIME)
            
            # Speichere Status in Redis für historische Überwachung
            try:
                from core.redis_client import redis_client
                # Kompakten Status speichern
                redis_client.set(
                    f"health:status:{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    json.dumps({
                        "status": health_status["status"],
                        "timestamp": health_status["timestamp"],
                        "component_status": {k: v["status"] for k, v in health_status["checks"].items()}
                    }),
                    ex=86400  # 24 Stunden aufbewahren
                )
                # Aktuellsten Status für schnellen Zugriff speichern
                redis_client.set("health:latest", json.dumps(health_status), ex=3600)
            except Exception as redis_error:
                log_step("Health-Check", "WARNING", f"Konnte Status nicht in Redis speichern: {str(redis_error)}")
            
            log_step("Health-Check", "SUCCESS", f"Health-Check abgeschlossen: {health_status['status']}")
            return jsonify(health_status), 200
            
        except Exception as e:
            log_step("Health-Check", "ERROR", f"Fehlerhafte Komponente: {str(e)}")
            return jsonify({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500
    
    # Füge einen simplen Ping-Endpunkt hinzu
    @app.route('/api/v1/ping', methods=['GET'])
    def ping():
        """Einfacher Ping-Endpunkt ohne Datenbankprüfung oder andere Abhängigkeiten"""
        log_step("Ping", "INFO", f"Ping-Anfrage von {request.remote_addr}")
        
        # Forciere Log-Ausgabe sofort
        force_flush_handlers()
        
        return jsonify({
            "status": "ok",
            "message": "pong",
            "timestamp": datetime.now().isoformat()
        }), 200
    
    # Neuer Diagnose-Endpunkt für Systeminfos
    @app.route('/api/v1/debug/diagnose', methods=['GET'])
    def diagnose():
        """Bereitstellung detaillierter Systemdiagnose für Fehleranalyse"""
        import psutil
        import platform
        import socket
        
        # Grundlegende Authentifizierung (einfach für Debug-Zwecke)
        auth_token = request.args.get('token')
        expected_token = os.environ.get('DEBUG_TOKEN')
        
        if expected_token and auth_token != expected_token:
            return jsonify({"error": "Nicht autorisiert"}), 401
            
        log_step("Diagnose", "START", "Sammle Systemdiagnose")
        
        # Umgebungsvariablen erfassen
        env_vars = {}
        for key in ['CONTAINER_TYPE', 'RUN_MODE', 'REDIS_URL', 'REDIS_HOST', 'DATABASE_URL']:
            if key in os.environ:
                value = os.environ[key]
                # Maskiere sensible Daten
                if key in ['DATABASE_URL', 'REDIS_URL'] and ':' in value and '@' in value:
                    value = re.sub(r'(://[^:]+:)([^@]+)(@)', r'\1*****\3', value)
                env_vars[key] = value
        
        # Systeminfos
        system_info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
            "run_mode": os.environ.get('RUN_MODE', 'unknown'),
            "process_id": os.getpid(),
            "uptime": time.time() - psutil.Process(os.getpid()).create_time(),
            "environment_variables": env_vars
        }
        
        # Direkte Redis-Verbindungsprüfung
        redis_checks = []
        redis_hosts = []
        redis_host = os.environ.get('REDIS_HOST')
        if redis_host:
            redis_hosts.append(redis_host)
        # DO-spezifische Hosts
        api_host = os.environ.get('api_PRIVATE_URL', '').replace('https://', '').replace('http://', '')
        if api_host:
            redis_hosts.append(api_host)
            
        # Standard-Hosts
        for host in ['localhost', '127.0.0.1', 'api', 'redis']:
            if host not in redis_hosts:
                redis_hosts.append(host)
                
        for host in redis_hosts:
            try:
                import redis
                start_time = time.time()
                client = redis.Redis(host=host, port=6379, db=0, socket_timeout=2)
                ping_result = client.ping()
                end_time = time.time()
                redis_checks.append({
                    "host": host,
                    "status": "connected" if ping_result else "failed",
                    "response_time_ms": (end_time - start_time) * 1000
                })
            except Exception as e:
                redis_checks.append({
                    "host": host,
                    "status": "error",
                    "error": str(e)
                })
        
        # CPU und RAM
        try:
            cpu_info = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "cpu_count": psutil.cpu_count(),
                "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
            
            memory_info = {
                "total_memory": psutil.virtual_memory().total,
                "available_memory": psutil.virtual_memory().available,
                "memory_percent": psutil.virtual_memory().percent,
                "used_memory": psutil.virtual_memory().used
            }
        except Exception as e:
            cpu_info = {"error": str(e)}
            memory_info = {"error": str(e)}
        
        # Netzwerkverbindungen
        try:
            connections = [
                {
                    "local_addr": f"{c.laddr.ip}:{c.laddr.port}",
                    "remote_addr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "None",
                    "status": c.status,
                    "type": c.type
                }
                for c in psutil.net_connections()
                if c.status == 'ESTABLISHED'
            ][:20]  # Begrenze auf 20 Verbindungen
        except Exception as e:
            connections = [{"error": str(e)}]
        
        # Celery-Worker-Status
        try:
            worker_status = {
                "active_tasks": get_active_tasks(),
                "worker_count": len(get_active_workers())
            }
        except Exception as e:
            worker_status = {"error": str(e)}
        
        # Redis-Verbindungsstatus
        try:
            from core.redis_client import redis_client
            redis_test = redis_client.ping()
            redis_info = {
                "connected": redis_test,
                "url": REDIS_URL.replace("redis://", "redis://***:***@") if 'REDIS_URL' in globals() else os.environ.get('REDIS_URL', 'unknown'),
                "direct_checks": redis_checks
            }
        except Exception as e:
            redis_info = {"error": str(e), "direct_checks": redis_checks}
        
        # DigitalOcean-spezifische Infos
        do_info = {}
        for key, value in os.environ.items():
            if 'DIGITAL_OCEAN' in key or 'DO_' in key:
                do_info[key] = value
        
        # Diagnose-Informationen zusammenstellen
        diagnose_info = {
            "timestamp": datetime.now().isoformat(),
            "system": system_info,
            "digitalocean": do_info,
            "cpu": cpu_info,
            "memory": memory_info,
            "network_connections": connections,
            "celery": worker_status,
            "redis": redis_info
        }
        
        log_step("Diagnose", "SUCCESS", "Systemdiagnose abgeschlossen")
        return jsonify(diagnose_info), 200
    
    # Root-Route für API-Status
    @app.route('/', methods=['GET', 'OPTIONS'])
    def api_status():
        """
        Liefert den API-Status und grundlegende Informationen.
        """
        log_step("API-Status", "INFO", f"Anfrage von {request.remote_addr}")
        if request.method == 'OPTIONS':
            response = jsonify({"success": True})
            return response
            
        return jsonify({
            "status": "online",
            "version": "1.0.0",
            "api_base": "/api/v1",
            "documentation": "https://api.hackthestudy.ch/docs",
            "timestamp": datetime.now().isoformat()
        })
    
    # Füge einen sehr einfachen Health-Check hinzu, der immer erfolgreich ist
    @app.route('/api/v1/simple-health', methods=['GET'])
    def simple_health_check():
        """
        Ein extrem einfacher Health-Check-Endpunkt für DigitalOcean App Platform,
        der keine Abhängigkeiten wie Datenbank oder Redis prüft.
        """
        log_step("Simple-Health", "SUCCESS", f"Anfrage von {request.remote_addr}")
        force_flush_handlers()
        
        return jsonify({
            "status": "healthy",
            "message": "Einfacher Health Check - keine DB-Prüfung",
            "timestamp": datetime.now().isoformat(),
            "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
            "version": "1.0.0",
            "environment": os.environ.get('ENVIRONMENT', 'production')
        }), 200
    
    # Globaler Error Handler für 405 Method Not Allowed
    @app.errorhandler(405)
    def method_not_allowed(e):
        log_step("API-Error", "WARNING", f"405 Method Not Allowed: {request.method} {request.path}")
        return jsonify({
            "success": False,
            "error": {
                "code": "METHOD_NOT_ALLOWED",
                "message": f"Die Methode {request.method} ist für diesen Endpunkt nicht erlaubt",
                "allowed_methods": e.valid_methods if hasattr(e, 'valid_methods') else None
            }
        }), 405
    
    # Globaler Error Handler für 401 Unauthorized
    @app.errorhandler(401)
    def unauthorized(e):
        log_step("API-Error", "WARNING", f"401 Unauthorized: {request.path}")
        return jsonify({
            "success": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Bitte melden Sie sich an oder überprüfen Sie Ihre Authentifizierung",
                "details": str(e)
            }
        }), 401
    
    # Globaler Error Handler für alle anderen Fehler
    @app.errorhandler(Exception)
    def handle_exception(e):
        log_step("API-Error", "ERROR", f"Unbehandelter Fehler: {str(e)}")
        
        # Verbesserte Diagnose für Worker Timeout
        if "WORKER TIMEOUT" in str(e):
            # Rufe erweiterte Diagnose auf
            diagnostics = diagnose_worker_timeout()
            
            # Status in Redis speichern
            try:
                from core.redis_client import redis_client
                redis_client.set("worker_timeout_diagnose", json.dumps(diagnostics), ex=86400)
            except Exception as redis_error:
                log_step("Redis", "ERROR", f"Fehler beim Speichern der Timeout-Diagnose: {str(redis_error)}")
                
            # Direkte Systemdiagnose aus den diagnostics-Daten
            try:
                process_info = diagnostics.get("process", {})
                system_info = diagnostics.get("system", {})
                
                log_step("Worker", "ERROR", 
                        f"Worker Timeout - " 
                        f"CPU: {process_info.get('cpu_percent', '?')}%, "
                        f"RAM: {process_info.get('memory_percent', '?')}%, "
                        f"Threads: {process_info.get('threads', '?')}, "
                        f"Systemlast: {system_info.get('cpu_usage_percent', '?')}%", 
                        "error")
            except Exception as log_error:
                log_step("Worker", "ERROR", f"Diagnose unvollständig: {str(log_error)}", "error")
        
        if isinstance(e, HTTPException):
            response = e.get_response()
            response.data = json.dumps({
                "success": False,
                "error": {
                    "code": e.name,
                    "message": e.description,
                    "status_code": e.code
                }
            })
            response.content_type = "application/json"
            return response
            
        return jsonify({
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Ein interner Serverfehler ist aufgetreten",
                "details": str(e) if app.debug else None
            }
        }), 500
    
    # Konfiguriere Prometheus Metrics
    metrics = PrometheusMetrics(app)
    
    @app.after_request
    def process_response(response):
        # Setze CORS-Header für alle Anfragen
        origin = request.headers.get('Origin')
        if origin and origin in cors_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin, X-CSRF-Token, Cache-Control'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Max-Age'] = '3600'
            response.headers['Vary'] = 'Origin'
        
        # Setze zusätzliche Sicherheitsheader
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Protokollierung der API-Anfragen - IMMER loggen, egal was in der Umgebungsvariable steht
        if not request.path.startswith('/static/'):
            # Kürze Anfragedaten für Logging
            req_data = None
            content_type = request.headers.get('Content-Type', '')
            
            if 'application/json' in content_type and request.data:
                try:
                    raw_data = request.get_json(silent=True)
                    if raw_data:
                        # Sensible Daten filtern
                        if isinstance(raw_data, dict):
                            filtered_data = raw_data.copy()
                            for key in ['password', 'token', 'api_key']:
                                if key in filtered_data:
                                    filtered_data[key] = '[REDACTED]'
                            req_data = filtered_data
                        else:
                            req_data = "[JSON DATA, nicht dict]"
                except:
                    req_data = "[Ungültiges JSON]"
            
            # Benutzerinformationen aus Session oder Auth holen, wenn vorhanden
            user_info = "nicht authentifiziert"
            if hasattr(request, 'user') and request.user:
                user_info = f"user:{request.user.id}"
            elif hasattr(request, 'session') and 'user_id' in request.session:
                user_info = f"user:{request.session['user_id']}"
                
            # IP-Adresse mit Proxy-Berücksichtigung
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            
            # Log-Nachricht zusammenstellen
            log_msg = (
                f"!!! API-REQUEST EMPFANGEN !!! {request.method} {request.path} - Status: {response.status_code} - " 
                f"IP: {client_ip} - User: {user_info}"
            )
            
            # Log auf verschiedenen Kanälen ausgeben, um sicherzustellen, dass es sichtbar ist
            logger.info(log_msg)                    # HackTheStudy.app Logger
            api_request_logger.info(log_msg)        # API Request Logger
            app.logger.info(log_msg)                # Flask App Logger
            print(f"[STDOUT] {log_msg}")            # Direkte STDOUT-Ausgabe
            sys.stdout.flush()                      # Explizites Flushen von stdout
            
            # Erzwinge sofortiges Flushen der Logs
            force_flush_handlers()
        
        # Response zurückgeben
        return response
    
    @app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
    @app.route('/<path:path>', methods=['OPTIONS'])
    def handle_options(path):
        response = jsonify({"success": True})
        return process_response(response)
    
    # Catch-all Route für nicht gefundene Endpunkte
    @app.route('/<path:path>', methods=['GET'])
    def catch_all(path):
        app.logger.info(f"Catch-all Route für unbekannten Pfad: {path}")
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Der Endpunkt '{path}' wurde nicht gefunden",
                "path": path
            }
        }), 404
    
    return app

def setup_gunicorn_logging():
    """Konfiguriert die Logger für Gunicorn und verknüpft sie mit unseren Loggern"""
    if 'gunicorn' in os.environ.get('SERVER_SOFTWARE', ''):
        # Konfiguriere das Logging neu, um die Gunicorn-Handler zu berücksichtigen
        setup_logging()
        
        logger.info("Gunicorn-Logging-Konfiguration erfolgreich angewendet")
        
        force_flush_handlers()
        
        return True
    return False

# Initialisiere die globale app-Variable für Gunicorn
app = init_app(run_mode='app')
print("Globale app-Variable wurde initialisiert")

# Main-Funktion für den direkten Start der Anwendung
if __name__ == '__main__':
    # Logger initialisieren
    logger = setup_logging()
    
    # Ausführungsmodus bestimmen
    run_mode = os.environ.get('RUN_MODE', 'app')
    
    # App initialisieren basierend auf dem Modus
    app = init_app(run_mode)
    
    # Wenn USE_SUPERVISOR gesetzt ist, gibt es nichts zu tun - 
    # alle Prozesse werden von Supervisor gesteuert
    if os.environ.get('USE_SUPERVISOR') == 'true':
        logger.info("Container wird im Supervisor-Modus ausgeführt. Einzelne Prozesse werden von Supervisor verwaltet.")
        # Hier nichts tun, Supervisor übernimmt die Kontrolle
        import time
        while True:
            time.sleep(3600)  # Hauptprozess am Leben halten, aber nichts tun
    
    # Wenn es sich um einen Worker- oder Payment-Service handelt, läuft dieser bereits
    elif run_mode in ['worker']:
        logger.info(f"Worker-Ausführung gestartet im {run_mode.upper()}-Modus.")
        # Blockiere den Hauptthread, damit der Worker weiterlaufen kann
        # Da der Worker bereits in init_app gestartet wurde
        import time
        try:
            while True:
                time.sleep(60)  # Prüfe alle 60 Sekunden
                logger.debug("Worker läuft...")
        except KeyboardInterrupt:
            logger.info("Worker-Ausführung wird auf Anforderung beendet...")
            sys.exit(0)
    
    # Im App-Modus die Flask-App starten
    elif app:
        # Debug-Modus bestimmen
        debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
        
        # Port bestimmen (Standard: 5000 für lokale Entwicklung, 8080 für DigitalOcean)
        port = int(os.environ.get('PORT', 5000))
        
        # Hostname bestimmen (Standard: localhost für Entwicklung, 0.0.0.0 für Produktion)
        host = os.environ.get('HOST', '0.0.0.0')
        
        logger.info(f"Flask-App wird gestartet auf {host}:{port} (Debug: {debug})")
        
        # App starten mit Werkzeug Server
        app.run(host=host, port=port, debug=debug, threaded=True)
    else:
        logger.error("Konnte keine App initialisieren. Beende...")
        sys.exit(1)

def diagnose_worker_timeout(task_id=None):
    """
    Erweiterte Diagnose für Worker-Timeouts mit nützlichen Umgebungsinformationen
    Ersetzt die Shell-Skript-basierte Überwachung
    """
    import psutil
    import os
    import json
    from datetime import datetime
    
    try:
        # Aktuelle Systeminformationen sammeln
        process = psutil.Process(os.getpid())
        memory_info = psutil.virtual_memory()
        
        # Prozessinformationen
        process_info = {
            "pid": os.getpid(),
            "cpu_percent": process.cpu_percent(interval=1.0),
            "memory_percent": process.memory_percent(),
            "threads": process.num_threads(),
            "open_files": len(process.open_files()),
            "connections": len(process.connections()),
            "uptime_seconds": time.time() - process.create_time()
        }
        
        # Systeminformationen
        system_info = {
            "cpu_usage_percent": psutil.cpu_percent(interval=1.0),
            "memory_total_mb": memory_info.total / (1024 * 1024),
            "memory_available_mb": memory_info.available / (1024 * 1024),
            "memory_percent": memory_info.percent,
            "hostname": socket.gethostname()
        }
        
        # Netzwerkverbindungen prüfen
        network_info = []
        try:
            for conn in process.connections():
                if conn.status == 'ESTABLISHED':
                    network_info.append({
                        "local_addr": f"{conn.laddr.ip}:{conn.laddr.port}",
                        "remote_addr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "None",
                        "status": conn.status
                    })
        except:
            pass
            
        # Redis-Verbindung explizit testen
        redis_info = test_redis_connection_health()
        
        # Alles zusammenstellen
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "event": "worker_timeout",
            "task_id": task_id,
            "process": process_info,
            "system": system_info,
            "network_connections": network_info[:20],  # Begrenze auf 20 Verbindungen
            "redis": redis_info,
            "environment": {
                "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
                "run_mode": os.environ.get('RUN_MODE', 'unknown')
            }
        }
        
        # Speichere Diagnose in Redis für weitere Analyse
        try:
            from core.redis_client import redis_client
            redis_client.set(
                f"diagnostics:worker_timeout:{datetime.now().strftime('%Y%m%d%H%M%S')}",
                json.dumps(diagnostics),
                ex=86400  # 24 Stunden
            )
            
            # Füge zur Liste der Timeouts hinzu (für einfacheren Zugriff)
            redis_client.lpush("diagnostics:worker_timeouts", task_id or "unknown")
            redis_client.ltrim("diagnostics:worker_timeouts", 0, 99)  # Behalte nur die letzten 100
        except Exception as e:
            log_step("Diagnose", "ERROR", f"Konnte Timeout-Diagnose nicht in Redis speichern: {str(e)}")
        
        log_step("Worker-Timeout", "ERROR", 
                f"CPU: {diagnostics['process']['cpu_percent']}%, RAM: {diagnostics['process']['memory_percent']}%, " 
                f"Netzwerk: {len(network_info)} Verbindungen")
                
        return diagnostics
    except Exception as e:
        log_step("Diagnose", "ERROR", f"Fehler bei Worker-Timeout-Diagnose: {str(e)}")
        return {"error": str(e)}

def test_redis_connection_health():
    """
    Testet Redis-Verbindungen zu verschiedenen Hosts und gibt detaillierte Diagnoseinformationen zurück.
    Ersetzt die shell-basierte Prüfung.
    """
    import redis
    
    redis_hosts = []
    # Sammle potenzielle Redis-Hosts
    redis_url = os.environ.get('REDIS_URL', '')
    if redis_url and '://' in redis_url:
        # Extrahiere Host aus URL
        try:
            host = redis_url.split('://', 1)[1].split(':', 1)[0].split('@')[-1]
            if host and host not in redis_hosts:
                redis_hosts.append(host)
        except:
            pass
    
    # Prüfe expliziten Redis-Host
    redis_host = os.environ.get('REDIS_HOST', '')
    if redis_host and redis_host not in redis_hosts:
        redis_hosts.append(redis_host)
    
    # Standard-Hosts hinzufügen
    standard_hosts = ['localhost', '127.0.0.1', 'api', 'redis']
    for host in standard_hosts:
        if host not in redis_hosts:
            redis_hosts.append(host)
    
    # Ergebnisse sammeln
    results = []
    success = False
    
    for host in redis_hosts:
        try:
            start_time = time.time()
            client = redis.Redis(host=host, port=6379, db=0, socket_timeout=2)
            ping_result = client.ping()
            response_time = (time.time() - start_time) * 1000  # ms
            
            results.append({
                "host": host,
                "status": "connected" if ping_result else "error",
                "response_time_ms": response_time
            })
            
            if ping_result:
                success = True
        except Exception as e:
            results.append({
                "host": host,
                "status": "error",
                "error": str(e)
            })
    
    return {
        "status": "healthy" if success else "error",
        "checks": results
    }

def check_database_health():
    """Prüft die Datenbankverbindung für den Health-Check"""
    try:
        # Einfache Abfrage ausführen
        db.session.execute("SELECT 1")
        db.session.commit()
        
        return {
            "status": "healthy",
            "message": "Datenbankverbindung erfolgreich"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def check_celery_workers():
    """Prüft die Verfügbarkeit von Celery-Workern"""
    try:
        workers = get_active_workers()
        
        if not workers:
            return {
                "status": "degraded",
                "message": "Keine aktiven Worker gefunden",
                "worker_count": 0
            }
            
        # Prüfe, ob Tasks bearbeitet werden
        active_tasks = get_active_tasks()
        
        return {
            "status": "healthy",
            "worker_count": len(workers),
            "active_tasks": len(active_tasks),
            "workers": [w for w in workers]
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def check_system_health():
    """Prüft Systemressourcen für den Health-Check"""
    try:
        import psutil
        
        # CPU und RAM prüfen
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Status basierend auf Grenzwerten
        status = "healthy"
        
        # CPU über 80% - degraded, über 90% - critical
        if cpu_percent > 90:
            status = "critical"
        elif cpu_percent > 80:
            status = "degraded"
            
        # RAM über 85% - degraded, über 95% - critical
        if memory.percent > 95:
            status = "critical"
        elif memory.percent > 85:
            status = "degraded"
            
        # Plattenplatz unter 10% - degraded, unter 5% - critical
        free_disk_percent = 100 - disk.percent
        if free_disk_percent < 5:
            status = "critical"
        elif free_disk_percent < 10:
            status = "degraded"
        
        return {
            "status": status,
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_mb": memory.available / (1024 * 1024),
            "disk_free_percent": free_disk_percent,
            "disk_free_gb": disk.free / (1024 * 1024 * 1024)
        }
    except Exception as e:
        return {
            "status": "unknown",
            "message": str(e)
        }