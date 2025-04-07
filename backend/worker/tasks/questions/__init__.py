"""
Questions-Modul für die Generierung von Multiple-Choice-Fragen.
"""
import logging

logger = logging.getLogger(__name__)

# Exportiere die Hauptfunktion für den Import von außen
from .generation import generate_questions_with_openai

__all__ = ['generate_questions_with_openai'] 