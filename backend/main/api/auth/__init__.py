"""
Authentifizierungsmodul für den API-Container.
Bietet Funktionen für OAuth, JWT und Benutzeridentifikation.
"""

from flask import Blueprint

# Blueprint erstellen
auth_bp = Blueprint('auth', __name__)

# Importiere alle Submodule
from .oauth_providers import setup_oauth, validate_provider, get_user_info
from .token_auth import token_required
from .controllers import handle_oauth_callback
from .routes import register_routes

# Exportiere wichtige Komponenten
__all__ = [
    'auth_bp',
    'setup_oauth',
    'token_required',
    'validate_provider',
    'get_user_info',
    'handle_oauth_callback',
    'register_routes'
] 