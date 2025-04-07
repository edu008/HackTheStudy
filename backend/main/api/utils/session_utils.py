# api/session_utils.py
"""
Funktionen zur Verwaltung von Benutzer-Sessions und Upload-Sessions.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timedelta

from core.models import (Flashcard, Question, Topic, Upload,
                         UserActivity, db)
from core.redis_client import redis_client
from flask import current_app, g, request

from ..auth import token_required
from ..auth.token_auth import get_current_user

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
                logger.info("Lösche alte Session %s für Benutzer %s", upload.session_id, user_id)
                delete_session(upload.session_id)

        return True
    except Exception as e:
        logger.error("Fehler beim Verwalten der Benutzer-Sessions: %s", str(e))
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
            logger.warning("Keine Session mit ID %s gefunden", session_id)
            return False

        # Lösche zugehörige Daten in der richtigen Reihenfolge (wegen Fremdschlüsselbeziehungen)
        # Beachte: Die Connection-Tabelle existiert nicht mehr
        
        # Fragen und Flashcards
        Question.query.filter_by(upload_id=upload.id).delete()
        Flashcard.query.filter_by(upload_id=upload.id).delete()

        # Topics
        Topic.query.filter_by(upload_id=upload.id).delete()

        # Benutzeraktivitäten
        UserActivity.query.filter_by(session_id=session_id).delete()

        # Upload selbst
        db.session.delete(upload)

        # Commit der Änderungen
        db.session.commit()

        # Lösche Redis-Daten
        delete_redis_session_data(session_id)

        logger.info("Session %s erfolgreich gelöscht", session_id)
        return True
    except Exception as e:
        logger.error("Fehler beim Löschen der Session %s: %s", session_id, str(e))
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

        logger.info("Redis-Daten für Session %s gelöscht", session_id)
        return True
    except Exception as e:
        logger.error("Fehler beim Löschen der Redis-Daten für Session %s: %s", session_id, str(e))
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
            logger.warning("Keine Session mit ID %s gefunden", session_id)
            return False

        # Aktualisiere den Zeitstempel
        upload.last_used_at = datetime.utcnow()

        # Speichere die Änderung
        db.session.commit()

        # Aktualisiere den Heartbeat in Redis
        redis_client.set(f"processing_heartbeat:{session_id}", int(time.time()))

        return True
    except Exception as e:
        logger.error("Fehler beim Aktualisieren des Session-Zeitstempels: %s", str(e))
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
        logger.error("Fehler beim Abrufen der aktiven Sessions: %s", str(e))
        return []


def delete_session_data(session_id, remove_uploads=False):
    """
    Löscht alle Daten, die mit einer Session verbunden sind.

    Args:
        session_id: Die zu löschende Session-ID
        remove_uploads: Ob auch Upload-Einträge entfernt werden sollen

    Returns:
        dict: Ergebnis der Löschoperation
    """
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            logger.warning(f"Kein Upload gefunden für Session {session_id}")
            return {"success": False, "error": "Keine Session-Daten gefunden."}

        upload_id = upload.id
        logger.info(f"Lösche alle Daten für Upload {upload_id} (Session {session_id})")

        # Lösche alle abhängigen Daten
        Question.query.filter_by(upload_id=upload_id).delete()
        Flashcard.query.filter_by(upload_id=upload_id).delete()
        Topic.query.filter_by(upload_id=upload_id).delete()
        
        # In der Connection-Tabelle wurden Verbindungen gespeichert,
        # Diese Zeile wurde entfernt, da die Connection-Tabelle nicht mehr existiert

        if remove_uploads:
            Upload.query.filter_by(id=upload_id).delete()

        # Commit die Änderungen
        db.session.commit()
        logger.info(f"Alle Daten für Upload {upload_id} wurden gelöscht")

        return {"success": True, "upload_id": upload_id}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Löschen der Session-Daten: {str(e)}")
        return {"success": False, "error": str(e)}
