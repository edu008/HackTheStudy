# api/upload.py
from flask import request, jsonify, Blueprint, current_app, g
from . import api_bp
from core.models import db, Upload, Question, Topic, Connection, Flashcard, User
from sqlalchemy.orm import Session as SQLAlchemySession  # korrekte Quelle für Session
# import tasks  # In main/api sollte dieser Import durch Celery API ersetzt werden
import os  # Für Zugriff auf os.environ
from .cleanup import cleanup_processing_for_session
import uuid
from .utils import allowed_file, extract_text_from_file, check_and_manage_user_sessions, update_session_timestamp, count_tokens, detect_language, clean_text_for_database, analyze_content, generate_concept_map_suggestions, unified_content_processing
import logging
from .auth import token_required
from api.token_tracking import check_credits_available, calculate_token_cost, deduct_credits
import time
import json
# Redis-Client direkt erstellen
import redis
from celery import Celery
from datetime import datetime

# Verwende die korrekte Redis-URL, die auch der Worker nutzt
redis_url = os.environ.get('REDIS_URL', 'redis://hackthestudy-backend-main:6379/0')
redis_client = redis.from_url(redis_url)

# Celery-Client zum Senden von Tasks an den Worker
celery_app = Celery('api', broker=redis_url, backend=redis_url)

# Hilfsfunktion, um Tasks an den Worker zu delegieren
def delegate_to_worker(task_name, *args, **kwargs):
    """Delegiert eine Aufgabe an den Worker über Celery."""
    try:
        logger.info(f"📤 WORKER-DELEGATION: Sende Task '{task_name}' an Worker mit args={args[:30]} und kwargs={kwargs}")
        task = celery_app.send_task(task_name, args=args, kwargs=kwargs)
        logger.info(f"✅ WORKER-DELEGATION: Task erfolgreich gesendet - Task-ID: {task.id}")
        
        # Zusätzliche Diagnoseinformationen
        celery_broker = celery_app.conf.broker_url
        logger.info(f"📊 WORKER-DIAGNOSE: Broker-URL={celery_broker}, Worker-Task-ID={task.id}")
        
        # Versuche Verbindungsstatus zu prüfen
        try:
            broker_reachable = celery_app.connection().ensure_connection(max_retries=1)
            logger.info(f"🔌 WORKER-VERBINDUNG: Broker erreichbar = {broker_reachable}")
        except Exception as conn_err:
            logger.error(f"❌ WORKER-VERBINDUNG: Broker-Verbindungsfehler: {str(conn_err)}")
        
        return task
    except Exception as e:
        error_message = f"❌ WORKER-DELEGATION: Fehler beim Senden der Task '{task_name}' an Worker: {str(e)}"
        logger.error(error_message)
        logger.error(f"Stacktrace: {traceback.format_exc()}")
        raise Exception(error_message)

logger = logging.getLogger(__name__)

# Konfiguriere maximale Dateigröße und Timeout
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
UPLOAD_TIMEOUT = 180  # 3 Minuten
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB pro Chunk
MAX_CHUNKS = 10  # Maximale Anzahl von Chunks pro Datei

# Hilfsroute, die auf die richtige Upload-Route weiterleitet
@api_bp.route('/upload', methods=['GET', 'POST', 'OPTIONS'])
def upload_redirect():
    """
    Hilfsfunktion zur Weiterleitung auf den korrekten Upload-Endpunkt
    """
    if request.method == 'OPTIONS':
        return jsonify(success=True)
    
    # Bei POST auf /upload zur korrekten Datei-Upload-Route weiterleiten
    if request.method == 'POST':
        return upload_file()
    
    # Bei GET eine Hilfsnachricht zurückgeben
    return jsonify({
        "message": "Dies ist der Upload-Endpunkt. Für Datei-Uploads bitte POST-Anfragen an /api/v1/upload/file senden."
    })

