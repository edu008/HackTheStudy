import os
import sys
from celery import Celery
import logging
import time
import redis

# Add the current directory to the Python path to ensure app.py is found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Create the Celery instance
celery = Celery(
    'tasks',
    broker=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://redis:6379/0')
)

logger = logging.getLogger(__name__)

# Redis-Client für Session-Locking initialisieren
redis_client = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'))

# Function to create or get the Flask app
def get_flask_app():
    try:
        from app import create_app
    except ImportError:
        import os
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app import create_app
    from flask import current_app
    if current_app:
        return current_app
    return create_app()

# Configure Celery to use Flask app context
def init_celery(flask_app):
    celery.conf.update(flask_app.config)
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            app = get_flask_app()
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask

# Session-Lock Funktion mit Timeout
def acquire_session_lock(session_id, timeout=1800):
    """
    Versucht, einen Lock für die angegebene Session zu erwerben.
    
    Args:
        session_id: Die Session-ID für den Lock
        timeout: Gültigkeitsdauer des Locks in Sekunden (default: 30 Minuten)
        
    Returns:
        bool: True wenn Lock erworben wurde, False sonst
    """
    lock_key = f"session_lock:{session_id}"
    
    # Versuche, den Lock zu erwerben (NX = nur setzen, wenn der Key nicht existiert)
    acquired = redis_client.set(lock_key, "1", ex=timeout, nx=True)
    
    if acquired:
        logger.info(f"Acquired lock for session_id: {session_id}")
        return True
    else:
        logger.info(f"Session {session_id} is already being processed by another task")
        return False

# Session-Lock freigeben
def release_session_lock(session_id):
    """Gibt den Lock für die angegebene Session frei."""
    lock_key = f"session_lock:{session_id}"
    redis_client.delete(lock_key)
    logger.info(f"Released lock for session_id: {session_id}")

