"""
Dokumentenverarbeitungs-Tasks für den Worker.
"""
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

# Stellen sicher, dass der Python-Pfad korrekt gesetzt ist
base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)
    
# Import aus dem lokalen models-Modul
import tasks.models as models
from tasks.models import ProcessingTask, Upload, UploadedFile, Flashcard, Topic, Question, get_db_session, db
from .ai_tasks import DEFAULT_MODEL

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Importiere die Hilfsfunktionen aus utils
from utils import import_function_safely, import_module_safely

# Importiere das neue direkte File-Handling-Modul
direct_file_paths = [
    'utils.direct_file_handling',
    'backend.worker.utils.direct_file_handling',
    'worker.utils.direct_file_handling'
]

direct_file_module = import_module_safely(direct_file_paths)

if direct_file_module:
    logger.info("Direktes File-Handling-Modul erfolgreich importiert")
    prepare_file_for_openai = getattr(direct_file_module, 'prepare_file_for_openai', None)
    cleanup_temp_file = getattr(direct_file_module, 'cleanup_temp_file', None)
    get_file_info = getattr(direct_file_module, 'get_file_info', None)
else:
    # Einfache Fallback-Funktionen für den Fall, dass der Import fehlschlägt
    logger.warning("Konnte direktes File-Handling-Modul nicht importieren, verwende Fallback-Funktionen")
    
    def prepare_file_for_openai(file_content, file_name=None):
        file_extension = os.path.splitext(file_name)[1].lower() if file_name else ".pdf"
        temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
        temp_file_path = temp_file.name
        with open(temp_file_path, 'wb') as f:
            f.write(file_content)
        return temp_file_path
        
    def cleanup_temp_file(file_path):
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                return True
            return False
        except Exception:
            return False
            
    def get_file_info(file_path):
        return {
            'file_path': file_path,
            'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            'file_extension': os.path.splitext(file_path)[1].lower(),
            'exists': os.path.exists(file_path)
        }

from celery import current_app as celery_app, group
from redis_utils.client import get_redis_client

# --- Fallback-Funktionen definieren ---
def _save_file_for_processing_fallback(file_content, file_name=None):
    logger.warning("Verwende Fallback-Funktion zum Speichern der temporären Datei.")
    file_extension = os.path.splitext(file_name)[1].lower() if file_name else ".tmp"
    temp_file = None
    try:
        temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
        temp_file_path = temp_file.name
        temp_file.write(file_content)
        temp_file.flush() # Ensure content is written
        return temp_file_path
    except Exception as e:
        logger.error(f"Fehler im Fallback _save_file_for_processing_fallback: {e}")
        if temp_file and os.path.exists(temp_file.name):
             try: 
                 temp_file.close()
                 os.unlink(temp_file.name)
             except: pass
        return None # Indicate failure
    finally:
        if temp_file:
            try: temp_file.close()
            except: pass

def _cleanup_temp_file_fallback(file_path):
    logger.warning(f"Verwende Fallback-Funktion zum Löschen der temporären Datei: {file_path}")
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
            return True
        return False
    except Exception as e:
        logger.error(f"Fehler im Fallback _cleanup_temp_file_fallback: {e}")
        return False

# --- Versuche, echte Funktionen zu importieren ---
save_file_func_paths = ['utils.direct_file_handling.save_file_for_processing', 'tasks.utils.direct_file_handling.save_file_for_processing']
_real_save_file_for_processing = import_function_safely(save_file_func_paths, 'save_file_for_processing')

cleanup_func_paths = ['utils.direct_file_handling.cleanup_temp_file', 'tasks.utils.direct_file_handling.cleanup_temp_file']
_real_cleanup_temp_file = import_function_safely(cleanup_func_paths, 'cleanup_temp_file')

# --- Entscheide, welche Funktion verwendet wird ---
if callable(_real_save_file_for_processing):
    save_file_for_processing = _real_save_file_for_processing
    logger.info("Verwende echte 'save_file_for_processing' Funktion.")
else:
    save_file_for_processing = _save_file_for_processing_fallback
    logger.warning("Echte 'save_file_for_processing' Funktion nicht gefunden oder nicht aufrufbar, verwende Fallback.")

