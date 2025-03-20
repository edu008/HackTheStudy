# api/upload.py
from flask import request, jsonify
from . import api_bp
from models import db, Upload, Question, Topic
from models import Flashcard, User
from tasks import process_upload
import uuid
from .utils import allowed_file, extract_text_from_file, check_and_manage_user_sessions, update_session_timestamp, count_tokens
import logging
from .auth import token_required
from api.credit_service import check_credits_available, calculate_token_cost, deduct_credits
import time
import json
from tasks import redis_client, cleanup_processing_for_session

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
    user_id = getattr(request, 'user_id', None)  # Falls Authentifizierung aktiviert ist
    
    # Wenn keine Session-ID übergeben wird, erstellen wir eine neue und prüfen die Begrenzung
    if not session_id:
        # Überprüfe und verwalte die Anzahl der Sessions des Benutzers
        if user_id:
            check_and_manage_user_sessions(user_id)
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
    
    # Prüfe auf leere Datei
    if len(file_content) == 0:
        return jsonify({
            "success": False, 
            "error": {
                "code": "EMPTY_FILE", 
                "message": "Die hochgeladene Datei ist leer."
            }
        }), 400
    
    # Extrahiere Text aus der Datei
    try:
        text_content = extract_text_from_file(file_content, file_name)
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren des Textes: {str(e)}")
        return jsonify({
            "success": False, 
            "error": {
                "code": "TEXT_EXTRACTION_ERROR", 
                "message": f"Der Text konnte nicht aus der Datei extrahiert werden: {str(e)}"
            }
        }), 400
    
    # Schätze die Tokenanzahl und Kosten für die Verarbeitung
    estimated_token_count = count_tokens(text_content)
    
    # Größere Dateien kosten mehr (linear mit der Anzahl der Token, plus Ausgabetoken, die etwa 30% der Eingabetoken ausmachen)
    estimated_output_tokens = max(1000, int(estimated_token_count * 0.3))  # Mindestens 1000 Tokens für die Ausgabe
    estimated_cost = calculate_token_cost(estimated_token_count, estimated_output_tokens)
    
    # Überprüfe, ob der Benutzer genügend Credits hat
    if user_id:
        user = User.query.get(user_id)
        if user:
            if user.credits < estimated_cost:
                return jsonify({
                    "success": False,
                    "error": {
                        "code": "INSUFFICIENT_CREDITS",
                        "message": f"Nicht genügend Credits für die Verarbeitung dieser Datei. Benötigt: {estimated_cost} Credits. Verfügbar: {user.credits} Credits.",
                        "credits_required": estimated_cost,
                        "credits_available": user.credits
                    }
                }), 402
        else:
            logger.error(f"Benutzer mit ID {user_id} wurde nicht gefunden.")
            return jsonify({
                "success": False,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "Der angegebene Benutzer existiert nicht."
                }
            }), 404
    
    # Speichere die Upload-Informationen
    try:
        # Versuche, Informationen über existierende Uploads für die angegebene Session_id abzurufen
        upload_session = Upload.query.filter_by(session_id=session_id).first()
        
        # Wenn die Sitzung bereits für einen anderen Benutzer verwendet wird, lehne die Anfrage ab
        if upload_session and upload_session.user_id and user_id and upload_session.user_id != user_id:
            logger.error(f"Session {session_id} already belongs to a different user: {upload_session.user_id}")
            return jsonify({
                "success": False, 
                "error": {
                    "code": "SESSION_CONFLICT", 
                    "message": "Diese Session gehört bereits zu einem anderen Benutzer."
                }
            }), 403
    except Exception as e:
        logger.error(f"Error checking session ownership: {str(e)}")
        # Wir setzen den Vorgang fort, auch wenn es einen Fehler gibt
    
    # Prüfe auf zu grosse Datei (z.B. > 20 MB)
    max_file_size = 20 * 1024 * 1024  # 20 MB
    if len(file_content) > max_file_size:
        return jsonify({
            "success": False, 
            "error": {
                "code": "FILE_TOO_LARGE", 
                "message": f"Die Datei ist zu gross ({len(file_content) // (1024*1024)} MB). Maximale Grösse: 20 MB."
            }
        }), 400
    
    # Prüfe, ob es sich um eine PDF mit Anmerkungen handelt
    is_annotated_pdf = False
    if 'annotation' in file_name.lower() or 'annot' in file_name.lower():
        is_annotated_pdf = True
        logger.info(f"Detected annotated PDF: {file_name}")
    
    # Aggressive Bereinigung für alle PDFs aktivieren
    aggressive_cleaning = False  # Aggressive Bereinigung deaktiviert
    
    if aggressive_cleaning and file_name.lower().endswith('.pdf'):
        import re
        try:
            # Speichere die originale Grösse für Diagnose
            original_size = len(file_content)
            
            # Entferne Null-Bytes und andere problematische Binärdaten - REDUZIERT
            # file_content = re.sub(b'\x00', b'', file_content)
            
            # Bei PDFs mit Anmerkungen, entferne weitere problematische Zeichen - DEAKTIVIERT
            # if is_annotated_pdf:
            #     # Problematische Bytefolgen, die oft in Anmerkungen vorkommen
            #     for pattern in [b'\x0c', b'\xfe\xff', b'\xff\xfe']:
            #         try:
            #             file_content = re.sub(pattern, b' ', file_content)
            #         except:
            #             pass
            
            cleaned_size = len(file_content)
            
            if original_size != cleaned_size:
                bytes_removed = original_size - cleaned_size
                logger.info(f"Minimal cleaning applied to {file_name}, removed {bytes_removed} potentially problematic bytes")
        except Exception as e:
            logger.warning(f"Error during minimal cleaning: {str(e)}")
    
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
            from .utils import clean_text_for_database
            
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
        
        # Nach erfolgreicher Verarbeitung die Credits abziehen
        if user_id and user:
            deduct_credits(user_id, estimated_cost)
            logger.info(f"Deducted {estimated_cost} credits from user {user_id} for file processing")
        
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
    
    # Aktualisiere den last_used_at-Timestamp
    update_session_timestamp(session_id)
    
    # Direkte Datenbankabfrage verwenden, um sicherzustellen, dass wir aktuelle Daten bekommen
    db.session.refresh(upload)
    
    # Prüfe auf spezielle Statuswerte in Redis
    processing_status_key = f"processing_status:{session_id}"
    special_status = redis_client.get(processing_status_key)
    
    # Wenn ein spezieller Status gefunden wurde, diesen berücksichtigen
    if special_status:
        special_status = special_status.decode('utf-8')
        logger.info(f"Special status found for session {session_id}: {special_status}")
        
        # Bei Rate-Limit-Fehlern
        if special_status == "rate_limit_error" or special_status.startswith("failed:rate_limit"):
            error_key = f"error_details:{session_id}"
            stored_error = redis_client.get(error_key)
            error_data = {"code": "RATE_LIMIT", "message": "API-Anfragelimit erreicht"}
            
            if stored_error:
                try:
                    parsed_error = json.loads(stored_error)
                    error_data.update(parsed_error)
                except:
                    pass
            
            # Stelle sicher, dass alle Ressourcen freigegeben werden
            from tasks import cleanup_processing_for_session as cleanup_session
            cleanup_session(session_id, "rate_limit_from_api")
            
            # Markiere die Verarbeitung als beendet
            update_processing_status(session_id, "failed")
            
            return jsonify({
                "success": False,
                "error": error_data,
                "error_type": "rate_limit",
                "upload_aborted": True
            }), 429, response_headers
    
    # Überprüfe den Verarbeitungsstatus und gib bei Fehlern entsprechende Informationen zurück
    if upload.processing_status == "failed":
        error_message = "Bei der Verarbeitung ist ein Fehler aufgetreten"
        error_type = "processing_failed"
        
        # Versuche, aus Redis eventuell gespeicherte detailliertere Fehlerinformationen zu bekommen
        error_key = f"error_details:{session_id}"
        
        stored_error = redis_client.get(error_key)
        if stored_error:
            try:
                error_data = json.loads(stored_error)
                error_type = error_data.get("error_type", error_type)
                error_message = error_data.get("message", error_message)
                
                # Spezielle Behandlung für Rate-Limit-Fehler
                if error_type == "rate_limit" and "429" in error_message:
                    # Stelle sicher, dass die Session als abgebrochen markiert ist
                    from tasks import cleanup_processing_for_session
                    cleanup_processing_for_session(session_id, "openai_429_explicit_abort")
                    
                    return jsonify({
                        "success": False,
                        "error": {
                            "code": "OPENAI_429",
                            "message": "Das OpenAI-Tokenlimit pro Minute wurde überschritten. Bitte teilen Sie die Datei in kleinere Abschnitte auf oder versuchen Sie es später erneut.",
                            "original_error": error_message
                        },
                        "error_type": "rate_limit",
                        "error_code": "openai_429",
                        "upload_aborted": True  # Explizites Flag, dass der Upload abgebrochen wurde
                    }), 429, response_headers
            except:
                pass  # Bei Parsing-Fehlern verwenden wir die Standardnachricht
        
        return jsonify({
            "success": False,
            "error": {
                "code": error_type.upper(),
                "message": error_message
            },
            "error_type": error_type
        }), 400, response_headers
    
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
    
    # Verarbeite spezielle Redis-Status auch für erfolgreich verarbeitete Uploads
    processing_status = upload.processing_status
    if special_status:
        processing_status = special_status
    
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
                "language": detect_language(upload.content),
                "processing_status": processing_status,
                "files": file_list,
                "token_count": token_count
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
