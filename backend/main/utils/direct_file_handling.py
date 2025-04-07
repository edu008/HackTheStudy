"""
Direkte Dateihandhabung
------------------------

Diese Datei stellt Funktionen für die direkte Dateihandhabung bereit, ohne
Text zu extrahieren. Sie ersetzt die bisherigen Textextraktionsfunktionen.
"""

import os
import tempfile
import logging
from typing import Dict, Any, Tuple, Union, BinaryIO

logger = logging.getLogger(__name__)

def handle_uploaded_file(file_content: bytes, filename: str = None) -> Dict[str, Any]:
    """
    Verarbeitet eine hochgeladene Datei ohne Textextraktion.
    
    Args:
        file_content (bytes): Der Binärinhalt der Datei
        filename (str, optional): Der Dateiname
        
    Returns:
        dict: Informationen über die Datei
    """
    file_extension = os.path.splitext(filename)[1].lower() if filename else ".pdf"
    
    return {
        'filename': filename,
        'size': len(file_content),
        'extension': file_extension,
        'binary_content': True,
        'content_type': get_content_type(file_extension)
    }

def save_file_for_processing(file_content: bytes, filename: str = None) -> str:
    """
    Speichert eine Datei temporär für die Verarbeitung.
    
    Args:
        file_content (bytes): Der Binärinhalt der Datei
        filename (str, optional): Der Dateiname
        
    Returns:
        str: Pfad zur temporären Datei
    """
    file_extension = os.path.splitext(filename)[1].lower() if filename and '.' in filename else ".pdf"
    
    temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
    temp_file_path = temp_file.name
    
    try:
        with open(temp_file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"Datei für Verarbeitung gespeichert: {temp_file_path} ({len(file_content)} Bytes)")
        return temp_file_path
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Datei: {str(e)}")
        try:
            os.unlink(temp_file_path)
        except:
            pass
        raise

def cleanup_temp_file(file_path: str) -> bool:
    """
    Löscht eine temporäre Datei.
    
    Args:
        file_path (str): Pfad zur temporären Datei
        
    Returns:
        bool: True, wenn die Datei erfolgreich gelöscht wurde, sonst False
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Temporäre Datei gelöscht: {file_path}")
            return True
        else:
            logger.warning(f"Temporäre Datei existiert nicht: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Fehler beim Löschen der temporären Datei: {str(e)}")
        return False

def get_content_type(file_extension: str) -> str:
    """
    Bestimmt den Content-Type basierend auf der Dateiendung.
    
    Args:
        file_extension (str): Die Dateiendung (mit Punkt, z.B. ".pdf")
        
    Returns:
        str: Der MIME-Typ der Datei
    """
    content_types = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
        '.txt': 'text/plain',
        '.rtf': 'application/rtf',
        '.odt': 'application/vnd.oasis.opendocument.text',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.csv': 'text/csv',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.zip': 'application/zip',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif'
    }
    
    return content_types.get(file_extension.lower(), 'application/octet-stream')

# Exportierte Funktionen (für Abwärtskompatibilität)
def extract_text_from_file(file_content, filename):
    """
    Abwärtskompatibilitätsfunktion für extract_text_from_file.
    Statt Text zu extrahieren, gibt diese Funktion nur einen Platzhalter zurück.
    
    Dies ist nur eine Übergangslösung, bis alle Aufrufe auf die neue
    direkte Dateiverarbeitung umgestellt sind.
    """
    logger.warning(f"Legacy-Funktion extract_text_from_file aufgerufen für {filename}. Keine Textextraktion wird durchgeführt.")
    return f"[BINARY_CONTENT] Datei {filename}, {len(file_content)} Bytes"

def extract_text_from_pdf(file_content, filename):
    """
    Abwärtskompatibilitätsfunktion für extract_text_from_pdf.
    Statt Text zu extrahieren, gibt diese Funktion nur einen Platzhalter zurück.
    """
    logger.warning(f"Legacy-Funktion extract_text_from_pdf aufgerufen für {filename}. Keine Textextraktion wird durchgeführt.")
    return f"[BINARY_CONTENT] PDF-Datei {filename}, {len(file_content)} Bytes"

# Definiere alle exportierten Funktionen
__all__ = [
    'handle_uploaded_file',
    'save_file_for_processing',
    'cleanup_temp_file',
    'get_content_type',
    'extract_text_from_file',  # Legacy-Funktion
    'extract_text_from_pdf'   # Legacy-Funktion
] 