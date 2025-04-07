"""
App-Factory für die Flask-Anwendung.
Erstellt und konfiguriert die Flask-App.
"""

import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Optional

from config.config import config
from core.models import db, init_db
from core.redis_client import get_redis_client, redis_client
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from bootstrap.extensions import cache, cors, jwt, migrate

# Logger konfigurieren
logger = logging.getLogger(__name__)


def create_app(config_name='default'):
    """Erstellt und konfiguriert die Flask-Anwendung."""
    app = Flask(__name__)

    # Konfiguration laden
    app.config.from_object(config.flask_config)

    # WICHTIG: Stelle sicher, dass SQLALCHEMY_DATABASE_URI in der app.config gesetzt ist
    if 'SQLALCHEMY_DATABASE_URI' in os.environ:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['SQLALCHEMY_DATABASE_URI']
        logger.info(f"SQLALCHEMY_DATABASE_URI aus Umgebungsvariablen gesetzt: {app.config['SQLALCHEMY_DATABASE_URI'][:20]}...")
    elif 'DATABASE_URL' in os.environ:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
        logger.info(f"SQLALCHEMY_DATABASE_URI aus DATABASE_URL gesetzt: {app.config['SQLALCHEMY_DATABASE_URI'][:20]}...")
    else:
        # Fallback zu SQLite-Datenbank
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
        logger.warning("Weder SQLALCHEMY_DATABASE_URI noch DATABASE_URL gefunden. Fallback zu SQLite: sqlite:///app.db")

    # WICHTIG: Stelle sicher, dass JWT_SECRET_KEY gesetzt ist
    if 'JWT_SECRET_KEY' not in app.config or not app.config['JWT_SECRET_KEY']:
        jwt_secret = os.environ.get('JWT_SECRET_KEY', os.environ.get('JWT_SECRET'))
        if jwt_secret:
            app.config['JWT_SECRET_KEY'] = jwt_secret
            logger.info("JWT_SECRET_KEY aus Umgebungsvariablen gesetzt")
        else:
            # Fallback zu einem sicheren Wert
            app.config['JWT_SECRET_KEY'] = os.urandom(24).hex()
            logger.warning("JWT_SECRET_KEY nicht gefunden, generiere zufälligen Schlüssel")
    
    # Stelle auch sicher, dass SECRET_KEY gesetzt ist (als Fallback für JWT)
    if 'SECRET_KEY' not in app.config or not app.config['SECRET_KEY']:
        app.config['SECRET_KEY'] = app.config['JWT_SECRET_KEY']
        logger.info("Flask SECRET_KEY auf JWT_SECRET_KEY gesetzt")

    # Weitere SQLAlchemy-Konfigurationen
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_timeout': 30,
        'max_overflow': 15
    }

    # CORS konfigurieren
    origins = os.environ.get('CORS_ORIGINS', 'https://www.hackthestudy.ch,https://hackthestudy.ch,http://www.hackthestudy.ch,http://hackthestudy.ch,http://localhost:8080,http://localhost:3000,http://127.0.0.1:8080,http://127.0.0.1:3000')
    origins_list = origins.split(',')
    app.config['ALLOWED_ORIGINS'] = origins_list
    app.logger.info(f"CORS erlaubte Origins: {origins_list}")
    
    # CORS-Konfiguration für die gesamte App
    cors_resources = {
        r"/*": {
            "origins": origins_list,
            "allow_headers": ["Content-Type", "Authorization", "Cache-Control", "Pragma", "Expires"],
            "expose_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    }
    
    try:
        cors.init_app(app, resources=cors_resources, supports_credentials=True, allow_credentials=True)
        app.logger.info("✅ CORS konfiguriert mit spezifischen Origins und Credentials-Support")
    except Exception as e:
        app.logger.error(f"❌ Fehler bei der CORS-Konfiguration: {str(e)}")
        # Trotzdem fortsetzen - CORS-Fehler sind nicht fatal

    # Datenbank initialisieren
    db.init_app(app)
    
    # Datenbanktabellen erstellen oder aktualisieren
    with app.app_context():
        logger.info("Führe Datenbank-Initialisierung aus...")
        init_db(app)
        logger.info("Datenbank-Initialisierung abgeschlossen")
        
        # SQLAlchemy Event-Listener hier innerhalb des app_context registrieren
        from sqlalchemy import event
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    # Redis-URL aus der Zentralen Konfiguration nehmen
    redis_url = config.redis_url
    app.logger.info("Main-Backend verwendet Redis: %s", redis_url)

    # Flask-Erweiterungen initialisieren
    migrate.init_app(app, db)
    cache.init_app(app, config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': redis_url})
    jwt.init_app(app)
    app.logger.info("✅ JWT-Manager für JWT-Token-Verarbeitung initialisiert")

    # Redis-Client initialisieren
    try:
        app.logger.info("Versuche Redis-Verbindung zu: %s", redis_url)
        # Verwende die zentrale RedisClient-Implementierung
        redis_instance = get_redis_client()
        redis_instance.ping()  # Teste die Verbindung
        app.logger.info("✅ Redis-Verbindung erfolgreich hergestellt: %s", redis_url)

        # Speichere Redis-Server-Info für Debugging
        redis_info = redis_instance.info()
        app.logger.info(
            f"Redis-Server-Info: Version={redis_info.get('redis_version', 'unbekannt')}, OS={redis_info.get('os', 'unbekannt')}")

        # Setze einen Test-Schlüssel, um die Verbindung zu validieren
        redis_instance.set('backend_main_test', datetime.now().isoformat())
        app.logger.info(f"Test-Schlüssel in Redis gesetzt: {redis_instance.get('backend_main_test')}")

        # Speichere Referenz auf die Redis-Instanz
        app.redis = redis_instance
    except Exception as e:
        app.logger.error("❌ Redis-Verbindungsfehler: %s", str(e))
        app.logger.error("Redis-URL: %s", redis_url)

        # KEINE FEHLER WERFEN - App muss für Health-Checks starten
        app.logger.warning("⚠️ App startet trotz Redis-Fehler, damit Health-Checks funktionieren")

        # Verwende den Dummy-Redis-Client aus der zentralen Implementierung
        app.redis = get_redis_client()  # Gibt automatisch einen Dummy-Client zurück bei Fehlern
        app.logger.warning("⚠️ Dummy-Redis wird verwendet! Keine echte Funktionalität verfügbar!")

    # API-Blueprints registrieren
    from api import api_bp, api_v1_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(api_v1_bp, url_prefix='/api/v1')

    # OAuth-Konfiguration initialisieren
    try:
        from api import setup_oauth
        setup_oauth(app)
        app.logger.info("✅ OAuth erfolgreich konfiguriert (Google, GitHub)")
    except Exception as e:
        app.logger.error("❌ Fehler bei der OAuth-Konfiguration: %s", str(e))

    # Health-Monitoring wird jetzt direkt in app.py initialisiert
    # Das vereinfacht die Architektur und vermeidet redundante Initialisierungen
    app.logger.info("✅ Health-Monitoring wird in app.py konfiguriert")

    # Kein separater Health-Check-Server mehr - Health-Checks direkt in Flask
    app.logger.info("Health-Checks sind direkt in der Flask-App unter /health, /ping, etc. verfügbar")

    app.logger.info("App initialisiert mit der zentralen Konfiguration")
    return app