@api_bp.route('/upload/file', methods=['POST', 'OPTIONS'])
@token_required
def upload_file():
    """
    Verarbeitet Datei-Uploads mit verbesserter Fehlerbehandlung und Timeout-Management.
    Unterstützt jetzt auch Chunk-Uploads für große Dateien.
    """
    try:
        # OPTIONS-Anfragen sofort beantworten
        if request.method == 'OPTIONS':
            response = jsonify({"success": True})
            return response
            
        # Authentifizierung für nicht-OPTIONS Anfragen
        auth_decorator = token_required(lambda: None)
        auth_result = auth_decorator()
        if auth_result is not None:
            return auth_result
        
        # Überprüfe die Dateigröße
        if request.content_length and request.content_length > MAX_CONTENT_LENGTH:
            # Für große Dateien: Empfehle Chunk-Upload
            return jsonify({
                "success": False,
                "message": "Datei ist zu groß für direkten Upload",
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": "Bitte verwenden Sie den Chunk-Upload für Dateien über 50MB",
                    "max_size": MAX_CONTENT_LENGTH,
                    "chunk_size": CHUNK_SIZE
                }
            }), 413
        
        # Setze einen längeren Timeout für die Verarbeitung
        request.timeout = UPLOAD_TIMEOUT
        
        if 'file' not in request.files:
            return create_error_response(
                "Keine Datei gefunden", 
                ERROR_INVALID_INPUT, 
                {"detail": "No file part"}
            )
        
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return create_error_response(
                "Ungültige oder keine Datei ausgewählt", 
                ERROR_INVALID_INPUT, 
                {"detail": "Invalid or no file selected"}
            )
        
        # Verwende die übergebene session_id, falls vorhanden, sonst generiere eine neue
        session_id = request.form.get('session_id')
        user_id = getattr(request, 'user_id', None)
        
        # Verwende AppLogger für strukturierte Logs
        AppLogger.structured_log(
            "INFO",
            f"Datei-Upload-Anfrage empfangen: {file.filename}",
            user_id=user_id,
            component="upload_file",
            file_name=file.filename
        )
        
        # SCHRITT 1: Wenn keine Session-ID übergeben wird, erstellen wir eine neue und prüfen die Begrenzung
        if not session_id:
            # Zuerst einen alten Upload löschen, falls nötig
            if user_id:
                AppLogger.structured_log(
                    "INFO",
                    f"Prüfe und verwalte Benutzer-Sessions für Benutzer {user_id}",
                    user_id=user_id,
                    component="session_management"
                )
                # Setze max_sessions=5 und session_to_exclude=None für die Überprüfung
                sessions_removed = check_and_manage_user_sessions(user_id, max_sessions=5, session_to_exclude=None)
                if sessions_removed:
                    AppLogger.structured_log(
                        "INFO",
                        f"Alte Sessions wurden gelöscht, da der Benutzer das Limit erreicht hat",
                        user_id=user_id,
                        component="session_management"
                    )
            
            # Dann eine neue Session-ID erstellen
            session_id = str(uuid.uuid4())
            AppLogger.structured_log(
                "INFO",
                f"Neue Session-ID generiert: {session_id}",
                session_id=session_id,
                user_id=user_id,
                component="upload_file"
            )
        
        # Setze Metadaten für Nachverfolgung
        AppLogger.structured_log(
            "INFO",
            f"Datei-Upload gestartet: {file.filename}",
            session_id=session_id,
            user_id=user_id,
            component="upload_file",
            file_name=file.filename
        )
        
        # Initialen Fortschritt setzen
        AppLogger.track_session_progress(
            session_id, 
            progress_percent=0,
            message="Upload empfangen, Initialisierung...", 
            stage="initializing"
        )
        
        # SCHRITT 2: Lese die Datei mit Fehlerbehandlung
        try:
            file_content = file.read()
            
            # Setze den Verarbeitungsstatus in Redis
            redis_client.set(f"processing_status:{session_id}", "initializing", ex=3600)
            redis_client.set(f"processing_start_time:{session_id}", str(time.time()), ex=3600)
            
            # SCHRITT 3: Speichere Upload in der Datenbank
            try:
                # Erzeuge eine neue Upload-Instanz oder aktualisiere eine bestehende
                upload_session = Upload.query.filter_by(session_id=session_id).first()
                
                if upload_session:
                    # Aktualisiere die bestehende Session
                    upload = upload_session
                    upload.file_name_1 = file.filename
                    upload.processing_status = "pending"
                    upload.last_used_at = db.func.current_timestamp()
                    if user_id and not upload.user_id:
                        upload.user_id = user_id
                else:
                    # Erzeuge eine neue Upload-Instanz mit einer eindeutigen ID
                    new_id = str(uuid.uuid4())
                    upload = Upload(
                        id=new_id,
                        session_id=session_id,
                        user_id=user_id,
                        file_name_1=file.filename,
                        processing_status="pending",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        last_used_at=datetime.utcnow()
                    )
                    db.session.add(upload)
                
                # Commit der Datenbankänderungen
                db.session.commit()
                AppLogger.structured_log(
                    "INFO",
                    f"{'Upload-Eintrag aktualisiert' if upload_session else 'Neuer Upload-Eintrag erstellt'} für Session {session_id}",
                    session_id=session_id,
                    user_id=user_id,
                    component="database",
                    upload_id=upload.id
                )
                
                # SCHRITT 4: Starte den Worker-Task
                task_files_data = [(file.filename, file_content.hex())]
                task = delegate_to_worker('process_upload', session_id, task_files_data, user_id)
                
                # Speichere die Task-ID in Redis für Tracking
                redis_client.set(f"task_id:{session_id}", task.id, ex=3600)
                
                # Erfolgreiche Antwort mit session_id
                success_response = jsonify({
                    "success": True,
                    "message": "Datei erfolgreich hochgeladen und wird verarbeitet",
                    "session_id": session_id,
                    "upload_id": upload.id,
                    "task_id": task.id,
                    "progress": 100  # Direkter Upload ist sofort 100%
                })
                
                return success_response
                
            except Exception as e:
                AppLogger.track_error(
                    session_id,
                    "database_error",
                    f"Fehler beim Speichern des Uploads: {str(e)}",
                    trace=traceback.format_exc()
                )
                db.session.rollback()
                return create_error_response(
                    f"Fehler beim Speichern des Uploads: {str(e)}", 
                    ERROR_DATABASE
                )
                
        except Exception as e:
            AppLogger.track_error(
                session_id,
                "file_read_error",
                f"Die Datei konnte nicht gelesen werden: {str(e)}",
                trace=traceback.format_exc()
            )
            return create_error_response(
                f"Die Datei konnte nicht gelesen werden: {str(e)}", 
                ERROR_FILE_PROCESSING
            )
            
    except Exception as e:
        # Allgemeine Ausnahmebehandlung für alle anderen Fehler
        session_id = request.form.get('session_id', 'unknown')
        AppLogger.track_error(
            session_id,
            "critical_upload_error",
            f"Kritischer Fehler bei Upload: {str(e)}",
            trace=traceback.format_exc()
        )
        return jsonify({
            "success": False,
            "error": {
                "message": "Ein kritischer Serverfehler ist aufgetreten",
                "type": str(type(e).__name__),
                "details": str(e)
            }
        }), 500

