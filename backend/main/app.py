# Gevent-Monkey-Patch vor anderen Imports ausführen
# Dies verhindert SSL-Rekursionsfehler
import gevent.monkey
gevent.monkey.patch_all()

import os
import logging
import sys
import socket
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
    log_format = f'[%(asctime)s] {log_prefix}[%(levelname)s] %(name)s: %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Konfiguriere das Logging-System mit verbessertem Format
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
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
    formatter = logging.Formatter(log_format, date_format)
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
    
    # Wichtige Variablen, die angezeigt werden sollen
    important_vars = [
        'RUN_MODE', 'CONTAINER_TYPE', 'PORT', 'FLASK_DEBUG', 
        'REDIS_URL', 'REDIS_HOST', 'API_HOST',
        'DATABASE_URL', 'CELERY_BROKER_URL', 'LOG_LEVEL'
    ]
    
    # Sammle alle verfügbaren kritischen Variablen
    critical_vars = {}
    for var in important_vars:
        if var in os.environ:
            # Verberge vertrauliche Informationen
            value = os.environ.get(var)
            if var in ['DATABASE_URL'] and value:
                # Maskiere Passwörter in URLs
                import re
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
        log_step("Datenbank-Konfiguration", "SUCCESS", "DATABASE_URL konfiguriert")
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
    
    # Forciere Ausgabe sofort
    sys.stdout.flush()
    force_flush_handlers()
    
    return redis_hosts

# Konfiguriere Logging
logger = setup_logging()

# Explizites Debug-Logging von OpenAI ermöglichen
os.environ['OPENAI_LOG'] = 'debug'

# Lade die Umgebungsvariablen - Nur in Entwicklung, nicht in Produktion
if os.environ.get('ENVIRONMENT', 'production').lower() == 'development':
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
    
    # Status-Emojis für bessere Sichtbarkeit
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
    
    # Jeden Host testen
    for host in redis_hosts:
        redis_url = f"redis://{host}:{port}/{db}"
        try:
            # Verbindung mit Timeout testen
            client = Redis.from_url(redis_url, socket_timeout=5)
            client.ping()
            log_step("Redis-Verbindung", "SUCCESS", f"Host: {host}, Port: {port}")
            # Erfolgreiche Verbindung zurückgeben
            return host, redis_url
        except Exception as e:
            # Weniger ausführliches Logging für fehlgeschlagene Verbindungen
            continue
    
    # Wenn keine Verbindung erfolgreich war, None zurückgeben
    log_step("Redis-Verbindungstests", "ERROR", "Keine erfolgreiche Verbindung gefunden", "ERROR")
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
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S'))
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
    
    # Health-Check-Endpunkt für Digital Ocean
    @app.route('/api/v1/health', methods=['GET'])
    def health_check():
        """
        Health-Check-Endpunkt für Digital Ocean App Platform.
        Prüft, ob die Anwendung läuft und Datenbankverbindung besteht.
        """
        # Prüfe, ob wir die DB-Prüfung überspringen sollen
        skipdb = request.args.get('skipdb', 'false').lower() == 'true'
        
        # Log für alle API-Anfragen
        log_step("Health-Check", "START", f"IP={request.remote_addr}, skipdb={skipdb}")
        
        # Forciere Log-Ausgabe sofort
        force_flush_handlers()
        
        if skipdb:
            log_step("Health-Check", "SUCCESS", "DB-Prüfung übersprungen auf Anfrage")
            return jsonify({
                "status": "healthy",
                "message": "DB-Prüfung übersprungen auf Anfrage",
                "timestamp": datetime.now().isoformat(),
                "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
                "version": "1.0.0"
            }), 200
        
        try:
            # Prüfe Datenbankverbindung mit einer einfachen Abfrage
            log_step("Health-Check", "INFO", "Prüfe Datenbankverbindung...")
            db.session.execute("SELECT 1")
            log_step("Health-Check", "SUCCESS", "Datenbankverbindung OK")
            
            # Prüfe Redis-Verbindung, wenn wir im API-Container sind
            if os.environ.get('CONTAINER_TYPE') == 'api':
                log_step("Health-Check", "INFO", "Prüfe Redis-Verbindung...")
                from core.redis_client import redis_client
                redis_client.ping()
                log_step("Health-Check", "SUCCESS", "Redis-Verbindung OK")
            
            return jsonify({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
                "version": "1.0.0"
            }), 200
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
            "ping": "pong",
            "timestamp": datetime.now().isoformat(),
            "ip": request.remote_addr
        }), 200
    
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
            log_step("Worker", "ERROR", "Gunicorn Worker Timeout - Überprüfe blockierende Operationen", "error")
            # Erfasse Systeminformationen zur Diagnose
            import psutil
            memory_info = psutil.virtual_memory()
            log_step("System-Diagnose", "INFO", 
                     f"RAM: {memory_info.percent}% genutzt, Verfügbar: {memory_info.available/1024/1024:.1f} MB")
        
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
    
    # Debug-Diagnose-Endpunkt für die Anwendung
    @app.route('/api/v1/debug/diagnose', methods=['GET'])
    def diagnose():
        """
        Diagnose-Endpunkt, der grundlegende Systeminformationen zurückgibt
        """
        import psutil
        import platform
        
        log_step("Diagnose", "START", f"Diagnose angefordert von {request.remote_addr}")
        
        # Systemressourcen sammeln
        system_info = {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory": {
                "total": psutil.virtual_memory().total / (1024 * 1024),  # MB
                "available": psutil.virtual_memory().available / (1024 * 1024),  # MB
                "percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total": psutil.disk_usage('/').total / (1024 * 1024 * 1024),  # GB
                "free": psutil.disk_usage('/').free / (1024 * 1024 * 1024),  # GB
                "percent": psutil.disk_usage('/').percent
            },
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "open_file_descriptors": len(psutil.Process().open_files()),
            "connections": len(psutil.Process().connections()),
            "threads": psutil.Process().num_threads()
        }
        
        # Container spezifische Informationen
        container_info = {
            "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
            "run_mode": os.environ.get('RUN_MODE', 'unknown'),
            "port": os.environ.get('PORT', 'unknown'),
            "environment": os.environ.get('ENVIRONMENT', 'production'),
            "hostname": socket.gethostname(),
            "pid": os.getpid()
        }
        
        # Redis-Status prüfen
        redis_status = "unknown"
        try:
            from redis import Redis
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            client = Redis.from_url(redis_url, socket_timeout=2)
            if client.ping():
                redis_status = "connected"
                log_step("Diagnose", "SUCCESS", "Redis-Verbindung erfolgreich")
            else:
                redis_status = "ping_failed"
                log_step("Diagnose", "WARNING", "Redis-Ping fehlgeschlagen")
        except Exception as e:
            redis_status = f"error: {str(e)}"
            log_step("Diagnose", "ERROR", f"Redis-Verbindungsfehler: {str(e)}")
        
        return jsonify({
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "system": system_info,
            "container": container_info,
            "redis_status": redis_status
        }), 200
    
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