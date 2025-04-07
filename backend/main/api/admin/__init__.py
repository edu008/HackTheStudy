"""
Administrationsmodul für den API-Container.
Bietet Funktionen für Systemverwaltung, Debugging und Überwachung.
"""

import logging
import os

from flask import Blueprint

# Blueprint erstellen
admin_bp = Blueprint('admin', __name__)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Import nach Blueprint-Definition, um zirkuläre Importe zu vermeiden
from .auth import admin_required
from .cache import clear_cache, get_cache_stats
from .debugging import get_openai_errors, test_openai_api, toggle_openai_debug
from .token_usage import get_token_stats, get_top_users
from .routes import register_routes

# Exportiere wichtige Komponenten
__all__ = [
    'admin_bp',
    'admin_required',
    'register_routes'
]
