"""
Authentifizierungsmodul für den API-Container.
Diese Datei dient als Wrapper für die modulare Authentifizierungsstruktur
unter api/auth/*.py und wird nur für Abwärtskompatibilität beibehalten.
"""

from .auth import auth_bp, setup_oauth, token_required, validate_provider, get_user_info
from .auth.routes import register_routes

# Registriere alle Routen
register_routes()

# Re-exportiere für Abwärtskompatibilität
__all__ = [
    'auth_bp',
    'setup_oauth',
    'token_required',
    'validate_provider',
    'get_user_info'
]