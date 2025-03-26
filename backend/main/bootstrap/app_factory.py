"""
App-Factory für die Flask-Anwendung.
Erstellt und konfiguriert die Flask-App.
"""

import os
import logging
from typing import Optional
from flask import Flask, request, jsonify
from datetime import datetime
import uuid
import time
from flask import g
from flask_cors import CORS
from redis import Redis
from fakeredis import FakeRedis

from core.models import db
from config.env_handler import load_env, setup_cors_origins
from health.monitor import start_health_monitoring
from health.server import setup_health_server
from resource_manager.fd_monitor import check_and_set_fd_limits, monitor_file_descriptors
from resource_manager.limits import set_memory_limit
from utils.logging_utils import log_step

# Logger konfigurieren
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    """Erstellt und konfiguriert die Flask-Anwendung."""
    app = Flask(__name__)
    
    # Konfiguration laden
    app.config.from_object(config[config_name])
    
    # CORS konfigurieren
    origins = os.getenv('CORS_ORIGINS', '').split(',')
    origins = [origin.strip() for origin in origins if origin.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}})
    
    # Datenbank initialisieren
    db.init_app(app)
    
    # Redis-URL korrigieren
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    if redis_url.startswith('redis://http://'):
        redis_url = redis_url.replace('redis://http://', 'redis://')
    if redis_url.startswith('redis://https://'):
        redis_url = redis_url.replace('redis://https://', 'redis://')
    
    # Redis-Client initialisieren
    try:
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()  # Teste die Verbindung
        app.logger.info(f"Redis-Verbindung erfolgreich hergestellt: {redis_url}")
    except Exception as e:
        app.logger.error(f"Redis-Verbindungsfehler: {str(e)}")
        app.logger.error(f"Redis-URL: {redis_url}")
        # Verwende FakeRedis als Fallback
        redis_client = FakeRedis(decode_responses=True)
        app.logger.warning("Verwende FakeRedis als Fallback")
    
    # Redis-Client im App-Kontext speichern
    app.redis = redis_client
    
    # API-Blueprints registrieren
    from api import api_bp, api_v1_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(api_v1_bp, url_prefix='/api/v1')
    
    # Health-Monitoring starten
    from health.monitor import start_health_monitor
    start_health_monitor(app)
    
    app.logger.info("App initialisiert im %s-Modus", config_name)
    return app

def _configure_resources(app: Flask):
    """Konfiguriert Systemressourcen."""
    # Datei-Deskriptor-Limits prüfen und anpassen
    check_and_set_fd_limits()
    
    # Datei-Deskriptoren überwachen
    monitor_file_descriptors()
    
    # Speicherlimit setzen (nur in Produktionsumgebung)
    if os.environ.get('ENVIRONMENT') == 'production':
        memory_limit_mb = int(os.environ.get('MEMORY_LIMIT_MB', '2048'))
        set_memory_limit(memory_limit_mb)

def _init_database(app: Flask):
    """Initialisiert die Datenbankverbindung."""
    db.init_app(app)
    
    # Datenbank-Tabellen erstellen, falls sie nicht existieren
    with app.app_context():
        try:
            from core.db_init import init_db
            init_db()
        except Exception as e:
            logger.error(f"Fehler bei der Datenbank-Initialisierung: {str(e)}")

def _check_redis_connection():
    """Prüft die Redis-Verbindung."""
    try:
        # Verzögerter Import, um zirkuläre Importe zu vermeiden
        import redis as redis_direct
        
        # Redis-Verbindung aus Umgebungsvariablen herstellen
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        redis_client = redis_direct.from_url(redis_url)
        redis_client.ping()
        logger.info("Redis-Verbindung erfolgreich hergestellt")
    except ImportError:
        logger.error("Redis-Paket nicht installiert")
    except Exception as e:
        # Prüfen, ob wir Redis-Fehler ignorieren sollen
        if os.environ.get('IGNORE_REDIS_ERRORS', 'false').lower() == 'true':
            logger.warning(f"Redis-Verbindungsfehler ignoriert (wegen IGNORE_REDIS_ERRORS=true): {str(e)}")
        else:
            logger.error(f"Fehler bei der Redis-Verbindung: {str(e)}")
            # In Entwicklungsumgebung Fehler nicht weiterwerfen
            if os.environ.get('ENVIRONMENT', 'production').lower() != 'development':
                raise

def _register_blueprints(app: Flask):
    """Registriert die API-Blueprints."""
    try:
        from api import api_bp
        app.register_blueprint(api_bp, url_prefix='/api')
        logger.info("API-Blueprints erfolgreich registriert")
    except Exception as e:
        logger.error(f"Fehler beim Registrieren der Blueprints: {str(e)}")

