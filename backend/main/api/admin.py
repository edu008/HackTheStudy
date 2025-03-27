"""
Administrationsmodul für den API-Container.
Diese Datei dient als Wrapper für die modulare Administrationsstruktur
unter api/admin/*.py und wird nur für Abwärtskompatibilität beibehalten.
"""

from .admin import admin_bp, admin_required
from .admin.routes import register_routes

# Registriere alle Routen
register_routes()

# Re-exportiere für Abwärtskompatibilität
__all__ = [
    'admin_bp',
    'admin_required'
] 