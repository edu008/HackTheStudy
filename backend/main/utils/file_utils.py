"""
Hilfsfunktionen für Dateioperationen.
"""

import importlib
import io
import logging
import os
import re
import shutil
import tempfile
import traceback
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Standard-Menge erlaubter Dateitypen
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.rtf', '.odt'}

# Abhängigkeiten für verschiedene Dateitypen
DEPENDENCIES = {
    '.pdf': ['fitz'],  # PyMuPDF (Modul heißt fitz)
    '.docx': ['docx'],
    '.doc': ['docx'],
    '.rtf': ['striprtf'],
    '.odt': ['odf']
}

# Funktionen im Modul, die exportiert werden sollen
__all__ = [
    "extract_text_from_file",
    "extract_text_from_pdf",
    "check_extension",
    "allowed_file",
    "get_secure_filename"
]

def _check_dependency(module_name: str) -> bool:
    """
    Prüft, ob eine Abhängigkeit installiert ist.

    Args:
        module_name: Der Name des zu prüfenden Moduls

    Returns:
        True, wenn das Modul installiert ist, sonst False
    """
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def _safely_import(module_name: str) -> Optional[Any]:
    """
    Importiert ein Modul sicher und gibt None zurück, wenn es nicht verfügbar ist.

    Args:
        module_name: Der Name des zu importierenden Moduls

    Returns:
        Das importierte Modul oder None, wenn der Import fehlschlägt
    """
    try:
        return importlib.import_module(module_name)
    except ImportError:
        logger.warning("Modul %s konnte nicht importiert werden.", module_name)
        return None


def check_extension(filename: str) -> str:
    """
    Extrahiert und prüft die Dateierweiterung.

    Args:
        filename: Der zu prüfende Dateiname

    Returns:
        Die Dateierweiterung (z.B. '.pdf') oder leeren String wenn ungültig
    """
    if not filename or not isinstance(filename, str):
        logger.warning("Ungültiger Dateiname für Erweiterungsprüfung: %s", filename)
        return ""

    try:
        # Normalisiere den Dateinamen und extrahiere die Erweiterung
        filename = filename.lower()
        ext = os.path.splitext(filename)[1]
        
        if not ext:
            logger.warning("Keine Erweiterung gefunden in: %s", filename)
            return ""
            
        return ext
    except Exception as e:
        logger.error("Fehler bei der Extraktion der Dateierweiterung: %s, Fehler: %s", filename, str(e))
        return ""


def get_secure_filename(filename: str) -> str:
    """
    Gibt einen sicheren Dateinamen zurück, der für die Speicherung auf dem Dateisystem geeignet ist.
    
    Basierend auf werkzeug.utils.secure_filename, aber als direktes Utility verfügbar.

    Args:
        filename: Der zu sichernde Dateiname

    Returns:
        Ein sicherer Dateiname ohne problematische Zeichen
    """
    if not filename:
        return ""
        
    # Ersetzt Leerzeichen durch Unterstriche und entfernt alle nicht-ASCII-Zeichen
    # sowie Schrägstriche und Punkte am Anfang der Datei
    filename = str(filename).strip().replace(" ", "_")
    filename = re.sub(r"[^a-zA-Z0-9_.-]", "", filename)
    filename = re.sub(r"^[.]+", "", filename)
    
    # Entferne doppelte Dateiendungen, z.B. .pdf.pdf
    filename = re.sub(r"(\.[a-zA-Z0-9]+)\1+$", r"\1", filename)
    
    # Begrenze die Länge auf 255 Zeichen (maximale Dateipfadlänge in vielen Dateisystemen)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
        
    return filename


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
        logger.warning("Ungültiger Dateiname für Validierung: %s", filename)
        return False

    # Verwende Standard-Erweiterungen, wenn keine angegeben sind
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS

    try:
        # Normalisiere den Dateinamen und extrahiere die Erweiterung
        filename = filename.lower()
        ext = os.path.splitext(filename)[1]

        return ext in allowed_extensions
    except Exception:
        logger.error("Fehler bei der Validierung des Dateityps: %s", filename)
        return False


def are_dependencies_installed(file_extension: str) -> bool:
    """
    Prüft, ob alle erforderlichen Abhängigkeiten für einen Dateityp installiert sind.

    Args:
        file_extension: Die Dateierweiterung (z.B. '.pdf')

    Returns:
        True, wenn alle Abhängigkeiten installiert sind, sonst False
    """
    if file_extension not in DEPENDENCIES:
        # Keine speziellen Abhängigkeiten für diesen Dateityp
        return True

    for dependency in DEPENDENCIES[file_extension]:
        if not _check_dependency(dependency):
            return False

    return True


