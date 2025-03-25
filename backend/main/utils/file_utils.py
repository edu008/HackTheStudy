"""
Hilfsfunktionen für Dateioperationen.
"""

import os
import re
import io
import logging
from typing import Optional, Set, List, Dict, Any, Tuple
import tempfile

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Standard-Menge erlaubter Dateitypen
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.rtf', '.odt'}

def allowed_file(filename: str, allowed_extensions: Set[str] = None) -> bool:
    """
    Prüft, ob ein Dateiname eine erlaubte Erweiterung hat.
    
    Args:
        filename: Der zu prüfende Dateiname
        allowed_extensions: Set mit erlaubten Erweiterungen (z.B. {'.pdf', '.docx'})
    
    Returns:
        True, wenn die Datei erlaubt ist, sonst False
    """
    if not filename or not isinstance(filename, str):
        return False
    
    # Verwende Standard-Erweiterungen, wenn keine angegeben sind
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS
    
    # Normalisiere den Dateinamen und extrahiere die Erweiterung
    filename = filename.lower()
    ext = os.path.splitext(filename)[1]
    
    return ext in allowed_extensions

def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """
    Extrahiert Text aus verschiedenen Dateiformaten.
    
    Args:
        file_content: Binärer Inhalt der Datei
        filename: Name der Datei (für Formatbestimmung)
    
    Returns:
        Extrahierter Text
    
    Raises:
        ValueError: Wenn die Datei nicht unterstützt wird oder nicht gelesen werden kann
    """
    # Erweiterung bestimmen
    ext = os.path.splitext(filename.lower())[1]
    
    # Tempfile für binäre Dateien erstellen
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp:
        temp_path = temp.name
        temp.write(file_content)
    
    try:
        # Je nach Dateityp verschiedene Extraktionsmethoden verwenden
        if ext == '.pdf':
            text = _extract_text_from_pdf(temp_path)
        elif ext in ['.docx', '.doc']:
            text = _extract_text_from_word(temp_path)
        elif ext == '.txt':
            text = _extract_text_from_text(file_content)
        elif ext == '.rtf':
            text = _extract_text_from_rtf(temp_path)
        elif ext == '.odt':
            text = _extract_text_from_odt(temp_path)
        else:
            raise ValueError(f"Nicht unterstütztes Dateiformat: {ext}")
        
        # Temporäre Datei löschen
        os.unlink(temp_path)
        
        return text
    except Exception as e:
        # Temporäre Datei aufräumen
        try:
            os.unlink(temp_path)
        except:
            pass
        
        logger.error(f"Fehler beim Extrahieren von Text aus {filename}: {str(e)}")
        raise ValueError(f"Konnte Text nicht aus Datei extrahieren: {str(e)}")

def _extract_text_from_pdf(file_path: str) -> str:
    """Extrahiert Text aus einer PDF-Datei."""
    try:
        import PyPDF2
        
        text = ""
        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n"
        
        return text
    except ImportError:
        logger.error("PyPDF2 ist nicht installiert")
        raise ImportError("PyPDF2 ist erforderlich, um PDF-Dateien zu verarbeiten")

def _extract_text_from_word(file_path: str) -> str:
    """Extrahiert Text aus einer Word-Datei."""
    try:
        import docx
        
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except ImportError:
        logger.error("python-docx ist nicht installiert")
        raise ImportError("python-docx ist erforderlich, um Word-Dateien zu verarbeiten")

def _extract_text_from_text(file_content: bytes) -> str:
    """Extrahiert Text aus einer Textdatei."""
    try:
        # Versuche mit UTF-8 zu decodieren
        return file_content.decode('utf-8')
    except UnicodeDecodeError:
        # Fallback zu anderen Kodierungen
        encodings = ['latin-1', 'cp1252', 'ascii']
        for encoding in encodings:
            try:
                return file_content.decode(encoding)
            except UnicodeDecodeError:
                continue
        
        # Wenn keine Kodierung funktioniert, verwende 'latin-1' mit Ersetzung
        return file_content.decode('latin-1', errors='replace')

def _extract_text_from_rtf(file_path: str) -> str:
    """Extrahiert Text aus einer RTF-Datei."""
    try:
        from striprtf.striprtf import rtf_to_text
        
        with open(file_path, 'r', errors='ignore') as file:
            rtf = file.read()
        
        text = rtf_to_text(rtf)
        return text
    except ImportError:
        logger.error("striprtf ist nicht installiert")
        raise ImportError("striprtf ist erforderlich, um RTF-Dateien zu verarbeiten")

def _extract_text_from_odt(file_path: str) -> str:
    """Extrahiert Text aus einer ODT-Datei."""
    try:
        import odf.opendocument
        from odf.text import P
        
        textdoc = odf.opendocument.load(file_path)
        paragraphs = textdoc.getElementsByType(P)
        text = "\n".join([p.plainText() for p in paragraphs])
        return text
    except ImportError:
        logger.error("odfpy ist nicht installiert")
        raise ImportError("odfpy ist erforderlich, um ODT-Dateien zu verarbeiten")

def clean_text_for_database(text: str, max_length: int = 10000000) -> str:
    """
    Bereinigt Text für die Speicherung in der Datenbank.
    
    Args:
        text: Der zu bereinigende Text
        max_length: Maximale Textlänge
    
    Returns:
        Bereinigter Text
    """
    if not text:
        return ""
    
    # Entferne Steuerzeichen außer Zeilenumbrüchen und Tabulatoren
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Entferne mehrfache Leerzeichen
    text = re.sub(r' +', ' ', text)
    
    # Entferne mehrfache Zeilenumbrüche
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Kürze auf maximale Länge
    if len(text) > max_length:
        logger.warning(f"Text war zu lang ({len(text)} Zeichen) und wurde auf {max_length} gekürzt")
        text = text[:max_length]
    
    return text

def detect_language(text: str) -> str:
    """
    Erkennt die Sprache eines Textes.
    
    Args:
        text: Der zu analysierende Text
    
    Returns:
        Sprachcode (z.B. 'de', 'en', 'fr')
    """
    try:
        import langdetect
        
        # Stichprobe nehmen für lange Texte (Leistungsoptimierung)
        sample = text[:10000] if len(text) > 10000 else text
        
        # Sprache erkennen
        lang = langdetect.detect(sample)
        return lang
    except ImportError:
        logger.warning("langdetect ist nicht installiert, Spracherkennung nicht verfügbar")
        return "unknown"
    except Exception as e:
        logger.error(f"Fehler bei der Spracherkennung: {str(e)}")
        return "unknown" 