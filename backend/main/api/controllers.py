"""
Controller-Datei für die Integration aller API-Module.
Importiert alle API-Komponenten und initialisiert sie.
"""

import logging

from flask import current_app

# Logger konfigurieren
logger = logging.getLogger(__name__)


def register_blueprints(app):
    """
    Registriert alle Blueprints für die API.

    Args:
        app: Die Flask-Anwendung
    """
    from .admin import admin_bp
    from .auth import auth_bp
    from .finance import finance_bp

    # Register blueprints
    logger.info("Registriere API-Blueprints...")
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(finance_bp, url_prefix='/api/finance')

    logger.info("API-Blueprints erfolgreich registriert.")

    return app
