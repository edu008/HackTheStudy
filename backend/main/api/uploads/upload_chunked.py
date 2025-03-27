# api/upload_chunked.py
"""
Funktionen für das Hochladen großer Dateien in Chunks.
"""

import logging
import os
import time
import uuid

import redis
from core.models import Upload, db
from flask import jsonify, request

from api.auth import token_required
from . import api_bp
from .processing import initiate_processing
from .upload_core import create_error_response
from ..utils.file_utils import allowed_file, extract_text_from_file

# Redis-Client direkt erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://hackthestudy-backend-main:6379/0')
redis_client = redis.from_url(redis_url)

# Konfiguriere Logger
logger = logging.getLogger(__name__)

# Konfiguriere Chunk-Parameter
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB pro Chunk
MAX_CHUNKS = 10  # Maximale Anzahl von Chunks pro Datei

# Fehlercodes
ERROR_INVALID_INPUT = "INVALID_INPUT"
ERROR_PROCESSING_FAILED = "PROCESSING_FAILED"


def save_chunk(session_id, chunk_index, chunk_data):
    """
    Speichert einen Chunk in Redis.
    """
    try:
        redis_client.hset(f"chunks:{session_id}", f"chunk:{chunk_index}", chunk_data)
        logger.info("Chunk %s für Session %s gespeichert", chunk_index, session_id)
        return True
    except Exception as e:
        logger.error("Fehler beim Speichern von Chunk %s für Session %s: %s", chunk_index, session_id, str(e))
        return False


def combine_chunks(session_id):
    """
    Kombiniert alle Chunks einer Session zu einer vollständigen Datei.
    """
    try:
        # Hole alle Chunks
        chunks = redis_client.hgetall(f"chunks:{session_id}")

        # Sortiere die Chunks nach Index
        sorted_chunks = sorted(chunks.items(), key=lambda x: int(x[0].decode('utf-8').split(':')[1]))

        # Kombiniere die Chunks
        combined_data = b''.join([chunk[1] for chunk in sorted_chunks])

        return combined_data
    except Exception as e:
        logger.error("Fehler beim Kombinieren der Chunks für Session %s: %s", session_id, str(e))
        return None


def cleanup_chunks(session_id):
    """
    Löscht alle Chunks einer Session.
    """
    try:
        redis_client.delete(f"chunks:{session_id}")
        redis_client.delete(f"chunk_upload_progress:{session_id}")
        redis_client.delete(f"chunk_upload_filename:{session_id}")
        logger.info("Chunks für Session %s gelöscht", session_id)
        return True
    except Exception as e:
        logger.error("Fehler beim Löschen der Chunks für Session %s: %s", session_id, str(e))
        return False


