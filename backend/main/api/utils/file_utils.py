# api/file_utils.py
"""
Funktionen zur Verarbeitung und Extraktion von Dateien verschiedener Formate.

HINWEIS: Dieses Modul importiert die primären Dateifunktionen aus dem utils.file_utils-Modul.
Neue Code-Implementierungen sollten direkt das Hauptmodul verwenden.
"""

import logging

# Importiere die Kernfunktionen aus dem Hauptmodul
try:
    from utils.file_utils import (
        allowed_file, extract_text_from_file, extract_text_from_pdf,
        extract_text_from_pdf_safe
    )
except ImportError:
    # Fallback für den Import mit vollständigem Pfad
    try:
        from backend.main.utils.file_utils import (
            allowed_file, extract_text_from_file, extract_text_from_pdf,
            extract_text_from_pdf_safe
        )
    except ImportError:
        # Fehlermeldung loggen
        logging.getLogger(__name__).error(
            "Kritischer Fehler: Konnte utils.file_utils nicht importieren. "
            "Die Dateifunktionalität wird nicht korrekt funktionieren."
        )

# Re-exportiere die Funktionen für Abwärtskompatibilität
__all__ = [
    'allowed_file',
    'extract_text_from_file',
    'extract_text_from_pdf',
    'extract_text_from_pdf_safe'
]
