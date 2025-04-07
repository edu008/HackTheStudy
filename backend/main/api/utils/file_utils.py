# api/file_utils.py
"""
Funktionen zur Verarbeitung und Extraktion von Dateien verschiedener Formate.

HINWEIS: Dieses Modul importiert die primären Dateifunktionen aus dem utils.file_utils-Modul.
Neue Code-Implementierungen sollten direkt das Hauptmodul verwenden.
"""

import logging
import os
import tempfile
import sys
import re

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Importiere die Kernfunktionen aus dem Hauptmodul
try:
    # Importiere direkt aus dem backend.main.utils-Paket
    from backend.main.utils import (
        allowed_file, extract_text_from_file, extract_text_from_pdf,
        extract_text_from_pdf_safe, check_extension, get_secure_filename
    )
    logger.info("Erfolgreich utils-Modul importiert")
except ImportError as e:
    # Versuche einen alternativen Import-Pfad
    try:
        # Füge das Hauptverzeichnis zum Pythonpfad hinzu
        backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        
        # Versuche den Import mit dem angepassten Pfad
        from utils import (
            allowed_file, extract_text_from_file, extract_text_from_pdf,
            extract_text_from_pdf_safe, check_extension, get_secure_filename
        )
        logger.info("Erfolgreich utils-Modul über relativen Pfad importiert")
    except ImportError as e2:
        # Fehlermeldung loggen
        logger.error(
            "Kritischer Fehler: Konnte utils.file_utils nicht importieren. "
            f"Import-Fehler: {str(e)} und {str(e2)}"
        )
        
        # Fallback-Implementierungen für die wichtigsten Funktionen
        def allowed_file(filename, allowed_extensions=None):
            """Einfache Fallback-Implementierung für allowed_file."""
            if not filename or not isinstance(filename, str):
                return False
                
            if allowed_extensions is None:
                allowed_extensions = {'.pdf', '.docx', '.doc', '.txt', '.rtf', '.odt'}
                
            ext = os.path.splitext(filename.lower())[1]
            return ext in allowed_extensions
            
        def check_extension(filename):
            """Einfache Fallback-Implementierung für check_extension."""
            if not filename or not isinstance(filename, str):
                return ""
                
            ext = os.path.splitext(filename.lower())[1]
            return ext
            
        def get_secure_filename(filename):
            """Einfache Fallback-Implementierung für get_secure_filename."""
            if not filename:
                return ""
                
            # Ersetzt Leerzeichen durch Unterstriche und entfernt problematische Zeichen
            filename = str(filename).strip().replace(" ", "_")
            filename = re.sub(r"[^a-zA-Z0-9_.-]", "", filename)
            return filename
            
        def extract_text_from_file(file_content, filename):
            """Einfache Fallback-Implementierung für extract_text_from_file."""
            if not file_content:
                return "Leerer Dateiinhalt"
                
            # Einfache Erkennung für Textdateien
            if filename.lower().endswith('.txt'):
                try:
                    return file_content.decode('utf-8')
                except UnicodeDecodeError:
                    return "Fehler beim Dekodieren der Textdatei"
            else:
                return f"Textextraktion aus {filename} nicht verfügbar (Fallback-Modus)"
                
        def extract_text_from_pdf(file_path):
            """Einfache Fallback-Implementierung für extract_text_from_pdf."""
            return f"PDF-Textextraktion aus {file_path} nicht verfügbar (Fallback-Modus)"
            
        def extract_text_from_pdf_safe(file_content):
            """Einfache Fallback-Implementierung für extract_text_from_pdf_safe."""
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp:
                    temp_path = temp.name
                    temp.write(file_content)
                
                return extract_text_from_pdf(temp_path)
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        logger.warning("Konnte temporäre Datei nicht löschen")

# Re-exportiere die Funktionen für Abwärtskompatibilität
__all__ = [
    'allowed_file',
    'extract_text_from_file',
    'extract_text_from_pdf',
    'extract_text_from_pdf_safe',
    'check_extension',
    'get_secure_filename'
]
