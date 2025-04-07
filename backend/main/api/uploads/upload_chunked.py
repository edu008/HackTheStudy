# api/upload_chunked.py
"""
Implementierung des Chunk-basierten File-Uploads für große Dateien.

Diese Implementierung unterstützt:
- Initialisierung eines Chunk-Uploads
- Hochladen einzelner Chunks
- Zusammenführen der hochgeladenen Chunks
- Fortschrittsüberwachung
"""

import logging
import os
import time
import json
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime

from flask import jsonify, request, current_app, g, Response, make_response
from werkzeug.utils import secure_filename
from flask_jwt_extended import jwt_required, get_jwt_identity

from core.models import db, Upload, UploadedFile, ProcessingTask, User
from core.redis_client import get_redis_client
from utils.common import generate_random_id, get_upload_dir
from api.auth import token_required
from .session_management import manage_user_sessions, update_session_timestamp, update_session_info, create_or_refresh_session, enforce_session_limit
from celery import Celery
from config.config import config
from . import uploads_bp

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Chunk-Einstellungen
CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', 5 * 1024 * 1024))  # 5MB default
MAX_CHUNKS = int(os.environ.get('MAX_CHUNKS', 1000))

# Import für _start_processing anpassen
try:
    # Lokaler Import (Entwicklung)
    from api.uploads._start_processing import _start_processing
    logger.info("Standard-Import von _start_processing erfolgreich")
except ImportError:
    try:
        # Relativer Import (Container)
        from ._start_processing import _start_processing
        logger.info("Relativer Import von _start_processing erfolgreich")
    except ImportError:
        try:
            # Absoluter Import (Container)
            from main.api.uploads._start_processing import _start_processing
            logger.info("Absoluter Import von _start_processing erfolgreich")
        except ImportError as e:
            logger.error(f"Konnte _start_processing nicht importieren: {e}")
            # Dummy-Funktion als Fallback
            def _start_processing(session_id, task_id):
                logger.error(f"Dummy _start_processing aufgerufen für Session {session_id}, Task {task_id}")
                return {
                    'task_id': task_id,
                    'session_id': session_id,
                    'status': 'error',
                    'error': 'Import-Fehler: _start_processing konnte nicht importiert werden'
                }

# Stelle lokale Celery Sender Instanz wieder her
celery_sender = Celery('main_chunked_sender', broker=config.redis_url)
logger.info(f"Celery Sender (lokal in upload_chunked) konfiguriert mit Broker: {config.redis_url.replace(config.redis_password, '****') if config.redis_password else config.redis_url}")

@uploads_bp.route('/upload/chunk', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True)
def upload_chunk():
    """Empfängt entweder die Initialisierungsanfrage oder einen einzelnen Chunk."""
        if request.method == 'OPTIONS':
        # Korrekte OPTIONS-Antwort mit CORS Headern
        response = make_response()
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        return add_cors_headers(response)

    # Unterscheidung zwischen Initialisierung und Chunk-Upload
    is_init_request = request.form.get('init') == 'true' or request.args.get('init') == 'true'
    if is_init_request:
            return _initialize_chunked_upload()
    else:
        # Chunk-Upload verarbeiten
        session_id = request.form.get('session_id') or request.args.get('session_id')
        chunk_number_str = request.form.get('chunk_number') or request.args.get('chunk_number')
        file_chunk = request.files.get('file')

        if not session_id or not chunk_number_str or not file_chunk:
            missing = []
            if not session_id: missing.append('session_id')
            if not chunk_number_str: missing.append('chunk_number')
            if not file_chunk: missing.append('file')
            return create_error_response(f"Fehlende Daten: {', '.join(missing)}", "MISSING_CHUNK_DATA", status_code=400)

        try:
            chunk_number = int(chunk_number_str)
        except ValueError:
            return create_error_response("Ungültige Chunk-Nummer", "INVALID_CHUNK_NUMBER", status_code=400)

        return _handle_chunk(session_id, chunk_number, file_chunk)

