# api/upload_core.py
"""
Kern-Funktionalität für den Datei-Upload-Prozess.
"""

import logging
import os
import time
import uuid
from datetime import datetime
import json

from flask import (Response, current_app, jsonify, redirect, render_template,
                  request, session, url_for, make_response)
from werkzeug.utils import secure_filename
from flask_jwt_extended import jwt_required, get_jwt_identity

from core.models import Upload, UploadedFile, User, db, Flashcard, Question, Topic, ProcessingTask
from core.redis_client import get_redis_client
from utils.common import generate_random_id, get_upload_dir
from .session_management import create_or_refresh_session, manage_user_sessions, enforce_session_limit
from celery import Celery
from config.config import config
from . import uploads_bp

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Maximale Upload-Größe (in Megabytes)
MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', 100))

# Stelle lokale Celery Sender Instanz wieder her
celery_sender = Celery('main_upload_core_sender', broker=config.redis_url)
logger.info(f"Celery Sender (lokal in upload_core) konfiguriert mit Broker: {config.redis_url.replace(config.redis_password, '****') if config.redis_password else config.redis_url}")


def upload_redirect():
    """
    Umleitung auf die Upload-Seite. Für Abwärtskompatibilität.

    Returns:
        Umleitung auf die Upload-Seite oder HTTP 200 für OPTIONS-Anfragen
    """
    if request.method == 'OPTIONS':
        # Für CORS-Preflight
        return Response('', status=200)

    if request.method == 'GET':
        logger.info("Umleitung zur Upload-Seite")
        return redirect(url_for('upload_page'))
    
    # POST-Anfragen für ältere API-Versionen
    return jsonify({
        "status": "redirect",
        "message": "Bitte verwenden Sie /api/upload/file für den Upload",
        "url": url_for('api.upload_file')
    })


