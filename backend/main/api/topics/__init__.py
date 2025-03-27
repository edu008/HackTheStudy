"""
Topics-Modul für das Backend
--------------------------

Dieses Modul bietet eine modularisierte Struktur für die Verwaltung von Themen und Concept Maps:

- routes: API-Endpunkte für Themen-Operationen
- concept_map: Funktionen für die Generierung von Concept Maps
- generation: Funktionen für die Generierung von Topics
- models: Datenbankoperationen für Topics-Objekte
- utils: Hilfsfunktionen für das Topics-Modul
"""

from flask import Blueprint

from .concept_map import generate_concept_map_suggestions
from .generation import generate_topics
from .models import create_connection, create_topic, get_topic_hierarchy
from .routes import *
from .utils import process_topic_response

# Erstelle den Blueprint für das Topics-Modul
topics_bp = Blueprint('topics', __name__)

# Importiere die Routen, um sie zu registrieren

# Exportiere wichtige Komponenten

__all__ = [
    'topics_bp',
    'generate_concept_map_suggestions',
    'generate_topics',
    'get_topic_hierarchy',
    'create_topic',
    'create_connection',
    'process_topic_response'
]