def _setup_cors(app: Flask):
    """Richtet CORS für die App ein."""
    try:
        from flask_cors import CORS
        origins = setup_cors_origins()
        CORS(app, resources={
            r"/*": {
                "origins": origins,
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
                "supports_credentials": True
            }
        })
        logger.info(f"CORS für Origins {origins} konfiguriert")
    except Exception as e:
        logger.error(f"Fehler beim Einrichten von CORS: {str(e)}")

def _setup_health_monitoring(app: Flask):
    """Startet das Health-Monitoring."""
    try:
        # Health-Monitoring für die API starten
        start_health_monitoring(app)
        
        # Health-Check-Server starten (falls aktiviert)
        if os.environ.get('ENABLE_HEALTH_SERVER', 'false').lower() == 'true':
            port = int(os.environ.get('HEALTH_SERVER_PORT', '8080'))
            setup_health_server(port)
            logger.info(f"Health-Check-Server auf Port {port} gestartet")
    except Exception as e:
        logger.error(f"Fehler beim Starten des Health-Monitorings: {str(e)}")

def _setup_metrics(app: Flask):
    """Richtet Prometheus-Metrics ein."""
    try:
        if os.environ.get('ENABLE_METRICS', 'false').lower() == 'true':
            from prometheus_flask_exporter import PrometheusMetrics
            metrics = PrometheusMetrics(app)
            logger.info("Prometheus-Metrics erfolgreich konfiguriert")
    except ImportError:
        logger.warning("prometheus_flask_exporter nicht installiert, keine Metrics verfügbar")
    except Exception as e:
        logger.error(f"Fehler beim Einrichten der Metrics: {str(e)}")

def _register_base_routes(app: Flask):
    """Registriert grundlegende Routen."""
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
    
    # Ping-Endpunkt für einfache Verfügbarkeitsprüfung
    @app.route('/ping', methods=['GET'])
    def ping():
        """
        Ein einfacher Ping-Endpunkt zur Verfügbarkeitsprüfung.
        Dieser Endpunkt wird von DigitalOcean für Health Checks verwendet.
        """
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        test_message = f"PING-TEST von {client_ip} - ZEIT: {datetime.now().isoformat()}"
        
        # Direkte Print-Anweisungen für Debugging
        print("DIREKT-PRINT:", test_message, flush=True)
        
        # Standard Python-Logging auf allen Ebenen
        logging.debug("DEBUG-PYTHON: " + test_message)
        logging.info("INFO-PYTHON: " + test_message)
        logging.warning("WARNING-PYTHON: " + test_message)
        logging.error("ERROR-PYTHON: " + test_message)
        logging.critical("CRITICAL-PYTHON: " + test_message)
        
        # Flask App-Logger
        app.logger.debug("DEBUG-FLASK: " + test_message)
        app.logger.info("INFO-FLASK: " + test_message)
        app.logger.warning("WARNING-FLASK: " + test_message)
        app.logger.error("ERROR-FLASK: " + test_message)
        
        # Eigene Logging-Funktion
        log_step("Ping-Test", "DEBUG", test_message)
        log_step("Ping-Test", "INFO", test_message)
        log_step("Ping-Test", "WARNING", test_message)
        log_step("Ping-Test", "ERROR", test_message)
        
        return "pong", 200
    
    # Logging-Test-Endpunkt
    @app.route('/log-test', methods=['GET'])
    def log_test():
        """
        Test-Endpunkt für Logging, der alle Log-Level verwendet.
        Hilfreich zur Überprüfung, ob Logs korrekt erfasst werden.
        """
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        test_message = f"LOG-TEST von {client_ip} - ZEIT: {datetime.now().isoformat()}"
        
        # Direkte Print-Anweisungen
        print("DIREKT-PRINT:", test_message, flush=True)
        
        # Standard Python-Logging
        logging.debug("DEBUG-PYTHON: " + test_message)
        logging.info("INFO-PYTHON: " + test_message)
        logging.warning("WARNING-PYTHON: " + test_message)
        logging.error("ERROR-PYTHON: " + test_message)
        
        # Flask App-Logger
        app.logger.debug("DEBUG-FLASK: " + test_message)
        app.logger.info("INFO-FLASK: " + test_message)
        app.logger.warning("WARNING-FLASK: " + test_message)
        app.logger.error("ERROR-FLASK: " + test_message)
        
        # Eigene Logging-Funktion
        log_step("Log-Test", "DEBUG", test_message)
        log_step("Log-Test", "INFO", test_message)
        log_step("Log-Test", "WARNING", test_message)
        log_step("Log-Test", "ERROR", test_message)
        
        return jsonify({
            "success": True, 
            "message": "Logging-Test durchgeführt",
            "log_message": test_message
        })
    
    # Einfacher Health-Check für Load Balancer
    @app.route('/api/v1/simple-health', methods=['GET'])
    def simple_health_check():
        """
        Ein extrem einfacher Health-Check-Endpunkt für DigitalOcean App Platform,
        der keine Abhängigkeiten wie Datenbank oder Redis prüft.
        """
        log_step("Simple-Health", "SUCCESS", f"Anfrage von {request.remote_addr}")
        
        return jsonify({
            "status": "healthy",
            "message": "Einfacher Health Check - keine DB-Prüfung",
            "timestamp": datetime.now().isoformat(),
            "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
            "version": "1.0.0",
            "environment": os.environ.get('ENVIRONMENT', 'production')
        }), 200
    
    # Dupliziere den Health-Check unter standardisiertem Pfad
    @app.route('/health', methods=['GET'])
    def root_health_check():
        """
        Haupt-Health-Check-Endpunkt unter einheitlichem Pfad.
        Sollte in allen Umgebungen gleich sein.
        """
        log_step("Root-Health", "SUCCESS", f"Anfrage von {request.remote_addr}")
        
        return jsonify({
            "status": "healthy",
            "message": "API-Service ist aktiv",
            "timestamp": datetime.now().isoformat(),
            "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
            "version": "1.0.0",
            "environment": os.environ.get('ENVIRONMENT', 'production')
        }), 200
    
    # Error Handler für häufige HTTP-Fehler
    @app.errorhandler(404)
    def not_found(e):
        log_step("API-Error", "WARNING", f"404 Not Found: {request.path}")
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Die angefragte Resource '{request.path}' wurde nicht gefunden"
            }
        }), 404
    
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
    
    @app.errorhandler(500)
    def server_error(e):
        log_step("API-Error", "ERROR", f"500 Server Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": {
                "code": "SERVER_ERROR",
                "message": "Ein interner Serverfehler ist aufgetreten"
            }
        }), 500