@uploads_bp.route('/upload/file', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True)
def upload_file():
    """
    Hauptfunktion für den Upload von Dateien (unterstützt mehrere).
    Prüft Session-Limits, erstellt Upload- und UploadedFile-Einträge und startet EINEN Task.
    """
    if request.method == 'OPTIONS':
        # Korrekte OPTIONS-Antwort mit CORS Headern
        response = make_response()
        # Setze explizit erlaubte Methoden für diese Route
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS' 
        return response # Füge alle Standard-CORS-Header hinzu

    logger.info("Dateiupload-Anfrage empfangen (potenziell mehrere Dateien)")
    
    try:
        # Hole alle Dateien aus dem Feld 'file' (oder wie auch immer es heißt)
        uploaded_files_list = request.files.getlist("file")
        
        if not uploaded_files_list or all(f.filename == '' for f in uploaded_files_list):
            logger.error("Keine Dateien im Request gefunden oder alle Dateinamen leer")
            return jsonify({
                "success": False, 
                "error": {"code": "NO_FILE", "message": "Keine gültige Datei hochgeladen"}
            }), 400

        # Benutzer-ID ermitteln (wie bisher)
        user_id = None
        jwt_user_id = get_jwt_identity()
        if jwt_user_id:
            # ... (Logik zur User-Verifizierung) ...
            user = User.query.filter_by(id=jwt_user_id).first()
            if user: user_id = user.id
        elif 'user_id' in request.form: user_id = request.form.get('user_id')
        elif 'user_id' in session: user_id = session['user_id']
        # Optional: User-Existenz prüfen, wenn ID nicht aus JWT kommt
        if user_id and not jwt_user_id:
            if not User.query.get(user_id): user_id = None
        logger.info(f"Benutzer-ID für Upload: {user_id}")

        # --- SESSION LIMITIERUNG PRÜFEN --- #
        if user_id:
            try:
                # Setze das Limit auf 5
                limit = 5
                num_deleted = enforce_session_limit(user_id, limit)
                if num_deleted > 0:
                     logger.info(f"Benutzer {user_id} hat das Session-Limit ({limit}) erreicht. {num_deleted} älteste Upload(s) gelöscht.")
            except Exception as limit_err:
                 # Fehler loggen, aber den Upload-Prozess nicht unbedingt stoppen
                 logger.error(f"Fehler beim Anwenden des Session-Limits für User {user_id}: {limit_err}", exc_info=True)
        # --------------------------------- #

        # Session-Management (wie bisher)
        session_id = create_or_refresh_session()
        if user_id:
            manage_user_sessions(user_id)

        # Erstelle EINEN Upload-Datensatz für diesen Vorgang
        upload_language = request.form.get('language', 'de') # Beispiel für Metadaten
        new_upload = Upload(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_used_at=datetime.utcnow(),
            overall_processing_status='pending', # Initialer Status
            upload_metadata=json.dumps({"language": upload_language}) # Speichere Metadaten
        )
        db.session.add(new_upload)
        logger.info(f"Neuer Upload-Datensatz vorbereitet: ID={new_upload.id}, Session={session_id}")

        # Verarbeite jede hochgeladene Datei
        processed_files_info = []
        files_to_save = []
        file_counter = 0

        for file_storage in uploaded_files_list:
            if file_storage and file_storage.filename != '':
                file_counter += 1
                filename = secure_filename(file_storage.filename)
                logger.info(f"Verarbeite Datei {file_counter}: {filename}")

                # Dateityp prüfen
                if not _allowed_file(filename):
                    logger.warning(f"Datei übersprungen (ungültiger Typ): {filename}")
                    # Optional: Fehler für diese Datei speichern?
                    continue
                
                # Dateigröße prüfen (im Speicher)
                file_storage.seek(0, os.SEEK_END)
                file_size = file_storage.tell()
                file_storage.seek(0)
                if file_size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                    logger.warning(f"Datei übersprungen (zu groß: {file_size / (1024*1024):.2f} MB): {filename}")
                    continue

                # Lese binären Inhalt
                file_content = file_storage.read()

                # Erstelle UploadedFile-Objekt
                new_file_entry = UploadedFile(
                    id=str(uuid.uuid4()),
                    upload_id=new_upload.id, # Verknüpfung zum Haupt-Upload
                    file_index=file_counter, # Optional
                    file_name=filename,
                    mime_type=file_storage.mimetype,
                    file_size=file_size,
                    file_content=file_content,
                    extraction_status='pending', # Wird vom Worker gesetzt
                    created_at=datetime.utcnow()
                )
                files_to_save.append(new_file_entry)
                processed_files_info.append({"name": filename, "size": file_size, "type": file_storage.mimetype})

        # Prüfen, ob überhaupt gültige Dateien verarbeitet wurden
        if not files_to_save:
             logger.error("Keine gültigen Dateien zum Speichern gefunden nach Filterung.")
             # Hier sollte man ggf. den bereits hinzugefügten new_upload wieder entfernen
             # db.session.delete(new_upload) # Vorsicht hiermit!
             # db.session.commit()
             return jsonify({
                 "success": False, 
                 "error": {"code": "NO_VALID_FILES", "message": "Keine gültigen Dateien im Upload gefunden."}
             }), 400

        # Alle neuen Datei-Einträge zur Session hinzufügen
        db.session.add_all(files_to_save)
        
        # Status des Haupt-Uploads aktualisieren
        new_upload.overall_processing_status = 'queued'
        if isinstance(new_upload.upload_metadata, str): # Lade JSON falls als String gespeichert
             meta = json.loads(new_upload.upload_metadata)
        else: 
             meta = new_upload.upload_metadata or {}
        meta["num_files"] = len(files_to_save)
        new_upload.upload_metadata = meta # Speichere aktualisierte Metadaten

        # Alles committen (Upload + alle UploadedFiles)
        db.session.commit()
        logger.info(f"{len(files_to_save)} Datei-Einträge für Upload {new_upload.id} committet.")

        # --- Task an Worker senden (angepasst: Task pro Datei) --- #
        task_ids = []
        for saved_file in files_to_save:
            try:
                file_task_id = str(uuid.uuid4())
                # Erstelle ProcessingTask für jede Datei
                proc_task = ProcessingTask(
                    id=file_task_id,
                    upload_id=new_upload.id,
                    session_id=session_id,
                    task_type="document.process_document",
                    status="pending",
                    created_at=datetime.utcnow(),
                    task_metadata={ # ID wird hier korrekt übergeben
                        'uploaded_file_id': saved_file.id,
                        'file_name': saved_file.file_name,
                        'file_index': saved_file.file_index,
                        'user_id': user_id,
                        'language': upload_language
                    }
                )
                db.session.add(proc_task)
                db.session.commit() 

                # Sende Task an Worker
                celery_sender.send_task(
                    'document.process_document',
                    args=[file_task_id],
                    queue='celery'
                )
                task_ids.append(file_task_id)
                logger.info(f"✅ Task 'document.process_document' für Datei {saved_file.id} gesendet (Task ID: {file_task_id})")

            except Exception as proc_error:
                logger.error(f"❌ Fehler beim Senden des Tasks für Datei {saved_file.id}: {proc_error}", exc_info=True)
                # Rollback für den einzelnen Task Commit?
                db.session.rollback()

        # Gesamtstatus des Uploads ggf. anpassen, wenn keine Tasks gestartet wurden
        if not task_ids and files_to_save:
             logger.error(f"Konnte keine Verarbeitungs-Tasks für Upload {new_upload.id} starten.")
             new_upload.overall_processing_status = "error"
             new_upload.error_message = "Failed to start any processing tasks."
             db.session.commit()

        return jsonify({
            "success": True,
            "message": f"{len(files_to_save)} Datei(en) erfolgreich hochgeladen. {len(task_ids)} Verarbeitungs-Task(s) gestartet.",
            "session_id": session_id,
            "upload_id": new_upload.id,
            "files": processed_files_info,
            "task_ids": task_ids # Liste der gestarteten Task-IDs
        }), 202
        
    except Exception as e:
        logger.error("Genereller Fehler beim Dateiupload: %s", str(e), exc_info=True)
        # Wichtig: Rollback bei unerwartetem Fehler!
        try:
            db.session.rollback()
        except Exception as rb_err:
            logger.error(f"Fehler beim Rollback: {rb_err}")
        return jsonify({
            "success": False,
            "error": {"code": "UPLOAD_FAILED", "message": f"Upload fehlgeschlagen: {str(e)}"}
        }), 500


