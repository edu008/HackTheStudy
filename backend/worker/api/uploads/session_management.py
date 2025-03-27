# api/session_management.py
"""
Funktionen zur Verwaltung von Upload-Sessions und Benutzer-Sessions.
"""

from flask import current_app
from core.models import db, Upload, Question, Topic, Connection, Flashcard, UserActivity
import redis
import os
import logging
from datetime import datetime

# Redis-Client direkt erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://hackthestudy-backend-main:6379/0')
redis_client = redis.from_url(redis_url)

# Konfiguriere Logger
logger = logging.getLogger(__name__)

def update_session_timestamp(session_id):
    """
    Aktualisiert den Zeitstempel der letzten Verwendung einer Session
    """
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if upload:
            upload.last_used_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Zeitstempel für Session {session_id} aktualisiert")
        else:
            logger.warning(f"Session {session_id} nicht gefunden, Zeitstempel nicht aktualisiert")
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Zeitstempels für Session {session_id}: {str(e)}")

def manage_user_sessions(user_id):
    """
    Verwaltet die Sessions eines Benutzers.
    Löscht alte Sessions, um Platz für neue zu schaffen.
    """
    if not user_id:
        logger.info("Kein Benutzer angegeben, Session-Management übersprungen")
        return
        
    logger.info(f"Verwalte Sessions für Benutzer {user_id}")
    
    try:
        # Alle Uploads des Benutzers finden, sortiert nach last_used_at
        all_uploads = Upload.query.filter_by(user_id=user_id).order_by(
            Upload.last_used_at.is_(None).desc(),  # NULL-Werte zuerst
            Upload.last_used_at.asc()              # Dann nach Alter sortiert
        ).all()
        
        # Anzahl der Uploads protokollieren
        logger.info(f"Benutzer hat {len(all_uploads)} Uploads. Behalte nur die 4 neuesten.")
        
        # Bestimme, wie viele Uploads zu löschen sind (alle außer die 4 neuesten)
        uploads_to_delete = all_uploads[:-4] if len(all_uploads) > 4 else []
        
        # Lösche diese Uploads und ihre zugehörigen Daten
        for upload in uploads_to_delete:
            delete_upload_and_related_data(upload)
            
    except Exception as e:
        logger.error(f"Fehler beim Verwalten der Sessions für Benutzer {user_id}: {str(e)}")

def delete_upload_and_related_data(upload):
    """
    Löscht einen Upload und alle zugehörigen Daten.
    """
    try:
        upload_id = upload.id
        session_id = upload.session_id
        user_id = upload.user_id
        
        # Debug-Ausgabe des last_used_at-Werts
        last_used_value = "NULL" if upload.last_used_at is None else upload.last_used_at.isoformat()
        logger.info(f"Lösche Upload {upload_id} mit session_id={session_id}, last_used_at={last_used_value}")
        
        # WICHTIG: Korrekte Reihenfolge beim Löschen - erst Abhängigkeiten, dann Haupteinträge
        # 1. Zuerst Verbindungen löschen, weil sie auf Topics verweisen
        Connection.query.filter_by(upload_id=upload_id).delete()
        logger.info(f"Verbindungen für Upload {upload_id} gelöscht")
        
        # 2. Andere abhängige Daten löschen
        Flashcard.query.filter_by(upload_id=upload_id).delete()
        Question.query.filter_by(upload_id=upload_id).delete()
        
        # 3. Topics löschen (nachdem Verbindungen gelöscht wurden)
        Topic.query.filter_by(upload_id=upload_id).delete()
        
        # 4. UserActivity-Einträge löschen
        UserActivity.query.filter_by(session_id=session_id).delete()
        
        # 5. Schließlich den Upload selbst löschen
        db.session.delete(upload)
        
        # Commit der Änderungen sofort für jeden Upload
        db.session.commit()
        
        logger.info(f"Upload {upload_id} (session_id={session_id}) erfolgreich gelöscht")
        
        # Lösche auch zugehörige Redis-Daten
        delete_redis_session_data(session_id)
        
        return True
    except Exception as e:
        logger.error(f"Fehler beim Löschen des Uploads {upload.id}: {str(e)}")
        return False

def delete_redis_session_data(session_id):
    """
    Löscht alle Redis-Daten, die zu einer Session gehören.
    """
    keys_to_delete = [
        f"processing_status:{session_id}",
        f"processing_progress:{session_id}",
        f"processing_start_time:{session_id}",
        f"processing_heartbeat:{session_id}",
        f"processing_last_update:{session_id}",
        f"processing_details:{session_id}",
        f"processing_result:{session_id}",
        f"task_id:{session_id}",
        f"error_details:{session_id}",
        f"openai_error:{session_id}",
        f"all_data_stored:{session_id}",
        f"finalization_complete:{session_id}"
    ]
    
    # Überprüfe, ob redis_client existiert und initialisiert ist
    if redis_client:
        try:
            # Verwende Redis pipeline für effizientes Löschen
            pipeline = redis_client.pipeline()
            for key in keys_to_delete:
                pipeline.delete(key)
            pipeline.execute()
            
            logger.info(f"Redis-Daten für Session {session_id} gelöscht")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Redis-Daten für Session {session_id}: {str(e)}")
            return False
    else:
        logger.warning("Redis-Client nicht verfügbar, Redis-Daten wurden nicht gelöscht")
        return False

def get_session_info(session_id):
    """
    Gibt Informationen zu einer Session zurück.
    """
    try:
        # Basisinformationen aus der Datenbank abrufen
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return None, "Session nicht gefunden"
            
        # Aktualisiere den Zeitstempel der letzten Verwendung
        update_session_timestamp(session_id)
        
        # Statusdaten aus Redis abrufen
        processing_status = redis_client.get(f"processing_status:{session_id}")
        processing_status = processing_status.decode('utf-8') if processing_status else "unknown"
        
        processing_progress = redis_client.get(f"processing_progress:{session_id}")
        processing_progress = float(processing_progress.decode('utf-8')) if processing_progress else 0
        
        session_info = {
            "session_id": session_id,
            "upload_id": upload.id,
            "filename": upload.filename,
            "file_type": upload.file_type,
            "file_size": upload.file_size,
            "page_count": upload.page_count,
            "created_at": upload.created_at.isoformat() if upload.created_at else None,
            "last_used_at": upload.last_used_at.isoformat() if upload.last_used_at else None,
            "processing_status": processing_status,
            "processing_progress": processing_progress
        }
        
        return session_info, None
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Session-Informationen für {session_id}: {str(e)}")
        return None, f"Fehler: {str(e)}" 