@api_bp.route('/results/<session_id>', methods=['GET'])
@token_required
def get_results(session_id):
    """
    Liefert die Analyseergebnisse für eine bestimmte Session.
    Verbessert: Stellt sicher, dass die Verarbeitung abgeschlossen ist, bevor Ergebnisse zurückgegeben werden.
    """
    from api.log_utils import AppLogger
    from .utils import update_session_timestamp
    
    # Logge Anfrage
    AppLogger.structured_log(
        "INFO",
        f"Ergebnisabfrage für Session {session_id}",
        session_id=session_id,
        component="get_results"
    )
    
    # Aktualisiere den Zeitstempel, um diese Session als zuletzt verwendet zu markieren
    # Dies hilft bei der Entscheidung, welche Sessions beibehalten werden sollen
    update_session_timestamp(session_id)
    
    try:
        # Prüfe den Redis-Status für die Session
        redis_key = f"processing_status:{session_id}"
        processing_status = redis_client.get(redis_key)
        special_status = None
        
        if processing_status:
            processing_status = processing_status.decode('utf-8')
            logger.info(f"Redis-Status für Session {session_id}: {processing_status}")
            
            if processing_status in ["failed", "error"] or processing_status.startswith("failed:") or processing_status.startswith("error:"):
                special_status = "error"
                logger.info(f"Fehler erkannt für Session {session_id}")
            elif processing_status == "initializing":
                special_status = "initializing"
            elif processing_status == "completed":
                special_status = "completed"
                
                # OPTIMIERUNG: Versuche, die Ergebnisse direkt aus Redis zu holen
                cached_result = redis_client.get(f"processing_result:{session_id}")
                if cached_result:
                    try:
                        result_data = json.loads(cached_result.decode('utf-8'))
                        logger.info(f"Ergebnisse aus Redis geladen für Session {session_id}")
                        
                        # Formatiere die Antwort
                        # Hauptthema extrahieren
                        main_topic_name = "Unknown Topic"
                        if "main_topic" in result_data:
                            main_topic_name = result_data["main_topic"]
                        
                        # Prüfe, ob der Upload in der Datenbank existiert, um sicherzustellen,
                        # dass die Daten vollständig gespeichert wurden
                        upload = Upload.query.filter_by(session_id=session_id).first()
                        if not upload or upload.processing_status != 'completed':
                            logger.info(f"Datenbank-Upload noch nicht abgeschlossen für Session {session_id}, Status: {upload.processing_status if upload else 'nicht gefunden'}")
                            return jsonify({
                                "status": "processing", 
                                "message": "Verarbeitung läuft...",
                                "progress": 95,
                                "detail": "Ergebnisse werden finalisiert"
                            }), 200
                        
                        # Aktualisiere den last_used_at-Zeitstempel
                        upload.last_used_at = db.func.current_timestamp()
                        db.session.commit()
                        
                        return jsonify({
                            "status": "completed",
                            "data": result_data,
                            "source": "redis_cache"
                        }), 200
                    except json.JSONDecodeError:
                        logger.warning(f"Ungültige JSON-Daten in Redis-Ergebnissen für {session_id}")
        
        # Suche nach dem Upload in der Datenbank
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            # Wenn kein Upload existiert, prüfe, ob es einen laufenden Task gibt
            task_id = redis_client.get(f"task_id:{session_id}")
            if task_id:
                # Es gibt einen laufenden Task, also gib "processing" zurück
                return jsonify({
                    "status": "processing", 
                    "message": "Verarbeitung läuft...",
                    "task_id": task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
                }), 200
            
            return jsonify({"error": "Session nicht gefunden"}), 404
        
        logger.info(f"Upload Status: {upload.processing_status}, special_status: {special_status}")
        
        # Bei Fehler: Überprüfe, ob Fehlerdetails in Redis vorhanden sind
        error_details = None
        if special_status == "error" or upload.processing_status == 'failed':
            error_key = f"error_details:{session_id}"
            error_data = redis_client.get(error_key)
            
            if error_data:
                try:
                    error_details = json.loads(error_data.decode('utf-8'))
                    logger.info(f"Fehlerdetails gefunden: {error_details.get('message', 'Keine Nachricht')}")
                except json.JSONDecodeError:
                    logger.warning(f"Fehlerhafte JSON-Daten in Redis für {error_key}")
            else:
                logger.info("Keine Fehlerdetails in Redis gefunden")
            
            # Wenn wir Fehlerdetails haben ODER die Verarbeitung länger als MIN_PROCESSING_TIME läuft, gebe den Fehler zurück
            MIN_PROCESSING_TIME = 10  # Sekunden
            
            # Zeitdifferenz seit Start der Verarbeitung berechnen
            start_time_key = f"processing_start_time:{session_id}"
            start_time_data = redis_client.get(start_time_key)
            processing_time = 0
            
            if start_time_data:
                try:
                    start_time = float(start_time_data.decode('utf-8'))
                    processing_time = time.time() - start_time
                    logger.info(f"Verarbeitung läuft seit {processing_time:.2f} Sekunden")
                except (ValueError, TypeError):
                    logger.warning(f"Ungültiger Zeitstempel in Redis für {start_time_key}")
            
            # Überprüfe explizit auf OpenAI-API-Fehler - diese sollten sofort gemeldet werden
            openai_error_key = f"openai_error:{session_id}"
            openai_error_data = redis_client.get(openai_error_key)
            has_openai_error = openai_error_data is not None
            
            # Wenn wir Fehlerdetails haben ODER die Verarbeitung länger als MIN_PROCESSING_TIME läuft
            # ODER ein OpenAI-Fehler aufgetreten ist, gebe den Fehler zurück
            if error_details or processing_time > MIN_PROCESSING_TIME or has_openai_error:
                # Wenn keine detaillierten Fehlerinformationen vorhanden sind, aber ein OpenAI-Fehler
                if not error_details and has_openai_error:
                    try:
                        openai_error = json.loads(openai_error_data.decode('utf-8'))
                        error_details = {
                            "message": f"OpenAI API-Fehler: {openai_error.get('error', 'Unbekannter Fehler')}",
                            "error_type": "openai_api_error",
                            "timestamp": openai_error.get('timestamp', time.time())
                        }
                        logger.info(f"OpenAI-Fehlerdetails verwendet: {error_details['message']}")
                    except json.JSONDecodeError:
                        error_details = {
                            "message": "Fehler bei der OpenAI API-Kommunikation",
                            "error_type": "openai_api_error",
                            "timestamp": time.time()
                        }
                
                # Wenn immer noch keine Fehlerdetails vorhanden sind, erstelle generische
                if not error_details:
                    error_details = {
                        "message": "Ein Fehler ist bei der Verarbeitung aufgetreten",
                        "error_type": "general_processing_error",
                        "timestamp": time.time()
                    }
                
                return jsonify({
                    "status": "error",
                    "error": error_details.get("message", "Unbekannter Fehler"),
                    "error_type": error_details.get("error_type", "unbekannt"),
                    "timestamp": error_details.get("timestamp", time.time())
                }), 400
            else:
                # Wenn der Fehler erkannt wurde, aber die Verarbeitung noch nicht lange genug läuft,
                # geben wir 'processing' zurück, damit das Frontend weiter abfragt
                logger.info(f"Fehler erkannt, aber Verarbeitung läuft erst seit {processing_time:.2f} Sekunden bei MIN_PROCESSING_TIME={MIN_PROCESSING_TIME}. Gebe 'processing' zurück.")
                return jsonify({"status": "processing", "progress": None}), 200
        
        # Wenn Verarbeitung abgeschlossen ist
        if upload.processing_status == 'completed' or special_status == 'completed':
            # Zusätzliche Prüfung: Sind alle Daten in der Datenbank vorhanden?
            try:
                # Überprüfe, ob Topics, Flashcards etc. bereits erstellt wurden
                topics_count = Topic.query.filter_by(upload_id=upload.id).count()
                flashcards_count = Flashcard.query.filter_by(upload_id=upload.id).count()
                questions_count = Question.query.filter_by(upload_id=upload.id).count()
                
                # Wenn keine Daten in der Datenbank vorhanden sind, sind wir noch im Finalisierungsprozess
                if topics_count == 0 and flashcards_count == 0 and questions_count == 0:
                    logger.info(f"Verarbeitung abgeschlossen, aber keine Daten in der Datenbank für Session {session_id}")
                    return jsonify({
                        "status": "processing", 
                        "message": "Finalisierung...",
                        "progress": 95,
                        "detail": "Ergebnisse werden in Datenbank gespeichert"
                    }), 200
                
                # Einführung einer kurzen Verzögerung, um sicherzustellen, dass alle Daten
                # vollständig in der Datenbank gespeichert wurden (z.B. Verbindungen)
                finalization_key = f"finalization_timestamp:{session_id}"
                finalization_timestamp = redis_client.get(finalization_key)
                
                if not finalization_timestamp:
                    # Wenn kein Zeitstempel existiert, setze ihn jetzt
                    redis_client.set(finalization_key, str(time.time()), ex=3600)  # 1 Stunde Gültigkeit
                    logger.info(f"Erster Abruf nach Abschluss für Session {session_id}, setze Finalisierungs-Zeitstempel")
                    return jsonify({
                        "status": "processing", 
                        "message": "Daten werden finalisiert...",
                        "progress": 98
                    }), 200
                else:
                    # Berechne, wie viel Zeit seit der Finalisierung vergangen ist
                    finalization_time = float(finalization_timestamp.decode('utf-8'))
                    elapsed_time = time.time() - finalization_time
                    
                    # Füge eine kleine Verzögerung hinzu (z.B. 1-2 Sekunden), um sicherzustellen,
                    # dass alle Transaktionen abgeschlossen sind
                    FINALIZATION_DELAY = 2  # Sekunden
                    if elapsed_time < FINALIZATION_DELAY:
                        logger.info(f"Warte auf Finalisierung: {elapsed_time:.2f}/{FINALIZATION_DELAY} Sekunden vergangen")
                        return jsonify({
                            "status": "processing", 
                            "message": "Abschließende Datenverarbeitung...",
                            "progress": 99
                        }), 200
                    else:
                        logger.info(f"Finalisierungsverzögerung abgeschlossen ({elapsed_time:.2f} s), liefere Ergebnisse")
                        # Lösche den Finalisierungs-Zeitstempel, da er nicht mehr benötigt wird
                        redis_client.delete(finalization_key)
            except Exception as e:
                logger.error(f"Fehler bei der Datenprüfung: {str(e)}")
                # Bei einem Fehler geben wir trotzdem die Daten zurück, sofern vorhanden
            
            # Frage die verarbeiteten Daten ab
            flashcards = Flashcard.query.filter_by(upload_id=upload.id).all()
            questions = Question.query.filter_by(upload_id=upload.id).all()
            topics = Topic.query.filter_by(upload_id=upload.id).all()
            connections = Connection.query.filter_by(upload_id=upload.id).all()
            
            # Aktualisiere den last_used_at-Zeitstempel
            upload.last_used_at = db.func.current_timestamp()
            db.session.commit()
            
            # Finde das Hauptthema
            main_topic = next((t for t in topics if t.is_main_topic), None)
            main_topic_name = main_topic.name if main_topic else "Unknown Topic"
            
            # Sammle Unterthemen
            subtopics = [t for t in topics if not t.is_main_topic and not t.is_key_term]
            subtopics_data = []
            
            for subtopic in subtopics:
                # Finde alle Verbindungen für dieses Unterthema
                sub_connections = [c for c in connections if c.target_id == subtopic.id]
                parent_id = subtopic.parent_id
                
                # Finde Kinder-Unterthemen (nur für oberste Ebene)
                children = []
                if not parent_id or (main_topic and parent_id == main_topic.id):
                    children = [t for t in topics if t.parent_id == subtopic.id]
                    children_data = [{"id": c.id, "name": c.name} for c in children]
                else:
                    children_data = []
                
                subtopics_data.append({
                    "id": subtopic.id,
                    "name": subtopic.name,
                    "parent_id": parent_id,
                    "connections": [{"source": c.source_id, "label": c.label} for c in sub_connections],
                    "children": children_data
                })
            
            # Sammle Schlüsselbegriffe
            key_terms = [t for t in topics if t.is_key_term]
            key_terms_data = [{
                "id": t.id,
                "term": t.name,
                "definition": t.description
            } for t in key_terms]
            
            # Bereite Daten für Flashcards vor
            flashcards_data = [{
                "id": f.id,
                "question": f.question,
                "answer": f.answer
            } for f in flashcards]
            
            # Bereite Daten für Fragen vor
            questions_data = [{
                "id": q.id,
                "text": q.text,
                "options": q.options,
                "correct": q.correct_answer,
                "explanation": q.explanation
            } for q in questions]
            
            # Bereite Daten für Verbindungen vor
            connections_data = [{
                "id": c.id,
                "source": c.source_id,
                "target": c.target_id,
                "label": c.label
            } for c in connections]
            
            # Erstelle und gib die Antwort zurück
            return jsonify({
                "status": "completed",
                "data": {
                    "main_topic": main_topic_name,
                    "subtopics": subtopics_data,
                    "key_terms": key_terms_data,
                    "flashcards": flashcards_data,
                    "questions": questions_data,
                    "connections": connections_data,
                    "file_names": [
                        upload.file_name_1,
                        upload.file_name_2,
                        upload.file_name_3,
                        upload.file_name_4,
                        upload.file_name_5
                    ]
                }
            }), 200
        
        # Wenn die Verarbeitung noch nicht abgeschlossen ist, Fortschritt aus Redis abrufen
        progress_key = f"processing_progress:{session_id}"
        progress_data = redis_client.get(progress_key)
        
        if progress_data:
            try:
                progress_details = json.loads(progress_data.decode('utf-8'))
                return jsonify({
                    "status": "processing",
                    "progress": progress_details.get("progress", 0),
                    "stage": progress_details.get("stage", "unknown"),
                    "message": progress_details.get("message", "Verarbeitung läuft...")
                }), 200
            except json.JSONDecodeError:
                logger.warning(f"Ungültige JSON-Daten für Fortschrittsinformationen: {progress_data}")
        
        # Fallback, wenn keine Fortschrittsinformationen gefunden wurden
        return jsonify({
            "status": "processing",
            "progress": None,
            "message": "Verarbeitung läuft..."
        }), 200
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Ergebnisse: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "error": f"Interner Serverfehler: {str(e)}"
        }), 500

