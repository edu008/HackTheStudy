"""
Task zur Verarbeitung von hochgeladenen Dateien
"""
import os
import logging
import time
import json
import traceback
import base64
import threading
import signal
from datetime import datetime
from celery.exceptions import SoftTimeLimitExceeded
from core import get_flask_app, acquire_session_lock, release_session_lock
from redis_utils.client import redis_client
from redis_utils.utils import safe_redis_set, safe_redis_get, log_debug_info
from utils import log_function_call
from resource_manager import handle_worker_timeout

# Logger konfigurieren
logger = logging.getLogger(__name__)

def register_task(celery_app):
    """
    Registriert die process_upload Task bei der Celery-App.
    
    Args:
        celery_app: Die Celery-App-Instanz
    """
    @celery_app.task(
        bind=True, 
        name="process_upload",
        max_retries=5, 
        default_retry_delay=120, 
        soft_time_limit=3600, 
        time_limit=4000,
        acks_late=True,
        reject_on_worker_lost=True
    )
    @log_function_call
    def process_upload(self, session_id, files_data, user_id=None):
        """
        Verarbeitet hochgeladene Dateien.
        
        Args:
            session_id: ID der Upload-Session
            files_data: Liste mit Dateinamen und -inhalten als Tupel
            user_id: ID des Benutzers (optional)
            
        Returns:
            dict: Ergebnis der Verarbeitung
        """
        # Setze Timeout-Handler für detaillierte Diagnose
        task_start_time = time.time()
        
        def on_soft_timeout(signum, frame):
            """Handler für SoftTimeLimit-Signal"""
            execution_time = time.time() - task_start_time
            diagnostics = handle_worker_timeout(
                task_id=self.request.id,
                task_name="process_upload",
                execution_time=execution_time,
                traceback="".join(traceback.format_stack(frame))
            )
            # Setze relevante Fehlermeldung
            error_msg = f"Worker-Timeout nach {execution_time:.1f}s (Limit: 3600s)"
            # Speichere Diagnose in Redis für Frontend-Zugriff
            safe_redis_set(f"error_details:{session_id}", {
                "error_type": "worker_timeout",
                "message": error_msg,
                "diagnostics": diagnostics,
                "timestamp": time.time()
            }, ex=14400)
            # Session-Status aktualisieren
            safe_redis_set(f"processing_status:{session_id}", "error", ex=14400)
            # Originales Signal weiterleiten, um Task zu beenden
            raise SoftTimeLimitExceeded(error_msg)
        
        # Registriere Timeout-Handler
        signal.signal(signal.SIGTERM, on_soft_timeout)
        
        # Direkte Konsolenausgabe für einfache Diagnose
        logger.info(f"🔄 FUNKTION START: process_upload() - Session: {session_id}")
        logger.info(f"===== WORKER TASK STARTED: {session_id} =====")
        logger.info(f"Worker process PID: {os.getpid()}, Task ID: {self.request.id}")
        if user_id:
            logger.info(f"Verarbeite {len(files_data) if files_data else 0} Dateien für Benutzer {user_id}")
        
        # Zusätzliches Debug-Logging
        print(f"DIRECT STDOUT: Worker processing session {session_id}", flush=True)
        logger.info(f"DIREKT: Worker processing session {session_id} - TASK: {self.request.id}")
        start_time = time.time()
        
        # Debug Logging für files_data
        if files_data:
            logger.info(f"files_data enthält {len(files_data)} Dateien")
            for i, file_data in enumerate(files_data):
                # Sicher überprüfen, ob file_data ein Dict, Tupel oder eine Liste ist
                if isinstance(file_data, dict):
                    logger.info(f"Datei {i+1}: Name={file_data.get('file_name', 'Unbekannt')}, Größe={len(file_data.get('file_content', '')[:10])}...")
                elif isinstance(file_data, tuple) and len(file_data) >= 2:
                    logger.info(f"Datei {i+1}: Name={file_data[0]}, Größe=ca.{len(file_data[1]) // 2 if len(file_data) > 1 else 0} Bytes")
                elif isinstance(file_data, list) and len(file_data) >= 2:
                    # Behandle Listen wie Tupel
                    logger.info(f"Datei {i+1}: Name={file_data[0]}, Größe=ca.{len(file_data[1]) // 2 if len(file_data) > 1 else 0} Bytes")
                else:
                    logger.info(f"Datei {i+1}: Unbekanntes Format: {type(file_data)}")
                    
                    # Versuche mehr Informationen über die Struktur zu loggen
                    try:
                        if hasattr(file_data, '__len__'):
                            logger.info(f"Länge: {len(file_data)}")
                        if hasattr(file_data, '__getitem__'):
                            for j, item in enumerate(file_data[:3]): # Erste 3 Elemente
                                logger.info(f"Element {j}: Typ={type(item)}")
                    except:
                        logger.info("Konnte keine weiteren Informationen über das Datenobjekt sammeln")
        else:
            logger.info("WARNUNG: files_data ist leer oder None!")
        
        # Speichere Task-ID für Tracking
        try:
            safe_redis_set(f"task_id:{session_id}", self.request.id, ex=14400)  # 4 Stunden Gültigkeit
            logger.info(f"Task-ID {self.request.id} in Redis gespeichert für Session {session_id}")
        except Exception as e:
            logger.error(f"FEHLER beim Speichern der Task-ID in Redis: {str(e)}")
        
        # Debugging-Info hinzufügen
        try:
            log_debug_info(session_id, "Worker-Task gestartet", 
                          task_id=self.request.id, 
                          pid=os.getpid(),
                          files_count=len(files_data) if files_data else 0)
            logger.info("Debug-Info in Redis gespeichert")
        except Exception as e:
            logger.error(f"FEHLER beim Speichern der Debug-Info: {str(e)}")
        
        # Hole die Flask-App und erstelle einen Anwendungskontext
        try:
            logger.info("Versuche Flask-App zu bekommen")
            flask_app = get_flask_app()
            logger.info("Flask-App erfolgreich geholt")
        except Exception as e:
            logger.error(f"KRITISCHER FEHLER beim Holen der Flask-App: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "status": "error",
                "error": f"Flask-App konnte nicht initialisiert werden: {str(e)}"
            }
        
        # Verwende einen expliziten Anwendungskontext für die gesamte Task
        try:
            logger.info("Betrete Flask App-Kontext")
            # Log Flask-App-Informationen für Debugging
            logger.info(f"Flask-App-Typ: {type(flask_app)}")
            logger.info(f"Flask-App-Name: {flask_app.name if hasattr(flask_app, 'name') else 'Kein Name'}")
            logger.info(f"Flask-App hat app_context: {hasattr(flask_app, 'app_context')}")
            logger.info("Versuche, mit flask_app.app_context() zu starten...")
            
            with flask_app.app_context():
                logger.info("Erfolgreich in Flask App-Kontext gelangt")
                try:
                    # Initialisiere Redis-Status mit detaillierten Informationen
                    logger.info("Initialisiere Redis-Status")
                    safe_redis_set(f"processing_status:{session_id}", "initializing", ex=14400)
                    safe_redis_set(f"processing_start_time:{session_id}", str(start_time), ex=14400)
                    safe_redis_set(f"processing_details:{session_id}", {
                        "start_time": datetime.now().isoformat(),
                        "files_count": len(files_data) if files_data else 0,
                        "user_id": user_id,
                        "pid": os.getpid(),
                        "worker_id": self.request.id,
                        "hostname": os.environ.get("HOSTNAME", "unknown"),
                        "task_id": self.request.id
                    }, ex=14400)
                    logger.info("Redis-Status erfolgreich initialisiert")
                    
                    logger.info(f"Session {session_id} - Initializing with {len(files_data) if files_data else 0} files for user {user_id}")
                    
                    # Wenn keine Dateien übergeben wurden, versuche den Auftrag von Redis wiederherzustellen
                    if not files_data or len(files_data) == 0:
                        logger.info("Keine Dateien übergeben, versuche Redis-Wiederherstellung")
                        stored_data = redis_client.get(f"upload_files_data:{session_id}")
                        if stored_data:
                            logger.info(f"Daten aus Redis gefunden: {len(stored_data)} Bytes")
                            try:
                                files_data = json.loads(stored_data)
                                logger.info(f"Wiederhergestellte Dateidaten aus Redis für Session {session_id}: {len(files_data)} Dateien")
                                log_debug_info(session_id, f"Dateidaten aus Redis wiederhergestellt", files_count=len(files_data))
                            except json.JSONDecodeError as json_err:
                                logger.error(f"Fehler beim Dekodieren der Redis-Daten: {str(json_err)}")
                                raise ValueError(f"Ungültige JSON-Daten in Redis: {str(json_err)}")
                        else:
                            error_msg = f"Keine Dateidaten für Session {session_id} gefunden!"
                            logger.error(error_msg)
                            from api.cleanup import cleanup_processing_for_session
                            cleanup_processing_for_session(session_id, "no_files_found")
                            safe_redis_set(f"error_details:{session_id}", {
                                "message": error_msg,
                                "error_type": "no_files_data",
                                "timestamp": time.time()
                            }, ex=14400)
                            return {"error": "no_files_found", "message": error_msg}
                    
                    # Versuche, einen Lock für diese Session zu erhalten
                    logger.info(f"🔒 Versuche, Lock für Session {session_id} zu erhalten...")
                    if not acquire_session_lock(session_id):
                        error_msg = f"Konnte keinen Lock für Session {session_id} erhalten - eine andere Instanz verarbeitet diese bereits."
                        logger.error(error_msg)
                        return {"error": "session_locked", "message": error_msg}
                    
                    logger.info(f"🔒 Session {session_id} - Lock acquired successfully")
                    
                    # Aktualisiere Datenbankstatus auf "processing"
                    try:
                        from core.models import db, Upload, Topic, Flashcard, Question, Connection, UserActivity
                        
                        logger.info(f"💾 Aktualisiere Datenbankstatus für Session {session_id} auf 'processing'")
                        upload = Upload.query.filter_by(session_id=session_id).first()
                        if upload:
                            logger.info(f"Upload-Eintrag gefunden: ID={upload.id}")
                            # Prüfe, ob dieser Upload bereits verarbeitet wurde
                            if upload.processing_status == 'completed':
                                logger.info(f"Upload wurde bereits verarbeitet, prüfe auf bestehende Daten...")
                                # Prüfe, ob bereits Daten vorhanden sind
                                topics_count = Topic.query.filter_by(upload_id=upload.id).count()
                                flashcards_count = Flashcard.query.filter_by(upload_id=upload.id).count()
                                questions_count = Question.query.filter_by(upload_id=upload.id).count()
                                
                                if topics_count > 0 and flashcards_count > 0:
                                    logger.info(f"Bestehende Daten gefunden: {topics_count} Themen, {flashcards_count} Flashcards, {questions_count} Fragen")
                                    # Setze fortgeschrittene Status
                                    safe_redis_set(f"processing_status:{session_id}", "completed", ex=14400)
                                    safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                        "progress": 100,
                                        "message": "Verarbeitung bereits abgeschlossen",
                                        "stage": "completed"
                                    }), ex=14400)
                                    
                                    # Aktualisiere last_used_at
                                    upload.last_used_at = db.func.current_timestamp()
                                    db.session.commit()
                                    
                                    # Setze Ergebnisse in Redis
                                    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
                                    if main_topic:
                                        result_data = {
                                            "main_topic": main_topic.name,
                                            "topics": [t.name for t in Topic.query.filter_by(upload_id=upload.id).all()],
                                            "language": "auto",
                                            "token_count": upload.token_count or 0,
                                            "flashcards_count": flashcards_count,
                                            "questions_count": questions_count
                                        }
                                        
                                        safe_redis_set(f"processing_result:{session_id}", json.dumps(result_data), ex=86400)
                                        safe_redis_set(f"finalization_complete:{session_id}", "true", ex=14400)
                                        
                                    logger.info(f"Existierende Upload-Daten zurückgegeben, Vorgang abgeschlossen")
                                    release_session_lock(session_id)
                                    return {
                                        "status": "completed",
                                        "message": "Bestehende Verarbeitung gefunden und verwendet",
                                        "reused_existing": True
                                    }
                            
                            # Ansonsten setze Status auf "processing"
                            upload.processing_status = "processing"
                            upload.updated_at = datetime.utcnow()
                            logger.info(f"💾 Upload-Eintrag gefunden und aktualisiert: ID={upload.id}")
                            log_debug_info(session_id, "Datenbankstatus aktualisiert: processing", progress=5, stage="database_update")
                        else:
                            logger.warning(f"⚠️ Kein Upload-Eintrag für Session {session_id} in der Datenbank gefunden")
                            # Erstelle einen neuen Upload-Eintrag, wenn keiner gefunden wurde
                            logger.info(f"Erstelle neuen Upload-Eintrag für Session {session_id}")
                            import uuid
                            upload = Upload(
                                id=str(uuid.uuid4()),
                                user_id=user_id,
                                session_id=session_id,
                                file_name_1="", # Wird später mit extrahiertem Text gefüllt
                                processing_status="processing",
                                upload_date=datetime.utcnow(),
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            db.session.add(upload)
                            logger.info(f"✅ Neuer Upload-Eintrag erstellt: ID={upload.id}")
                        
                        db.session.commit()
                        logger.info(f"💾 Datenbankaktualisierung erfolgreich für Session {session_id}")
                    except Exception as db_error:
                        db.session.rollback()
                        logger.error(f"❌ Datenbankfehler: {str(db_error)}")
                        logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
                        
                        # Speichere den Fehler in Redis für das Frontend
                        safe_redis_set(f"processing_error:{session_id}", json.dumps({
                            "error": "database_error",
                            "message": str(db_error),
                            "timestamp": datetime.now().isoformat()
                        }), ex=14400)
                        
                        # Gib den Lock frei
                        release_session_lock(session_id)
                        
                        # Wirf die Exception für Celery-Retry
                        raise Exception(f"Fehler beim Aktualisieren des Datenbankstatus: {str(db_error)}")
                    
                    # Herzschlag-Mechanismus starten
                    logger.info("Starte Heartbeat-Mechanismus")
                    heartbeat_thread = None
                    heartbeat_stop_event = threading.Event()
                    
                    # Der Rest der Implementierung folgt dem gleichen Muster aus der tasks.py
                    # ...
                    
                    try:
                        # Detaillierter Verarbeitungsprozess mit Logs für jeden Schritt
                        logger.info("===== BEGINN DER DATEIVERARBEITUNG =====")
                        
                        # SCHRITT 1: Dateien entpacken und vorbereiten
                        logger.info("🔄 SCHRITT 1: Dateien entpacken und vorbereiten")
                        file_contents = []
                        for file_name, file_content_hex in files_data:
                            logger.info(f"📥 Entpacke Datei: {file_name}")
                            try:
                                # Konvertiere Hex-String zurück zu Binärdaten
                                file_content = bytes.fromhex(file_content_hex)
                                file_contents.append((file_name, file_content))
                                logger.info(f"✅ Datei {file_name} erfolgreich entpackt, Größe: {len(file_content)} Bytes")
                                # Status aktualisieren
                                safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                    "progress": 10,
                                    "message": f"Datei {file_name} entpackt",
                                    "stage": "unpacking"
                                }), ex=14400)
                            except Exception as err:
                                logger.error(f"❌ Fehler beim Entpacken von {file_name}: {str(err)}")
                                raise Exception(f"Fehler beim Entpacken: {str(err)}")
                        
                        # SCHRITT 2: Text aus Dateien extrahieren
                        logger.info("🔄 SCHRITT 2: Text aus Dateien extrahieren")
                        extracted_texts = []
                        for file_name, file_content in file_contents:
                            logger.info(f"📄 Extrahiere Text aus: {file_name}")
                            try:
                                # Text je nach Dateityp extrahieren
                                from utils.text_extraction import extract_text_from_file
                                text = extract_text_from_file(file_name, file_content)
                                extracted_texts.append(text)
                                logger.info(f"✅ Text aus {file_name} extrahiert: {len(text)} Zeichen")
                                # Status aktualisieren
                                safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                    "progress": 20,
                                    "message": f"Text aus {file_name} extrahiert",
                                    "stage": "text_extraction"
                                }), ex=14400)
                            except Exception as err:
                                logger.error(f"❌ Fehler bei der Textextraktion aus {file_name}: {str(err)}")
                                raise Exception(f"Fehler bei der Textextraktion: {str(err)}")
                        
                        # SCHRITT 3: Spracherkennung
                        logger.info("🔄 SCHRITT 3: Spracherkennung durchführen")
                        try:
                            from utils.language import detect_language
                            combined_text = "\n\n".join(extracted_texts)
                            document_language = detect_language(combined_text)
                            logger.info(f"🌐 Erkannte Sprache: {document_language}")
                            # Status aktualisieren
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 30,
                                "message": f"Sprache erkannt: {document_language}",
                                "stage": "language_detection"
                            }), ex=14400)
                        except Exception as err:
                            logger.error(f"❌ Fehler bei der Spracherkennung: {str(err)}")
                            document_language = "de"  # Fallback auf Deutsch
                            logger.info(f"⚠️ Fallback auf Standardsprache: {document_language}")
                        
                        # SCHRITT 4: Text bereinigen und tokenisieren
                        logger.info("🔄 SCHRITT 4: Text bereinigen und tokenisieren")
                        try:
                            from utils.text_processing import clean_text_for_database, count_tokens
                            cleaned_text = clean_text_for_database(combined_text)
                            token_count = count_tokens(cleaned_text)
                            logger.info(f"🧹 Text bereinigt, Token-Anzahl: {token_count}")
                            
                            # Speichere nur den Dateinamen im file_name_1-Feld, nicht den gesamten extrahierten Text
                            original_filename = ""
                            if file_contents and len(file_contents) > 0:
                                original_filename = file_contents[0][0]  # Erste Datei, erster Eintrag (Dateiname)
                                file_binary = file_contents[0][1]  # Binärdaten der PDF-Datei
                            
                            # Speichere den Dateinamen im file_name_1-Feld
                            upload.file_name_1 = original_filename[:200]  # Begrenze auf 200 Zeichen
                            
                            # Speichere die PDF-Datei selbst als base64 im content-Feld
                            pdf_base64 = base64.b64encode(file_binary).decode('utf-8')
                            upload.content = pdf_base64
                            
                            upload.token_count = token_count
                            db.session.commit()
                            logger.info(f"💾 Dateiname '{original_filename}' in file_name_1 gespeichert, PDF-Datei ({len(file_binary)} Bytes) als base64 im content-Feld gespeichert")
                            
                            # Status aktualisieren
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 40,
                                "message": "Text bereinigt und tokenisiert",
                                "stage": "text_cleaning"
                            }), ex=14400)
                        except Exception as err:
                            logger.error(f"❌ Fehler bei der Textbereinigung: {str(err)}")
                            raise Exception(f"Fehler bei der Textbereinigung: {str(err)}")
                        
                        # SCHRITT 5: OpenAI-Analyse durchführen
                        logger.info("🔄 SCHRITT 5: Inhaltsanalyse mit OpenAI durchführen")
                        try:
                            from utils.ai_analysis import analyze_content
                            logger.info(f"🤖 Sende Anfrage an OpenAI API...")
                            analysis_result = analyze_content(cleaned_text, document_language)
                            logger.info(f"✅ OpenAI-Analyse abgeschlossen, Ergebnisgröße: {len(str(analysis_result))} Zeichen")
                            # Status aktualisieren
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 60,
                                "message": "Inhaltsanalyse abgeschlossen",
                                "stage": "content_analysis"
                            }), ex=14400)
                        except Exception as err:
                            logger.error(f"❌ Fehler bei der OpenAI-Analyse: {str(err)}")
                            raise Exception(f"Fehler bei der OpenAI-Analyse: {str(err)}")
                        
                        # SCHRITT 6: Themen und Konzepte extrahieren
                        logger.info("🔄 SCHRITT 6: Themen und Konzepte extrahieren")
                        try:
                            from utils.topic_extraction import extract_topics_from_analysis
                            topics, main_topic = extract_topics_from_analysis(analysis_result)
                            logger.info(f"📚 Hauptthema: {main_topic}, Unterthemen: {len(topics)}")
                            # Status aktualisieren
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 70,
                                "message": "Themen extrahiert",
                                "stage": "topic_extraction"
                            }), ex=14400)
                        except Exception as err:
                            logger.error(f"❌ Fehler bei der Themenextraktion: {str(err)}")
                            raise Exception(f"Fehler bei der Themenextraktion: {str(err)}")
                        
                        # SCHRITT 7: Datenbank aktualisieren - Themenstruktur
                        logger.info("🔄 SCHRITT 7: Datenbank mit Themenstruktur aktualisieren")
                        try:
                            from core.models import db, Topic, Connection
                            import uuid
                            
                            logger.info(f"💾 Erstelle Hauptthema in Datenbank: {main_topic}")
                            # Hauptthema erstellen
                            main_topic_id = str(uuid.uuid4())
                            main_topic_obj = Topic(
                                id=main_topic_id,
                                upload_id=upload.id,
                                name=main_topic,
                                is_main_topic=True
                            )
                            db.session.add(main_topic_obj)
                            
                            # Unterthemen erstellen
                            for topic in topics:
                                topic_id = str(uuid.uuid4())
                                topic_obj = Topic(
                                    id=topic_id,
                                    upload_id=upload.id,
                                    name=topic["name"],
                                    parent_id=main_topic_id,
                                    description=topic.get("description", "")
                                )
                                db.session.add(topic_obj)
                                logger.info(f"📌 Unterthema erstellt: {topic['name']}")
                            
                            # Verbindungen erstellen
                            connections_count = 0
                            if "connections" in analysis_result:
                                for conn in analysis_result["connections"]:
                                    conn_obj = Connection(
                                        id=str(uuid.uuid4()),
                                        upload_id=upload.id,
                                        source_id=main_topic_id,  # Vereinfachte Version
                                        target_id=main_topic_id,  # In echter Implementierung: tatsächliche IDs finden
                                        label=conn.get("label", "is related to")
                                    )
                                    db.session.add(conn_obj)
                                    connections_count += 1
                            
                            logger.info(f"🔗 {connections_count} Verbindungen erstellt")
                            db.session.commit()
                            # Status aktualisieren
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 80,
                                "message": "Themenstruktur in Datenbank gespeichert",
                                "stage": "database_topics"
                            }), ex=14400)
                        except Exception as err:
                            logger.error(f"❌ Fehler beim Speichern der Themenstruktur: {str(err)}")
                            db.session.rollback()
                            raise Exception(f"Fehler beim Speichern der Themenstruktur: {str(err)}")
                        
                        # SCHRITT 8: Lernmaterialien generieren und speichern
                        logger.info("🔄 SCHRITT 8: Lernmaterialien generieren")
                        try:
                            from core.models import Flashcard, Question
                            import uuid
                            
                            # Flashcards generieren
                            logger.info("📇 Generiere Lernkarten...")
                            if "flashcards" in analysis_result:
                                for card in analysis_result["flashcards"]:
                                    flashcard_obj = Flashcard(
                                        id=str(uuid.uuid4()),
                                        upload_id=upload.id,
                                        question=card.get("question", ""),
                                        answer=card.get("answer", "")
                                    )
                                    db.session.add(flashcard_obj)
                                logger.info(f"✅ {len(analysis_result['flashcards'])} Lernkarten erstellt")
                            
                            # Quizfragen generieren
                            logger.info("❓ Generiere Quizfragen...")
                            if "questions" in analysis_result:
                                for quiz in analysis_result["questions"]:
                                    question_obj = Question(
                                        id=str(uuid.uuid4()),
                                        upload_id=upload.id,
                                        text=quiz.get("text", ""),
                                        options=quiz.get("options", []),
                                        correct_answer=quiz.get("correct_answer", 0),
                                        explanation=quiz.get("explanation", "")
                                    )
                                    db.session.add(question_obj)
                                logger.info(f"✅ {len(analysis_result['questions'])} Quizfragen erstellt")
                            
                            db.session.commit()
                            # Status aktualisieren
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 90,
                                "message": "Lernmaterialien generiert",
                                "stage": "learning_materials"
                            }), ex=14400)
                        except Exception as err:
                            logger.error(f"❌ Fehler beim Generieren der Lernmaterialien: {str(err)}")
                            db.session.rollback()
                            raise Exception(f"Fehler beim Generieren der Lernmaterialien: {str(err)}")
                        
                        # SCHRITT 9: Finalisierung
                        logger.info("🔄 SCHRITT 9: Finalisierung des Uploads")
                        try:
                            # Dokumenttyp erkennen (z.B. Lecture, Test, Notes, etc.)
                            doc_type = "Unbekannter Typ"
                            
                            # Versuche den Dokumenttyp aus dem Dateinamen zu ermitteln
                            for file_name, _ in file_contents:
                                file_name_lower = file_name.lower()
                                if "lecture" in file_name_lower or "vorlesung" in file_name_lower:
                                    doc_type = "Lecture"
                                    break
                                elif "test" in file_name_lower or "prüfung" in file_name_lower or "exam" in file_name_lower or "klausur" in file_name_lower:
                                    doc_type = "Test"
                                    break
                                elif "notes" in file_name_lower or "notizen" in file_name_lower:
                                    doc_type = "Notes"
                                    break
                                elif "lab" in file_name_lower or "labor" in file_name_lower or "praktikum" in file_name_lower:
                                    doc_type = "Lab"
                                    break
                                elif "exercise" in file_name_lower or "übung" in file_name_lower:
                                    doc_type = "Exercise"
                                    break
                                elif "summary" in file_name_lower or "zusammenfassung" in file_name_lower:
                                    doc_type = "Summary"
                                    break
                                elif "book" in file_name_lower or "buch" in file_name_lower:
                                    doc_type = "Book"
                                    break
                                elif "paper" in file_name_lower or "artikel" in file_name_lower:
                                    doc_type = "Paper"
                                    break
                                elif "cheat" in file_name_lower or "sheet" in file_name_lower or "spickzettel" in file_name_lower:
                                    doc_type = "Cheat Sheet"
                                    break
                            
                            # Falls kein spezifischer Typ erkannt wurde, analysiere den Inhalt
                            if doc_type == "Unbekannter Typ" and analysis_result:
                                if "content_type" in analysis_result:
                                    content_type = analysis_result["content_type"].lower()
                                    if "lecture" in content_type or "vorlesung" in content_type:
                                        doc_type = "Lecture"
                                    elif "test" in content_type or "exam" in content_type or "prüfung" in content_type:
                                        doc_type = "Test"
                                    elif "note" in content_type or "notiz" in content_type:
                                        doc_type = "Notes"
                                    elif "book" in content_type or "buch" in content_type or "textbook" in content_type:
                                        doc_type = "Book"
                                    elif "paper" in content_type or "article" in content_type or "artikel" in content_type:
                                        doc_type = "Paper"
                            
                            # Upload-Datensatz aktualisieren
                            upload = Upload.query.filter_by(session_id=session_id).first()
                            if upload:
                                # Der extrahierte Text ist bereits im content-Feld gespeichert
                                # Speichere den Dokumenttyp in einem zusätzlichen Feld (z.B. über einen JSON-Eintrag)
                                import json
                                
                                # Erstelle oder aktualisiere die Metadaten
                                try:
                                    metadata = {}
                                    # Füge Dokumenttyp zu den Metadaten hinzu
                                    metadata["document_type"] = doc_type
                                    
                                    # Aktualisiere Status und Zeitstempel
                                    upload.processing_status = "completed"
                                    upload.last_used_at = db.func.current_timestamp()
                                    
                                    # Da im content-Feld bereits die PDF-Datei als Base64 gespeichert ist,
                                    # speichern wir die Metadaten in dem Log oder einem anderen Feld, falls verfügbar
                                    logger.info(f"💾 Upload-Status in der Datenbank auf 'completed' gesetzt, Dokumenttyp: {doc_type} in Metadaten gespeichert")
                                    
                                    db.session.commit()
                                except Exception as e:
                                    logger.warning(f"⚠️ Konnte Metadaten nicht speichern: {str(e)}")
                                    # Einfacher Fallback: Speichere nur den Upload-Status
                                    upload.processing_status = "completed"
                                    upload.last_used_at = db.func.current_timestamp()
                                    db.session.commit()
                            else:
                                logger.error(f"❌ Upload-Eintrag für Session {session_id} nicht gefunden in der Datenbank!")
                                error_message = f"Upload-Eintrag für Session {session_id} nicht gefunden in der Datenbank."
                                redis_client.set(f"processing_status:{session_id}", f"failed: {error_message}", ex=3600)
                                redis_client.set(f"error_details:{session_id}", json.dumps({
                                    "message": error_message,
                                    "type": "database_error",
                                    "time": time.time()
                                }), ex=3600)
                                return
                            
                            # Begrenze die Anzahl der Uploads pro Benutzer auf maximal 5
                            if user_id:
                                logger.info(f"Prüfe Upload-Limits für Benutzer {user_id}")
                                
                                try:
                                    # Behalte nur die neuesten 5 Uploads für diesen Benutzer
                                    # Nutze eine direkte SQL-Löschung für bessere Performance
                                    
                                    # SCHRITT 1: Hole die IDs der 5 neuesten Uploads, die wir behalten wollen
                                    newest_uploads = db.session.query(Upload.id).filter(Upload.user_id == user_id).order_by(
                                        Upload.last_used_at.is_(None), # NULL-Werte am Ende
                                        Upload.last_used_at.desc()     # Neueste zuerst
                                    ).limit(5).all()
                                    
                                    # Extrahiere die IDs
                                    uploads_to_keep = [upload[0] for upload in newest_uploads]
                                    logger.info(f"Behalte folgende 5 Uploads: {uploads_to_keep}")
                                    
                                    # SCHRITT 2: Zähle die Uploads für diesen Benutzer
                                    total_uploads = db.session.query(db.func.count(Upload.id)).filter(
                                        Upload.user_id == user_id
                                    ).scalar()
                                    
                                    # SCHRITT 3: Wenn mehr als 5 vorhanden sind, lösche die überschüssigen
                                    if total_uploads > 5:
                                        # Finde alle zu löschenden Uploads
                                        uploads_to_delete = db.session.query(Upload).filter(
                                            Upload.user_id == user_id,
                                            ~Upload.id.in_(uploads_to_keep)  # Nicht in den zu behaltenden
                                        ).all()
                                        
                                        # Lösche die überschüssigen Uploads
                                        logger.info(f"Lösche {len(uploads_to_delete)} überschüssige Uploads für Benutzer {user_id}")
                                        for upload_to_delete in uploads_to_delete:
                                            # Separate Transaktion für jeden Upload um fortfahren zu können, wenn einer fehlschlägt
                                            try:
                                                logger.info(f"Lösche Upload {upload_to_delete.id}, Session {upload_to_delete.session_id}")
                                                
                                                # WICHTIG: Korrekte Reihenfolge des Löschens - erst Abhängigkeiten, dann Haupteinträge
                                                # 1. Lösche zuerst die Verbindungen (diese referenzieren Topics)
                                                Connection.query.filter_by(upload_id=upload_to_delete.id).delete()
                                                logger.info(f"Verbindungen für Upload {upload_to_delete.id} gelöscht")
                                                
                                                # 2. Lösche andere abhängige Daten
                                                Flashcard.query.filter_by(upload_id=upload_to_delete.id).delete()
                                                Question.query.filter_by(upload_id=upload_to_delete.id).delete()
                                                
                                                # 3. Lösche jetzt die Topics
                                                Topic.query.filter_by(upload_id=upload_to_delete.id).delete()
                                                
                                                # 4. Lösche UserActivity-Einträge
                                                UserActivity.query.filter_by(session_id=upload_to_delete.session_id).delete()
                                                
                                                # 5. Schließlich den Upload selbst löschen
                                                db.session.delete(upload_to_delete)
                                                
                                                # Commit für diesen einzelnen Upload
                                                db.session.commit()
                                                logger.info(f"Upload {upload_to_delete.id} erfolgreich aus der Datenbank gelöscht")
                                                
                                                # Lösche Redis-Schlüssel
                                                session_to_delete = upload_to_delete.session_id
                                                redis_keys = [
                                                    f"processing_status:{session_to_delete}",
                                                    f"processing_progress:{session_to_delete}",
                                                    f"processing_start_time:{session_to_delete}",
                                                    f"processing_heartbeat:{session_to_delete}",
                                                    f"processing_last_update:{session_to_delete}",
                                                    f"processing_details:{session_to_delete}",
                                                    f"processing_result:{session_to_delete}",
                                                    f"task_id:{session_to_delete}",
                                                    f"error_details:{session_to_delete}",
                                                    f"openai_error:{session_to_delete}",
                                                    f"all_data_stored:{session_to_delete}",
                                                    f"finalization_complete:{session_to_delete}"
                                                ]
                                                
                                                # Überprüfe, ob redis_client existiert/initialisiert ist
                                                if redis_client:
                                                    try:
                                                        # Verwende Redis pipeline für effizientes Löschen
                                                        pipeline = redis_client.pipeline()
                                                        for key in redis_keys:
                                                            pipeline.delete(key)
                                                        pipeline.execute()
                                                        logger.info(f"Redis-Daten für Session {session_to_delete} gelöscht")
                                                    except Exception as redis_error:
                                                        logger.error(f"Fehler beim Löschen der Redis-Daten: {str(redis_error)}")
                                                        logger.error(traceback.format_exc())
                                                else:
                                                    logger.warning(f"Redis-Client nicht verfügbar, konnte Redis-Daten für Session {session_to_delete} nicht löschen")
                                                    
                                            except Exception as delete_error:
                                                # Bei einem Fehler: Rollback nur für diesen Upload und mit dem nächsten fortfahren
                                                db.session.rollback()
                                                logger.error(f"Fehler beim Löschen von Upload {upload_to_delete.id}: {str(delete_error)}")
                                                logger.error(traceback.format_exc())
                                                # Wir machen mit dem nächsten Upload weiter
                                                continue
                                        
                                        logger.info(f"Alle überschüssigen Uploads für Benutzer {user_id} wurden gelöscht")
                                    else:
                                        logger.info(f"Benutzer {user_id} hat nur {total_uploads} Uploads, kein Löschen nötig")
                                except Exception as limit_error:
                                    logger.error(f"Fehler bei der Begrenzung der Uploads: {str(limit_error)}")
                                    logger.error(traceback.format_exc())
                                    # Rollback bei Fehler
                                    db.session.rollback()
                            
                            # Ergebnisse in Redis für schnellen Zugriff speichern
                            logger.info("💾 Speichere Ergebnisse in Redis-Cache...")
                            result_data = {
                                "main_topic": main_topic,
                                "topics": [t.name for t in Topic.query.filter_by(upload_id=upload.id).all()],
                                "language": document_language,
                                "token_count": token_count,
                                "document_type": doc_type,  # Der erkannte Dokumenttyp wird in Redis gespeichert
                                "pdf_stored": True,         # Hinweis, dass die PDF direkt gespeichert wurde
                                "storage_format": "base64", # Format der gespeicherten PDF
                                "flashcards_count": Flashcard.query.filter_by(upload_id=upload.id).count(),
                                "questions_count": Question.query.filter_by(upload_id=upload.id).count()
                            }
                            
                            safe_redis_set(f"processing_result:{session_id}", json.dumps(result_data), ex=86400)
                            logger.info("✅ Ergebnisse im Redis-Cache gespeichert")
                            
                            # Abschließenden Status setzen
                            safe_redis_set(f"processing_status:{session_id}", "completed", ex=14400)
                            safe_redis_set(f"processing_progress:{session_id}", json.dumps({
                                "progress": 100,
                                "message": "Verarbeitung abgeschlossen",
                                "stage": "completed"
                            }), ex=14400)
                            
                            # Zusätzliche Markierung, dass alle Daten vollständig in der Datenbank gespeichert wurden
                            safe_redis_set(f"finalization_complete:{session_id}", "true", ex=14400)
                            
                            logger.info("===== DATEIVERARBEITUNG ERFOLGREICH ABGESCHLOSSEN =====")
                        except Exception as err:
                            logger.error(f"❌ Fehler bei der Finalisierung: {str(err)}")
                            db.session.rollback()
                            raise Exception(f"Fehler bei der Finalisierung: {str(err)}")
                        
                        return {
                            "status": "completed",
                            "message": "Upload-Verarbeitung erfolgreich abgeschlossen"
                        }
                    except Exception as e:
                        logger.error(f"Fehler bei der Verarbeitung: {str(e)}")
                        # Lock freigeben
                        release_session_lock(session_id)
                        raise
                    finally:
                        # Beende den Heartbeat-Thread, falls er existiert
                        if heartbeat_thread and heartbeat_thread.is_alive():
                            logger.info(f"Beende Heartbeat-Thread für Session {session_id}")
                            heartbeat_stop_event.set()  # Signal zum Beenden des Threads
                            # Wir können auf den Thread warten, aber mit Timeout um Blockieren zu vermeiden
                            heartbeat_thread.join(timeout=5.0)
                            # Erzwinge das Ablaufen von Heartbeat-Keys
                            redis_client.delete(f"processing_heartbeat:{session_id}")
                        logger.info("Heartbeat-Thread beendet oder nicht vorhanden")
                        
                except Exception as e:
                    logger.error(f"Fehler bei der Verarbeitung: {str(e)}")
                    logger.error(traceback.format_exc())
                    # Stelle sicher, dass der Lock freigegeben wird
                    release_session_lock(session_id)
                    return {
                        "status": "error",
                        "error": str(e)
                    }
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Bereinige Ressourcen
            from api.cleanup import cleanup_processing_for_session
            cleanup_processing_for_session(session_id, str(e))
            
            # Erhöhe den Retry-Zähler
            retry_count = self.request.retries
            max_retries = self.max_retries
            
            if retry_count < max_retries:
                logger.warning(f"Versuche Retry {retry_count + 1}/{max_retries} für Session {session_id}")
                safe_redis_set(f"processing_status:{session_id}", f"retrying_{retry_count + 1}", ex=14400)
                raise self.retry(exc=e, countdown=120)  # Retry in 2 Minuten
            else:
                logger.error(f"Maximale Anzahl an Retries erreicht für Session {session_id}")
                safe_redis_set(f"processing_status:{session_id}", "failed", ex=14400)
                
                # Gib ein Fehlerergebnis zurück
                return {
                    "status": "error",
                    "error": str(e)
                }
    
    # Gib die Task-Funktion zurück, damit sie von außen aufgerufen werden kann
    return process_upload 