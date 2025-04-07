"""
Topics-Modul für das Backend (Refaktoriert)
-------------------

Enthält den Blueprint und exportiert notwendige Komponenten
für das Abrufen von Topics und Concept Map Vorschlägen.
Generierungs-, Speicher- und Formatierungs-Funktionen wurden entfernt oder sind intern.
"""

from flask import Blueprint

# Entferne Imports für Generierungs-Funktionen
# from .generation import generate_topics, generate_related_topics

# Behalte notwendige Imports
# Entferne Import von save_topic, da dies im Worker geschieht
from .models import get_topic_hierarchy #, save_topic
# Entferne Import von routes, da dort keine Routen mehr definiert sind
# from .routes import *
# Entferne Import von format_topics, da nicht mehr direkt exportiert/benötigt
# from .utils import format_topics
from .concept_map import generate_concept_map_suggestions

# Erstelle den Blueprint für das Topics-Modul
topics_bp = Blueprint('topics', __name__)

# Routen werden jetzt in api/__init__.py registriert

# Exportiere wichtige Komponenten (bereinigt)
__all__ = [
    'topics_bp',
    # Keine Generierungs-Funktionen mehr exportieren
    # 'generate_topics',
    # 'generate_related_topics',
    'get_topic_hierarchy',
    # Kein save_topic mehr exportieren
    # 'save_topic',
    # Kein format_topics mehr exportieren
    # 'format_topics',
    'generate_concept_map_suggestions'
]
