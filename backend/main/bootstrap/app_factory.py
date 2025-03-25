"""
App-Factory für die Flask-Anwendung.
Erstellt und konfiguriert die Flask-App.
"""

import os
import logging
from typing import Optional
from flask import Flask, request, jsonify
from datetime import datetime

from core.models import db
from config.env_handler import load_env, setup_cors_origins
from health.monitor import start_health_monitoring
from health.server import setup_health_server
from resource_manager.fd_monitor import check_and_set_fd_limits, monitor_file_descriptors
from resource_manager.limits import set_memory_limit
from utils.logging_utils import log_step

# Logger konfigurieren
logger = logging.getLogger(__name__)

def create_app(environment: Optional[str] = None) -> Flask:
    """
    Erstellt und konfiguriert die Flask-App.
    
    Args:
        environment: Umgebung (development, production, testing)
        
    Returns:
        Konfigurierte Flask-App
    """
    # Umgebungsvariable direkt setzen, falls angegeben
    if environment:
        os.environ['ENVIRONMENT'] = environment
    else:
        os.environ['ENVIRONMENT'] = os.environ.get('ENVIRONMENT', 'production')
    
    # App-Objekt erstellen
    app = Flask(__name__)
    
    # Wenn wir hinter einem Proxy laufen (z.B. nginx), die richtigen Header einstellen
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # Konfiguration laden
    load_env(app)
    
    # Flask-Konfiguration für SQLAlchemy setzen
    if 'DATABASE_URL' in os.environ and os.environ['DATABASE_URL']:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        logger.info("Datenbank-Konfiguration aus DATABASE_URL übernommen")
    else:
        logger.error("DATABASE_URL nicht gefunden in Umgebungsvariablen")
    
    # Ressourcen konfigurieren
    _configure_resources(app)
    
    # Datenbankverbindung initialisieren
    _init_database(app)
    
    # Redis-Verbindung prüfen
    _check_redis_connection()
    
    # Blueprints registrieren
    _register_blueprints(app)
    
    # CORS einrichten
    _setup_cors(app)
    
    # Health-Monitoring starten
    _setup_health_monitoring(app)
    
    # Metrics einrichten (falls aktiviert)
    _setup_metrics(app)
    
    # Basis-Routen registrieren
    _register_base_routes(app)
    
    logger.info(f"App initialisiert im {os.environ['ENVIRONMENT']}-Modus")
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
        CORS(app, resources={r"/api/*": {"origins": origins}})
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