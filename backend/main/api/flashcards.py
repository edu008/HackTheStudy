"""
Wrapper-Modul für das Flashcards-Paket
-------------------------------------

HINWEIS: Diese Datei dient nur der Abwärtskompatibilität.
Neue Entwicklungen sollten direkt das Paket api.flashcards.*
verwenden.

Dieses Modul importiert und re-exportiert alle öffentlichen
Komponenten des flashcards-Pakets, um bestehenden Code, der diese Datei
importiert, weiterhin funktionsfähig zu halten.
"""

# Importiere den Namespace als Ganzes für bessere Modularität
from .flashcards import (
    routes,
    controllers,
    generation,
    models,
    schemas,
    study,
    utils,
    validation
)

# Importiere Blueprint explizit für Kompatibilität
try:
    flashcards_bp = routes.flashcards_bp
except AttributeError:
    flashcards_bp = None
    import logging
    logging.getLogger(__name__).error("Konnte flashcards_bp nicht importieren")

# Stelle sicher, dass alles exportiert wird, was vorher verfügbar war
__all__ = [
    'flashcards_bp',
    'routes',
    'controllers',
    'generation',
    'models',
    'schemas',
    'study',
    'utils',
    'validation'
]
