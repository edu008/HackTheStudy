"""
Flashcards-Modul für das Backend
------------------------------

Dieses Modul bietet eine modularisierte Struktur für die Verwaltung von Lernkarten:

- routes: API-Endpunkte für Flashcard-Operationen
- controllers: Geschäftslogik für Anfragenverarbeitung
- generation: Funktionen für die Generierung von Flashcards
- models: Datenbankoperationen für Flashcard-Objekte
- schemas: Validierungsschemas für Flashcard-Formate
- validation: Validierungslogik und Bereinigung von Flashcards
- utils: Hilfsfunktionen für das Flashcards-Modul
"""

from flask import Blueprint

from .controllers import (process_generate_flashcards,
                          process_generate_more_flashcards)
from .generation import generate_additional_flashcards, generate_flashcards
from .models import get_flashcards, save_flashcard
from .routes import *
from .schemas import FlashcardRequestSchema
from .utils import detect_language_wrapper, format_flashcards
from .validation import (sanitize_flashcard, sanitize_flashcard_back,
                         sanitize_flashcard_front, validate_flashcard_data,
                         validate_generated_flashcards)

# Erstelle den Blueprint für das Flashcards-Modul
flashcards_bp = Blueprint('flashcards', __name__)

# Importiere die Routen, um sie zu registrieren

# Exportiere wichtige Komponenten

__all__ = [
    'flashcards_bp',
    'generate_flashcards',
    'generate_additional_flashcards',
    'process_generate_flashcards',
    'process_generate_more_flashcards',
    'get_flashcards',
    'save_flashcard',
    'FlashcardRequestSchema',
    'validate_flashcard_data',
    'validate_generated_flashcards',
    'sanitize_flashcard',
    'sanitize_flashcard_front',
    'sanitize_flashcard_back',
    'format_flashcards',
    'detect_language_wrapper'
]