def extract_text_from_file(file_content, filename):
    """
    Extrahiert Text aus einer Datei basierend auf ihrer Erweiterung.
    Falls die eigentliche Extraktionsfunktion nicht verfügbar ist,
    wird eine Platzhalter-Implementierung verwendet.
    
    Args:
        file_content: Der binäre Inhalt der Datei
        filename: Der Name der Datei (für die Erweiterungserkennung)
        
    Returns:
        Extrahierter Text oder Platzhaltertext
    """
    logger.info(f"Extrahiere Text aus Datei: {filename}")
    
    if filename.lower().endswith('.pdf'):
        try:
            return extract_text_from_pdf(file_content, filename)
        except Exception as e:
            logger.error(f"Fehler bei PDF-Extraktion: {e}")
            return f"[PDF-Text konnte nicht extrahiert werden: {filename}]"
    elif filename.lower().endswith(('.doc', '.docx')):
        return f"[Word-Text konnte nicht extrahiert werden: {filename}]"
    elif filename.lower().endswith('.txt'):
        try:
            return file_content.decode('utf-8', errors='replace')
        except Exception:
            return f"[Text konnte nicht decodiert werden: {filename}]"
    else:
        return f"[Nicht unterstütztes Dateiformat: {filename}]"
    

def extract_text_from_pdf(file_content, filename):
    """
    Verbesserte Funktion für PDF-Textextraktion mit zusätzlichen Fehlerprüfungen.
    
    Args:
        file_content: Der binäre Inhalt der PDF-Datei
        filename: Der Name der PDF-Datei
        
    Returns:
        Extrahierter Text oder Platzhaltertext
    """
    # Versuche PyMuPDF zu importieren
    try:
        import fitz
        # Speichere die PDF temporär
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp:
            temp_path = temp.name
            temp.write(file_content)
        
        # Überprüfe explizit, ob die temporäre Datei existiert
        if not os.path.exists(temp_path):
            logger.error(f"Temporäre Datei wurde nicht erstellt: {temp_path}")
            return f"[Fehler bei der PDF-Extraktion: temporäre Datei konnte nicht erstellt werden: {temp_path}]"
            
        try:
            # Log die tatsächliche Dateigröße
            file_size = os.path.getsize(temp_path)
            logger.info(f"Temporäre PDF-Datei erstellt: {temp_path}, Größe: {file_size} Bytes")
            
            # Öffne die PDF mit PyMuPDF
            doc = fitz.open(temp_path)
            text = ""
            
            # Extrahiere Text aus jeder Seite
            for page in doc:
                text += page.get_text() + "\n\n"
                
            # Schließe das Dokument
            doc.close()
            
            # Lösche die temporäre Datei
            try:
                os.unlink(temp_path)
                logger.info(f"Temporäre Datei gelöscht: {temp_path}")
            except Exception as del_err:
                logger.warning(f"Konnte temporäre Datei nicht löschen: {temp_path}, Fehler: {del_err}")
            
            return text
        except FileNotFoundError as fnf:
            error_msg = f"Fehler bei der PDF-Extraktion: no such file: '{temp_path}'"
            logger.error(error_msg)
            
            # Überprüfe das Verzeichnis
            dir_path = os.path.dirname(temp_path)
            if not os.path.exists(dir_path):
                logger.error(f"Verzeichnis existiert nicht: {dir_path}")
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    logger.info(f"Verzeichnis erstellt: {dir_path}")
                except Exception as dir_err:
                    logger.error(f"Konnte Verzeichnis nicht erstellen: {dir_err}")
            
            # Versuche, Berechtigungen zu überprüfen
            try:
                logger.info(f"Temporäres Verzeichnis: {tempfile.gettempdir()}")
                temp_dir_writable = os.access(tempfile.gettempdir(), os.W_OK)
                logger.info(f"Temp-Verzeichnis beschreibbar: {temp_dir_writable}")
            except Exception as perm_err:
                logger.error(f"Fehler beim Überprüfen der Berechtigungen: {perm_err}")
            
            return error_msg
        except Exception as e:
            logger.error(f"PyMuPDF-Fehler: {e}")
            # Lösche die temporäre Datei im Fehlerfall
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    logger.info(f"Temporäre Datei im Fehlerfall gelöscht: {temp_path}")
            except Exception as del_err:
                logger.warning(f"Konnte temporäre Datei nicht löschen: {del_err}")
            
            return f"[Fehler bei der PDF-Extraktion: {str(e)}]"
    except ImportError:
        logger.error("PyMuPDF (fitz) ist nicht installiert")
        return f"[PDF-Text konnte nicht extrahiert werden (PyMuPDF fehlt): {filename}]"


