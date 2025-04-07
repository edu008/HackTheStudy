"""
Utils-Modul für die Hauptanwendung.
"""

import os
import sys
import logging
import re
from importlib import import_module
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

# Basisverzeichnis-Pfad für spätere Importe
base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)
    
logger = logging.getLogger(__name__)

# Liste der zu exportierenden Funktionen und Klassen
__all__ = [
    # Neue direkte Dateihandhabungsfunktionen
    'handle_uploaded_file',
    'save_file_for_processing',
    'cleanup_temp_file',
    'get_content_type',
    
    # Legacy-Funktionen (bleiben für Kompatibilität)
    'extract_text_from_file',
    'extract_text_from_pdf',
    'extract_text_from_pdf_safe',
    
    # Andere Module
    'allowed_file',
    'check_extension',
    'get_secure_filename',
    'convert_to_timestamp'
]

# Importiere die direkte Dateihandhabungsmodule
try:
    from .direct_file_handling import (
        handle_uploaded_file, save_file_for_processing,
        cleanup_temp_file, get_content_type,
        extract_text_from_file, extract_text_from_pdf
    )
    logger.info("Direkte Dateihandhabungsfunktionen erfolgreich importiert")
except ImportError as e:
    logger.error(f"Fehler beim Importieren der Dateihandhabungsfunktionen: {e}")
    
    # Dummy-Implementierungen für den Fall eines Import-Fehlers
    def handle_uploaded_file(file_content, filename):
        logger.warning("Dummy-Funktion handle_uploaded_file aufgerufen")
        return {'filename': filename, 'size': len(file_content) if file_content else 0}
    
    def save_file_for_processing(file_content, filename):
        logger.warning("Dummy-Funktion save_file_for_processing aufgerufen")
        return None
        
    def cleanup_temp_file(file_path):
        logger.warning("Dummy-Funktion cleanup_temp_file aufgerufen")
        return False
        
    def get_content_type(file_extension):
        logger.warning("Dummy-Funktion get_content_type aufgerufen")
        return 'application/octet-stream'
        
    def extract_text_from_file(file_content, filename):
        logger.warning("Dummy-Funktion extract_text_from_file aufgerufen")
        return "[FEHLER] Konnte Datei nicht verarbeiten"
        
    def extract_text_from_pdf(file_content, filename):
        logger.warning("Dummy-Funktion extract_text_from_pdf aufgerufen")
        return "[FEHLER] Konnte PDF nicht verarbeiten"

# Stellen wir sicher, dass extract_text_from_pdf_safe exportiert wird
def extract_text_from_pdf_safe(file_content):
    """
    Sichere Wrapper-Funktion für extract_text_from_pdf.
    
    Diese Funktion ist für Abwärtskompatibilität und ruft einfach extract_text_from_pdf auf.
    """
    import tempfile
    
    temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    try:
        with open(temp_path, 'wb') as f:
            f.write(file_content)
        
        return extract_text_from_pdf(file_content, temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass

# Andere Hilfsfunktionen importieren
try:
    from .file_utils import allowed_file, check_extension, get_secure_filename
    from .date_utils import convert_to_timestamp
except ImportError as e:
    logger.error(f"Fehler beim Importieren weiterer Hilfsfunktionen: {e}")
    
    # Dummy-Implementierungen
    def allowed_file(filename):
        return True
        
    def check_extension(filename):
        if not filename:
            return ""
        return os.path.splitext(filename.lower())[1]
        
    def get_secure_filename(filename):
        """Sicherere Dummy-Implementierung für get_secure_filename."""
        if not filename:
            return ""
            
        # Ersetzt Leerzeichen durch Unterstriche und entfernt problematische Zeichen
        filename = str(filename).strip().replace(" ", "_")
        filename = re.sub(r"[^a-zA-Z0-9_.-]", "", filename)
        filename = re.sub(r"^[.]+", "", filename)  # Entferne führende Punkte
        
        return filename
        
    def convert_to_timestamp(dt):
        return 0
