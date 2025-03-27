"""
App-Factory für den Worker.
"""
import logging

from flask import Flask

logger = logging.getLogger(__name__)


def create_app():
    """
    Erstellt eine einfache Flask-App für den Worker.
    Vereinfachte Version, die nur die nötigen Komponenten enthält.
    """
    app = Flask(__name__)

    # Konfiguration laden
    try:
        from config.config import config
        app.config.from_object(config)
        logger.info("Worker-App mit zentraler Konfiguration initialisiert")
    except ImportError:
        logger.warning("Zentrale Konfiguration nicht verfügbar, verwende Standard-Konfiguration")

    # Flask-Extensions initialisieren (minimale Konfiguration)
    with app.app_context():
        register_extensions(app)

    # Health-Check-Endpunkt
    @app.route('/ping')
    def ping():
        return "pong", 200

    return app


def register_extensions(app):
    """Registriert Flask-Extensions."""
    # Minimale Extensions für Worker
    try:
        from bootstrap.extensions import db
        db.init_app(app)
        logger.info("Datenbank initialisiert")
    except ImportError:
        logger.warning("Datenbank-Extension nicht verfügbar")

    return app