@api_bp.route('/session-info/<session_id>', methods=['GET', 'OPTIONS'])
def get_session_info(session_id):
    """Gibt grundlegende Informationen über eine Session zurück, ohne die vollständigen Daten."""
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    # Rest der Funktion bleibt unverändert...
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Aktualisiere den last_used_at-Timestamp
    update_session_timestamp(session_id)
    
    # Sammle alle Dateinamen
    files = []
    if upload.file_name_1: files.append(upload.file_name_1)
    if upload.file_name_2: files.append(upload.file_name_2)
    if upload.file_name_3: files.append(upload.file_name_3)
    if upload.file_name_4: files.append(upload.file_name_4)
    if upload.file_name_5: files.append(upload.file_name_5)
    
    # Ermittle die Token-Anzahl (einfache Schätzung: 1 Token = ca. 4 Zeichen)
    token_count = len(upload.content) // 4 if upload.content else 0
    
    # Ermittle das Hauptthema, falls vorhanden
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    main_topic_name = main_topic.name if main_topic else "Unknown Topic"
    
    return jsonify({
        "success": True,
        "data": {
            "session_id": session_id,
            "files": files,
            "token_count": token_count,
            "main_topic": main_topic_name,
            "user_id": upload.user_id,
            "created_at": upload.created_at.isoformat() if upload.created_at else None,
            "updated_at": upload.updated_at.isoformat() if upload.updated_at else None,
            "last_used_at": upload.last_used_at.isoformat() if upload.last_used_at else None,
            "processing_status": "waiting" if token_count > 0 and not main_topic else ("completed" if main_topic else "pending")
        }
    }), 200

def update_processing_status(session_id, status):
    """
    Aktualisiert den Verarbeitungsstatus einer Session in der Datenbank
    
    Args:
        session_id: Die ID der Session
        status: Der neue Status ("completed", "processing", "failed", etc.)
    """
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if upload:
            upload.processing_status = status
            db.session.commit()
            logger.info(f"Updated processing status for session {session_id} to {status}")
            return True
        else:
            logger.warning(f"Could not update processing status for session {session_id}: Session not found")
            return False
    except Exception as e:
        logger.error(f"Error updating processing status for session {session_id}: {str(e)}")
        return False

