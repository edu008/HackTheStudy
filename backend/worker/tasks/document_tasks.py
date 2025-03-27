"""
Dokumentenverarbeitungs-Tasks für den Worker.
"""
import json
import logging
import os
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


def register_tasks(celery_app):
    """
    Registriert alle Dokumentenverarbeitungs-Tasks mit der Celery-App.

    Args:
        celery_app: Die Celery-App-Instanz.

    Returns:
        dict: Dictionary mit den registrierten Tasks.
    """
    tasks = {}

    @celery_app.task(name='document.process_upload', bind=True, max_retries=3)
    def process_upload(self, upload_id, file_path, file_type, options=None):
        """
        Verarbeitet eine hochgeladene Datei und extrahiert Text.

        Args:
            upload_id (str): Eindeutige ID des Uploads.
            file_path (str): Pfad zur Datei.
            file_type (str): Dateityp (pdf, docx, txt, ...).
            options (dict, optional): Zusätzliche Verarbeitungsoptionen.

        Returns:
            dict: Ergebnis der Verarbeitung.
        """
        logger.info("Verarbeite Upload %s vom Typ %s: %s", upload_id, file_type, file_path)

        options = options or {}
        result = {
            'upload_id': upload_id,
            'file_type': file_type,
            'status': 'processing',
            'started_at': datetime.now().isoformat(),
            'text_content': None,
            'chunks': [],
            'error': None
        }

        try:
            # 1. Überprüfe, ob die Datei existiert
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

            # 2. Text basierend auf Dateityp extrahieren
            if file_type.lower() == 'pdf':
                text_content, chunks = extract_text_from_pdf(file_path, **options)
            elif file_type.lower() == 'docx':
                text_content, chunks = extract_text_from_docx(file_path, **options)
            elif file_type.lower() == 'txt':
                text_content, chunks = extract_text_from_txt(file_path, **options)
            else:
                raise ValueError(f"Nicht unterstützter Dateityp: {file_type}")

            # 3. Ergebnis speichern
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()
            result['text_content'] = text_content
            result['chunks'] = chunks

            # 4. Aktualisiere den Status in Redis
            update_upload_status(upload_id, 'completed', {
                'chunks_count': len(chunks),
                'text_length': len(text_content) if text_content else 0
            })

            return result

        except Exception as e:
            # Bei Fehler: Status aktualisieren und erneut versuchen
            error_message = str(e)
            logger.error("Fehler bei der Verarbeitung von Upload %s: %s", upload_id, error_message)

            result['status'] = 'error'
            result['error'] = error_message
            result['completed_at'] = datetime.now().isoformat()

            # Aktualisiere den Status in Redis
            update_upload_status(upload_id, 'error', {'error': error_message})

            # Wiederhole den Task bei bestimmten Fehlern
            if not isinstance(e, (FileNotFoundError, ValueError)):
                try:
                    self.retry(countdown=30, exc=e)
                except self.MaxRetriesExceededError:
                    logger.error("Maximale Anzahl an Wiederholungen für Upload %s erreicht", upload_id)

            return result

    tasks['document.process_upload'] = process_upload

    @celery_app.task(name='document.merge_chunks', bind=True)
    def merge_chunks(self, upload_id, chunk_files, output_path):
        """
        Zusammenführen von Upload-Chunks zu einer vollständigen Datei.

        Args:
            upload_id (str): Eindeutige ID des Uploads.
            chunk_files (list): Liste der Chunk-Dateipfade.
            output_path (str): Pfad für die zusammengeführte Datei.

        Returns:
            dict: Ergebnis der Zusammenführung.
        """
        logger.info("Führe %s Chunks für Upload %s zusammen", len(chunk_files), upload_id)

        result = {
            'upload_id': upload_id,
            'status': 'processing',
            'started_at': datetime.now().isoformat(),
            'output_path': output_path,
            'error': None
        }

        try:
            # Prüfe, ob alle Chunk-Dateien existieren
            missing_chunks = [f for f in chunk_files if not os.path.exists(f)]
            if missing_chunks:
                raise FileNotFoundError(f"Fehlende Chunk-Dateien: {missing_chunks}")

            # Erstelle Zielverzeichnis, falls nicht vorhanden
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Zusammenführen der Chunks
            with open(output_path, 'wb') as outfile:
                for chunk_file in sorted(chunk_files, key=lambda x: int(os.path.basename(x).split('_')[1])):
                    with open(chunk_file, 'rb') as infile:
                        outfile.write(infile.read())

            # Aktualisiere Status
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()
            result['file_size'] = os.path.getsize(output_path)

            # Aktualisiere Upload-Status in Redis
            update_upload_status(upload_id, 'merged', {
                'file_size': result['file_size'],
                'output_path': output_path
            })

            return result

        except Exception as e:
            error_message = str(e)
            logger.error("Fehler beim Zusammenführen von Chunks für Upload %s: %s", upload_id, error_message)

            result['status'] = 'error'
            result['error'] = error_message
            result['completed_at'] = datetime.now().isoformat()

            # Aktualisiere Status in Redis
            update_upload_status(upload_id, 'error', {'error': error_message})

            return result

    tasks['document.merge_chunks'] = merge_chunks

    return tasks

# --- Hilfsfunktionen für die Dokumentenverarbeitung ---


