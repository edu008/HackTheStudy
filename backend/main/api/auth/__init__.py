"""
Authentifizierungsmodul für den API-Container.
Bietet Funktionen für OAuth, JWT und Benutzeridentifikation.
"""

from flask import Blueprint

from .controllers import handle_oauth_callback
from .oauth_providers import get_user_info, setup_oauth, validate_provider
from .routes import register_routes
from .token_auth import token_required

# Blueprint erstellen
auth_bp = Blueprint('auth', __name__)

# Importiere alle Submodule

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
