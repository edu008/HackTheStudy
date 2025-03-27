"""
Wrapper-Modul für das Questions-Paket
-------------------------------------

HINWEIS: Diese Datei dient nur der Abwärtskompatibilität.
Neue Entwicklungen sollten direkt das Paket api.questions.*
verwenden.

Dieses Modul importiert und re-exportiert alle öffentlichen
Komponenten des questions-Pakets, um bestehenden Code, der diese Datei
importiert, weiterhin funktionsfähig zu halten.
"""

# Importiere den Namespace als Ganzes für bessere Modularität
from .questions import (
    routes,
    controllers,
    generation,
    models,
    schemas,
    utils,
    validation
)

# Importiere Blueprint explizit für Kompatibilität
try:
    questions_bp = routes.questions_bp
except AttributeError:
    questions_bp = None
    import logging
    logging.getLogger(__name__).error("Konnte questions_bp nicht importieren")

# Stelle sicher, dass alles exportiert wird, was vorher verfügbar war
__all__ = [
    'questions_bp',
    'routes',
    'controllers',
    'generation',
    'models',
    'schemas',
    'utils',
    'validation'
]