def update_upload_status(upload_id, status, metadata=None):
    """
    Aktualisiert den Status eines Uploads in Redis.

    Args:
        upload_id (str): Die Upload-ID.
        status (str): Der neue Status.
        metadata (dict, optional): Zusätzliche Metadaten.
    """
    try:
        from redis_utils.client import get_redis_client
        redis_client = get_redis_client()

        if not redis_client:
            logger.warning(
                f"Redis-Client nicht verfügbar, Upload-Status {status} für {upload_id} konnte nicht gespeichert werden")
            return

        # Status-Update vorbereiten
        update_data = {
            'status': status,
            'updated_at': datetime.now().isoformat()
        }

        if metadata:
            update_data.update(metadata)

        # Status in Redis speichern
        redis_client.hset(f"upload:{upload_id}", mapping=update_data)
        redis_client.expire(f"upload:{upload_id}", 86400 * 7)  # 7 Tage TTL

        # Event für Frontend-Benachrichtigung veröffentlichen
        event_data = {
            'upload_id': upload_id,
            'status': status,
            'timestamp': update_data['updated_at']
        }
        if metadata:
            event_data.update(metadata)

        redis_client.publish('upload_status_channel', json.dumps(event_data))

    except Exception as e:
        logger.error("Fehler beim Aktualisieren des Upload-Status für %s: %s", upload_id, e)


def extract_text_from_pdf(file_path, **options):
    """
    Extrahiert Text aus einer PDF-Datei.

    Args:
        file_path (str): Pfad zur PDF-Datei.
        **options: Zusätzliche Optionen für die Textextraktion.

    Returns:
        tuple: (vollständiger Text, Liste von Textchunks)
    """
    try:
        logger.info("Extrahiere Text aus PDF: %s", file_path)

        # Versuche zuerst mit PyMuPDF (schneller und besser für die meisten PDFs)
        import fitz  # PyMuPDF

        text_content = ""
        chunks = []
        chunk_size = options.get('chunk_size', 4000)

        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            text_content += page_text + "\n\n"

            # Füge Seitentext als Chunk hinzu
            chunks.append({
                'page': page_num + 1,
                'text': page_text,
                'chars': len(page_text)
            })

        doc.close()

        return text_content, chunks

    except ImportError:
        # Fallback zu PyPDF2
        logger.warning("PyMuPDF nicht verfügbar, verwende PyPDF2 als Fallback")

        from PyPDF2 import PdfReader

        text_content = ""
        chunks = []

        reader = PdfReader(file_path)
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            text_content += page_text + "\n\n"

            chunks.append({
                'page': i + 1,
                'text': page_text,
                'chars': len(page_text)
            })

        return text_content, chunks

    except Exception as e:
        logger.error("Fehler bei der Textextraktion aus PDF: %s", e)
        raise


def extract_text_from_docx(file_path, **options):
    """
    Extrahiert Text aus einer DOCX-Datei.

    Args:
        file_path (str): Pfad zur DOCX-Datei.
        **options: Zusätzliche Optionen für die Textextraktion.

    Returns:
        tuple: (vollständiger Text, Liste von Textchunks)
    """
    try:
        logger.info("Extrahiere Text aus DOCX: %s", file_path)

        from docx import Document

        document = Document(file_path)
        paragraphs = [p.text for p in document.paragraphs]
        text_content = "\n".join(paragraphs)

        # Erstelle Chunks basierend auf Absätzen
        chunks = []
        current_chunk = ""
        chunk_num = 1

        for p in paragraphs:
            if p.strip():  # Ignoriere leere Absätze
                if len(current_chunk) + len(p) > 4000:  # Maximale Chunk-Größe
                    if current_chunk:
                        chunks.append({
                            'chunk': chunk_num,
                            'text': current_chunk,
                            'chars': len(current_chunk)
                        })
                        chunk_num += 1
                        current_chunk = p
                else:
                    current_chunk += ("\n" if current_chunk else "") + p

        # Letzten Chunk hinzufügen
        if current_chunk:
            chunks.append({
                'chunk': chunk_num,
                'text': current_chunk,
                'chars': len(current_chunk)
            })

        return text_content, chunks

    except Exception as e:
        logger.error("Fehler bei der Textextraktion aus DOCX: %s", e)
        raise


def extract_text_from_txt(file_path, **options):
    """
    Extrahiert Text aus einer TXT-Datei.

    Args:
        file_path (str): Pfad zur TXT-Datei.
        **options: Zusätzliche Optionen für die Textextraktion.

    Returns:
        tuple: (vollständiger Text, Liste von Textchunks)
    """
    try:
        logger.info("Extrahiere Text aus TXT: %s", file_path)

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            text_content = f.read()

        # Erstelle Chunks basierend auf Zeilenlänge
        chunk_size = options.get('chunk_size', 4000)
        lines = text_content.split('\n')

        chunks = []
        current_chunk = ""
        chunk_num = 1

        for line in lines:
            if len(current_chunk) + len(line) > chunk_size:
                if current_chunk:
                    chunks.append({
                        'chunk': chunk_num,
                        'text': current_chunk,
                        'chars': len(current_chunk)
                    })
                    chunk_num += 1
                    current_chunk = line
            else:
                current_chunk += ("\n" if current_chunk else "") + line

        # Letzten Chunk hinzufügen
        if current_chunk:
            chunks.append({
                'chunk': chunk_num,
                'text': current_chunk,
                'chars': len(current_chunk)
            })

        return text_content, chunks

    except Exception as e:
        logger.error("Fehler bei der Textextraktion aus TXT: %s", e)
        raise