def _extract_text_from_word(file_path: str) -> str:
    """
    Extrahiert Text aus einer Word-Datei.

    Args:
        file_path: Pfad zur Word-Datei

    Returns:
        Extrahierter Text

    Raises:
        ValueError: Wenn der Text nicht extrahiert werden kann
    """
    docx_module = _safely_import('docx')
    if not docx_module:
        raise ImportError("python-docx ist erforderlich, um Word-Dateien zu verarbeiten")

    try:
        document = docx_module.Document(file_path)
        paragraphs = [p.text for p in document.paragraphs]
        text = '\n'.join(paragraphs)
        return text
    except Exception as e:
        logger.error("Fehler beim Extrahieren von Text aus Word-Datei: %s", str(e))
        logger.debug(traceback.format_exc())
        raise ValueError(f"Word-Extraktion fehlgeschlagen: {str(e)}") from e


def _extract_text_from_text(file_content: bytes) -> str:
    """
    Extrahiert Text aus einer Textdatei.

    Args:
        file_content: Binärer Inhalt der Datei

    Returns:
        Extrahierter Text

    Raises:
        ValueError: Wenn der Text nicht extrahiert werden kann
    """
    try:
        # Versuche, die Datei als UTF-8 zu dekodieren
        text = file_content.decode('utf-8', errors='replace')
        return text
    except UnicodeDecodeError:
        # Wenn UTF-8 fehlschlägt, versuche andere Codierungen
        encodings = ['iso-8859-1', 'windows-1252', 'latin-1']
        for enc in encodings:
            try:
                text = file_content.decode(enc, errors='replace')
                logger.info("Text erfolgreich mit %s-Kodierung dekodiert", enc)
                return text
            except UnicodeDecodeError:
                continue

        # Wenn alle Versuche fehlschlagen, verwende 'replace' mit UTF-8
        logger.warning("Konnte Kodierung nicht bestimmen, verwende UTF-8 mit Ersatzzeuchen")
        return file_content.decode('utf-8', errors='replace')


def _extract_text_from_rtf(file_path: str) -> str:
    """
    Extrahiert Text aus einer RTF-Datei.

    Args:
        file_path: Pfad zur RTF-Datei

    Returns:
        Extrahierter Text

    Raises:
        ValueError: Wenn der Text nicht extrahiert werden kann
    """
    striprtf_module = _safely_import('striprtf')
    if not striprtf_module:
        raise ImportError("striprtf ist erforderlich, um RTF-Dateien zu verarbeiten")

    try:
        # RTF-Dateien können unterschiedliche Kodierungen haben, versuche mit UTF-8
        # und setze Fehlerbehandlung auf 'replace' für nicht-decodierbare Zeichen
        with open(file_path, 'r', encoding='utf-8', errors='replace') as rtf_file:
            rtf_text = rtf_file.read()
        
        # Extrahiere den Text aus dem RTF
        text = striprtf_module.rtf_to_text(rtf_text)
        return text
    except Exception as e:
        logger.error("Fehler beim Extrahieren von Text aus RTF-Datei: %s", str(e))
        logger.debug(traceback.format_exc())
        raise ValueError(f"RTF-Extraktion fehlgeschlagen: {str(e)}") from e


def _extract_text_from_odt(file_path: str) -> str:
    """
    Extrahiert Text aus einer ODT-Datei.

    Args:
        file_path: Pfad zur ODT-Datei

    Returns:
        Extrahierter Text

    Raises:
        ValueError: Wenn der Text nicht extrahiert werden kann
    """
    odf_module = _safely_import('odf')
    if not odf_module:
        raise ImportError("odfpy ist erforderlich, um ODT-Dateien zu verarbeiten")

    try:
        # Importiere die Module dynamisch, um den Pylint-Fehler zu vermeiden
        # und um ein Fallback anbieten zu können, wenn sie nicht verfügbar sind
        odf_opendocument = _safely_import('odf.opendocument')
        odf_text = _safely_import('odf.text')
        
        if not odf_opendocument or not odf_text:
            logger.warning("Erforderliche ODT-Submodule nicht verfügbar")
            # Rückgabe eines einfachen Fehlertexts als Fallback
            return "[ODT-Inhalt konnte nicht extrahiert werden - Bibliothekskomponenten fehlen]"

        # Lade das ODT-Dokument
        doc = odf_opendocument.load(file_path)
        
        # Extrahiere alle Textabschnitte
        paragraphs = []
        for paragraph in doc.getElementsByType(odf_text.P):
            paragraphs.append(paragraph.plainText())
        
        # Verbinde alle Absätze zu einem Text
        text = '\n'.join(paragraphs)
        return text
    except Exception as e:
        logger.error("Fehler beim Extrahieren von Text aus ODT-Datei: %s", str(e))
        logger.debug(traceback.format_exc())
        raise ValueError(f"ODT-Extraktion fehlgeschlagen: {str(e)}") from e


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

    try:
        # Entferne Steuerzeichen außer Zeilenumbrüchen und Tabulatoren
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

        # Entferne mehrfache Leerzeichen
        text = re.sub(r' +', ' ', text)

        # Entferne mehrfache Zeilenumbrüche
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Entferne führende und abschließende Leerzeichen von jeder Zeile
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines]
        text = '\n'.join(cleaned_lines)

        # Kürze auf maximale Länge
        if len(text) > max_length:
            logger.warning("Text war zu lang (%s Zeichen) und wurde auf %s gekürzt", len(text), max_length)
            text = text[:max_length]

        return text
    except Exception as error:
        logger.error("Fehler bei der Textbereinigung: %s", str(error))
        # Fallback: Zumindest die Länge begrenzen
        return text[:max_length] if text and len(text) > max_length else text


