"""
Funktionen zur Spracherkennung in Texten.
"""
import logging

logger = logging.getLogger(__name__)

def detect_language(text):
    """
    Erkennt die Sprache eines Textes.
    
    Args:
        text: Der zu analysierende Text
        
    Returns:
        str: Sprachcode (z.B. 'de', 'en')
    """
    try:
        # Kurzer Text für bessere Performance
        sample_text = text[:500] if len(text) > 500 else text
        
        # Versuche langdetect zu importieren und zu verwenden
        try:
            from langdetect import detect
            lang = detect(sample_text)
            logger.info(f"Sprache mit langdetect erkannt: {lang}")
            return 'de' if lang == 'de' else 'en'
        except ImportError:
            logger.warning("langdetect nicht verfügbar, verwende Fallback-Methode")
            
        # Fallback-Methode: Einfache Wortzählung für Deutsch vs. Englisch
        german_words = ['der', 'die', 'das', 'und', 'in', 'von', 'mit', 'auf', 'für', 'ist', 'sind', 
                        'werden', 'nicht', 'eine', 'ein', 'zu', 'dass', 'es', 'auch', 'als', 'oder']
        
        english_words = ['the', 'and', 'to', 'of', 'in', 'is', 'that', 'for', 'on', 'with', 'as', 
                         'by', 'this', 'be', 'at', 'from', 'but', 'not', 'or', 'have', 'are']
        
        # Zu Kleinbuchstaben konvertieren und Satzzeichen entfernen
        cleaned_text = ''.join(c.lower() if c.isalpha() or c.isspace() else ' ' for c in sample_text)
        words = cleaned_text.split()
        
        # Zähle deutsche und englische Wörter
        de_count = sum(1 for word in words if word in german_words)
        en_count = sum(1 for word in words if word in english_words)
        
        logger.info(f"Fallback-Spracherkennung: DE Wörter: {de_count}, EN Wörter: {en_count}")
        
        # Entscheide basierend auf der höheren Anzahl
        if de_count > en_count:
            return 'de'
        else:
            return 'en'
            
    except Exception as e:
        logger.error(f"Fehler bei der Spracherkennung: {str(e)}")
        return 'de'  # Standardmäßig Deutsch zurückgeben 