@api_bp.route('/process-upload/<session_id>', methods=['POST', 'OPTIONS'])
def process_upload(session_id):
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Sitzung abrufen
    upload = Upload.query.filter_by(session_id=session_id).first()
    
    if not upload:
        return jsonify({'error': 'Sitzung nicht gefunden', 'success': False}), 404
    
    # Aktualisiere den Verarbeitungsstatus
    upload.processing_status = 'processing'
    db.session.commit()
    
    # OpenAI-Client initialisieren
    openai_api_key = current_app.config.get('OPENAI_API_KEY')
    client = OpenAI(api_key=openai_api_key)
    
    # Textverarbeitung und Analyse durchführen
    try:
        # Textextraktion wurde bereits in upload_file durchgeführt
        extracted_text = upload.content
        
        # Prüfe Textlänge und extrahiere eine vernünftige Menge
        max_text_length = 50000  # Grenzwert für die Analyse
        if extracted_text and len(extracted_text) > max_text_length:
            extracted_text = extracted_text[:max_text_length] + "... [Text gekürzt]"
        
        # Nur wenn tatsächlich Text vorhanden ist
        if extracted_text and len(extracted_text) > 100:  # Mindestens 100 Zeichen
            # Spracherkennung
            language = detect_language(extracted_text)
            
            # Eingebettete Analyse durchführen - mit Session-ID für Token-Tracking
            analysis_result = analyze_content(
                extracted_text, 
                client, 
                language=language,
                session_id=session_id,  # Session-ID für Token-Tracking
                function_name="process_upload_analyze"  # Funktion für Token-Tracking
            )
            
            # rest of the function stays the same...
        else:
            # Kein Text gefunden oder zu kurz
            upload.processing_status = 'failed'
            db.session.commit()
            
            return jsonify({
                'error': 'Kein ausreichender Text extrahiert',
                'success': False
            }), 400
    except Exception as e:
        logger.error(f"Error in process_upload: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}), 500

# Hinzufügen eines neuen API-Endpunkts für Session-Diagnostik
@api_bp.route('/diagnostics/<session_id>', methods=['GET'])
@token_required
def get_diagnostics(session_id):
    """API-Endpunkt für umfassende Session-Diagnose"""
    # Grundlegende Authentifizierung
    if not hasattr(g, 'user') or not g.user:
        return jsonify({"error": "Nicht authentifiziert"}), 401
        
    # Daten aus verschiedenen Quellen sammeln
    diagnostics = {}
    
    # Redis-Daten
    redis_keys = [
        f"processing_status:{session_id}",
        f"processing_progress:{session_id}",
        f"error_details:{session_id}",
        f"openai_last_response:{session_id}"
    ]
    
    diagnostics["redis"] = {}
    for key in redis_keys:
        value = redis_client.get(key)
        if value:
            try:
                diagnostics["redis"][key] = json.loads(value)
            except:
                diagnostics["redis"][key] = value.decode('utf-8')
        else:
            diagnostics["redis"][key] = None
    
    # Datenbank-Status
    upload = Upload.query.filter_by(session_id=session_id).first()
    if upload:
        diagnostics["database"] = {
            "id": upload.id,
            "user_id": upload.user_id,
            "created_at": upload.created_at.isoformat() if upload.created_at else None,
            "last_used_at": upload.last_used_at.isoformat() if upload.last_used_at else None,
            "processing_status": upload.processing_status,
            "file_names": [
                getattr(upload, f"file_name_{i}") 
                for i in range(1, 6) 
                if hasattr(upload, f"file_name_{i}") and getattr(upload, f"file_name_{i}")
            ],
            "content_length": len(upload.content) if upload.content else 0
        }
    else:
        diagnostics["database"] = None
        
    # Aktuelle Verarbeitungsstatistiken
    flashcards_count = Flashcard.query.filter_by(upload_id=upload.id).count() if upload else 0
    questions_count = Question.query.filter_by(upload_id=upload.id).count() if upload else 0
    topics_count = Topic.query.filter_by(upload_id=upload.id).count() if upload else 0
    
    diagnostics["stats"] = {
        "flashcards": flashcards_count,
        "questions": questions_count,
        "topics": topics_count
    }
    
    return jsonify({
        "success": True,
        "diagnostics": diagnostics,
        "session_id": session_id
    })

def calculate_upload_progress(session_id):
    """Berechnet den Upload-Fortschritt basierend auf den gespeicherten Chunks."""
    try:
        total_chunks = int(redis_client.get(f"total_chunks:{session_id}") or 0)
        uploaded_chunks = int(redis_client.get(f"uploaded_chunks:{session_id}") or 0)
        if total_chunks == 0:
            return 0
        return (uploaded_chunks / total_chunks) * 100
    except Exception as e:
        logger.error(f"Fehler bei der Fortschrittsberechnung: {str(e)}")
        return 0

def estimate_remaining_time(session_id):
    """Schätzt die verbleibende Upload-Zeit basierend auf der bisherigen Geschwindigkeit."""
    try:
        start_time = float(redis_client.get(f"upload_start_time:{session_id}") or 0)
        uploaded_chunks = int(redis_client.get(f"uploaded_chunks:{session_id}") or 0)
        total_chunks = int(redis_client.get(f"total_chunks:{session_id}") or 0)
        
        if uploaded_chunks == 0 or start_time == 0:
            return None
            
        elapsed_time = time.time() - start_time
        chunks_per_second = uploaded_chunks / elapsed_time
        remaining_chunks = total_chunks - uploaded_chunks
        
        if chunks_per_second > 0:
            return remaining_chunks / chunks_per_second
        return None
    except Exception as e:
        logger.error(f"Fehler bei der Zeitberechnung: {str(e)}")
        return None

def save_chunk(session_id, chunk_index, chunk_data):
    """Speichert einen einzelnen Chunk in Redis."""
    try:
        chunk_key = f"chunk:{session_id}:{chunk_index}"
        redis_client.set(chunk_key, chunk_data, ex=3600)  # 1 Stunde Gültigkeit
        redis_client.incr(f"uploaded_chunks:{session_id}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern des Chunks: {str(e)}")
        return False

def combine_chunks(session_id):
    """Kombiniert alle gespeicherten Chunks zu einer vollständigen Datei."""
    try:
        total_chunks = int(redis_client.get(f"total_chunks:{session_id}") or 0)
        combined_data = b""
        
        for i in range(total_chunks):
            chunk_key = f"chunk:{session_id}:{i}"
            chunk_data = redis_client.get(chunk_key)
            if chunk_data:
                combined_data += chunk_data
                redis_client.delete(chunk_key)  # Lösche den Chunk nach dem Kombinieren
        
        return combined_data
    except Exception as e:
        logger.error(f"Fehler beim Kombinieren der Chunks: {str(e)}")
        return None

def cleanup_chunks(session_id):
    """Entfernt alle gespeicherten Chunks für eine Session."""
    try:
        total_chunks = int(redis_client.get(f"total_chunks:{session_id}") or 0)
        for i in range(total_chunks):
            chunk_key = f"chunk:{session_id}:{i}"
            redis_client.delete(chunk_key)
        redis_client.delete(f"total_chunks:{session_id}")
        redis_client.delete(f"uploaded_chunks:{session_id}")
        redis_client.delete(f"upload_start_time:{session_id}")
    except Exception as e:
        logger.error(f"Fehler beim Aufräumen der Chunks: {str(e)}")

@api_bp.route('/upload/chunk', methods=['POST', 'OPTIONS'])
@token_required
def upload_chunk():
    """
    Verarbeitet einzelne Chunks eines Datei-Uploads mit Fortschrittsverfolgung.
    """
    try:
        logger.info("💾 CHUNK-UPLOAD: Chunk-Upload-Anfrage empfangen")
        
        if request.method == 'OPTIONS':
            return jsonify({"success": True})
            
        # Authentifizierung für nicht-OPTIONS Anfragen
        auth_decorator = token_required(lambda: None)
        auth_result = auth_decorator()
        if auth_result is not None:
            return auth_result
        
        # Überprüfe die erforderlichen Parameter
        if 'chunk' not in request.files or 'chunk_index' not in request.form or 'total_chunks' not in request.form:
            logger.error("❌ CHUNK-UPLOAD: Fehlende erforderliche Parameter")
            return create_error_response(
                "Fehlende Parameter", 
                ERROR_INVALID_INPUT, 
                {"detail": "Missing required parameters"}
            )
        
        chunk = request.files['chunk']
        chunk_index = int(request.form['chunk_index'])
        total_chunks = int(request.form['total_chunks'])
        session_id = request.form.get('session_id')
        file_name = request.form.get('file_name')
        user_id = getattr(request, 'user_id', None)
        
        logger.info(f"📁 CHUNK-UPLOAD: Parameter - chunk_index={chunk_index}, total_chunks={total_chunks}, session_id={session_id}, file_name={file_name}, user_id={user_id}")
        
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"🔑 CHUNK-UPLOAD: Neue Session-ID generiert: {session_id}")
        
        # Initialisiere die Upload-Session beim ersten Chunk
        if chunk_index == 0:
            logger.info(f"🏁 CHUNK-UPLOAD: Erster Chunk empfangen, initialisiere Session {session_id}")
            redis_client.set(f"total_chunks:{session_id}", total_chunks, ex=3600)
            redis_client.set(f"upload_start_time:{session_id}", str(time.time()), ex=3600)
            redis_client.set(f"file_name:{session_id}", file_name, ex=3600)
        
        # Speichere den Chunk
        logger.info(f"📥 CHUNK-UPLOAD: Lese Chunk {chunk_index} von {total_chunks} für Session {session_id}")
        chunk_data = chunk.read()
        logger.info(f"📦 CHUNK-UPLOAD: Chunk {chunk_index} Größe = {len(chunk_data)} Bytes")
        
        if not save_chunk(session_id, chunk_index, chunk_data):
            logger.error(f"❌ CHUNK-UPLOAD: Fehler beim Speichern von Chunk {chunk_index}")
            return create_error_response(
                "Fehler beim Speichern des Chunks", 
                ERROR_FILE_PROCESSING
            )
        
        # Berechne Fortschritt und verbleibende Zeit
        progress = calculate_upload_progress(session_id)
        remaining_time = estimate_remaining_time(session_id)
        logger.info(f"📊 CHUNK-UPLOAD: Progress={progress}%, Remaining Time={remaining_time}s")
        
        # Aktualisiere den Fortschritt in Redis
        redis_client.set(f"upload_progress:{session_id}", progress, ex=3600)
        
        # Wenn alle Chunks hochgeladen wurden, starte die Verarbeitung
        if chunk_index == total_chunks - 1:
            logger.info(f"🏆 CHUNK-UPLOAD: Letzter Chunk empfangen, beginne Verarbeitung für Session {session_id}")
            
            # Kombiniere alle Chunks
            logger.info(f"🔄 CHUNK-UPLOAD: Kombiniere alle Chunks für Session {session_id}")
            file_content = combine_chunks(session_id)
            if not file_content:
                logger.error(f"❌ CHUNK-UPLOAD: Fehler beim Kombinieren der Chunks für Session {session_id}")
                return create_error_response(
                    "Fehler beim Kombinieren der Chunks", 
                    ERROR_FILE_PROCESSING
                )
            
            logger.info(f"📋 CHUNK-UPLOAD: Kombinierte Datei Größe = {len(file_content)} Bytes")
            
            # Starte die Verarbeitung
            logger.info(f"🚀 CHUNK-UPLOAD: Sende Verarbeitungsauftrag an Worker für Session {session_id}")
            task_files_data = [(file_name, file_content.hex())]
            
            # Ausführliche Protokollierung bei der Erstellung der Worker-Task
            logger.info(f"📤 CHUNK-UPLOAD: Delegiere 'process_upload' Aufgabe für Session {session_id}")
            task = delegate_to_worker('process_upload', session_id, task_files_data, user_id)
            logger.info(f"✅ CHUNK-UPLOAD: Worker-Task erstellt mit ID {task.id}")
            
            # Speichere die Task-ID
            redis_client.set(f"task_id:{session_id}", task.id, ex=3600)
            logger.info(f"💾 CHUNK-UPLOAD: Task-ID in Redis gespeichert: {task.id}")
            
            # Lösche die Chunks
            logger.info(f"🧹 CHUNK-UPLOAD: Bereinige temporäre Chunks für Session {session_id}")
            cleanup_chunks(session_id)
        
        return jsonify({
            "success": True,
            "message": "Chunk erfolgreich hochgeladen",
            "session_id": session_id,
            "progress": progress,
            "remaining_time": remaining_time,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks
        })
        
    except Exception as e:
        session_id = request.form.get('session_id', 'unknown')
        error_message = f"❌ CHUNK-UPLOAD: Kritischer Fehler: {str(e)}"
        logger.error(error_message)
        logger.error(f"Stacktrace: {traceback.format_exc()}")
        
        AppLogger.track_error(
            session_id,
            "chunk_upload_error",
            error_message,
            trace=traceback.format_exc()
        )
        
        return create_error_response(
            f"Fehler beim Chunk-Upload: {str(e)}", 
            ERROR_FILE_PROCESSING
        )