def get_upload_progress(session_id):
    """
    Gibt den Fortschritt eines Chunk-Uploads zurück.
    
    Args:
        session_id: Die Session-ID des Uploads
        
    Returns:
        JSON-Antwort mit dem Fortschritt des Uploads
    """
    try:
        # Prüfe, ob die Session existiert
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            logger.error(f"Upload-Session nicht gefunden: {session_id}")
            return jsonify({
                "success": False,
                "error": {"code": "SESSION_NOT_FOUND", "message": "Upload-Session nicht gefunden"}
            }), 404
            
        # Hole die Chunk-Informationen aus Redis
        redis_client = get_redis_client()
        chunk_data = redis_client.hgetall(f"upload:chunks:{session_id}")
        
        # Hole die Meta-Informationen aus Redis
        meta_data = redis_client.hgetall(f"upload:meta:{session_id}")
        
        # Konvertiere die Redis-Daten
        total_chunks = 0
        uploaded_chunks = 0
        uploaded_size = 0
        
        # Chunks verarbeiten
        for chunk_index, chunk_size in chunk_data.items():
            if isinstance(chunk_index, bytes):
                chunk_index = chunk_index.decode('utf-8')
            if isinstance(chunk_size, bytes):
                chunk_size = chunk_size.decode('utf-8')
                
            uploaded_size += int(chunk_size)
            uploaded_chunks += 1
        
        # Meta-Daten verarbeiten
        meta_dict = {}
        for key, value in meta_data.items():
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            meta_dict[key] = value
        
        # Gesamtanzahl der Chunks aus Meta-Daten oder Standard verwenden
        total_chunks = int(meta_dict.get('total_chunks', 1))
        
        # Berechne den Fortschritt
        progress = (uploaded_chunks / total_chunks) * 100 if total_chunks > 0 else 0
        
        # Status ermitteln
        status = upload.processing_status or "unknown"
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "filename": upload.file_name_1,
            "total_size": int(meta_dict.get('total_size', 0)),
            "uploaded_size": uploaded_size,
            "uploaded_chunks": uploaded_chunks,
            "total_chunks": total_chunks,
            "progress": progress,
            "status": status,
            "started_at": upload.created_at.isoformat() if upload.created_at else None,
            "last_activity": upload.updated_at.isoformat() if upload.updated_at else None
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Upload-Fortschritts: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {"code": "PROGRESS_ERROR", "message": f"Fehler beim Abrufen des Fortschritts: {str(e)}"}
        }), 500

