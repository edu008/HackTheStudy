"""
Authentifizierungsmodul für den API-Container.
Diese Datei dient als Wrapper für die modulare Authentifizierungsstruktur
unter api/auth/*.py und wird nur für Abwärtskompatibilität beibehalten.
"""

# Direkter Import aus den spezifischen Modulen
from .auth.routes import auth_bp, register_routes
from .auth.oauth_providers import get_user_info, validate_provider
from .auth.controllers import handle_oauth_callback
from .auth.token_auth import token_required

# Registriere alle Routen
register_routes()

# Re-exportiere für Abwärtskompatibilität
__all__ = [
    'auth_bp',
    'handle_oauth_callback',
    'token_required',
    'validate_provider',
    'get_user_info'
]
