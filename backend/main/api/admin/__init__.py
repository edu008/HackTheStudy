"""
Administrationsmodul für den API-Container.
Bietet Funktionen für Systemverwaltung, Debugging und Überwachung.
"""

import os
import logging
from flask import Blueprint

# Blueprint erstellen
admin_bp = Blueprint('admin', __name__)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Importiere alle Submodule
from .auth import admin_required
from .cache import get_cache_stats, clear_cache
from .token_usage import get_token_stats, get_top_users
from .debugging import toggle_openai_debug, test_openai_api, get_openai_errors
from .routes import register_routes

# Exportiere wichtige Komponenten
__all__ = [
    'admin_bp',
    'admin_required',
    'register_routes'
] 