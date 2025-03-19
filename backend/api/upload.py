# api/upload.py
from flask import request, jsonify
from . import api_bp
from models import db, Upload, Question, Topic
from models import Flashcard
from tasks import process_upload
import uuid
from .utils import allowed_file, extract_text_from_file
import logging
from .auth import token_required
import time

logger = logging.getLogger(__name__)

@api_bp.route('/upload', methods=['POST'])
@token_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": {"code": "NO_FILE", "message": "No file part"}}), 400
    
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"success": False, "error": {"code": "INVALID_FILE", "message": "Invalid or no file selected"}}), 400
    
    # Verwende die übergebene session_id, falls vorhanden, sonst generiere eine neue
    session_id = request.form.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    
    logger.info(f"Using session_id: {session_id} ({'provided by request' if request.form.get('session_id') else 'newly generated'})")
    
    # Lese die Datei mit Fehlerbehandlung
    try:
        file_content = file.read()
    except Exception as e:
        logger.error(f"Fehler beim Lesen der Datei: {str(e)}")
        return jsonify({
            "success": False, 
            "error": {
                "code": "FILE_READ_ERROR", 
                "message": f"Die Datei konnte nicht gelesen werden: {str(e)}"
            }
        }), 400
    
    file_name = file.filename
    user_id = getattr(request, 'user_id', None)  # Falls Authentifizierung aktiviert ist
    
    # Prüfe auf leere Datei
    if len(file_content) == 0:
        return jsonify({
            "success": False, 
            "error": {
                "code": "EMPTY_FILE", 
                "message": "Die hochgeladene Datei ist leer."
            }
        }), 400
    
    # Prüfe auf zu große Datei (z.B. > 20 MB)
    max_file_size = 20 * 1024 * 1024  # 20 MB
    if len(file_content) > max_file_size:
        return jsonify({
            "success": False, 
            "error": {
                "code": "FILE_TOO_LARGE", 
                "message": f"Die Datei ist zu groß ({len(file_content) // (1024*1024)} MB). Maximale Größe: 20 MB."
            }
        }), 400
    
    # Prüfe, ob es sich um eine PDF mit Anmerkungen handelt
    is_annotated_pdf = False
    if 'annotation' in file_name.lower() or 'annot' in file_name.lower():
        is_annotated_pdf = True
        logger.info(f"Detected annotated PDF: {file_name}")
    
    # Aggressive Bereinigung für alle PDFs aktivieren
    aggressive_cleaning = True
    
    if aggressive_cleaning and file_name.lower().endswith('.pdf'):
        import re
        try:
            # Speichere die originale Größe für Diagnose
            original_size = len(file_content)
            
            # Entferne Null-Bytes und andere problematische Binärdaten
            file_content = re.sub(b'\x00', b'', file_content)
            
            # Bei PDFs mit Anmerkungen, entferne weitere problematische Zeichen
            if is_annotated_pdf:
                # Problematische Bytefolgen, die oft in Anmerkungen vorkommen
                for pattern in [b'\x0c', b'\xfe\xff', b'\xff\xfe']:
                    try:
                        file_content = re.sub(pattern, b' ', file_content)
                    except:
                        pass
            
            cleaned_size = len(file_content)
            
            if original_size != cleaned_size:
                bytes_removed = original_size - cleaned_size
                logger.info(f"Aggressive cleaning applied to {file_name}, removed {bytes_removed} potentially problematic bytes")
        except Exception as e:
            logger.warning(f"Error during aggressive cleaning: {str(e)}")
    
    logger.info(f"Received upload request: session_id={session_id}, file_name={file_name}, user_id={user_id}, file_size={len(file_content) // 1024}KB")
    
    try:
        # Überprüfe, ob die Session bereits existiert
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            # Erstelle einen neuen Upload-Eintrag
            upload = Upload(session_id=session_id, user_id=user_id)
            db.session.add(upload)
        
        # Finde die erste NULL-Spalte und speichere den Dateinamen
        if not upload.file_name_1:
            upload.file_name_1 = file_name
            file_position = 1
        elif not upload.file_name_2:
            upload.file_name_2 = file_name
            file_position = 2
        elif not upload.file_name_3:
            upload.file_name_3 = file_name
            file_position = 3
        elif not upload.file_name_4:
            upload.file_name_4 = file_name
            file_position = 4
        elif not upload.file_name_5:
            upload.file_name_5 = file_name
            file_position = 5
        else:
            return jsonify({"success": False, "error": {"code": "MAX_FILES", "message": "Maximum number of files reached"}}), 400
        
        # Umfassende Textextraktion mit Fehlerbehandlung
        try:
            # Extrahiere den aktuellen Inhalt
            from .utils import extract_text_from_file, clean_text_for_database
            
            # Bei annotierten PDFs spezielle Behandlung
            if is_annotated_pdf:
                # Für annotierte PDFs direkt die sichere Methode in utils verwenden
                from .utils import extract_text_from_pdf_safe
                extracted_text = extract_text_from_pdf_safe(file_content)
            else:
                # Standard-Extraktionsmethode
                extracted_text = extract_text_from_file(file_content, file_name)
            
            # Prüfe direkt auf den speziellen Fehlercode für korrupte PDFs
            if isinstance(extracted_text, str) and extracted_text.startswith('CORRUPTED_PDF:'):
                error_message = extracted_text[len('CORRUPTED_PDF:'):].strip()
                logger.error(f"Korrupte PDF erkannt: {file_name} - {error_message}")
                return jsonify({
                    "success": False,
                    "error": {
                        "code": "CORRUPTED_PDF",
                        "message": f"Die PDF-Datei '{file_name}' scheint beschädigt zu sein und kann nicht verarbeitet werden: {error_message}"
                    }
                }), 400
            
            # Prüfe auf korrupte PDF-Datei anhand typischer Fehlermeldungen oder Indikatoren
            indicators_of_corruption = [
                "Fehler bei der PDF-Textextraktion",
                "maximum recursion depth exceeded",
                "Invalid Elementary Object",
                "Stream has ended unexpectedly",
                "PdfReadError",
                "FloatObject",
                "incorrect startxref"
            ]
            
            # Zähle die Warnungen und Fehler in den Log-Zeilen
            error_count = 0
            
            # Prüfe, ob im extrahierten Text oder den Logs Hinweise auf eine korrupte PDF zu finden sind
            if file_name.lower().endswith('.pdf'):
                if isinstance(extracted_text, str):
                    for indicator in indicators_of_corruption:
                        if indicator in extracted_text:
                            error_count += 1
                
                # Wenn mehr als 150 Zeichen extrahiert wurden, aber trotzdem viele Fehler auftreten,
                # ist die Datei möglicherweise trotzdem korrupt
                if len(extracted_text) < 300 and is_annotated_pdf:
                    logger.warning(f"Sehr wenig Text aus PDF extrahiert ({len(extracted_text)} Zeichen), könnte korrupt sein: {file_name}")
                    error_count += 1
                
                # Wenn zu viele Fehler erkannt wurden, markiere die Datei als korrupt
                if error_count >= 2:
                    logger.error(f"PDF-Datei scheint korrupt zu sein oder hat ungewöhnliche Formatierung: {file_name}")
                    return jsonify({
                        "success": False,
                        "error": {
                            "code": "CORRUPTED_PDF",
                            "message": "Die PDF-Datei scheint beschädigt zu sein oder hat eine komplexe Struktur, die nicht verarbeitet werden kann. Verwenden Sie bitte eine andere Datei oder konvertieren Sie diese in ein anderes Format."
                        }
                    }), 400
            
            # Explizit Null-Bytes entfernen
            extracted_text = clean_text_for_database(extracted_text)
            
            # Prüfe, ob der extrahierte Text nach der Bereinigung noch Null-Bytes enthält
            if '\x00' in extracted_text:
                logger.error(f"PDF enthält nach der Bereinigung immer noch Null-Bytes: {file_name}")
                
                # Letzte Chance: Noch aggressivere Bereinigung
                extracted_text = ''.join(c for c in extracted_text if c != '\x00')
                
                # Wenn immer noch Null-Bytes vorhanden sind, gib einen Fehler zurück
                if '\x00' in extracted_text:
                    return jsonify({
                        "success": False, 
                        "error": {
                            "code": "NULL_BYTES", 
                            "message": "Die Datei enthält Null-Bytes, die nicht entfernt werden konnten. Bitte konvertiere die PDF oder verwende eine andere Datei."
                        }
                    }), 400
        except Exception as e:
            logger.error(f"Fehler bei der Textextraktion: {str(e)}")
            # Statt Fehler zurückzugeben, einen Platzhaltertext verwenden
            extracted_text = f"Fehler bei der Textextraktion: {str(e)}\n\nDiese Datei konnte nicht vollständig verarbeitet werden. Möglicherweise handelt es sich um ein gescanntes Dokument ohne OCR-Text, ein beschädigtes PDF oder eine PDF mit komplexen Anmerkungen."
        
        # Prüfe auf leeren extrahierten Text
        if not extracted_text or not extracted_text.strip():
            logger.warning(f"Kein Text aus der Datei extrahiert: {file_name}")
            # Statt Fehler zurückzugeben, einen Platzhaltertext verwenden
            extracted_text = "Es konnte kein Text aus dieser Datei extrahiert werden. Möglicherweise handelt es sich um ein gescanntes Dokument ohne OCR-Text oder ein leeres Dokument."
        
        # Schätze die Token-Anzahl für diese Datei
        new_file_tokens = len(extracted_text) // 4
        logger.info(f"Geschätzte Token-Anzahl für neue Datei: {new_file_tokens}")
        
        # Bei annotierte PDFs, gib Feedback über den Extraktionszustand
        if is_annotated_pdf:
            if len(extracted_text.split()) < 50:  # Weniger als 50 Wörter
                logger.warning(f"Annotierte PDF hat sehr wenig extrahierten Text: {file_name}")
            else:
                logger.info(f"Erfolgreich Text aus annotierter PDF extrahiert: {len(extracted_text)} Zeichen")
        
        # Aktualisiere Datenbankeinträge - Umfassende Fehlerbehandlung
        try:
            # Commit, um den Dateinamen zu speichern
            db.session.commit()
            logger.info(f"Updated Upload record for session_id: {session_id}, file position: {file_position}")
            
            # Text zur Datenbank hinzufügen - in separater Transaktion
            try:
                # Vorhandenen Text laden, falls vorhanden
                current_content = upload.content or ""
                
                # Neuen Text hinzufügen
                marker = f"\n\n=== DOKUMENT: {file_name} ===\n\n"
                if current_content:
                    upload.content = current_content + marker + extracted_text
                else:
                    upload.content = marker + extracted_text
                    
                # Token-Anzahl aktualisieren
                upload.token_count = len(upload.content) // 4
                
                # Änderungen speichern
                db.session.commit()
                logger.info(f"Content saved to database: {upload.token_count} tokens (approx. {len(upload.content)} chars)")
            except Exception as content_error:
                logger.error(f"Fehler beim Speichern des Inhalts: {str(content_error)}")
                db.session.rollback()
                
                # Versuche nochmals mit aggressiverer Bereinigung
                try:
                    # Noch aggressivere Bereinigung bei Datenbankfehlern
                    import re
                    cleaned_text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', extracted_text)
                    
                    # Vorhandenen Text laden, falls vorhanden
                    current_content = upload.content or ""
                    
                    # Neuen Text hinzufügen
                    marker = f"\n\n=== DOKUMENT: {file_name} ===\n\n"
                    if current_content:
                        upload.content = current_content + marker + cleaned_text
                    else:
                        upload.content = marker + cleaned_text
                        
                    # Token-Anzahl aktualisieren
                    upload.token_count = len(upload.content) // 4
                    
                    # Änderungen speichern
                    db.session.commit()
                    logger.info(f"Content saved to database after aggressive cleaning: {upload.token_count} tokens")
                except Exception as second_error:
                    logger.error(f"Zweiter Versuch zum Speichern des Inhalts fehlgeschlagen: {str(second_error)}")
                    # Das Schlimmste ist, dass der Inhalt nicht gespeichert wurde, 
                    # aber wir haben zumindest den Dateinamen
        except Exception as db_error:
            logger.error(f"Fehler beim Speichern in der Datenbank: {str(db_error)}")
            db.session.rollback()
            
            # Versuche einen erneuten Commit mit nur dem Dateinamen, ohne Inhalt
            try:
                db.session.commit()
                logger.info("Dateiname wurde gespeichert, aber der Inhalt konnte nicht verarbeitet werden")
            except Exception as name_error:
                logger.error(f"Fehler beim Speichern des Dateinamens: {str(name_error)}")
                raise
        
        # Ermittle die Gesamtzahl der Dateien in dieser Session
        files_count = sum(1 for f in [upload.file_name_1, upload.file_name_2, upload.file_name_3, upload.file_name_4, upload.file_name_5] if f)
        
        # Starte nur einen Celery-Task, wenn dies die erste Datei ist ODER wenn die Session bereits 
        # vollständig verarbeitet wurde. Bei laufender Verarbeitung fügen wir die Datei nur hinzu.
        should_start_task = (files_count == 1) or (upload.processing_status == 'completed')
        
        if should_start_task:
            task = process_upload.delay(session_id, [(file_name, file_content)], user_id)
            logger.info(f"Started Celery task: {task.id} for session_id: {session_id}")
            task_id = task.id
        else:
            # Kein neuer Task, aber die Datei wurde zur Session hinzugefügt
            logger.info(f"No new task started for session {session_id}, file added to existing processing")
            task_id = "no_task_needed"
        
        return jsonify({
            "success": True,
            "message": "Upload processing started. If multiple files are uploaded simultaneously, only one will be analyzed at a time.",
            "info": "All files are added to your session, but the analysis will combine all files and run once.",
            "session_id": session_id,
            "task_id": task_id,
            "file_position": file_position,
            "files_count": files_count,
            "new_file_tokens": new_file_tokens,
            "current_processing_status": upload.processing_status,
            "task_started": should_start_task
        }), 202
        
    except Exception as e:
        logger.error(f"Error in upload_file: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}), 500

@api_bp.route('/results/<session_id>', methods=['GET'])
@token_required
def get_results(session_id):
    # Cache-Control-Header hinzufügen, um sicherzustellen, dass die Antwort nicht gecached wird
    response_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404, response_headers
    
    # Direkte Datenbankabfrage verwenden, um sicherzustellen, dass wir aktuelle Daten bekommen
    db.session.refresh(upload)
    
    # Flashcards und Fragen in separaten Abfragen laden
    flashcards = db.session.query(Flashcard).filter_by(upload_id=upload.id).all()
    questions = db.session.query(Question).filter_by(upload_id=upload.id).all()
    
    # Daten formatieren
    flashcards_data = [{"id": fc.id, "question": fc.question, "answer": fc.answer} for fc in flashcards]
    questions_data = [{"id": q.id, "text": q.text, "options": q.options, "correctAnswer": q.correct_answer, "explanation": q.explanation} for q in questions]
    
    # Get the main topic
    main_topic = "Unknown Topic"
    main_topic_obj = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    if main_topic_obj:
        main_topic = main_topic_obj.name
    
    # Get subtopics
    subtopics = [topic.name for topic in Topic.query.filter_by(upload_id=upload.id, is_main_topic=False).all()]
    
    # Erstelle eine Liste aller Dateien für diese Session
    file_list = []
    if upload.file_name_1: file_list.append(upload.file_name_1)
    if upload.file_name_2: file_list.append(upload.file_name_2)
    if upload.file_name_3: file_list.append(upload.file_name_3)
    if upload.file_name_4: file_list.append(upload.file_name_4)
    if upload.file_name_5: file_list.append(upload.file_name_5)
    
    # Ermittle die Token-Anzahl
    token_count = len(upload.content) // 4 if upload.content else 0
    
    # Log die zurückgegebenen Daten für Debugging-Zwecke
    print(f"DEBUG: Returning data for session {session_id}: {len(flashcards_data)} flashcards, {len(questions_data)} questions")
    
    return jsonify({
        "success": True,
        "data": {
            "flashcards": flashcards_data,
            "test_questions": questions_data,
            "analysis": {
                "main_topic": main_topic,
                "subtopics": subtopics,
                "content_type": "unknown",
                "language": "de",  # Default to German for this application
                "files": file_list,
                "token_count": token_count,
                "processing_status": upload.processing_status
            },
            "session_id": session_id
        },
        "timestamp": int(time.time())  # Timestamp hinzufügen, um Cache-Busting zu unterstützen
    }), 200, response_headers

@api_bp.route('/session-info/<session_id>', methods=['GET'])
@token_required
def get_session_info(session_id):
    """Gibt grundlegende Informationen über eine Session zurück, ohne die vollständigen Daten."""
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
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
            "processing_status": "waiting" if token_count > 0 and not main_topic else ("completed" if main_topic else "pending")
        }
    }), 200
