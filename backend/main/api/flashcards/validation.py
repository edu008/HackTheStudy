"""
Validierungs-Modul für das Flashcards-Paket
-----------------------------------------

Dieses Modul enthält Funktionen zur Validierung von Flashcards:
- Überprüfung der Flashcard-Struktur
- Validierung der Vorder- und Rückseite
- Bereinigung und Formatierung von Flashcard-Inhalten
"""

import re
import logging
from marshmallow import Schema, fields, ValidationError, validates, validates_schema
from .schemas import FlashcardDataSchema

logger = logging.getLogger(__name__)

def validate_flashcard_data(flashcard_data):
    """
    Validiert die Daten einer Lernkarte.
    
    Args:
        flashcard_data: Die zu validierenden Lernkartendaten
        
    Returns:
        (bool, str): Ein Tupel aus einem Erfolgs-Flag und einer Fehlermeldung (falls vorhanden)
    """
    try:
        FlashcardDataSchema().load(flashcard_data)
        return True, ""
    except ValidationError as err:
        error_message = "; ".join([f"{field}: {'; '.join(messages)}" for field, messages in err.messages.items()])
        return False, error_message

def validate_generated_flashcards(flashcards):
    """
    Validiert eine Liste von generierten Lernkarten.
    
    Args:
        flashcards: Die zu validierende Lernkartenliste
        
    Returns:
        (list, list): Ein Tupel aus gültigen Lernkarten und Fehlermeldungen für ungültige Lernkarten
    """
    valid_flashcards = []
    error_messages = []
    
    for i, flashcard in enumerate(flashcards):
        is_valid, error = validate_flashcard_data(flashcard)
        if is_valid:
            valid_flashcards.append(flashcard)
        else:
            error_messages.append(f"Lernkarte {i+1}: {error}")
            logger.warning(f"Ungültige Lernkarte: {error}")
    
    return valid_flashcards, error_messages

def is_valid_flashcard_front(front_text):
    """
    Prüft, ob der Text für die Vorderseite einer Lernkarte gültig ist.
    
    Args:
        front_text: Der zu prüfende Text
        
    Returns:
        bool: True, wenn der Text gültig ist, sonst False
    """
    if not front_text or not front_text.strip():
        return False
    
    # Mindestlänge prüfen (z.B. mindestens 2 Zeichen)
    if len(front_text.strip()) < 2:
        return False
    
    # Maximallänge prüfen (z.B. maximal 500 Zeichen)
    if len(front_text) > 500:
        return False
    
    return True

def is_valid_flashcard_back(back_text):
    """
    Prüft, ob der Text für die Rückseite einer Lernkarte gültig ist.
    
    Args:
        back_text: Der zu prüfende Text
        
    Returns:
        bool: True, wenn der Text gültig ist, sonst False
    """
    if not back_text or not back_text.strip():
        return False
    
    # Mindestlänge prüfen (z.B. mindestens 2 Zeichen)
    if len(back_text.strip()) < 2:
        return False
    
    # Maximallänge prüfen (z.B. maximal 1000 Zeichen)
    if len(back_text) > 1000:
        return False
    
    return True

def sanitize_flashcard_front(front_text):
    """
    Bereinigt den Text für die Vorderseite einer Lernkarte.
    
    Args:
        front_text: Der zu bereinigende Text
        
    Returns:
        str: Der bereinigte Text
    """
    if not front_text:
        return ""
    
    # Entferne überflüssige Whitespaces
    front_text = re.sub(r'\s+', ' ', front_text.strip())
    
    # Entferne potenziell problematische Zeichen
    front_text = re.sub(r'[^\w\s.,;:!?()[\]{}\'"-]', '', front_text)
    
    # Stelle sicher, dass der Text mit einem Großbuchstaben beginnt
    if front_text and front_text[0].isalpha():
        front_text = front_text[0].upper() + front_text[1:]
    
    return front_text

def sanitize_flashcard_back(back_text):
    """
    Bereinigt den Text für die Rückseite einer Lernkarte.
    
    Args:
        back_text: Der zu bereinigende Text
        
    Returns:
        str: Der bereinigte Text
    """
    if not back_text:
        return ""
    
    # Entferne überflüssige Whitespaces
    back_text = re.sub(r'\s+', ' ', back_text.strip())
    
    # Entferne potenziell problematische Zeichen, aber erlaube mehr als bei der Vorderseite
    back_text = re.sub(r'[^\w\s.,;:!?()[\]{}\'"-/*+<>=]', '', back_text)
    
    # Stelle sicher, dass der Text mit einem Großbuchstaben beginnt
    if back_text and back_text[0].isalpha():
        back_text = back_text[0].upper() + back_text[1:]
    
    return back_text

def sanitize_flashcard(flashcard):
    """
    Bereinigt eine komplette Lernkarte.
    
    Args:
        flashcard: Die zu bereinigende Lernkarte
        
    Returns:
        dict: Die bereinigte Lernkarte
    """
    sanitized = flashcard.copy()
    
    if 'front' in sanitized:
        sanitized['front'] = sanitize_flashcard_front(sanitized['front'])
    
    if 'back' in sanitized:
        sanitized['back'] = sanitize_flashcard_back(sanitized['back'])
    
    if 'category' in sanitized and sanitized['category']:
        # Bereinige die Kategorie
        sanitized['category'] = re.sub(r'\s+', ' ', sanitized['category'].strip())
        sanitized['category'] = sanitized['category'].capitalize()
    
    return sanitized

def validate_flashcard_category(category):
    """
    Validiert eine Lernkartenkategorie.
    
    Args:
        category: Die zu validierende Kategorie
        
    Returns:
        bool: True, wenn die Kategorie gültig ist, sonst False
    """
    if not category or not isinstance(category, str):
        return False
    
    # Mindestlänge prüfen
    if len(category.strip()) < 2:
        return False
    
    # Maximallänge prüfen
    if len(category) > 50:
        return False
    
    # Prüfen, ob die Kategorie nur alphanumerische Zeichen, Leerzeichen und Bindestriche enthält
    if not re.match(r'^[\w\s-]+$', category):
        return False
    
    return True

def validate_flashcard_difficulty(difficulty):
    """
    Validiert den Schwierigkeitsgrad einer Lernkarte.
    
    Args:
        difficulty: Der zu validierende Schwierigkeitsgrad
        
    Returns:
        bool: True, wenn der Schwierigkeitsgrad gültig ist, sonst False
    """
    if difficulty is None:
        return True  # Kein Schwierigkeitsgrad ist gültig
    
    try:
        difficulty = int(difficulty)
        return 1 <= difficulty <= 5  # Schwierigkeitsgrad muss zwischen 1 und 5 liegen
    except (ValueError, TypeError):
        return False
