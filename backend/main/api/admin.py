"""
Administrationsmodul für den API-Container.
Diese Datei dient als Wrapper für die modulare Administrationsstruktur
unter api/admin/*.py und wird nur für Abwärtskompatibilität beibehalten.
"""

# Direkter Import aus den spezifischen Modulen
from .admin.auth import admin_required
from .admin.routes import admin_bp, register_routes

# Registriere alle Routen
register_routes()

# Re-exportiere für Abwärtskompatibilität
__all__ = [
    'admin_bp',
    'admin_required'
]