def _initialize_chunked_upload():
    """
    Initialisiert einen neuen Chunk-basierten Upload.
    
    Returns:
        JSON-Antwort mit der Session-ID für den Chunk-Upload
    """
    try:
        # Debug-Logging für die eingehende Anfrage
        logger.info(f"Initialisierung eines Upload angefordert. Methode: {request.method}, Content-Type: {request.content_type}")
        logger.info(f"Form-Daten: {request.form}")
        logger.info(f"Query-Daten: {request.args}")
        
        # Parameter aus verschiedenen Quellen extrahieren
        # 1. Aus Form-Daten
        filename = request.form.get('filename', request.form.get('file_name'))
        total_chunks_str = request.form.get('total_chunks')
        total_size_str = request.form.get('total_size')
        
        # 2. Aus Query-Parametern, falls nicht in Form-Daten vorhanden
        if not filename:
            filename = request.args.get('filename', request.args.get('file_name'))
        if not total_chunks_str:
            total_chunks_str = request.args.get('total_chunks')
        if not total_size_str:
            total_size_str = request.args.get('total_size')
        
        # 3. Aus JSON-Daten, falls nicht in Form oder Query vorhanden
        if request.is_json:
            json_data = request.get_json()
            if json_data:
                logger.info(f"JSON-Daten: {json_data}")
                if not filename:
                    filename = json_data.get('filename', json_data.get('file_name'))
                if not total_chunks_str:
                    total_chunks_str = json_data.get('total_chunks')
                if not total_size_str:
                    total_size_str = json_data.get('total_size')
        
        # Prüfen, ob alle erforderlichen Parameter vorhanden sind
        missing_params = []
        if not filename:
            missing_params.append('filename/file_name')
        if not total_chunks_str:
            missing_params.append('total_chunks')
        if not total_size_str:
            missing_params.append('total_size')
            
        if missing_params:
            logger.error(f"Fehlende Parameter: {', '.join(missing_params)}")
            return jsonify({
                "success": False,
                "error": {"code": "MISSING_PARAMETER", "message": f"Fehlende Parameter: {', '.join(missing_params)}"}
            }), 400
        
        # Parameter konvertieren
        try:
            total_chunks = int(total_chunks_str)
            total_size = int(total_size_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Fehler beim Konvertieren der Parameter: {str(e)}")
            return jsonify({
                "success": False,
                "error": {"code": "INVALID_PARAMETERS", "message": f"Ungültige Parameter: {str(e)}"}
            }), 400
        
        # Prüfe, ob die Anzahl der Chunks gültig ist
        if total_chunks <= 0 or total_chunks > MAX_CHUNKS:
            logger.error(f"Ungültige Anzahl von Chunks: {total_chunks}")
            return jsonify({
                "success": False,
                "error": {"code": "INVALID_CHUNK_COUNT", "message": f"Ungültige Anzahl von Chunks (max. {MAX_CHUNKS})"}
            }), 400
            
        # Prüfe, ob die Dateigröße gültig ist
        max_size = CHUNK_SIZE * MAX_CHUNKS
        if total_size <= 0 or total_size > max_size:
            logger.error(f"Ungültige Dateigröße: {total_size}")
            return jsonify({
                "success": False,
                "error": {"code": "INVALID_FILE_SIZE", "message": f"Ungültige Dateigröße (max. {max_size/1024/1024} MB)"}
            }), 400
            
        # Session-ID generieren oder aus Request holen
        session_id = request.form.get('session_id') or request.args.get('session_id') or str(uuid.uuid4())
        
        # Upload-Verzeichnis erstellen
        upload_dir = get_upload_dir(session_id)
        os.makedirs(upload_dir, exist_ok=True)
        
        # Redis-Metadaten initialisieren
        try:
            redis_client = get_redis_client()
            redis_key_meta = f"upload:meta:{session_id}"
            redis_key_chunks = f"upload:chunks:{session_id}"
            redis_client.hmset(redis_key_meta, {
                "filename": filename,
                "total_chunks": total_chunks,
                "total_size": total_size,
                "status": "initializing",
                "timestamp": time.time(),
                "uploaded_chunks": 0
            })
            redis_client.expire(redis_key_meta, 86400)
        except Exception as redis_error:
            logger.error(f"Redis-Fehler bei Chunk-Initialisierung: {redis_error}")
        
        # Benutzer-ID ermitteln (wie in upload_core.py)
        user_id = None
        jwt_user_id = g.get('user_id')
        if jwt_user_id:
            user = User.query.filter_by(id=jwt_user_id).first()
            if user: user_id = user.id
        logger.info(f"Initialisiere Chunk-Upload für Benutzer: {user_id}")
        
        # Session Limit prüfen (wie in upload_core.py)
        if user_id:
            try:
                enforce_session_limit(user_id, 5)
            except Exception as limit_err:
                logger.error(f"Fehler beim Anwenden des Session-Limits (Chunked): {limit_err}")
        
        # Upload-Datensatz in DB erstellen
        try:
            safe_filename = secure_filename(filename) or f"upload_{session_id}"
            # Sprache aus Metadaten oder Default
            upload_language = request.form.get('language', 'de')

            new_upload = Upload(
                id=str(uuid.uuid4()),
                session_id=session_id,
                user_id=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_used_at=datetime.utcnow(),
                overall_processing_status="uploading",
                upload_metadata=json.dumps({
                    "filename": safe_filename,
                    "total_size": total_size,
                    "total_chunks": total_chunks,
                    "language": upload_language,
                    "upload_type": "chunked"
                })
            )
            db.session.add(new_upload)
            db.session.commit()
            logger.info(f"Neuer Upload (Chunked) {new_upload.id} für Session {session_id} erstellt.")
            
        except Exception as db_error:
            logger.error(f"DB-Fehler bei Chunk-Initialisierung: {db_error}")
            db.session.rollback()
            return jsonify({
                "success": False,
                "error": {"code": "DATABASE_ERROR", "message": f"DB-Fehler: {db_error}"}
            }), 500
        
        logger.info(f"Chunk-Upload erfolgreich initialisiert: {filename}, Session: {session_id}")
        return jsonify({
            "success": True,
            "message": "Chunk-Upload initialisiert",
            "session_id": session_id,
            "upload_id": new_upload.id,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total_chunks
        }), 201
        
    except Exception as e:
        logger.error(f"Fehler bei der Initialisierung des Chunk-Uploads: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {"code": "INIT_ERROR", "message": f"Initialisierungsfehler: {str(e)}"}
        }), 500

