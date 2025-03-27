# api/session_utils.py
"""
Funktionen zur Verwaltung von Benutzer-Sessions und Upload-Sessions.
"""

import logging
import time
from datetime import datetime
from core.models import db, Upload, Question, Topic, Connection, Flashcard, UserActivity
from core.redis_client import redis_client

logger = logging.getLogger(__name__)

def check_and_manage_user_sessions(user_id, max_sessions=5, session_to_exclude=None):
    """
    Überprüft und verwaltet die Anzahl der aktiven Sessions eines Benutzers.
    Löscht ältere Sessions, wenn die maximale Anzahl überschritten wird.
    
    Args:
        user_id: ID des Benutzers
        max_sessions: Maximale Anzahl von Sessions, die beibehalten werden sollen
        session_to_exclude: Session-ID, die nicht gelöscht werden soll
        
    Returns:
        bool: True, wenn erfolgreich, sonst False
    """
    if not user_id:
        logger.info("Kein Benutzer-ID angegeben, überspringe Session-Management")
        return True
        
    try:
        # Hole alle Uploads des Benutzers, sortiert nach Erstellungsdatum (neueste zuerst)
        user_uploads = Upload.query.filter_by(user_id=user_id).order_by(Upload.created_at.desc()).all()
        
        # Keine Sessions oder zu wenige, nichts zu tun
        if len(user_uploads) <= max_sessions:
            return True
            
        # Identifiziere Sessions, die gelöscht werden sollen (älteste zuerst, außer die ausgeschlossene)
        sessions_to_keep = [session_to_exclude] if session_to_exclude else []
        
        # Füge die neuesten max_sessions Sessions hinzu
        for upload in user_uploads[:max_sessions]:
            if upload.session_id not in sessions_to_keep:
                sessions_to_keep.append(upload.session_id)
                
        # Lösche alle übrigen Sessions
        for upload in user_uploads:
            if upload.session_id not in sessions_to_keep:
                logger.info(f"Lösche alte Session {upload.session_id} für Benutzer {user_id}")
                delete_session(upload.session_id)
                
        return True
    except Exception as e:
        logger.error(f"Fehler beim Verwalten der Benutzer-Sessions: {str(e)}")
        return False

def delete_session(session_id):
    """
    Löscht eine Session und alle zugehörigen Daten.
    
    Args:
        session_id: ID der zu löschenden Session
        
    Returns:
        bool: True, wenn erfolgreich, sonst False
    """
    try:
        # Hole den Upload für die Session
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        if not upload:
            logger.warning(f"Keine Session mit ID {session_id} gefunden")
            return False
            
        # Lösche zugehörige Daten in der richtigen Reihenfolge (wegen Fremdschlüsselbeziehungen)
        # 1. Verbindungen (hängen von Topics ab)
        Connection.query.filter_by(upload_id=upload.id).delete()
        
        # 2. Fragen und Flashcards
        Question.query.filter_by(upload_id=upload.id).delete()
        Flashcard.query.filter_by(upload_id=upload.id).delete()
        
        # 3. Topics
        Topic.query.filter_by(upload_id=upload.id).delete()
        
        # 4. Benutzeraktivitäten
        UserActivity.query.filter_by(session_id=session_id).delete()
        
        # 5. Upload selbst
        db.session.delete(upload)
        
        # Commit der Änderungen
        db.session.commit()
        
        # Lösche Redis-Daten
        delete_redis_session_data(session_id)
        
        logger.info(f"Session {session_id} erfolgreich gelöscht")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Löschen der Session {session_id}: {str(e)}")
        # Rollback bei Fehler
        db.session.rollback()
        return False

def delete_redis_session_data(session_id):
    """
    Löscht alle Redis-Daten, die zu einer Session gehören.
    
    Args:
        session_id: ID der Session
        
    Returns:
        bool: True, wenn erfolgreich, sonst False
    """
    try:
        # Liste aller Redis-Schlüssel für diese Session
        key_patterns = [
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
            f"finalization_complete:{session_id}",
            f"chunks:{session_id}",
            f"chunk_upload_progress:{session_id}",
            f"chunk_upload_filename:{session_id}"
        ]
        
        # Lösche alle Schlüssel
        pipeline = redis_client.pipeline()
        for key in key_patterns:
            pipeline.delete(key)
        pipeline.execute()
        
        logger.info(f"Redis-Daten für Session {session_id} gelöscht")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Löschen der Redis-Daten für Session {session_id}: {str(e)}")
        return False

def update_session_timestamp(session_id):
    """
    Aktualisiert den Zeitstempel der letzten Verwendung einer Session.
    
    Args:
        session_id: ID der Session
        
    Returns:
        bool: True, wenn erfolgreich, sonst False
    """
    try:
        # Hole den Upload für die Session
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        if not upload:
            logger.warning(f"Keine Session mit ID {session_id} gefunden")
            return False
            
        # Aktualisiere den Zeitstempel
        upload.last_used_at = datetime.utcnow()
        
        # Speichere die Änderung
        db.session.commit()
        
        # Aktualisiere den Heartbeat in Redis
        redis_client.set(f"processing_heartbeat:{session_id}", int(time.time()))
        
        return True
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Session-Zeitstempels: {str(e)}")
        # Rollback bei Fehler
        db.session.rollback()
        return False

def get_active_sessions(user_id=None, limit=10):
    """
    Gibt eine Liste der aktiven Sessions zurück.
    
    Args:
        user_id: Optional, ID des Benutzers, dessen Sessions zurückgegeben werden sollen
        limit: Maximale Anzahl von zurückgegebenen Sessions
        
    Returns:
        list: Liste von Session-Informationen
    """
    try:
        # Erstelle die Abfrage
        query = Upload.query
        
        # Filtere nach Benutzer, falls angegeben
        if user_id:
            query = query.filter_by(user_id=user_id)
            
        # Sortiere nach letzter Verwendung (neueste zuerst)
        query = query.order_by(Upload.last_used_at.desc())
        
        # Begrenze die Anzahl der Ergebnisse
        query = query.limit(limit)
        
        # Führe die Abfrage aus
        uploads = query.all()
        
        # Erstelle die Ergebnisliste
        sessions = []
        for upload in uploads:
            # Hole Redis-Status
            processing_status = redis_client.get(f"processing_status:{upload.session_id}")
            processing_status = processing_status.decode('utf-8') if processing_status else "unknown"
            
            sessions.append({
                "session_id": upload.session_id,
                "filename": upload.filename,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "last_used_at": upload.last_used_at.isoformat() if upload.last_used_at else None,
                "status": processing_status
            })
            
        return sessions
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der aktiven Sessions: {str(e)}")
        return [] 