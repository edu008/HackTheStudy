"""
Konfigurationsmodul für den Worker.

Dieses Modul stellt zentrale Konfigurationsfunktionen bereit.
"""
from .config import config  # Import der Konfiguration

# Konstanten für die Verwendung in anderen Modulen
LOG_LEVEL = config.logging_level
API_URL = config.api_url
REDIS_URL = config.redis_url
DATABASE_URI = config.database_url

__all__ = ['config', 'LOG_LEVEL', 'API_URL', 'REDIS_URL', 'DATABASE_URI'] 