@api_bp.route('/upload/progress/<session_id>', methods=['GET', 'OPTIONS'])
@token_required
def get_upload_progress(session_id):
    """
    Liefert detaillierte Informationen zum Fortschritt eines Uploads und der Verarbeitung.
    Enthält erweiterte Fehlerbehandlung und Timeouts.
    """
    try:
        if request.method == 'OPTIONS':
            return jsonify({"success": True})
            
        # Überprüfe, ob die Session existiert
        if not redis_client.exists(f"task_id:{session_id}"):
            # Prüfe in der Datenbank, ob die Session existiert
            upload = Upload.query.filter_by(session_id=session_id).first()
            if not upload:
                return jsonify({
                    "success": False,
                    "error": {
                        "message": f"Session {session_id} nicht gefunden",
                        "code": "session_not_found"
                    }
                }), 404
        
        # Sammle alle relevanten Daten
        progress_data = {}
        
        # 1. Fortschrittsdaten
        progress_json = redis_client.get(f"processing_progress:{session_id}")
        if progress_json:
            try:
                progress_data.update(json.loads(progress_json))
            except json.JSONDecodeError:
                pass
        
        # 2. Status
        status = redis_client.get(f"processing_status:{session_id}") or "unknown"
        progress_data["status"] = status.decode('utf-8') if isinstance(status, bytes) else status
        
        # 3. Task-ID
        task_id = redis_client.get(f"task_id:{session_id}")
        if task_id:
            progress_data["task_id"] = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
        
        # 4. Zeitberechnung
        start_time = redis_client.get(f"processing_start_time:{session_id}")
        if start_time:
            start_time = float(start_time.decode('utf-8') if isinstance(start_time, bytes) else start_time)
            current_time = time.time()
            elapsed_time = current_time - start_time
            progress_data["elapsed_time"] = elapsed_time
            
            # Verbleibende Zeit schätzen (falls Fortschritt > 0)
            if progress_data.get("progress", 0) > 0:
                estimated_total_time = elapsed_time / (progress_data["progress"] / 100)
                progress_data["estimated_remaining_time"] = max(0, estimated_total_time - elapsed_time)
        
        # 5. Heartbeat prüfen (Worker-Gesundheit)
        last_heartbeat = redis_client.get(f"processing_heartbeat:{session_id}")
        if last_heartbeat:
            last_heartbeat = float(last_heartbeat.decode('utf-8') if isinstance(last_heartbeat, bytes) else last_heartbeat)
            heartbeat_age = time.time() - last_heartbeat
            progress_data["worker_heartbeat_age"] = heartbeat_age
            
            # Warnung bei altem Heartbeat
            if heartbeat_age > 60:
                progress_data["worker_status"] = "degraded"
                if heartbeat_age > 300:
                    progress_data["worker_status"] = "stalled"
            else:
                progress_data["worker_status"] = "healthy"
        
        # 6. Fehlerdaten (falls vorhanden)
        error_json = redis_client.get(f"processing_error:{session_id}")
        if error_json:
            try:
                progress_data["error"] = json.loads(error_json)
            except json.JSONDecodeError:
                progress_data["error"] = {"message": "Fehler beim Parsen der Fehlerdaten"}
        
        # 7. Verarbeitungsdaten
        details_json = redis_client.get(f"processing_details:{session_id}")
        if details_json:
            try:
                progress_data["details"] = json.loads(details_json)
            except json.JSONDecodeError:
                pass
        
        # Prüfe, ob die Verarbeitung hängen geblieben ist (kein Fortschritt über lange Zeit)
        last_update = redis_client.get(f"processing_last_update:{session_id}")
        if last_update:
            last_update = float(last_update.decode('utf-8') if isinstance(last_update, bytes) else last_update)
            update_age = time.time() - last_update
            progress_data["last_update_age"] = update_age
            
            # Bei zu langem Stillstand (5 Minuten), setze Status auf "stalled"
            if update_age > 300 and progress_data.get("status") == "processing":
                progress_data["status"] = "stalled"
                progress_data["stall_detected"] = True
                redis_client.set(f"processing_status:{session_id}", "stalled", ex=7200)
        
        return jsonify({
            "success": True,
            "progress": progress_data.get("progress", 0),
            "status": progress_data.get("status", "unknown"),
            "message": progress_data.get("message", ""),
            "data": progress_data
        })
        
    except Exception as e:
        AppLogger.track_error(
            session_id,
            "progress_check_error",
            f"Fehler beim Abrufen des Fortschritts: {str(e)}",
            trace=traceback.format_exc()
        )
        return create_error_response(
            f"Fehler beim Abrufen des Fortschritts: {str(e)}", 
            ERROR_FILE_PROCESSING
        )