@api_bp.route('/upload/chunk', methods=['POST', 'OPTIONS'])
@token_required
def upload_chunk():
    """
    Verarbeitet Chunk-Uploads für große Dateien.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        return jsonify(success=True)

    try:
        # Überprüfe, ob die erforderlichen Parameter vorhanden sind
        if 'chunk' not in request.files:
            return create_error_response(
                "Keine Chunk-Datei gefunden",
                ERROR_INVALID_INPUT,
                {"detail": "No chunk part"}
            )

        chunk = request.files['chunk']
        if chunk.filename == '':
            return create_error_response(
                "Keine Datei ausgewählt",
                ERROR_INVALID_INPUT,
                {"detail": "No file selected"}
            )

        # Hole die Session-ID und den Chunk-Index
        session_id = request.form.get('session_id')
        chunk_index = request.form.get('chunk_index')
        total_chunks = request.form.get('total_chunks')
        filename = request.form.get('filename')

        # Überprüfe, ob alle erforderlichen Parameter vorhanden sind
        if not session_id or not chunk_index or not total_chunks or not filename:
            return create_error_response(
                "Fehlende Parameter",
                ERROR_INVALID_INPUT,
                {"detail": "Missing required parameters"}
            )

        # Konvertiere zu Integer
        try:
            chunk_index = int(chunk_index)
            total_chunks = int(total_chunks)
        except ValueError:
            return create_error_response(
                "Ungültige Parameter",
                ERROR_INVALID_INPUT,
                {"detail": "Invalid parameters"}
            )

        # Überprüfe, ob die Datei zulässig ist
        if not allowed_file(filename):
            return create_error_response(
                "Dateityp nicht unterstützt",
                ERROR_INVALID_INPUT,
                {"detail": "File type not allowed"}
            )

        # Überprüfe, ob die maximale Anzahl von Chunks überschritten wurde
        if total_chunks > MAX_CHUNKS:
            return create_error_response(
                "Zu viele Chunks",
                ERROR_INVALID_INPUT,
                {"detail": f"Maximum of {MAX_CHUNKS} chunks allowed"}
            )

        # Speichere den Dateinamen in Redis
        redis_client.set(f"chunk_upload_filename:{session_id}", filename)

        # Hole die Benutzer-ID
        user_id = getattr(request, 'user_id', None)

        # Speichere den Chunk
        chunk_data = chunk.read()
        if not save_chunk(session_id, chunk_index, chunk_data):
            return create_error_response(
                "Fehler beim Speichern des Chunks",
                ERROR_PROCESSING_FAILED,
                {"detail": "Failed to save chunk"}
            )

        # Aktualisiere den Fortschritt
        progress = (chunk_index + 1) / total_chunks * 100
        redis_client.set(f"chunk_upload_progress:{session_id}", progress)

        # Überprüfe, ob alle Chunks hochgeladen wurden
        if chunk_index == total_chunks - 1:
            # Kombiniere die Chunks
            combined_data = combine_chunks(session_id)
            if not combined_data:
                return create_error_response(
                    "Fehler beim Kombinieren der Chunks",
                    ERROR_PROCESSING_FAILED,
                    {"detail": "Failed to combine chunks"}
                )

            # Extrahiere Text aus der kombinierten Datei
            try:
                from io import BytesIO
                file_obj = BytesIO(combined_data)
                file_obj.filename = filename

                text_content, file_type, file_size, page_count = extract_text_from_file(file_obj)

                if not text_content:
                    cleanup_chunks(session_id)
                    return create_error_response(
                        "Textextraktion fehlgeschlagen",
                        ERROR_PROCESSING_FAILED,
                        {"detail": "Failed to extract text from file"}
                    )

                # Erstelle einen neuen Upload-Eintrag in der Datenbank
                new_upload = Upload(
                    session_id=session_id,
                    filename=filename,
                    content=text_content,
                    file_type=file_type,
                    file_size=file_size,
                    page_count=page_count,
                    user_id=user_id if user_id else None
                )

                db.session.add(new_upload)
                db.session.commit()

                # Lösche die Chunks
                cleanup_chunks(session_id)

                # Leite zur Verarbeitung weiter
                return initiate_processing(session_id, new_upload.id)

            except Exception as e:
                logger.error("Fehler bei der Textextraktion: %s", str(e))
                cleanup_chunks(session_id)
                return create_error_response(
                    "Fehler bei der Textextraktion",
                    ERROR_PROCESSING_FAILED,
                    {"detail": str(e)}
                )

        # Wenn nicht alle Chunks hochgeladen wurden, gib den aktuellen Fortschritt zurück
        return jsonify({
            "success": True,
            "message": f"Chunk {chunk_index} von {total_chunks} erfolgreich hochgeladen",
            "session_id": session_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "progress": progress
        })

    except Exception as e:
        logger.error("Unerwarteter Fehler beim Chunk-Upload: %s", str(e))
        return create_error_response(
            "Unerwarteter Fehler",
            "UNEXPECTED_ERROR",
            {"detail": str(e)}
        )


@api_bp.route('/upload/progress/<session_id>', methods=['GET', 'OPTIONS'])
@token_required
def get_upload_progress(session_id):
    """
    Gibt den Fortschritt eines Chunk-Uploads zurück.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        return jsonify(success=True)

    try:
        # Hole den Fortschritt aus Redis
        progress = redis_client.get(f"chunk_upload_progress:{session_id}")
        if progress:
            progress = float(progress.decode('utf-8'))
        else:
            progress = 0

        # Hole den Dateinamen aus Redis
        filename = redis_client.get(f"chunk_upload_filename:{session_id}")
        if filename:
            filename = filename.decode('utf-8')
        else:
            filename = None

        return jsonify({
            "success": True,
            "session_id": session_id,
            "progress": progress,
            "filename": filename,
            "status": "uploading" if progress < 100 else "processing"
        })

    except Exception as e:
        logger.error("Fehler beim Abrufen des Fortschritts für Session %s: %s", session_id, str(e))
        return jsonify({
            "success": False,
            "message": "Fehler beim Abrufen des Fortschritts",
            "error": {"code": ERROR_PROCESSING_FAILED, "detail": str(e)}
        }), 500
