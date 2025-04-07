"""
Flashcards-Modul für die Generierung von Lernkarten.
"""
import logging

logger = logging.getLogger(__name__)

# Exportiere die Hauptfunktion für den Import von außen
from .generation import generate_flashcards_with_openai

__all__ = ['generate_flashcards_with_openai'] 