@api_bp.route('/upload/retry/<session_id>', methods=['POST', 'OPTIONS'])
@token_required
def retry_processing(session_id):
    """
    Ermöglicht die Wiederaufnahme der Verarbeitung für eine hängengebliebene Session.
    """
    try:
        if request.method == 'OPTIONS':
            return jsonify({"success": True})
            
        # Suche Upload in der Datenbank
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({
                "success": False,
                "error": {
                    "message": f"Session {session_id} nicht gefunden",
                    "code": "session_not_found"
                }
            }), 404
        
        # Prüfe den aktuellen Status
        current_status = redis_client.get(f"processing_status:{session_id}")
        if current_status:
            current_status = current_status.decode('utf-8') if isinstance(current_status, bytes) else current_status
            
            # Nur fehlgeschlagene oder hängengebliebene Sessions können neu gestartet werden
            if current_status not in ["failed", "stalled", "timeout"]:
                return jsonify({
                    "success": False,
                    "error": {
                        "message": f"Session {session_id} kann nicht neu gestartet werden (Status: {current_status})",
                        "code": "invalid_status_for_retry"
                    }
                }), 400
        
        # Setze Lock zurück
        redis_client.delete(f"session_lock:{session_id}")
        redis_client.delete(f"session_lock_info:{session_id}")
        
        # Setze Status zurück
        redis_client.set(f"processing_status:{session_id}", "restarting", ex=7200)
        
        # Erstelle neuen Celery-Task
        task = delegate_to_worker('process_upload', session_id, [], upload.user_id)
        
        # Speichere neue Task-ID
        redis_client.set(f"task_id:{session_id}", task.id, ex=7200)
        redis_client.set(f"restart_time:{session_id}", str(time.time()), ex=7200)
        
        return jsonify({
            "success": True,
            "message": "Verarbeitung wurde neu gestartet",
            "session_id": session_id,
            "task_id": task.id
        })
        
    except Exception as e:
        AppLogger.track_error(
            session_id,
            "retry_error",
            f"Fehler beim Neustart der Verarbeitung: {str(e)}",
            trace=traceback.format_exc()
        )
        return create_error_response(
            f"Fehler beim Neustart der Verarbeitung: {str(e)}", 
            ERROR_FILE_PROCESSING
        )

