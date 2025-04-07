"""
Topics-Modul für die Extraktion von Themen aus Dokumenten.
"""
import logging

logger = logging.getLogger(__name__)

# Exportiere die Hauptfunktion für den Import von außen
from .generation import extract_topics_with_openai

__all__ = ['extract_topics_with_openai'] 