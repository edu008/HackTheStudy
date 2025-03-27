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
import re

from core.models import db
from core.redis_client import redis_client, get_redis_client
from config.config import config

# Logger konfigurieren
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    """Erstellt und konfiguriert die Flask-Anwendung."""
    app = Flask(__name__)
    
    # Konfiguration laden
    app.config.from_object(config.flask_config)
    
    # CORS zentral und vollständig konfigurieren
    # Erlaube alle Origins und füge wichtige Header für Preflight-Requests hinzu
    CORS(app, 
         supports_credentials=True, 
         resources={r"/*": {
             "origins": "*",
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
             "expose_headers": ["Content-Type", "Authorization"],
             "max_age": 86400  # 24 Stunden Cache für Preflight-Requests
         }}
    )
    app.logger.info("✅ CORS für alle Origins (*) konfiguriert mit Preflight-Support")
    
    # Datenbank initialisieren
    db.init_app(app)
    
    # Redis-URL aus der Zentralen Konfiguration nehmen
    redis_url = config.redis_url
    app.logger.info(f"Main-Backend verwendet Redis: {redis_url}")
    
    # Flask-Erweiterungen initialisieren
    from bootstrap.extensions import migrate, cache, jwt, cors
    migrate.init_app(app, db)
    cache.init_app(app, config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': redis_url})
    jwt.init_app(app)
    app.logger.info("✅ JWT-Manager für JWT-Token-Verarbeitung initialisiert")
    
    # Redis-Client initialisieren
    try:
        app.logger.info(f"Versuche Redis-Verbindung zu: {redis_url}")
        # Verwende die zentrale RedisClient-Implementierung
        redis_instance = get_redis_client()
        redis_instance.ping()  # Teste die Verbindung
        app.logger.info(f"✅ Redis-Verbindung erfolgreich hergestellt: {redis_url}")
        
        # Speichere Redis-Server-Info für Debugging
        redis_info = redis_instance.info()
        app.logger.info(f"Redis-Server-Info: Version={redis_info.get('redis_version', 'unbekannt')}, OS={redis_info.get('os', 'unbekannt')}")
        
        # Setze einen Test-Schlüssel, um die Verbindung zu validieren
        redis_instance.set('backend_main_test', datetime.now().isoformat())
        app.logger.info(f"Test-Schlüssel in Redis gesetzt: {redis_instance.get('backend_main_test')}")
        
        # Speichere Referenz auf die Redis-Instanz
        app.redis = redis_instance
    except Exception as e:
        app.logger.error(f"❌ Redis-Verbindungsfehler: {str(e)}")
        app.logger.error(f"Redis-URL: {redis_url}")
        
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
        app.logger.error(f"❌ Fehler bei der OAuth-Konfiguration: {str(e)}")
    
    # Health-Monitoring wird jetzt direkt in app.py initialisiert
    # Das vereinfacht die Architektur und vermeidet redundante Initialisierungen
    app.logger.info(f"✅ Health-Monitoring wird in app.py konfiguriert")
    
    # Kein separater Health-Check-Server mehr - Health-Checks direkt in Flask
    app.logger.info("Health-Checks sind direkt in der Flask-App unter /health, /ping, etc. verfügbar")
    
    app.logger.info("App initialisiert mit der zentralen Konfiguration")
    return app 