def _setup_request_handlers(app: Flask):
    """Richtet globale Request-Handler für die App ein."""
    @app.before_request
    def log_request_info():
        """Loggt Details zu eingehenden Anfragen."""
        # Log ALLE Anfragen, auch statische Inhalte und /ping
        request_id = str(uuid.uuid4())
        g.request_id = request_id
        
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'Unbekannt')
        
        log_message = f"➡️ EINGEHEND [{request_id}]: {request.method} {request.path} von {client_ip}"
        logger.info(log_message)
        
        # Ausführlicheres Logging aller Anfragen
        params = dict(request.args)
        headers = {k: v for k, v in request.headers.items()}
        
        detail_message = (f"Request-Details [{request_id}]: "
                         f"Path={request.path}, "
                         f"Method={request.method}, "
                         f"Client={client_ip}, "
                         f"UA={user_agent}, "
                         f"Params={params}, "
                         f"Headers={headers}")
        logger.debug(detail_message)
    
    @app.after_request
    def log_response_info(response):
        """Loggt Details zu ausgehenden Antworten."""
        # Alle Antworten loggen, unabhängig vom Endpunkt
        request_id = getattr(g, 'request_id', 'keine-id')
        duration = getattr(g, 'request_duration', 0)
        
        # Alle Antworten loggen, unabhängig vom Status-Code
        status_emoji = "✅" if response.status_code < 400 else "❌"
        log_message = f"{status_emoji} AUSGEHEND [{request_id}]: {response.status_code} für {request.method} {request.path} in {duration:.2f}ms"
        
        # Antwort-Größe berechnen
        response_size = len(response.get_data())
        
        # Je nach Status-Code das richtige Log-Level verwenden
        if response.status_code >= 500:
            logger.error(log_message + f" (Size: {response_size} bytes)")
        elif response.status_code >= 400:
            logger.warning(log_message + f" (Size: {response_size} bytes)")
        else:
            logger.info(log_message + f" (Size: {response_size} bytes)")
        
        return response
    
    @app.before_request
    def start_timer():
        """Startet einen Timer für die Request-Dauer."""
        g.start_time = time.time()
    
    @app.after_request
    def calculate_duration(response):
        """Berechnet die Dauer der Request-Verarbeitung."""
        if hasattr(g, 'start_time'):
            duration = (time.time() - g.start_time) * 1000  # in Millisekunden
            g.request_duration = duration
        return response 