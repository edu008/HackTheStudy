"""
Questions-Modul für das Backend (Refaktoriert)
------------------------------------

Enthält den Blueprint und exportiert notwendige Komponenten
für das Abrufen und Verwalten von Questions.
Generierungs-Funktionen wurden entfernt.
"""

from flask import Blueprint

# Entferne Imports für Generierungs-Controller
# from .controllers import (
#    process_generate_more_questions,
#    process_generate_questions)

# Entferne Imports für Generierungs-Funktionen
# from .generation import generate_questions, generate_more_questions

# Behalte andere notwendige Imports
from .models import get_questions, save_question
# Keine Routen mehr in routes.py
# from .routes import *
from .schemas import QuestionRequestSchema # Wird das noch gebraucht?
from .utils import format_questions
from .validation import (sanitize_question, validate_generated_questions,
                         validate_question_data)

# Erstelle den Blueprint für das Questions-Modul
questions_bp = Blueprint('questions', __name__)

# Routen werden jetzt in api/__init__.py registriert (falls dieser BP genutzt wird)

# Exportiere wichtige Komponenten (bereinigt)
__all__ = [
    'questions_bp',
    # Keine Generierungs-Funktionen mehr exportieren
    # 'generate_questions',
    # 'generate_more_questions',
    # Keine Generierungs-Controller mehr exportieren
    # 'process_generate_questions',
    # 'process_generate_more_questions',
    'get_questions', # Wird das extern genutzt?
    'save_question', # Wird das extern genutzt?
    'QuestionRequestSchema',
    'validate_question_data',
    # 'validate_generated_questions',
    'sanitize_question',
    'format_questions'
]