@celery.task(bind=True)
def process_upload(self, session_id, files_data, user_id=None, openai_client=None):
    app = get_flask_app()
    with app.app_context():
        logger.info(f"Attempting to process task for session_id: {session_id}, user_id: {user_id}")
        
        # Versuche, den Session-Lock zu erwerben
        if not acquire_session_lock(session_id):
            # Wenn der Lock nicht erworben werden kann, warte und füge Dateien zur aktuellen Session hinzu
            try:
                # Warte kurz, damit der existierende Task Zeit hat, zu starten
                time.sleep(5)
                
                # Füge die Datei direkt in die Datenbank ein, ohne AI-Analyse durchzuführen
                from models import db, Upload
                from api.utils import extract_text_from_file
                
                upload = Upload.query.filter_by(session_id=session_id).first()
                if not upload:
                    logger.error(f"Lock exists but no upload record found for session_id {session_id}")
                    return {"success": False, "message": "Session is locked but no upload record found"}
                
                # Extrahiere Text aus den neuen Dateien
                logger.info(f"Extracting text from {len(files_data)} files and adding to existing session")
                current_text = ""
                for file_name, file_content in files_data:
                    text = extract_text_from_file(file_content, file_name)
                    current_text += f"\n\n=== DOKUMENT: {file_name} ===\n\n{text}"
                
                # Kombiniere mit vorhandenem Text
                if upload.content:
                    upload.content = upload.content + current_text
                else:
                    upload.content = current_text
                
                # Aktualisiere die Token-Anzahl (einfache Schätzung: 1 Token ≈ 4 Zeichen)
                upload.token_count = len(upload.content) // 4
                logger.info(f"Aktualisiere token_count auf {upload.token_count} (etwa {len(upload.content)} Zeichen)")
                
                # Aktualisiere die Dateinamen
                if not upload.file_name_1:
                    upload.file_name_1 = files_data[0][0] if len(files_data) > 0 else None
                elif not upload.file_name_2:
                    upload.file_name_2 = files_data[0][0] if len(files_data) > 0 else None
                elif not upload.file_name_3:
                    upload.file_name_3 = files_data[0][0] if len(files_data) > 0 else None
                elif not upload.file_name_4:
                    upload.file_name_4 = files_data[0][0] if len(files_data) > 0 else None
                elif not upload.file_name_5:
                    upload.file_name_5 = files_data[0][0] if len(files_data) > 0 else None
                
                # Nachdem ein neuer Dateningalt hinzugefügt wurde, löschen wir 
                # die bestehenden Daten, damit sie basierend auf dem kombinierten Text neu generiert werden
                logger.info("Lösche bestehende Einträge für diese Session, um sie neu zu generieren")
                Flashcard.query.filter_by(upload_id=upload.id).delete()
                Question.query.filter_by(upload_id=upload.id).delete()
                Connection.query.filter_by(upload_id=upload.id).delete()
                Topic.query.filter_by(upload_id=upload.id).delete()
                
                # Setze den Status auf "pending", damit der nächste Task weiß, dass alle Daten neu generiert werden müssen
                upload.processing_status = "pending"
                db.session.commit()
                logger.info(f"Session {session_id} für erneute Analyse vorbereitet")
                
                # Gib Erfolg zurück, aber mit Information, dass die Datei hinzugefügt wurde, ohne Analyse
                return {
                    "session_id": session_id,
                    "message": "Files added to session, but analysis is being performed by another task",
                    "status": "pending_reanalysis",
                    "token_count": upload.token_count
                }
                
            except Exception as e:
                logger.error(f"Error adding files to locked session: {str(e)}")
                return {"success": False, "message": f"Error adding files to session: {str(e)}"}
        
        try:
            logger.info(f"Starting task for session_id: {session_id}, user_id: {user_id}")
            logger.info("Running unified processing approach (v2025-03-19)")
            
            from api.utils import extract_text_from_file, unified_content_processing, clean_text_for_database
            from models import db, Upload, Flashcard, Question, Topic, UserActivity, Connection
            
            # 1. Finde den Upload-Eintrag in der Datenbank
            upload = Upload.query.filter_by(session_id=session_id).first()
            if not upload:
                logger.error(f"Kein Upload-Eintrag für session_id {session_id} gefunden")
                release_session_lock(session_id)
                raise Exception(f"Kein Upload-Eintrag für session_id {session_id} gefunden")
            
            # 2. Setze den Status auf "processing"
            previous_status = upload.processing_status
            upload.processing_status = "processing"
            db.session.commit()
            
            logger.info(f"Verarbeitungsstatus geändert: {previous_status} -> processing")
            
            # 3. Warte kurz, um zusätzlichen Dateien Zeit zu geben, zur Session hinzugefügt zu werden 
            # bevor wir mit der Analyse beginnen
            logger.info("Warte 3 Sekunden, um weitere Dateien zu sammeln...")
            time.sleep(3)  # Kurze Wartezeit
            
            # 3a. Aktualisiere den Upload-Eintrag, um sicherzustellen, dass wir die aktuellsten Daten haben
            db.session.refresh(upload)
            
            # 3. Sammle alle vorhandenen Dateinamen
            file_names = []
            if upload.file_name_1: file_names.append(upload.file_name_1)
            if upload.file_name_2: file_names.append(upload.file_name_2)
            if upload.file_name_3: file_names.append(upload.file_name_3)
            if upload.file_name_4: file_names.append(upload.file_name_4)
            if upload.file_name_5: file_names.append(upload.file_name_5)
            
            logger.info(f"Processing files: {file_names}")
            
            # 4. Extrahiere Text aus den neuen Dateien und kombiniere mit vorhandenem Text
            logger.info("Extracting text from files...")
            current_text = ""
            current_file_names = []
            
            for file_name, file_content in files_data:
                try:
                    # Text aus Datei extrahieren
                    text = extract_text_from_file(file_content, file_name)
                    
                    # Direkte Prüfung auf spezielle Fehlercodes
                    if isinstance(text, str) and text.startswith('CORRUPTED_PDF:'):
                        logger.error(f"Korrupte PDF erkannt und übersprungen: {file_name}")
                        continue
                    
                    # Prüfe auf korrupte PDF-Datei anhand typischer Fehlermeldungen
                    indicators_of_corruption = [
                        "Fehler bei der PDF-Textextraktion",
                        "maximum recursion depth exceeded",
                        "Invalid Elementary Object",
                        "Stream has ended unexpectedly",
                        "PdfReadError"
                    ]
                    
                    if file_name.lower().endswith('.pdf'):
                        error_count = 0
                        
                        # Prüfe, ob im extrahierten Text Hinweise auf eine korrupte PDF zu finden sind
                        if isinstance(text, str):
                            for indicator in indicators_of_corruption:
                                if indicator in text:
                                    error_count += 1
                        
                        # Wenn kaum Text extrahiert wurde, könnte die Datei korrupt sein
                        if len(text) < 200 and "annotation" in file_name.lower():
                            logger.warning(f"Sehr wenig Text aus PDF extrahiert ({len(text)} Zeichen), könnte korrupt sein: {file_name}")
                            error_count += 1
                        
                        # Wenn zu viele Fehler erkannt wurden, überspringe die Datei
                        if error_count >= 2:
                            logger.error(f"PDF-Datei scheint korrupt zu sein, wird übersprungen: {file_name}")
                            continue
                    
                    # Wenn die Datei in Ordnung ist, füge sie zum Text hinzu
                    current_text += f"\n\n=== DOKUMENT: {file_name} ===\n\n{text}"
                    current_file_names.append(file_name)
                except Exception as e:
                    logger.error(f"Fehler beim Extrahieren von Text aus {file_name}: {str(e)}")
                    # Überspringen der Datei bei einem Fehler
                    continue
            
            logger.info(f"Text extracted: {len(current_text)} characters, files: {current_file_names}")
            
            # 5. Kombiniere mit vorhandenem Text, falls vorhanden
            all_text = ""
            if upload.content:
                logger.info("Appending to existing content")
                all_text = upload.content + current_text
            else:
                all_text = current_text
            
            # Bereinige den Text, um NUL-Zeichen zu entfernen
            all_text = clean_text_for_database(all_text)
            
            # 6. Speichere kombinierten Text und aktualisiere Token-Anzahl
            try:
                upload.content = all_text
                upload.token_count = len(all_text) // 4
                logger.info(f"Aktualisiere token_count auf {upload.token_count} (etwa {len(all_text)} Zeichen)")
                db.session.commit()
                logger.info("Content saved to database")
            except Exception as e:
                logger.error(f"Error saving content to database: {str(e)}")
                db.session.rollback()
                upload.processing_status = "failed"
                db.session.commit()
                release_session_lock(session_id)
                raise
            
            # 7. Unified Content Processing - alles in einem API-Aufruf
            logger.info("Starting unified content processing...")
            
            if openai_client is None:
                from openai import OpenAI
                import httpx
                openai_client = OpenAI(
                    api_key=app.config['OPENAI_API_KEY'],
                    http_client=httpx.Client()
                )
                # Definiere das gpt-4o Modell als Standard für diesen Client
                app.config['OPENAI_MODEL'] = "gpt-4o"
            
            # 8. Verarbeitung des Textes in einem einzigen API-Aufruf
            result = unified_content_processing(
                text=all_text,
                client=openai_client, 
                file_names=file_names
            )
            
            if not result:
                logger.error("Unified content processing failed to return results")
                upload.processing_status = "failed"
                db.session.commit()
                release_session_lock(session_id)
                raise Exception("Content processing failed")
            
            logger.info(f"Unified processing completed successfully with {len(result.get('flashcards', []))} flashcards and {len(result.get('questions', []))} questions")
            
            # 9. In Transaktion alle DB-Änderungen durchführen
            try:
                # Lösche bestehende Einträge
                logger.info("Lösche bestehende Einträge für diese Session, um sie neu zu generieren")
                Flashcard.query.filter_by(upload_id=upload.id).delete()
                Question.query.filter_by(upload_id=upload.id).delete()
                Connection.query.filter_by(upload_id=upload.id).delete()
                Topic.query.filter_by(upload_id=upload.id).delete()
                
                # Extrahiere Daten aus dem Ergebnis
                main_topic = result.get('main_topic', 'Unknown Topic')
                subtopics = result.get('subtopics', [])
                flashcards = result.get('flashcards', [])
                questions = result.get('questions', [])
                key_terms = result.get('key_terms', [])
                
                # Logging der Struktur zum Debuggen
                logger.info(f"Main topic: {main_topic}")
                logger.info(f"Subtopics: {subtopics}")
                logger.info(f"Key terms count: {len(key_terms)}")
                logger.info(f"Flashcards count: {len(flashcards)}")
                logger.info(f"Questions count: {len(questions)}")
                
                # Stelle sicher, dass subtopics die richtige Struktur haben
                processed_subtopics = []
                if subtopics:
                    for item in subtopics:
                        if isinstance(item, dict) and 'name' in item:
                            processed_subtopics.append(item)
                        elif isinstance(item, str):
                            # Konvertiere String zu Dictionary
                            processed_subtopics.append({'name': item, 'child_topics': []})
                    
                    # Falls keine gültigen Subtopics gefunden wurden, erstelle Standardsubtopics
                    if not processed_subtopics:
                        logger.warning("Keine gültigen Subtopics gefunden, erstelle Standardsubtopics")
                        processed_subtopics = [
                            {'name': 'Topic 1', 'child_topics': []},
                            {'name': 'Topic 2', 'child_topics': []},
                            {'name': 'Topic 3', 'child_topics': []},
                            {'name': 'Topic 4', 'child_topics': []}
                        ]
                    
                    # Aktualisiere die subtopics Variable
                    subtopics = processed_subtopics
                    logger.info(f"Processed subtopics: {subtopics}")
                
                # Speichere Hauptthema
                logger.info(f"Saving main topic: {main_topic}")
                main_topic_entity = Topic(
                    upload_id=upload.id, 
                    name=main_topic, 
                    is_main_topic=True
                )
                db.session.add(main_topic_entity)
                db.session.flush()  # Um die ID zu erhalten
                
                # Speichere Unterthemen
                logger.info(f"Saving {len(subtopics)} subtopics")
                saved_subtopics = []
                
                for subtopic_item in subtopics:
                    if isinstance(subtopic_item, dict) and 'name' in subtopic_item:
                        subtopic_name = subtopic_item.get('name')
                        child_topics = subtopic_item.get('child_topics', [])
                        
                        # Überprüfen, ob ein Unterthema mit diesem Namen bereits existiert
                        existing_topic = None
                        for st in saved_subtopics:
                            if st.name == subtopic_name:
                                existing_topic = st
                                break
                                
                        # Wenn es bereits existiert, überspringen
                        if existing_topic:
                            logger.warning(f"Skipping duplicate subtopic: {subtopic_name}")
                            continue
                        
                        # Erstelle Unterthema
                        subtopic_entity = Topic(
                            upload_id=upload.id, 
                            name=subtopic_name, 
                            is_main_topic=False, 
                            parent_id=main_topic_entity.id
                        )
                        db.session.add(subtopic_entity)
                        db.session.flush()
                        saved_subtopics.append(subtopic_entity)
                        
                        # Verbindung zum Hauptthema
                        connection = Connection(
                            upload_id=upload.id,
                            source_id=main_topic_entity.id,
                            target_id=subtopic_entity.id,
                            label=f"includes"
                        )
                        db.session.add(connection)
                        
                        # Unterunterthemen
                        for child_name in child_topics:
                            child_entity = Topic(
                                upload_id=upload.id,
                                name=child_name,
                                is_main_topic=False,
                                parent_id=subtopic_entity.id
                            )
                            db.session.add(child_entity)
                            db.session.flush()
                            
                            # Verbindung zum Unterthema
                            child_connection = Connection(
                                upload_id=upload.id,
                                source_id=subtopic_entity.id,
                                target_id=child_entity.id,
                                label=f"includes"
                            )
                            db.session.add(child_connection)
                
                # Speichere Schlüsselbegriffe
                logger.info(f"Saving {len(key_terms)} key terms")
                for term_item in key_terms:
                    if isinstance(term_item, dict) and 'term' in term_item and 'definition' in term_item:
                        term_name = term_item.get('term')
                        definition = term_item.get('definition')
                        
                        term_entity = Topic(
                            upload_id=upload.id,
                            name=term_name,
                            is_main_topic=False,
                            parent_id=main_topic_entity.id,
                            description=definition,
                            is_key_term=True
                        )
                        db.session.add(term_entity)
                        db.session.flush()
                        
                        # Verbindung zum Hauptthema
                        term_connection = Connection(
                            upload_id=upload.id,
                            source_id=main_topic_entity.id,
                            target_id=term_entity.id,
                            label=f"defines"
                        )
                        db.session.add(term_connection)
                
                # Speichere Flashcards
                logger.info(f"Saving {len(flashcards)} flashcards")
                for fc in flashcards:
                    if isinstance(fc, dict) and 'question' in fc and 'answer' in fc:
                        db.session.add(Flashcard(
                            upload_id=upload.id, 
                            question=fc.get('question'), 
                            answer=fc.get('answer')
                        ))
                
                # Speichere Testfragen
                logger.info(f"Saving {len(questions)} test questions")
                for q in questions:
                    if isinstance(q, dict) and 'text' in q and 'options' in q and 'correct' in q:
                        db.session.add(Question(
                            upload_id=upload.id,
                            text=q.get('text'),
                            options=q.get('options'),
                            correct_answer=int(q.get('correct', 0)),
                            explanation=q.get('explanation', '')
                        ))
                
                # Speichere Benutzeraktivität
                if user_id:
                    logger.info("Recording user activity")
                    
                    # Flache Liste der Unterthemen für die Aktivitätsaufzeichnung
                    flat_subtopics = []
                    for sub in saved_subtopics:
                        flat_subtopics.append(sub.name)
                    
                    db.session.add(UserActivity(
                        user_id=user_id,
                        activity_type='upload',
                        title=f"Analyzed: {main_topic}",
                        main_topic=main_topic,
                        subtopics=flat_subtopics,
                        session_id=session_id,
                        details={
                            'main_topic': main_topic,
                            'subtopics': flat_subtopics,
                            'file_count': len(file_names),
                            'file_names': file_names,
                            'current_upload': current_file_names
                        }
                    ))
                
                # Commit aller Änderungen
                logger.info("Committing all database changes")
                upload.processing_status = "completed"
                db.session.commit()
                logger.info(f"Database transaction completed successfully")
                
            except Exception as e:
                logger.error(f"Error during database operations: {str(e)}")
                db.session.rollback()
                upload.processing_status = "failed"
                db.session.commit()
                release_session_lock(session_id)
                raise
            
            # 10. Rückgabe der Ergebnisse
            result_data = {
                "session_id": session_id,
                "flashcards": flashcards,
                "questions": questions,
                "analysis": {
                    "main_topic": main_topic,
                    "subtopics": flat_subtopics if 'flat_subtopics' in locals() else [],
                    "content_type": result.get('content_type', 'unknown'),
                    "file_count": len(file_names)
                }
            }
            
            # Gib den Session-Lock frei
            release_session_lock(session_id)
            
            return result_data
            
        except Exception as e:
            logger.error(f"Task failed for session_id: {session_id}, error: {str(e)}")
            # Stelle sicher, dass der Lock freigegebenen wird
            release_session_lock(session_id)
            raise