# Entferne den Route-Dekorator und behalte nur die Funktion
def get_results(session_id):
    """
    Ergebnisse einer verarbeiteten Datei abrufen.
    Gibt alle Daten (Flashcards, Questions und Topics) zusammen zurück.

    Args:
        session_id: ID der Upload-Session

    Returns:
        JSON mit den Verarbeitungsergebnissen
    """
    try:
        logger.info(f"[VOLLSTÄNDIGER DATENABRUF] get_results aufgerufen für Session ID: {session_id}")
        
        # Upload aus der Datenbank holen
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        if not upload:
            logger.error(f"[VOLLSTÄNDIGER DATENABRUF] Upload nicht gefunden für Session ID: {session_id}")
            return jsonify({
                "success": False,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "Upload-Session nicht gefunden"
                }
            }), 404
        
        # Zähle Flashcards, Fragen und Themen, um zu prüfen, ob Daten vorhanden sind
        flashcards_count = Flashcard.query.filter_by(upload_id=upload.id).count()
        questions_count = Question.query.filter_by(upload_id=upload.id).count()
        topics_count = Topic.query.filter_by(upload_id=upload.id).count()
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        
        logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Session {session_id}: Status={upload.processing_status}, Flashcards={flashcards_count}, Questions={questions_count}, Topics={topics_count}, Main Topic={main_topic.name if main_topic else 'None'}")
        
        # Wenn der Status 'completed' ist, markiere die Ergebnisse als verfügbar, unabhängig von der Anzahl der Daten
        if upload.processing_status == "completed":
            try:
                # Verwende die update_session_info-Funktion aus session_management
                from .session_management import update_session_info
                
                # Setze results_available immer auf True, wenn der Status completed ist
                update_session_info(
                    session_id=session_id,
                    status="completed",
                    results_available=True,  # Immer True, wenn Status completed ist
                    flashcards_count=flashcards_count,
                    questions_count=questions_count,
                    topics_count=topics_count,
                    main_topic=main_topic.name if main_topic else None
                )
                
                # Aktualisiere auch den Verarbeitungsstatus in Redis
                redis_client = get_redis_client()
                redis_client.set(f"processing_status:{session_id}", "completed")
                
                logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Ergebnisse sind verfügbar für Session {session_id}, Redis und DB aktualisiert.")
            except Exception as e:
                logger.warning(f"[VOLLSTÄNDIGER DATENABRUF] Fehler beim Aktualisieren des Redis-Status: {str(e)}")
                
        # Status prüfen
        if upload.processing_status == 'processing':
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Session {session_id} ist noch in Verarbeitung")
            return jsonify({
                "success": True,
                "status": "processing",
                "message": "Die Datei wird noch verarbeitet"
            }), 200
        elif upload.processing_status == 'uploaded':
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Session {session_id} wurde hochgeladen, aber noch nicht verarbeitet")
            return jsonify({
                "success": True,
                "status": "uploaded",
                "message": "Die Datei wurde hochgeladen, aber noch nicht verarbeitet"
            }), 200
        elif upload.processing_status == 'error':
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Session {session_id} hat einen Fehler bei der Verarbeitung")
            return jsonify({
                "success": False,
                "status": "error",
                "error": {
                    "code": "PROCESSING_ERROR",
                    "message": upload.error_message or "Fehler bei der Verarbeitung"
                }
            }), 500
        elif upload.processing_status == 'completed':
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Session {session_id} wurde erfolgreich verarbeitet, lade alle Daten")
            
            # Redis-Client für den Zugriff auf Redis-Cache
            redis_client = get_redis_client()
            
            # Lade Daten direkt aus der Datenbank
            
            # Flashcards aus der Datenbank laden
            flashcards = Flashcard.query.filter_by(upload_id=upload.id).all()
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] {len(flashcards)} Flashcards aus der Datenbank geladen")
            formatted_flashcards = []
            for card in flashcards:
                formatted_flashcards.append({
                    "id": card.id,
                    "question": card.question,
                    "answer": card.answer
                })
                
            # Fragen aus der Datenbank laden
            questions = Question.query.filter_by(upload_id=upload.id).all()
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] {len(questions)} Fragen aus der Datenbank geladen")
            formatted_questions = []
            for question in questions:
                options = []
                # Prüfen, ob options als String oder Liste gespeichert sind
                if isinstance(question.options, str):
                    try:
                        import json
                        options = json.loads(question.options)
                    except:
                        options = [question.options]
                else:
                    options = question.options
                    
                formatted_questions.append({
                    "id": question.id,
                    "text": question.text,
                    "options": options,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation
                })
                
            # Themen aus der Datenbank laden
            main_topic_obj = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Hauptthema: {main_topic_obj.name if main_topic_obj else 'Nicht gefunden'}")
            main_topic = main_topic_obj.name if main_topic_obj else "Unbekanntes Thema"
            
            subtopics = Topic.query.filter_by(upload_id=upload.id, is_main_topic=False).all()
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] {len(subtopics)} Unterthemen aus der Datenbank geladen")
            formatted_subtopics = []
            for topic in subtopics:
                formatted_subtopics.append({
                    "id": topic.id,
                    "name": topic.name,
                    "parent_id": topic.parent_id
                })
                
            # Erstelle Verbindungen basierend auf parent_id in der Topics-Tabelle
            formatted_connections = []
            for topic in subtopics:
                if topic.parent_id:
                    formatted_connections.append({
                        "id": f"conn_{topic.id}",
                        "source_id": topic.parent_id,
                        "target_id": topic.id,
                        "label": "has subtopic"
                    })
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] {len(formatted_connections)} Verbindungen erstellt")
            
            # Lade Topic-Hierarchie (zusätzliche Informationen für den Frontend-Topics-Endpunkt)
            # Import hier, um zirkuläre Imports zu vermeiden
            from api.topics.models import get_topic_hierarchy
            topics_hierarchy = get_topic_hierarchy(upload.id)
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Topic-Hierarchie für Upload {upload.id} geladen")
            
            # Ergebnisse auch aus Redis holen (falls vorhanden)
            redis_results = redis_client.hgetall(f"results:{session_id}")
            
            # Redis-Ergebnisse in JSON-Format umwandeln
            formatted_redis_results = {}
            if redis_results:
                for key, value in redis_results.items():
                    try:
                        if isinstance(key, bytes):
                            key = key.decode('utf-8')
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        formatted_redis_results[key] = value
                    except:
                        continue
            
            # Zusätzliche Debug-Informationen hinzufügen
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Formatierte Flashcards: {len(formatted_flashcards)}")
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Formatierte Fragen: {len(formatted_questions)}")
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Formatierte Subtopics: {len(formatted_subtopics)}")
            
            # Formatierte Antwort erstellen
            response_data = {
                "success": True,
                "status": "completed",
                "data": {
                    "session_id": session_id,
                    "flashcards": formatted_flashcards,
                    "test_questions": formatted_questions,
                    "analysis": {
                        "main_topic": main_topic,
                        "subtopics": [topic.name for topic in subtopics]
                    },
                    "topics": {
                        "main_topic": {
                            "id": main_topic_obj.id if main_topic_obj else "main_topic",
                            "name": main_topic
                        },
                        "subtopics": formatted_subtopics
                    },
                    "connections": formatted_connections,
                    "topics_hierarchy": topics_hierarchy  # Die vollständigen Topic-Daten hinzufügen
                }
            }
            
            # Füge eine zusätzliche direkte Property für Debugzwecke hinzu
            # Diese Struktur entspricht genauer dem, was das Frontend erwartet
            response_data["flashcards"] = formatted_flashcards
            response_data["test_questions"] = formatted_questions
            
            # Redis-Ergebnisse hinzufügen, falls vorhanden
            if formatted_redis_results:
                response_data["redis_results"] = formatted_redis_results
            
            # Log der zurückgegebenen Daten
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Ergebnisse für Session {session_id} zurückgegeben: {len(formatted_flashcards)} Flashcards, {len(formatted_questions)} Fragen, {len(formatted_subtopics) + 1} Themen")
                
            return jsonify(response_data), 200
        else:
            logger.info(f"[VOLLSTÄNDIGER DATENABRUF] Session {session_id} hat einen unbekannten Status: {upload.processing_status}")
            return jsonify({
                "success": False,
                "status": upload.processing_status,
                "message": "Unbekannter Upload-Status"
            }), 500
            
    except Exception as e:
        logger.error(f"[VOLLSTÄNDIGER DATENABRUF] Fehler beim Abrufen der Ergebnisse: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {
                "code": "RESULTS_RETRIEVAL_ERROR",
                "message": f"Fehler beim Abrufen der Ergebnisse: {str(e)}"
            }
        }), 500


def _allowed_file(filename):
    """
    Prüft, ob ein Dateiname eine erlaubte Erweiterung hat.

    Args:
        filename: Der zu prüfende Dateiname

    Returns:
        True, wenn die Datei erlaubt ist, sonst False
    """
    allowed_extensions = {'.pdf', '.docx', '.doc', '.txt', '.rtf', '.odt'}
    return os.path.splitext(filename.lower())[1] in allowed_extensions