if callable(_real_cleanup_temp_file):
    cleanup_temp_file = _real_cleanup_temp_file
    logger.info("Verwende echte 'cleanup_temp_file' Funktion.")
else:
    cleanup_temp_file = _cleanup_temp_file_fallback
    logger.warning("Echte 'cleanup_temp_file' Funktion nicht gefunden oder nicht aufrufbar, verwende Fallback.")

def process_document(task_id):
    """
    Verarbeitet ein Dokument basierend auf einem ProcessingTask.
    Liest die notwendigen Informationen aus dem Task und seinen Metadaten.
    
    Args:
        task_id (str): Die ID des ProcessingTask.
        
    Returns:
        dict: Das Ergebnis der Verarbeitung.
    """
    logger.info(f"Starte Dokumentenverarbeitung für Task {task_id}")

    result = {
        'task_id': task_id,
        'status': 'processing',
        'started_at': datetime.now().isoformat()
    }
    uploaded_file = None # Initialisieren
    task = None # Initialisieren
    db_session = None # Initialisieren
    
    try:
        db_session = get_db_session()
        
        # 1. ProcessingTask laden
            task = db_session.query(ProcessingTask).get(task_id)
        if not task:
            error_msg = f"ProcessingTask mit ID {task_id} nicht gefunden."
            logger.error(error_msg)
            # Kann hier nicht viel mehr tun, da kein Task-Kontext
            return {'task_id': task_id, 'status': 'error', 'error': 'TASK_NOT_FOUND', 'message': error_msg}

                # Task-Status aktualisieren
                task.status = "processing"
                task.started_at = datetime.now()
                db_session.commit()
        
        # 2. Notwendige Metadaten aus dem Task extrahieren
        task_metadata = task.task_metadata or {}
        uploaded_file_id = task_metadata.get('uploaded_file_id')
        upload_id = task.upload_id # Sollte vom API-Teil gesetzt sein
        session_id = task.session_id
        user_id = task_metadata.get('user_id')
        language = task_metadata.get('language', 'de') # Sprache aus Metadaten holen

        result['session_id'] = session_id # session_id zum Ergebnis hinzufügen

        if not uploaded_file_id:
            error_msg = f"Keine uploaded_file_id in den Metadaten von Task {task_id} gefunden."
            logger.error(error_msg)
                task.status = "error"
                task.error_message = error_msg
                task.completed_at = datetime.now()
                db_session.commit()
            return {'task_id': task_id, 'status': 'error', 'error': 'MISSING_METADATA', 'message': error_msg, 'session_id': session_id}

        # 3. Zugehöriges UploadedFile laden
        uploaded_file = db_session.query(UploadedFile).get(uploaded_file_id)
        if not uploaded_file:
            error_msg = f"UploadedFile mit ID {uploaded_file_id} (aus Task {task_id}) nicht gefunden."
            logger.error(error_msg)
            task.status = "error"
            task.error_message = error_msg
            task.completed_at = datetime.now()
            db_session.commit()
            return {'task_id': task_id, 'status': 'error', 'error': 'UPLOADED_FILE_NOT_FOUND', 'message': error_msg, 'session_id': session_id}

        # Status des UploadedFile aktualisieren
        uploaded_file.extraction_status = 'processing'
        db_session.commit()
        
        # 4. Datei-Informationen aus UploadedFile holen
        file_content = uploaded_file.file_content
        file_name = uploaded_file.file_name
        mime_type = uploaded_file.mime_type
        file_type = mime_type.split('/')[-1] if mime_type else os.path.splitext(file_name)[1].lower().lstrip('.')

        if not file_content:
            error_msg = f"Kein Dateiinhalt in UploadedFile {uploaded_file_id} gefunden."
            logger.error(error_msg)
            task.status = "error"
            task.error_message = error_msg
            task.completed_at = datetime.now()
            uploaded_file.extraction_status = "error"
            uploaded_file.extraction_info = {'error': 'NO_FILE_CONTENT'}
            db_session.commit()
            # Ggf. Gesamt-Upload-Status aktualisieren
            # check_and_update_overall_upload_status(db_session, upload_id)
            return {'task_id': task_id, 'status': 'error', 'error': 'NO_FILE_CONTENT', 'message': error_msg, 'session_id': session_id}

        logger.info(f"Verarbeite UploadedFile: {file_name} (ID: {uploaded_file_id}), Typ: {file_type}, Größe: {len(file_content)} Bytes")

        # 5. Datei temporär speichern für Verarbeitung (falls nötig)
        temp_file_path = None
        extraction_success = False # Flag für erfolgreiche Extraktion
        document_text = None # Sicherstellen, dass document_text definiert ist
        try:
            # Verwende die oben zugewiesene Funktion (echt oder Fallback)
            temp_file_path = save_file_for_processing(file_content, file_name)
            if not temp_file_path:
                 raise RuntimeError("Temporäre Datei konnte nicht gespeichert werden.")
            logger.info(f"Temporäre Datei erstellt: {temp_file_path}")
            
            # 6. Text extrahieren (abhängig vom Dateityp)
            extraction_details = {}
            extraction_successful = False

            logger.info(f"🔄 Starte Textextraktion für {file_name} (Typ: {file_type})")

            # --- Textextraktionslogik --- Start ---
            try:
            if file_type == 'pdf':
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(temp_file_path)
                    page_count = len(doc)
                        document_text = "\n".join(page.get_text() for page in doc)
                        extraction_details['pages'] = page_count
                        logger.info(f"✅ PDF-Text extrahiert ({page_count} Seiten)")
                        extraction_successful = True
                    except ImportError:
                        logger.error(f"❌ PyMuPDF (fitz) nicht installiert.")
                        raise RuntimeError("PyMuPDF (fitz) ist für die PDF-Verarbeitung erforderlich.")
                    except Exception as pdf_err:
                        logger.error(f"❌ Fehler bei PDF-Textextraktion: {str(pdf_err)}", exc_info=True)
                        extraction_details['error'] = f"PDF extraction failed: {str(pdf_err)}"

                elif file_type in ['docx', 'vnd.openxmlformats-officedocument.wordprocessingml.document', 'doc', 'msword']:
                try:
                    import docx
                    doc = docx.Document(temp_file_path)
                    document_text = "\n".join([para.text for para in doc.paragraphs])
                        logger.info(f"✅ Word-Text extrahiert.")
                        extraction_successful = True
                except ImportError:
                        logger.error(f"❌ python-docx nicht installiert.")
                        raise RuntimeError("python-docx ist für die Word-Verarbeitung erforderlich.")
                    except Exception as docx_err:
                        logger.error(f"❌ Fehler bei Word-Textextraktion: {str(docx_err)}", exc_info=True)
                        extraction_details['error'] = f"Word extraction failed: {str(docx_err)}"
            else:
                    # Generische Textverarbeitung (versucht als Text zu lesen)
                try:
                    with open(temp_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        document_text = f.read()
                        logger.info(f"✅ Generischer Text gelesen (Annahme: Textdatei).")
                        extraction_successful = True # Nehmen wir an, es hat geklappt, wenn keine Exception
                    except Exception as txt_err:
                        logger.warning(f"⚠️ Fehler beim Lesen als Textdatei: {str(txt_err)}. Versuche Binär-Fallback.")
                        # Fallback: Wenn das Lesen als Text fehlschlägt, haben wir keinen Text
                        document_text = None
                        extraction_details['warning'] = f"Could not read as text: {str(txt_err)}"

            except Exception as extraction_major_error:
                 # Fängt Fehler wie fehlende Bibliotheken ab
                 logger.error(f"Schwerwiegender Fehler bei der Textextraktion: {extraction_major_error}", exc_info=True)
                 extraction_details['fatal_error'] = str(extraction_major_error)
                 document_text = None
                 extraction_successful = False
            # --- Textextraktionslogik --- Ende ---

            # 7. Ergebnisse der Extraktion im UploadedFile speichern
            if document_text is not None:
                    char_count = len(document_text)
                estimated_tokens = char_count // 4 # Grobe Schätzung
                uploaded_file.extracted_text = document_text
                uploaded_file.extraction_status = 'completed' if extraction_successful else 'error'
                extraction_details['characters'] = char_count
                extraction_details['estimated_tokens'] = estimated_tokens
                uploaded_file.extraction_info = extraction_details
                logger.info(f"💾 Extraktion abgeschlossen ({uploaded_file.extraction_status}): {char_count} Zeichen, {estimated_tokens} geschätzte Tokens.")
                extraction_success = True
            else:
                uploaded_file.extraction_status = 'error'
                uploaded_file.extraction_info = extraction_details if extraction_details else {'error': 'No text could be extracted'}
                logger.warning(f"⚠️ Kein Text aus {file_name} extrahiert. Status: error.")

            db_session.commit()

            # 8. Extrahierter Text in Redis speichern (für AI Tasks)
            if extraction_success and document_text:
                try:
                    redis_client = get_redis_client()
                    # Verwende uploaded_file_id im Schlüssel!
                    redis_key = f"extracted_text:{uploaded_file_id}"
                    redis_client.set(redis_key, document_text, ex=86400) # 24h TTL
                    logger.info(f"💾 Extrahierter Text ({len(document_text)} Zeichen) in Redis gespeichert (Key: {redis_key})")
                except Exception as redis_err:
                    logger.error(f"❌ Fehler beim Speichern des extrahierten Texts in Redis: {redis_err}")
                    # Dies sollte die weitere Verarbeitung nicht unbedingt stoppen, aber loggen.
            else:
                logger.warning(f"Überspringe Redis-Speicherung für {uploaded_file_id} da Extraktion fehlgeschlagen.")

            # 9. Starte AI-Tasks als Gruppe (nur bei Erfolg)
            ai_task_group_id = None
            if extraction_success:
                try:
                    logger.info(f"🔍 Starte AI Task Gruppe für UploadedFile ID {uploaded_file_id} ...")

                    # Importiere Celery App sicher
                    if not celery_app or not callable(celery_app.signature):
                         raise RuntimeError("Celery App konnte nicht geladen werden oder hat keine Signatur.")

                    # Stelle sicher, dass AI Tasks registriert sind (nur zur Info, Registrierung erfolgt beim Start)
                    # ai_tasks_dict = celery_app.tasks # Dictionary der registrierten Tasks

                    # Argumente für alle Tasks
                common_kwargs = {
                        'uploaded_file_id': uploaded_file_id,
                    'upload_id': upload_id,
                        'language': language,
                        'options': { # Übergebe Optionen als verschachteltes Dict
                             'user_id': user_id,
                             'session_id': session_id,
                             'model': task_metadata.get('model', DEFAULT_MODEL),
                             'num_cards': task_metadata.get('num_flashcards', 5),
                             'num_questions': task_metadata.get('num_questions', 3),
                             'question_type': task_metadata.get('question_type', 'multiple_choice'),
                             'max_topics': task_metadata.get('max_topics', 8)
                        }
                    }

                    tasks_to_run_signatures = []

                    # Flashcards Signatur erstellen
                    try:
                    flashcard_kwargs = common_kwargs.copy()
                        flashcard_kwargs['num_cards'] = common_kwargs['options']['num_cards']
                        tasks_to_run_signatures.append(celery_app.signature('ai.generate_flashcards', kwargs=flashcard_kwargs))
                        logger.info("--> Signatur für ai.generate_flashcards erstellt.")
                    except KeyError as e:
                        logger.warning(f"Task ai.generate_flashcards nicht gefunden oder Argument {e} fehlt.")
                        
                    # Questions Signatur erstellen
                    try:
                    question_kwargs = common_kwargs.copy()
                        question_kwargs['num_questions'] = common_kwargs['options']['num_questions']
                        question_kwargs['question_type'] = common_kwargs['options']['question_type']
                        tasks_to_run_signatures.append(celery_app.signature('ai.generate_questions', kwargs=question_kwargs))
                        logger.info("--> Signatur für ai.generate_questions erstellt.")
                    except KeyError as e:
                        logger.warning(f"Task ai.generate_questions nicht gefunden oder Argument {e} fehlt.")

                    # Topics Signatur erstellen
                    try:
                    topic_kwargs = common_kwargs.copy()
                        topic_kwargs['max_topics'] = common_kwargs['options']['max_topics']
                        tasks_to_run_signatures.append(celery_app.signature('ai.extract_topics', kwargs=topic_kwargs))
                        logger.info("--> Signatur für ai.extract_topics erstellt.")
                    except KeyError as e:
                         logger.warning(f"Task ai.extract_topics nicht gefunden oder Argument {e} fehlt.")

                    # Starte die Gruppe
                if tasks_to_run_signatures:
                        logger.info(f"--> Starte Gruppe mit {len(tasks_to_run_signatures)} AI-Tasks...")
                    task_group = group(tasks_to_run_signatures)
                    group_result = task_group.apply_async()
                        ai_task_group_id = group_result.id
                        logger.info(f"--> AI Task Gruppe gestartet. Group ID: {ai_task_group_id}")
                        task.result_data = task.result_data or {}
                        task.result_data['ai_task_group_id'] = ai_task_group_id
                else:
                        logger.warning("Keine gültigen AI-Task-Signaturen zum Starten vorhanden.")

            except Exception as ai_err:
                    logger.error(f"❌ Fehler beim Vorbereiten/Starten der AI Task Gruppe: {ai_err}", exc_info=True)
                    task.error_message = (task.error_message + f" | AI Group Start Failed: {ai_err}") if task.error_message else f"AI Group Start Failed: {ai_err}"
                    # Setze Task-Status auf Fehler, wenn Gruppe nicht gestartet werden kann?
                    task.status = "error"
            else:
                 logger.warning(f"Überspringe AI-Tasks für {uploaded_file_id}, da Extraktion fehlgeschlagen.")

            # 10. Task abschließen (Status basiert auf Extraktion UND ob AI gestartet wurde?)
            # Derzeit basiert er nur auf Extraktion. Das ist OK, da die AI-Tasks asynchron laufen.
            task.status = "completed" if extraction_success else "error"
            if task.status == 'error' and not task.error_message:
                 task.error_message = f"Text extraction failed for {file_name}"
            task.completed_at = datetime.now()
            db_session.commit() # Commit für Task-Status
            logger.info(f"✅ Task {task_id} abgeschlossen mit Status: {task.status}")

            # 11. Gesamtstatus des Uploads aktualisieren!
            check_and_update_overall_upload_status(db_session, upload_id)
            db_session.commit() # Wichtig: Commit nach Status-Update

            return {
                'task_id': task_id,
                'status': task.status,
                'session_id': session_id,
                'uploaded_file_id': uploaded_file_id,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'message': f"Verarbeitung für {file_name} abgeschlossen mit Status {task.status}",
                'extraction_status': uploaded_file.extraction_status
            }

        finally:
            # 12. Temporäre Datei aufräumen
            if temp_file_path:
                 cleanup_temp_file(temp_file_path)
        
    except Exception as e:
        logger.error(f"Unerwarteter Fehler in Task {task_id}: {e}", exc_info=True)
        if db_session and task:
             try:
                 task.status = "error"
                 task.error_message = f"Unexpected error: {str(e)}"
                 task.completed_at = datetime.now()
                 if uploaded_file:
                      uploaded_file.extraction_status = "error"
                      if not uploaded_file.extraction_info or 'error' not in uploaded_file.extraction_info:
                           uploaded_file.extraction_info = uploaded_file.extraction_info or {}
                           uploaded_file.extraction_info['error'] = f"Unexpected task error: {str(e)}"
                 db_session.commit()
                 # Auch hier Gesamtstatus prüfen!
                 if upload_id: # Nur wenn upload_id bekannt ist
                      check_and_update_overall_upload_status(db_session, upload_id)
                      db_session.commit()
             except Exception as final_db_err:
                  logger.error(f"Fehler beim Speichern des finalen Fehlerstatus für Task {task_id}: {final_db_err}")
                  if db_session: db_session.rollback()
        result.update({
            'status': 'error',
            'error': 'UNEXPECTED_ERROR',
            'message': f"Unerwarteter Fehler: {str(e)}"
        })
        return result
    finally:
        if db_session:
            db_session.close()

def register_tasks(celery_app):
    """
    Registriert alle Dokumentenverarbeitungsaufgaben mit der Celery-App.
    """
    tasks = {}

    @celery_app.task(name='document.process_document', bind=True, max_retries=3)
    def process_document_task(self, task_id):
        """
        Verarbeitet ein Dokument über Celery.
        Empfängt nur die task_id und holt sich den Rest aus der DB.
        
        Args:
            self: Celery-Task-Instanz
            task_id: Die ID des ProcessingTask.
        """
        logger.info(f"Celery Task document.process_document gestartet für Task-ID: {task_id}")
        try:
        # Rufe die eigentliche Verarbeitungsfunktion auf
            result = process_document(task_id)
            logger.info(f"Celery Task document.process_document für Task-ID {task_id} Ergebnis: {result.get('status')}")
            return result
        except Exception as exc:
             logger.error(f"Schwerwiegender Fehler im Celery Task document.process_document für Task-ID {task_id}: {exc}", exc_info=True)
             # Wiederholung nach Fehler (Celery's default behavior mit max_retries)
             try:
                 # Versuche, den Fehler im DB Task zu speichern
                 db_session = get_db_session()
                 task = db_session.query(ProcessingTask).get(task_id)
                 if task:
                     task.status = "failed" # Oder behalte 'error'?
                     task.error_message = f"Celery task failed after retries: {str(exc)}"
                     task.completed_at = datetime.now()
                     db_session.commit()
                     # check_and_update_overall_upload_status(db_session, task.upload_id)
                 db_session.close()
             except Exception as db_log_err:
                 logger.error(f"Konnte finalen Fehlerstatus nicht in DB speichern für Task {task_id}: {db_log_err}")
             # Task erneut auslösen für Wiederholung
             raise self.retry(exc=exc, countdown=60 * self.request.retries)
    
    tasks['document.process_document'] = process_document_task
    return tasks

# --- Hilfsfunktion zum Aktualisieren des Gesamtstatus --- #
def check_and_update_overall_upload_status(db_session, upload_id):
    """
    Prüft den Status aller UploadedFile-Einträge für einen Upload
    und aktualisiert den overall_processing_status des Uploads.
    """
    if not upload_id:
        return

    try:
        upload = db_session.query(Upload).options(db.joinedload(Upload.files)).get(upload_id)
        if not upload:
            logger.warning(f"Upload {upload_id} nicht gefunden für Statusaktualisierung.")
            return

        all_files = upload.files.all() # Alle zugehörigen Dateien laden
        if not all_files:
            # Wenn keine Dateien (mehr) da sind, Status auf 'completed' oder 'error' setzen?
            if upload.overall_processing_status != 'completed':
                 logger.info(f"Keine Dateien für Upload {upload_id} gefunden. Setze Status auf 'completed'.")
                 upload.overall_processing_status = 'completed'
                 upload.updated_at = datetime.now()
            return

        num_files = len(all_files)
        num_completed = sum(1 for f in all_files if f.extraction_status == 'completed')
        num_failed = sum(1 for f in all_files if f.extraction_status == 'error')
        num_pending_or_processing = num_files - num_completed - num_failed

        new_status = upload.overall_processing_status

        if num_pending_or_processing > 0:
            new_status = 'processing'
        elif num_failed > 0:
            # Wenn mindestens eine Datei fehlgeschlagen ist, Gesamtstatus auf 'error'
            new_status = 'error'
            # Optional: Fehlermeldungen sammeln
            error_messages = [f.extraction_info.get('error', 'Unknown error') for f in all_files if f.extraction_status == 'error']
            upload.error_message = " | ".join(error_messages)
        elif num_completed == num_files:
            # Alle Dateien erfolgreich verarbeitet
            new_status = 'completed'
            upload.error_message = None # Fehler löschen

        if new_status != upload.overall_processing_status:
            logger.info(f"Aktualisiere Gesamtstatus für Upload {upload_id} von '{upload.overall_processing_status}' zu '{new_status}'.")
            upload.overall_processing_status = new_status
            upload.updated_at = datetime.now()
            # Commit wird außerhalb dieser Funktion erwartet

    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Gesamtstatus für Upload {upload_id}: {e}", exc_info=True)
        # Hier keinen Rollback machen, da dies in einem größeren Kontext aufgerufen wird

# WICHTIG: Die Funktion check_and_update_overall_upload_status muss noch
# an den richtigen Stellen im Code aufgerufen werden, z.B. am Ende von
# process_document oder in einem separaten Task, der auf das Ende der AI Group wartet.
