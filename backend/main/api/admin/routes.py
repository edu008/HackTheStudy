"""
Routenregistrierung für das Admin-Modul.
Definiert die HTTP-Endpunkte für die Administrationsfunktionen.
"""

import logging

from . import admin_bp, admin_required
from .cache import clear_cache, get_cache_stats
from .debugging import (get_openai_errors, get_system_logs, test_openai_api,
                        toggle_openai_debug)
from .token_usage import get_token_stats, get_top_users

# Logger konfigurieren
logger = logging.getLogger(__name__)


def register_routes():
    """Registriert alle Routen für das Admin-Modul."""

    # Cache-Verwaltungsrouten
    admin_bp.add_url_rule('/cache-stats', view_func=get_cache_stats, methods=['GET'])
    admin_bp.add_url_rule('/clear-cache', view_func=clear_cache, methods=['POST'])

    # Token-Nutzungsrouten
    admin_bp.add_url_rule('/token-stats', view_func=get_token_stats, methods=['GET'])
    admin_bp.add_url_rule('/top-users', view_func=get_top_users, methods=['GET'])

    # Debugging-Routen
    admin_bp.add_url_rule('/debug/openai', view_func=toggle_openai_debug, methods=['POST'])
    admin_bp.add_url_rule('/debug/openai-test', view_func=test_openai_api, methods=['POST'])
    admin_bp.add_url_rule('/debug/openai-errors', view_func=get_openai_errors, methods=['GET'])
    admin_bp.add_url_rule('/debug/system-logs', view_func=get_system_logs, methods=['GET'])

    # Hinzufügen weiterer dekorativen Funktionen
    # Hier kann auth.admin_required auf alle Routen angewendet werden,
    # wurde aber aus Gründen der Klarheit direkt in den jeweiligen Funktionen implementiert

    logger.info("Admin-Routen erfolgreich registriert")

    return "Admin routes registered"
