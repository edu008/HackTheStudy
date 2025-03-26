"""
Funktionen zur Textbereinigung und Tokenisierung.
"""
import re
import logging

logger = logging.getLogger(__name__)

def clean_text_for_database(text):
    """
    Bereinigt Text für die Speicherung in der Datenbank.
    
    Args:
        text: Der zu bereinigende Text
        
    Returns:
        str: Bereinigter Text
    """
    try:
        if not text or not isinstance(text, str):
            return ""
        
        # Entferne NUL-Bytes, die in Datenbanken Probleme verursachen
        cleaned_text = text.replace('\x00', '')
        
        # Normalisiere Zeilenumbrüche
        cleaned_text = re.sub(r'\r\n?', '\n', cleaned_text)
        
        # Entferne überflüssige Leerzeichen und Zeilenumbrüche
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
        cleaned_text = re.sub(r' {2,}', ' ', cleaned_text)
        
        # Begrenze die Länge (z.B. auf 10MB um Datenbankprobleme zu vermeiden)
        max_length = 10 * 1024 * 1024  # 10 MB
        if len(cleaned_text) > max_length:
            logger.warning(f"Text zu lang, wird auf {max_length} Zeichen begrenzt")
            cleaned_text = cleaned_text[:max_length]
        
        return cleaned_text
    except Exception as e:
        logger.error(f"Fehler bei der Textbereinigung: {str(e)}")
        return ""

def count_tokens(text):
    """
    Zählt ungefähr die Anzahl der Tokens im Text für die Verarbeitung mit OpenAI.
    
    Args:
        text: Der zu analysierende Text
        
    Returns:
        int: Geschätzte Anzahl der Tokens
    """
    try:
        if not text:
            return 0
            
        # Versuche tiktoken zu verwenden, wenn verfügbar
        try:
            import tiktoken
            
            # cl100k_base ist der Tokenizer für neuere GPT-Modelle
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
            return len(tokens)
        except ImportError:
            logger.warning("tiktoken nicht installiert, verwende Näherungsmethode")
        
        # Einfache Näherungsmethode: Wörter * 1.33
        words = text.split()
        return int(len(words) * 1.33)
    except Exception as e:
        logger.error(f"Fehler bei der Token-Zählung: {str(e)}")
        # Fallback: Ungefähre Schätzung anhand von Textlänge
        return len(text) // 4 