def _handle_chunk(session_id, chunk_number, file_chunk):
    # ... (Implementierung bleibt)
    pass

@uploads_bp.route('/upload/complete_chunk', methods=['POST', 'OPTIONS'])
def complete_chunked_upload_route():
    """Route zum Abschließen eines Chunked Uploads."""
    if request.method == 'OPTIONS':
        # Korrekte OPTIONS-Antwort mit CORS Headern
        response = make_response()
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        return add_cors_headers(response)

    # Extrahiere session_id und rufe die Logik-Funktion auf
    session_id = request.form.get('session_id') or request.args.get('session_id') or (request.is_json and request.get_json().get('session_id'))
    if not session_id:
         return create_error_response("Session ID fehlt", "MISSING_SESSION_ID", status_code=400)
    
    # Rufe die eigentliche Logik auf (ohne Unterstrich)
    return complete_chunked_upload(session_id)

def complete_chunked_upload(session_id):
    """Setzt die Chunks zusammen, erstellt UploadedFile und startet den Worker-Task."""
    logger.info(f"Versuche Chunk-Upload für Session {session_id} abzuschließen.")
    upload_dir = get_upload_dir(session_id)
    redis_client = get_redis_client()
    redis_key_meta = f"upload:meta:{session_id}"
    redis_key_chunks = f"upload:chunks:{session_id}"

    # 1. Metadaten aus Redis holen
    upload_meta = redis_client.hgetall(redis_key_meta)
    if not upload_meta:
        logger.error(f"Keine Metadaten in Redis für Session {session_id} gefunden.")
        # Optional: Versuche aus DB zu laden?
        upload = Upload.query.filter_by(session_id=session_id).first()
        if upload and isinstance(upload.upload_metadata, dict):
             upload_meta = upload.upload_metadata
             upload_meta[b'filename'] = upload_meta.get('filename', f"upload_{session_id}").encode('utf-8')
             upload_meta[b'total_chunks'] = str(upload_meta.get('total_chunks', 0)).encode('utf-8')
             upload_meta[b'total_size'] = str(upload_meta.get('total_size', 0)).encode('utf-8')
             logger.info("Metadaten aus DB-Fallback geladen.")
        else:
             return create_error_response("Metadaten für Upload nicht gefunden", "METADATA_NOT_FOUND", status_code=404)

    try:
        filename = upload_meta.get(b'filename', b'unknown_file').decode('utf-8')
        total_chunks = int(upload_meta.get(b'total_chunks', b'0'))
        total_size = int(upload_meta.get(b'total_size', b'0'))
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Ungültige Metadaten für Session {session_id}: {e}")
        return create_error_response("Ungültige Upload-Metadaten", "INVALID_METADATA", status_code=400)

    # 2. Zugehörigen Upload-Datensatz finden
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        logger.error(f"Kein Upload-Datensatz für Session {session_id} gefunden.")
        return create_error_response("Upload-Datensatz nicht gefunden", "UPLOAD_NOT_FOUND", status_code=404)

    # 3. Anzahl der vorhandenen Chunk-Dateien prüfen
    try:
        chunk_files = sorted([f for f in os.listdir(upload_dir) if f.startswith('chunk_')], key=lambda x: int(x.split('_')[1]))
        num_chunk_files = len(chunk_files)
        logger.info(f"Gefundene Chunk-Dateien für Session {session_id}: {num_chunk_files}/{total_chunks}")
    except FileNotFoundError:
         logger.error(f"Upload-Verzeichnis für Session {session_id} nicht gefunden.")
         upload.overall_processing_status = 'error'
         upload.error_message = "Upload directory missing"
        db.session.commit()
         return create_error_response("Upload-Verzeichnis fehlt", "DIRECTORY_MISSING", status_code=500)

    # 4. Prüfen, ob alle Chunks vorhanden sind
    # Wir verwenden die Anzahl der Dateien als Indikator
    if num_chunk_files != total_chunks:
        logger.warning(f"Nicht alle Chunks für Session {session_id} vorhanden ({num_chunk_files}/{total_chunks}). Abbruch.")
        return create_error_response(f"Nicht alle Teile hochgeladen ({num_chunk_files}/{total_chunks})", "INCOMPLETE_UPLOAD", status_code=400)

    # 5. Datei zusammensetzen und UploadedFile erstellen
    final_file_content = bytearray()
    try:
        logger.info(f"Setze Datei '{filename}' aus {num_chunk_files} Chunks zusammen...")
        for chunk_filename in chunk_files:
            chunk_path = os.path.join(upload_dir, chunk_filename)
            with open(chunk_path, 'rb') as f_chunk:
                final_file_content.extend(f_chunk.read())

        # Größe prüfen
        final_size = len(final_file_content)
        if final_size != total_size:
             logger.warning(f"Endgültige Dateigröße ({final_size}) stimmt nicht mit erwarteter Größe ({total_size}) überein für Session {session_id}.")
             # Trotzdem fortfahren?

        # MIME-Typ bestimmen (optional, könnte aus Metadaten kommen)
        mime_type, _ = mimetypes.guess_type(filename)

        # UploadedFile-Eintrag erstellen
        uploaded_file = UploadedFile(
            id=str(uuid.uuid4()),
            upload_id=upload.id,
            file_name=filename, # Originalname aus Metadaten
            mime_type=mime_type,
            file_size=final_size,
            file_content=bytes(final_file_content), # In bytes umwandeln
            extraction_status='pending',
            created_at=datetime.utcnow()
        )
        db.session.add(uploaded_file)

        # Upload-Status aktualisieren
        upload.overall_processing_status = 'queued'
        upload.updated_at = datetime.utcnow()
        upload.last_used_at = datetime.utcnow()
        # Metadaten ggf. bereinigen oder aktualisieren
        if isinstance(upload.upload_metadata, dict):
            upload.upload_metadata.pop('total_chunks', None)
            upload.upload_metadata['final_filename'] = filename
            upload.upload_metadata['final_size'] = final_size
        else: # Falls als JSON-String gespeichert
            try:
                meta = json.loads(upload.upload_metadata or '{}')
                meta.pop('total_chunks', None)
                meta['final_filename'] = filename
                meta['final_size'] = final_size
                upload.upload_metadata = json.dumps(meta)
            except json.JSONDecodeError:
                 logger.warning(f"Konnte JSON-Metadaten für Upload {upload.id} nicht parsen.")

        db.session.commit()
        uploaded_file_id = uploaded_file.id
        logger.info(f"Datei '{filename}' erfolgreich zusammengesetzt und als UploadedFile {uploaded_file_id} gespeichert.")

    except IOError as ioe:
        logger.error(f"IO-Fehler beim Zusammensetzen der Chunks für Session {session_id}: {ioe}")
        db.session.rollback()
        upload.overall_processing_status = 'error'
        upload.error_message = f"Error assembling file: {ioe}"
        db.session.commit()
        return create_error_response("Fehler beim Zusammensetzen der Datei", "ASSEMBLY_IO_ERROR", status_code=500)
    except Exception as e:
        logger.error(f"Fehler beim Erstellen von UploadedFile für Session {session_id}: {e}", exc_info=True)
        db.session.rollback()
        upload.overall_processing_status = 'error'
        upload.error_message = f"DB error finalizing upload: {e}"
        db.session.commit()
        return create_error_response("Fehler beim Speichern der Datei", "DB_FINALIZE_ERROR", status_code=500)

    # 6. Worker-Task starten
    task_id = None
    try:
        task_id = str(uuid.uuid4())
        proc_task = ProcessingTask(
            id=task_id,
            upload_id=upload.id,
            session_id=session_id,
            task_type="document.process_document",
            status="pending",
            created_at=datetime.utcnow(),
            task_metadata={ # ID wird hier korrekt übergeben
                'uploaded_file_id': uploaded_file_id,
                'file_name': filename,
                'user_id': upload.user_id,
                'language': upload.upload_metadata.get('language', 'de') if isinstance(upload.upload_metadata, dict) else 'de'
            }
        )
        db.session.add(proc_task)
        db.session.commit()
        
        # Task an Worker senden
        celery_sender.send_task(
            'document.process_document',
            args=[task_id],
            queue='celery'
        )
        logger.info(f"✅ Task '{task_id}' für UploadedFile {uploaded_file_id} (Chunked) gesendet.")

    except Exception as task_err:
        logger.error(f"Fehler beim Starten des Worker-Tasks für Session {session_id}: {task_err}", exc_info=True)
        # Setze Status auf Fehler, wenn Task nicht gestartet werden kann
        upload.overall_processing_status = 'error'
        upload.error_message = f"Failed to start processing task: {task_err}"
        # Setze auch Task-Status auf Fehler, falls er erstellt wurde
        if task_id and 'proc_task' in locals():
             try:
                 proc_task.status = 'error'
                 proc_task.error_message = upload.error_message
                 db.session.commit()
             except Exception as db_err2:
                 logger.error(f"Fehler beim Setzen des Task-Fehlerstatus: {db_err2}")
                 db.session.rollback()
        else:
             db.session.commit()
        # Keine Erfolgsmeldung senden
        return create_error_response("Fehler beim Starten der Verarbeitung", "TASK_START_ERROR", status_code=500)

    # 7. Aufräumen (Chunks löschen, Redis bereinigen)
    try:
        for chunk_filename in chunk_files:
            os.remove(os.path.join(upload_dir, chunk_filename))
        # Optional: Verzeichnis löschen, wenn leer?
        # if not os.listdir(upload_dir): os.rmdir(upload_dir)
        logger.info(f"Chunk-Dateien für Session {session_id} gelöscht.")
        # Redis-Einträge löschen
        redis_client.delete(redis_key_meta)
        redis_client.delete(redis_key_chunks)
        logger.info(f"Redis-Einträge für Session {session_id} gelöscht.")
    except Exception as cleanup_err:
        logger.warning(f"Fehler beim Aufräumen nach Chunked Upload für Session {session_id}: {cleanup_err}")

    # Erfolgreiche Antwort
        return jsonify({
            "success": True,
            "message": "Upload abgeschlossen und Verarbeitung gestartet",
            "session_id": session_id,
            "upload_id": upload.id,
        "uploaded_file_id": uploaded_file_id,
        "task_id": task_id
    }), 200 # OK statt 202, da der Upload jetzt wirklich abgeschlossen ist

def create_error_response(message, error_code, details=None, status_code=400):
    """Erstellt eine standardisierte Fehlerantwort."""
    error_response = {
            "success": False,
        "message": message,
        "error": {
            "code": error_code
        }
    }
    if details:
        error_response["error"]["details"] = details
    return jsonify(error_response), status_code
