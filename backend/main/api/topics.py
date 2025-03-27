"""
Topics-Funktionalität für das Backend - WRAPPER
--------------------------------------------

WARNUNG: Diese Datei wird zur Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.topics`.

Diese Datei importiert alle notwendigen Funktionen aus dem neuen modularen Topics-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Logger, der Verwendung der alten API dokumentiert
import logging

# Importiere den Namespace als Ganzes für bessere Modularität
from .topics import concept_map, generation, models, routes, utils

logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei topics.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.topics-Modul."
)

# Importiere Blueprint explizit für Kompatibilität
try:
    topics_bp = routes.topics_bp
except AttributeError:
    topics_bp = None
    logger.error("Konnte topics_bp nicht importieren")

# Exportiere Module für Abwärtskompatibilität
__all__ = [
    'topics_bp',
    'concept_map',
    'generation',
    'models',
    'routes',
    'utils'
]
