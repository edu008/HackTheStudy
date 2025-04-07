"""
Authentifizierungsmodul für den API-Container.
Bietet Funktionen für OAuth, JWT und Benutzeridentifikation.
"""

from flask import Blueprint, current_app
import logging

logger = logging.getLogger(__name__)

# Blueprint erstellen
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Importieren der Module in der richtigen Reihenfolge, nach Blueprint-Definition
from .oauth_providers import get_user_info, setup_oauth, validate_provider, get_authorization_url, get_token, get_oauth_client
from .token_auth import token_required
from .controllers import handle_oauth_callback
from .routes import register_routes as register_auth_sub_routes

# Registriere alle Auth-Routen am Blueprint
register_auth_sub_routes(auth_bp)

# Definiere die Funktion zum Registrieren des auth_bp an einem übergeordneten Blueprint
def register_routes(bp):
    """Registriert den auth_bp am übergeordneten Blueprint."""
    # Setup OAuth (falls benötigt)
    try:
        setup_oauth(current_app)
        logger.info("OAuth erfolgreich für die App konfiguriert.")
    except Exception as e:
        logger.error(f"Fehler bei der OAuth-Konfiguration: {e}")
    
    # Registriere den auth_bp am übergebenen Blueprint `bp`
    bp.register_blueprint(auth_bp)
    logger.info(f"Auth Blueprint ('auth_bp') erfolgreich am Blueprint '{bp.name}' registriert.")

# Exportiere wichtige Komponenten
__all__ = [
    'auth_bp',
    'setup_oauth',
    'token_required',
    'validate_provider',
    'get_user_info',
    'get_authorization_url',
    'get_token',
    'get_oauth_client',
    'handle_oauth_callback',
    'register_routes'
]