@api_bp.route('/debug-status/<session_id>', methods=['GET'])
def debug_session_status(session_id):
    """
    Gibt den aktuellen Status und interne Debug-Informationen für eine Session zurück.
    Nur für Entwicklungs- und Diagnose-Zwecke.
    """
    try:
        # Sammle alle relevanten Redis-Schlüssel für diese Session
        redis_keys = []
        for key_pattern in [
            f"processing_status:{session_id}",
            f"processing_start_time:{session_id}",
            f"processing_details:{session_id}",
            f"processing_progress:{session_id}",
            f"error_details:{session_id}",
            f"openai_error:{session_id}",
            f"task_id:{session_id}",
            f"processing_completed:{session_id}",
            f"processing_completed_at:{session_id}",
            f"processing_result:{session_id}",
            f"debug:{session_id}:*",
            f"processing_heartbeat:{session_id}",
            f"processing_current_file:{session_id}",
            f"processing_file_index:{session_id}",
            f"processing_file_count:{session_id}",
            f"upload_files_data:{session_id}",
            f"session_lock:{session_id}",
            f"session_lock_info:{session_id}"
        ]:
            # Bei Schlüsseln mit Wildcard
            if "*" in key_pattern:
                matching_keys = redis_client.keys(key_pattern)
                for key in matching_keys:
                    redis_keys.append(key.decode('utf-8') if isinstance(key, bytes) else key)
            # Bei normalen Schlüsseln
            elif redis_client.exists(key_pattern):
                redis_keys.append(key_pattern)
        
        # Sammle alle Werte aus Redis
        redis_data = {}
        for key in redis_keys:
            value = redis_client.get(key)
            if value:
                try:
                    # Versuche es als JSON zu dekodieren
                    value = json.loads(value.decode('utf-8'))
                except:
                    # Wenn nicht möglich, behandle es als String
                    value = value.decode('utf-8') if isinstance(value, bytes) else value
                redis_data[key] = value
            else:
                redis_data[key] = None
        
        # Hole Datenbank-Informationen
        db_info = {}
        upload = Upload.query.filter_by(session_id=session_id).first()
        if upload:
            db_info = {
                "id": upload.id,
                "user_id": upload.user_id,
                "session_id": upload.session_id,
                "processing_status": upload.processing_status,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "updated_at": upload.updated_at.isoformat() if upload.updated_at else None,
                "completed_at": upload.completed_at.isoformat() if upload.completed_at else None,
                "file_name_1": upload.file_name_1,
                "file_name_2": upload.file_name_2,
                "file_name_3": upload.file_name_3,
                "has_result": upload.result is not None,
                "has_content": bool(upload.content),
                "content_length": len(upload.content) if upload.content else 0
            }
            
            # Zähle die Einträge in anderen Tabellen
            db_info["flashcards_count"] = Flashcard.query.filter_by(upload_id=upload.id).count()
            db_info["questions_count"] = Question.query.filter_by(upload_id=upload.id).count()
            db_info["topics_count"] = Topic.query.filter_by(upload_id=upload.id).count()
            db_info["connections_count"] = Connection.query.filter_by(upload_id=upload.id).count()
        
        # Status für Celery-Worker
        worker_status = "unknown"
        task_id = redis_data.get(f"task_id:{session_id}")
        if isinstance(task_id, dict) and "task_id" in task_id:
            task_id = task_id["task_id"]
        
        try:
            # Versuche, den Task direkt anzuschauen
            from celery.result import AsyncResult
            if task_id:
                task_result = AsyncResult(task_id)
                worker_status = {
                    "status": task_result.status,
                    "ready": task_result.ready(),
                    "task_id": task_id,
                    "info": str(task_result.info) if task_result.info else None
                }
                
                # Versuche, den aktiven Worker zu identifizieren
                try:
                    from celery.task.control import inspect
                    i = inspect()
                    active = i.active()
                    reserved = i.reserved()
                    scheduled = i.scheduled()
                    
                    worker_tasks = {}
                    if active:
                        for worker_name, tasks in active.items():
                            for task in tasks:
                                if task.get('id') == task_id:
                                    worker_status["worker"] = worker_name
                                    worker_status["state"] = "active"
                                    worker_status["task_details"] = task
                                    break
                    
                    if not worker_status.get("worker") and reserved:
                        for worker_name, tasks in reserved.items():
                            for task in tasks:
                                if task.get('id') == task_id:
                                    worker_status["worker"] = worker_name
                                    worker_status["state"] = "reserved"
                                    worker_status["task_details"] = task
                                    break
                    
                    if not worker_status.get("worker") and scheduled:
                        for worker_name, tasks in scheduled.items():
                            for task in tasks:
                                if task[0].get('id') == task_id:  # Scheduled tasks sind als (task, eta) Tupel
                                    worker_status["worker"] = worker_name
                                    worker_status["state"] = "scheduled"
                                    worker_status["task_details"] = task[0]
                                    worker_status["eta"] = task[1]
                                    break
                    
                    # Hole alle laufenden Worker
                    stats = i.stats()
                    if stats:
                        worker_status["all_workers"] = list(stats.keys())
                except Exception as inspect_error:
                    worker_status["inspect_error"] = str(inspect_error)
            
        except Exception as e:
            worker_status = {"status": "error", "message": str(e)}
        
        # Überprüfe auch Systemressourcen
        system_info = {}
        try:
            import psutil
            system_info = {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent,
                "num_processes": len(psutil.pids()),
                "uptime": psutil.boot_time()
            }
        except:
            # psutil könnte nicht verfügbar sein
            pass
            
        # Zeitberechnung für verschiedene Aspekte
        timing_info = {}
        start_time = redis_data.get(f"processing_start_time:{session_id}")
        if start_time:
            start_time = float(start_time) if isinstance(start_time, str) else start_time
            current_time = time.time()
            elapsed = current_time - start_time
            timing_info["elapsed_seconds"] = elapsed
            timing_info["elapsed_formatted"] = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
            
            # Schätze verbleibende Zeit, wenn Fortschritt vorhanden
            progress_data = redis_data.get(f"processing_progress:{session_id}")
            if progress_data and isinstance(progress_data, dict) and "progress" in progress_data:
                progress = progress_data["progress"]
                if progress > 0:
                    total_estimated = elapsed / (progress / 100)
                    remaining = max(0, total_estimated - elapsed)
                    timing_info["estimated_remaining_seconds"] = remaining
                    timing_info["estimated_remaining_formatted"] = f"{int(remaining // 60)}m {int(remaining % 60)}s"
                    timing_info["estimated_total_seconds"] = total_estimated
                    timing_info["estimated_total_formatted"] = f"{int(total_estimated // 60)}m {int(total_estimated % 60)}s"
        
        # Zusammenfassung erstellen
        status_summary = "Unbekannt"
        status_value = redis_data.get(f"processing_status:{session_id}")
        if status_value:
            if isinstance(status_value, dict) and "status" in status_value:
                status_summary = status_value["status"]
            else:
                status_summary = status_value
                
        if upload and upload.processing_status:
            db_status = upload.processing_status
            if db_status == "completed":
                status_summary = "Abgeschlossen (DB)"
            elif db_status == "failed" or db_status == "error":
                status_summary = f"Fehler: {db_status} (DB)"
            
        # Problemidentifikation
        issues = []
        
        # Prüfe auf Fehler in Redis
        if status_summary and ("error" in status_summary.lower() or "failed" in status_summary.lower()):
            issues.append(f"Fehler-Status: {status_summary}")
        
        # Prüfe auf Diskrepanz zwischen Redis und DB
        if upload and status_value and upload.processing_status != status_value:
            issues.append(f"Status-Diskrepanz: Redis={status_value}, DB={upload.processing_status}")
        
        # Prüfe auf Heartbeat-Alter
        heartbeat = redis_data.get(f"processing_heartbeat:{session_id}")
        if heartbeat:
            heartbeat_time = float(heartbeat) if isinstance(heartbeat, str) else heartbeat
            heartbeat_age = time.time() - heartbeat_time
            if heartbeat_age > 120:  # 2 Minuten ohne Heartbeat
                issues.append(f"Heartbeat ist alt: {int(heartbeat_age)}s")
        
        # Prüfe auf veralteten Lock
        lock = redis_data.get(f"session_lock:{session_id}")
        if lock and not redis_data.get(f"processing_heartbeat:{session_id}"):
            issues.append("Session ist gesperrt, aber kein aktiver Heartbeat")
            
        # Rückgabe aller gesammelten Informationen
        return jsonify({
            "redis_data": redis_data,
            "db_info": db_info,
            "worker_status": worker_status,
            "system_info": system_info,
            "timing_info": timing_info,
            "status_summary": status_summary,
            "issues": issues,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error(f"Fehler beim Sammeln von Debug-Informationen: {str(e)}")
        logger.error(traceback_str)
        return jsonify({
            "status": "error",
            "message": f"Fehler beim Sammeln von Debug-Informationen: {str(e)}",
            "traceback": traceback_str
        }), 500
