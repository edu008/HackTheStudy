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

# Logger für API-Anfragen
api_request_logger = logging.getLogger('api_requests')

# Optimierte Funktion zum Konfigurieren spezialisierter Logger
def config_specialized_loggers():
    # Diese Funktion ist jetzt Teil von setup_logging()
    pass

# Konfiguriere Logging
logger = setup_logging()

# Explizites Debug-Logging von OpenAI ermöglichen
os.environ['OPENAI_LOG'] = 'debug'

# Lade die Umgebungsvariablen
load_dotenv(override=True, verbose=True)

def force_flush_handlers():
    """Flusht alle Logger-Handler, um sicherzustellen, dass Logs geschrieben werden"""
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()

def log_startup_info():
    """Gibt wichtige Informationen beim Start der Anwendung aus"""
    logger.info("================== HACKTHESTUDY BACKEND STARTET ==================")
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"Python-Version: {sys.version}")
    logger.info(f"Hostname: {socket.gethostname()}")
    logger.info(f"Arbeitsverzechnis: {os.getcwd()}")
    
    logger.info("DIGITAL_OCEAN_APP_PLATFORM: TRUE")
    
    # Umgebungsinformationen (ohne sensible Daten)
    env_vars = [
        'FLASK_ENV', 'FLASK_DEBUG', 'PORT', 'SERVER_SOFTWARE',
        'DIGITAL_OCEAN_APP_NAME', 'DIGITAL_OCEAN_DEPLOYMENT_ID',
        'RUN_MODE'
    ]
    logger.info("Umgebungsvariablen:")
    for var in env_vars:
        if var in os.environ:
            logger.info(f"  - {var}: {os.environ.get(var)}")
    
    # Server-Prozess-Info
    if 'gunicorn' in os.environ.get('SERVER_SOFTWARE', ''):
        logger.info("Server läuft unter Gunicorn")
        worker_id = os.environ.get('GUNICORN_WORKER_ID', 'unbekannt')
        logger.info(f"Gunicorn Worker ID: {worker_id}")
    else:
        logger.info("Server läuft im Flask-Entwicklungsmodus")
    
    # DigitalOcean-spezifische Informationen
    if 'DIGITAL_OCEAN_APP_NAME' in os.environ:
        logger.info(f"DigitalOcean App Platform: {os.environ.get('DIGITAL_OCEAN_APP_NAME')}")
        logger.info(f"WICHTIG: Runtime Logs werden für diesen Service angezeigt")
    
    logger.info("==============================")
    
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
    
    # Worker- oder Payment-Service Modi
    if run_mode in ['worker', 'payment']:
        # Konfiguriere Logging für den Prozess
        logger = setup_logging()
        logger.info(f"Starte im {run_mode.upper()}-Modus...")
        
        # Überprüfe, ob API-Anfragen protokolliert werden sollen
        log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
        if log_api_requests:
            logger.info("API-Anfragen-Protokollierung aktiviert")
        
        # Worker-Modus: Starte Celery-Worker
        if run_mode == 'worker':
            from tasks import start_worker
            start_worker()
            return None  # Worker hat keine Flask-App
        
        # Payment-Service: Starte speziellen Server
        if run_mode == 'payment':
            from services.payment_service import create_payment_app
            return create_payment_app()
    
    # Standard-App-Modus für API und Web-Funktionen
    app = Flask(__name__)
    
    # Konfiguriere Secret Key für Sessions
    secret_key = os.environ.get('FLASK_SECRET_KEY')
    if not secret_key:
        # Generiere einen zufälligen Schlüssel, wenn keiner gesetzt ist
        import secrets
        secret_key = secrets.token_hex(32)
        logger.warning("Kein FLASK_SECRET_KEY in Umgebungsvariablen gefunden. Verwende einen zufällig generierten Schlüssel (gilt nur für diese Sitzung).")
    
    app.secret_key = secret_key
    logger.info("Secret key für Flask-App und Sessions konfiguriert")
    
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
        logger.info("OAuth erfolgreich initialisiert und in Flask-App eingebunden")
    except Exception as e:
        logger.error(f"Fehler bei der OAuth-Konfiguration: {str(e)}")
        logger.error(traceback.format_exc())
    
    # Konfiguriere CORS
    cors_origins = setup_cors_origins()
    logger.info("Finale CORS-Origins: %s", ", ".join(cors_origins))
    
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
    
    # Health-Check-Endpunkt für Digital Ocean
    @app.route('/api/v1/health', methods=['GET'])
    def health_check():
        """
        Einfacher Health-Check-Endpunkt für Digital Ocean App Platform.
        """
        app.logger.info("Health-Check-Anfrage erhalten")
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat()
        }), 200
    
    # Root-Route für API-Status
    @app.route('/', methods=['GET', 'OPTIONS'])
    def api_status():
        """
        Liefert den API-Status und grundlegende Informationen.
        """
        app.logger.info("API-Status-Anfrage erhalten von %s", request.remote_addr)
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
    
    # Globaler Error Handler für 405 Method Not Allowed
    @app.errorhandler(405)
    def method_not_allowed(e):
        app.logger.warning(f"405 Method Not Allowed: {request.method} {request.path}")
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
        app.logger.warning(f"401 Unauthorized: {request.path}")
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
        app.logger.error(f"Unbehandelter Fehler: {str(e)}")
        app.logger.error(traceback.format_exc())
        
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
        
        # Protokollierung der API-Anfragen
        run_mode = os.environ.get('RUN_MODE', 'app')
        log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
        
        if log_api_requests and not request.path.startswith('/static/'):
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
            
            # Logge die API-Anfrage
            api_request_logger.info(f"API-Anfrage: {request.method} {request.path} - Status: {response.status_code} - Daten: {req_data}")
        
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