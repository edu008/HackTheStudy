"""
Funktionen zur Verarbeitung und Analyse von Texten.
"""

import re
import logging
from langdetect import detect
from .error_handler import log_error

logger = logging.getLogger(__name__)

def clean_text_for_database(text):
    """
    Bereinigt einen Text, um sicherzustellen, dass er in der Datenbank gespeichert werden kann.
    Entfernt NUL-Zeichen (0x00) und andere problematische Zeichen.
    
    Args:
        text (str): Der zu bereinigende Text
        
    Returns:
        str: Der bereinigte Text
    """
    if not text:
        return ""
    
    try:
        # Entferne Null-Bytes (0x00)
        cleaned_text = text.replace('\x00', '')
        
        # Aggressivere Bereinigung - alle Steuerzeichen außer Zeilenumbrüche und Tabs entfernen
        # Dies verhindert viele Probleme mit exotischen PDF-Formaten
        allowed_control = ['\n', '\r', '\t']
        cleaned_text = ''.join(c for c in cleaned_text if c >= ' ' or c in allowed_control)
        
        # Bereinige Unicode-Escape-Sequenzen, die Probleme verursachen könnten
        cleaned_text = cleaned_text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        
        # Entferne übermäßige Leerzeichen und Zeilenumbrüche
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)  # Mehr als 2 aufeinanderfolgende Zeilenumbrüche reduzieren
        cleaned_text = re.sub(r' {3,}', '  ', cleaned_text)     # Mehr als 2 aufeinanderfolgende Leerzeichen reduzieren
        
        return cleaned_text
    except Exception as e:
        log_error(e, endpoint="clean_text_for_database")
        # Im Fehlerfall einen sicheren leeren String zurückgeben
        return ""

def detect_language(text):
    """
    Erkennt die Sprache eines Textes.
    
    Args:
        text (str): Text, dessen Sprache erkannt werden soll
        
    Returns:
        str: Sprachcode ('de' für Deutsch, 'en' für Englisch)
    """
    try:
        if not text or len(text.strip()) < 10:
            logger.warning("Text zu kurz für zuverlässige Spracherkennung, verwende Englisch als Standard")
            return 'en'
            
        # Beschränke die Analyse auf die ersten 500 Zeichen für Effizienz
        lang = detect(text[:500])
        
        # Derzeit unterstützen wir hauptsächlich Deutsch und Englisch
        # Bei Deutsch gib 'de' zurück, bei allen anderen Sprachen 'en'
        return 'de' if lang == 'de' else 'en'
    except Exception as e:
        logger.warning(f"Fehler bei der Spracherkennung: {str(e)}, verwende Englisch als Standard")
        return 'en'

def count_words(text):
    """
    Zählt die Wörter in einem Text.
    
    Args:
        text (str): Der zu analysierende Text
        
    Returns:
        int: Anzahl der Wörter
    """
    if not text:
        return 0
        
    try:
        # Bereinigen und in Wörter aufteilen
        words = text.strip().split()
        return len(words)
    except Exception as e:
        logger.error(f"Fehler beim Zählen der Wörter: {str(e)}")
        return 0

def extract_sentences(text, max_sentences=10):
    """
    Extrahiert Sätze aus einem Text.
    
    Args:
        text (str): Der zu verarbeitende Text
        max_sentences (int): Maximale Anzahl von Sätzen, die zurückgegeben werden sollen
        
    Returns:
        list: Liste von Sätzen
    """
    if not text:
        return []
        
    try:
        # Einfache Satzextraktion mit Regex
        # Berücksichtigt gängige Satzenden: ., !, ?
        sentence_pattern = r'[^.!?]*[.!?]'
        sentences = re.findall(sentence_pattern, text)
        
        # Bereinige die extrahierten Sätze
        cleaned_sentences = []
        for sentence in sentences:
            s = sentence.strip()
            if s and len(s) > 5:  # Ignoriere zu kurze "Sätze"
                cleaned_sentences.append(s)
                
        return cleaned_sentences[:max_sentences]
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren von Sätzen: {str(e)}")
        return []

def get_text_statistics(text):
    """
    Berechnet Statistiken für einen Text.
    
    Args:
        text (str): Der zu analysierende Text
        
    Returns:
        dict: Wörterbuch mit Statistiken
    """
    if not text:
        return {
            "word_count": 0,
            "character_count": 0,
            "sentence_count": 0,
            "estimated_reading_time_minutes": 0,
            "language": "unknown"
        }
        
    try:
        # Bereinigen und in Wörter aufteilen
        words = text.strip().split()
        word_count = len(words)
        
        # Zeichenzahl berechnen
        character_count = len(text)
        
        # Sätze zählen
        sentences = extract_sentences(text, max_sentences=1000)
        sentence_count = len(sentences)
        
        # Lesezeit schätzen (durchschnittlich 250 Wörter pro Minute)
        reading_time = round(word_count / 250, 1)
        
        # Sprache erkennen
        language = detect_language(text)
        
        return {
            "word_count": word_count,
            "character_count": character_count,
            "sentence_count": sentence_count,
            "estimated_reading_time_minutes": reading_time,
            "language": language
        }
    except Exception as e:
        logger.error(f"Fehler beim Berechnen der Textstatistiken: {str(e)}")
        return {
            "word_count": 0,
            "character_count": 0,
            "sentence_count": 0,
            "estimated_reading_time_minutes": 0,
            "language": "unknown"
        } 