def detect_language(text: str) -> str:
    """
    Erkennt die Sprache eines Textes.

    Args:
        text: Der zu analysierende Text

    Returns:
        Sprachcode (z.B. 'de', 'en', 'fr') oder 'unknown' bei Fehlern
    """
    if not text or len(text.strip()) < 10:
        logger.warning("Text zu kurz für Spracherkennung.")
        return "unknown"

    langdetect = _safely_import('langdetect')
    if not langdetect:
        logger.warning("langdetect ist nicht installiert, Spracherkennung nicht verfügbar")
        return "unknown"

    try:
        # Stichprobe nehmen für lange Texte (Leistungsoptimierung)
        sample_size = 10000
        sample = text[:sample_size] if len(text) > sample_size else text

        # Setze Seed für deterministische Ergebnisse
        langdetect.DetectorFactory.seed = 0

        # Sprache erkennen
        lang = langdetect.detect(sample)
        return lang
    except Exception as e:
        logger.error("Fehler bei der Spracherkennung: %s", str(e))
        return "unknown"


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Gibt Informationen über eine Datei zurück.

    Args:
        file_path: Pfad zur Datei

    Returns:
        Dictionary mit Dateiinformationen (Größe, Typ, etc.)
    """
    try:
        if not os.path.exists(file_path):
            logger.error("Datei existiert nicht: %s", file_path)
            return {'error': 'Datei existiert nicht'}

        stat_info = os.stat(file_path)

        return {
            'path': file_path,
            'name': os.path.basename(file_path),
            'extension': os.path.splitext(file_path)[1].lower(),
            'size': stat_info.st_size,
            'created': stat_info.st_ctime,
            'modified': stat_info.st_mtime,
            'exists': True
        }
    except Exception as error:
        logger.error("Fehler beim Abrufen von Dateiinformationen: %s", str(error))
        return {'error': str(error), 'path': file_path, 'exists': False}


def safe_file_operation(operation: Callable, *args, **kwargs) -> Tuple[bool, str]:
    """
    Führt eine Dateioperation sicher aus und fängt Fehler ab.

    Args:
        operation: Die auszuführende Funktion
        *args: Argumente für die Funktion
        **kwargs: Keyword-Argumente für die Funktion

    Returns:
        Tupel (Erfolg, Fehlermeldung)
    """
    try:
        operation(*args, **kwargs)
        return True, ""
    except Exception as e:
        error_msg = f"Fehler bei Dateioperation: {str(e)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        return False, error_msg


def safe_copy_file(source: str, destination: str) -> Tuple[bool, str]:
    """
    Kopiert eine Datei sicher und fängt Fehler ab.

    Args:
        source: Quellpfad
        destination: Zielpfad

    Returns:
        Tupel (Erfolg, Fehlermeldung)
    """
    return safe_file_operation(shutil.copy2, source, destination)


def safe_move_file(source: str, destination: str) -> Tuple[bool, str]:
    """
    Verschiebt eine Datei sicher und fängt Fehler ab.

    Args:
        source: Quellpfad
        destination: Zielpfad

    Returns:
        Tupel (Erfolg, Fehlermeldung)
    """
    return safe_file_operation(shutil.move, source, destination)


def safe_delete_file(file_path: str) -> Tuple[bool, str]:
    """
    Löscht eine Datei sicher und fängt Fehler ab.

    Args:
        file_path: Pfad zur zu löschenden Datei

    Returns:
        Tupel (Erfolg, Fehlermeldung)
    """
    return safe_file_operation(os.remove, file_path)


def safe_create_directory(directory_path: str) -> Tuple[bool, str]:
    """
    Erstellt ein Verzeichnis sicher und fängt Fehler ab.

    Args:
        directory_path: Pfad zum zu erstellenden Verzeichnis

    Returns:
        Tupel (Erfolg, Fehlermeldung)
    """
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True, ""
    except Exception as e:
        error_msg = f"Fehler beim Erstellen des Verzeichnisses: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
