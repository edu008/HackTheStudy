"""
Flashcards-Modul für das Backend (Refaktoriert)
------------------------------

Enthält den Blueprint und exportiert notwendige Komponenten
für das Abrufen und Verwalten von Flashcards.
Generierungs-Funktionen wurden entfernt.
"""

from flask import Blueprint

# Entferne Imports für Generierungs-Controller
# from .controllers import (process_generate_flashcards,
#                          process_generate_more_flashcards)
# Behalte Imports für verbleibende Controller (falls benötigt und hier importiert)
# Beispiel: from .controllers import process_get_flashcards

# Entferne Imports für Generierungs-Funktionen
# from .generation import generate_additional_flashcards, generate_flashcards

# Behalte andere notwendige Imports
from .models import get_flashcards, save_flashcard
# Importiere Routes, wenn sie hier initialisiert werden (aktuell nicht der Fall)
# from .routes import *
from .schemas import FlashcardRequestSchema # Wird das noch gebraucht?
from .utils import detect_language_wrapper, format_flashcards
from .validation import (sanitize_flashcard, sanitize_flashcard_back,
                         sanitize_flashcard_front, validate_flashcard_data)
                         # validate_generated_flashcards entfernt

# Erstelle den Blueprint für das Flashcards-Modul
flashcards_bp = Blueprint('flashcards', __name__)

# Routen werden jetzt in api/__init__.py registriert

# Exportiere wichtige Komponenten (bereinigt)
__all__ = [
    'flashcards_bp',
    # Keine Generierungs-Funktionen mehr exportieren
    # 'generate_flashcards',
    # 'generate_additional_flashcards',
    # Keine Generierungs-Controller mehr exportieren
    # 'process_generate_flashcards',
    # 'process_generate_more_flashcards',
    'get_flashcards',
    'save_flashcard', # Wird save_flashcard noch extern genutzt?
    'FlashcardRequestSchema',
    'validate_flashcard_data',
    # 'validate_generated_flashcards',
    'sanitize_flashcard',
    'sanitize_flashcard_front',
    'sanitize_flashcard_back',
    'format_flashcards',
    'detect_language_wrapper' # Wird das noch extern genutzt?
]
