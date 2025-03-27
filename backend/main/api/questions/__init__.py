"""
Fragen-Modul für das Backend
-------------------------

Dieses Modul bietet eine modularisierte Struktur für die Verwaltung von Testfragen:

- routes: API-Endpunkte für Fragen-Operationen
- controllers: Geschäftslogik für Anfragenverarbeitung
- generation: Funktionen für die Generierung von Fragen
- models: Datenbankoperationen für Fragen-Objekte
- schemas: Validierungsschemas für Fragenformate
- validation: Validierungslogik und Bereinigung von Fragen
- utils: Hilfsfunktionen für das Fragen-Modul
"""

from flask import Blueprint

# Erstelle den Blueprint für das Questions-Modul
questions_bp = Blueprint('questions', __name__)

# Importiere die Routen, um sie zu registrieren
from .routes import *

# Exportiere wichtige Komponenten
from .generation import generate_questions, generate_additional_questions, generate_fallback_questions
from .controllers import process_generate_questions, process_generate_more_questions
from .models import get_questions, save_question
from .schemas import QuestionRequestSchema
from .validation import (
    validate_question_data, 
    validate_generated_questions,
    sanitize_question, 
    sanitize_question_text, 
    sanitize_question_options
)
from .utils import format_questions, detect_language_wrapper

__all__ = [
    'questions_bp',
    'generate_questions',
    'generate_additional_questions',
    'generate_fallback_questions',
    'process_generate_questions',
    'process_generate_more_questions',
    'get_questions',
    'save_question',
    'QuestionRequestSchema',
    'validate_question_data',
    'validate_generated_questions',
    'sanitize_question',
    'sanitize_question_text',
    'sanitize_question_options',
    'format_questions',
    'detect_language_wrapper'
]