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
    if not file_content:
        raise ValueError("Leerer Dateiinhalt")

    if not filename or not isinstance(filename, str):
        raise ValueError(f"Ungültiger Dateiname: {filename}")

    # Erweiterung bestimmen
    ext = os.path.splitext(filename.lower())[1]

    # Prüfen, ob der Dateityp unterstützt wird
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Nicht unterstütztes Dateiformat: {ext}")

    # Prüfen, ob alle Abhängigkeiten installiert sind
    if not are_dependencies_installed(ext):
        missing_deps = [dep for dep in DEPENDENCIES.get(ext, []) if not _check_dependency(dep)]
        raise ImportError(f"Fehlende Abhängigkeiten für {ext}: {', '.join(missing_deps)}")

    # Tempfile für binäre Dateien erstellen
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp:
            temp_path = temp.name
            temp.write(file_content)

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
            # Dieser Fall sollte durch die vorherige Prüfung abgefangen werden
            raise ValueError(f"Nicht unterstütztes Dateiformat: {ext}")

        return text
    except Exception as e:
        logger.error("Fehler beim Extrahieren von Text aus %s: %s", filename, str(e))
        logger.debug(traceback.format_exc())
        raise ValueError(f"Konnte Text nicht aus Datei extrahieren: {str(e)}") from e
    finally:
        # Temporäre Datei immer aufräumen
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                logger.warning("Konnte temporäre Datei nicht löschen")


def _extract_text_from_pdf(file_path: str) -> str:
    """
    Extrahiert Text aus einer PDF-Datei mit PyMuPDF (fitz).

    Args:
        file_path: Pfad zur PDF-Datei

    Returns:
        Extrahierter Text

    Raises:
        ValueError: Wenn der Text nicht extrahiert werden kann
    """
    fitz_module = _safely_import('fitz')
    if not fitz_module:
        raise ImportError("PyMuPDF (fitz) ist erforderlich, um PDF-Dateien zu verarbeiten")

    try:
        text = ""
        # Öffne das PDF-Dokument
        with fitz_module.open(file_path) as pdf_document:
            # Überprüfe, ob das Dokument Seiten hat
            num_pages = len(pdf_document)
            if num_pages == 0:
                logger.warning("Die PDF-Datei enthält keine Seiten")
                return ""

            # Extrahiere Text von jeder Seite
            for page_num in range(num_pages):
                page = pdf_document[page_num]
                # PyMuPDF bietet verschiedene Text-Extraktionsmodi
                # 'text' ist der Standardmodus, 'blocks' gibt strukturierten Text zurück
                page_text = page.get_text() or ""
                text += page_text + "\n"

                # Prüfen, ob die Seite Bilder enthält (für Debug-Zwecke)
                image_list = page.get_images(full=True)
                if len(image_list) > 0:
                    logger.debug("Seite %s enthält %s Bilder", page_num+1, len(image_list))

        if not text.strip():
            logger.warning("Die PDF-Datei enthält keinen extrahierbaren Text, möglicherweise ein gescanntes Dokument")

            # Option: Bei leeren PDFs können wir prüfen, ob es ein gescanntes Dokument ist
            # und eine OCR-Erkennung vorschlagen
            if num_pages > 0:
                logger.info(
                    "Die PDF enthält %s Seiten aber keinen Text. Möglicherweise ist OCR erforderlich.", num_pages)

        return text
    except Exception as e:
        logger.error("Fehler beim Extrahieren von Text aus PDF: %s", str(e))
        logger.debug(traceback.format_exc())
        raise ValueError(f"PDF-Extraktion fehlgeschlagen: {str(e)}") from e


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
