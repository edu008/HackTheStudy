# api/session_management.py
"""
Funktionen zur Verwaltung von Upload-Sessions und Benutzer-Sessions.
"""

import logging
import os
from datetime import datetime
import time
import uuid

import redis
from core.models import (Flashcard, Question, Topic, Upload,
                         UserActivity, db)
from flask import current_app, jsonify
from core.redis_client import get_redis_client

# Redis-Client direkt erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://hackthestudy-backend-main:6379/0')
redis_client = redis.from_url(redis_url)

# Konfiguriere Logger
logger = logging.getLogger(__name__)


def update_session_timestamp(session_id):
    """
    Aktualisiert den Zeitstempel einer Session.
    
    Dies ist wichtig für die Session-Bereinigung, um aktive Sessions nicht zu löschen.
    
    Args:
        session_id: Die Session-ID
        
    Returns:
        bool: True wenn erfolgreich, sonst False
    """
    try:
        # Redis-Client holen
        redis_client = get_redis_client()
        
        # Setze "last_activity" auf den aktuellen Zeitstempel in allen relevanten Schlüsseln
        current_time = time.time()
        
        # In session_info aktualisieren
        redis_client.hset(f"session_info:{session_id}", "last_activity", str(current_time))
        
        # Prüfe den aktuellen Status, um results_available korrekt zu setzen
        status = redis_client.get(f"processing_status:{session_id}")
        if status:
            # Sicher dekodieren, je nach Typ
            if isinstance(status, bytes):
                status = status.decode('utf-8')
            else:
                status = str(status)
                
            if status == 'completed':
                # Wenn der Status completed ist, setzen wir results_available auf true
                redis_client.hset(f"session_info:{session_id}", "results_available", "true")
        
        # Datenbank-Update
        try:
            upload = Upload.query.filter_by(session_id=session_id).first()
            if upload:
                upload.updated_at = datetime.utcnow()
                upload.last_used_at = datetime.utcnow()
                db.session.commit()
        except Exception as db_e:
            logger.warning(f"DB-Update für Session {session_id} fehlgeschlagen: {str(db_e)}")
            # Nicht kritisch, also kein return False
        
        logger.info(f"Zeitstempel für Session {session_id} aktualisiert")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Session-Zeitstempels: {str(e)}")
        return False


def manage_user_sessions(user_id):
    """
    Verwaltet die Sessions eines Benutzers effizienter.
    Löscht alte Sessions, um Platz für neue zu schaffen (Limit aus .env).
    """
    # Lese das Limit aus der .env-Datei, Standardwert 5
    try:
        max_sessions_str = os.environ.get('MAX_SESSIONS_PER_USER', '5')
        MAX_SESSIONS_PER_USER = int(max_sessions_str)
        logger.info(f"Session-Limit aus .env geladen: MAX_SESSIONS_PER_USER={MAX_SESSIONS_PER_USER}")
    except ValueError:
        logger.warning(f"Ungültiger Wert für MAX_SESSIONS_PER_USER in .env ('{max_sessions_str}'). Verwende Standardwert 5.")
        MAX_SESSIONS_PER_USER = 5
    
    if not user_id:
        logger.info("Kein Benutzer angegeben, Session-Management übersprungen")
        return

    logger.info("Verwalte Sessions für Benutzer %s (Limit: %s)", user_id, MAX_SESSIONS_PER_USER)

    try:
        # Zuerst nur die Anzahl der Uploads zählen
        upload_count = Upload.query.filter_by(user_id=user_id).count()
        logger.info("Benutzer hat aktuell %s Uploads.", upload_count)

        # Nur handeln, wenn das Limit überschritten ist
        if upload_count > MAX_SESSIONS_PER_USER:
            num_to_delete = upload_count - MAX_SESSIONS_PER_USER
            logger.info("Limit überschritten, lösche die %s ältesten Uploads...", num_to_delete)
            
            # Hole nur die zu löschenden Uploads (die ältesten)
            # Sortiere so, dass NULLs zuerst kommen (gelten als am ältesten),
            # dann nach dem Datum aufsteigend.
            # Wähle nur die Upload-Objekte aus (nicht nur IDs), da delete_upload_and_related_data das Objekt braucht
            uploads_to_delete = Upload.query.filter_by(user_id=user_id).order_by(
                Upload.last_used_at.is_(None).desc(), # NULLs zuerst
                Upload.last_used_at.asc()            # Dann nach Datum
            ).limit(num_to_delete).all()
            
            # Lösche diese Uploads und ihre zugehörigen Daten
            deleted_count = 0
            for upload in uploads_to_delete:
                if delete_upload_and_related_data(upload):
                    deleted_count += 1
                else:
                    logger.warning(f"Konnte Upload {upload.id} (Session: {upload.session_id}) nicht vollständig löschen.")
            
            logger.info("Erfolgreich %s von %s zu löschenden Uploads entfernt.", deleted_count, num_to_delete)
        else:
            logger.info("Session-Limit nicht überschritten.")

    except Exception as e:
        logger.error("Fehler beim Verwalten der Sessions für Benutzer %s: %s", user_id, str(e))


def delete_upload_and_related_data(upload):
    """
    Löscht einen Upload und alle zugehörigen Daten.
    """
    try:
        upload_id = upload.id
        session_id = upload.session_id

        # Debug-Ausgabe des last_used_at-Werts
        last_used_value = "NULL" if upload.last_used_at is None else upload.last_used_at.isoformat()
        logger.info("Lösche Upload %s mit session_id=%s, last_used_at=%s", upload_id, session_id, last_used_value)

        # WICHTIG: Korrekte Reihenfolge beim Löschen - erst Abhängigkeiten, dann Haupteinträge
        # Verbindungstabelle wurde entfernt, dieser Schritt ist nicht mehr notwendig
        # 1. Andere abhängige Daten löschen
        Flashcard.query.filter_by(upload_id=upload_id).delete()
        Question.query.filter_by(upload_id=upload_id).delete()

        # 2. Topics löschen
        Topic.query.filter_by(upload_id=upload_id).delete()

        # 3. UserActivity-Einträge löschen
        UserActivity.query.filter_by(session_id=session_id).delete()

        # 4. Schließlich den Upload selbst löschen
        db.session.delete(upload)

        # Commit der Änderungen sofort für jeden Upload
        db.session.commit()

        logger.info("Upload %s (session_id=%s) erfolgreich gelöscht", upload_id, session_id)

        # Lösche auch zugehörige Redis-Daten
        delete_redis_session_data(session_id)

        return True
    except Exception as e:
        logger.error("Fehler beim Löschen des Uploads %s: %s", upload.id, str(e))
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

            logger.info("Redis-Daten für Session %s gelöscht", session_id)
            return True
        except Exception as e:
            logger.error("Fehler beim Löschen der Redis-Daten für Session %s: %s", session_id, str(e))
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

        # Sichere Zugriffe auf Upload-Attribute
        session_info = {
            "session_id": session_id,
            "upload_id": upload.id
        }
        
        # Unterschiedliche Benennungen von Dateiname berücksichtigen
        if hasattr(upload, 'filename'):
            session_info["filename"] = upload.filename
        elif hasattr(upload, 'file_name_1'):
            session_info["filename"] = upload.file_name_1
            
        # Optionale Attribute hinzufügen
        if hasattr(upload, 'file_type'):
            session_info["file_type"] = upload.file_type
        if hasattr(upload, 'file_size'):
            session_info["file_size"] = upload.file_size
        if hasattr(upload, 'page_count'):
            session_info["page_count"] = upload.page_count
        
        # Zeitstempel hinzufügen
        if hasattr(upload, 'created_at') and upload.created_at:
            session_info["created_at"] = upload.created_at.isoformat()
        if hasattr(upload, 'last_used_at') and upload.last_used_at:
            session_info["last_used_at"] = upload.last_used_at.isoformat()
            
        # Status-Informationen hinzufügen
        session_info["processing_status"] = processing_status
        session_info["processing_progress"] = processing_progress

        return session_info, None
    except Exception as e:
        logger.error("Fehler beim Abrufen der Session-Informationen für %s: %s", session_id, str(e))
        return None, f"Fehler: {str(e)}"


def session_mgmt_get_session_info(session_id):
    """
    Wrapper-Funktion für get_session_info, spezifisch für das Sitzungs-Management.
    Gibt Basisinformationen zu einer Sitzung zurück.
    
    Args:
        session_id: Die Sitzungs-ID für die Upload-Session
        
    Returns:
        JSON-Response mit den Session-Informationen oder einer Fehlermeldung
    """
    session_info, error = get_session_info(session_id)
    
    if error:
        return jsonify({
            "success": False,
            "error": {"code": "SESSION_ERROR", "message": error}
        }), 404 if "nicht gefunden" in error else 500
    
    return jsonify({
        "success": True,
        "session_info": session_info
    })


def update_session_info(session_id, upload_id=None, status=None, results_available=None, 
                  flashcards_count=None, questions_count=None, topics_count=None, 
                  main_topic=None, **additional_info):
    """
    Aktualisiert die Session-Informationen im Redis-Cache.
    
    Args:
        session_id: Die Session-ID
        upload_id: Die Upload-ID (optional)
        status: Der Status der Session (optional)
        results_available: Ob Ergebnisse verfügbar sind (optional)
        flashcards_count: Anzahl der Flashcards (optional)
        questions_count: Anzahl der Fragen (optional)
        topics_count: Anzahl der Themen (optional)
        main_topic: Das Hauptthema (optional)
        **additional_info: Zusätzliche Key-Value-Paare für den Redis-Cache
        
    Returns:
        bool: True wenn erfolgreich, sonst False
    """
    try:
        redis_client = get_redis_client()
        
        # Erstelle ein Mapping mit den gegebenen Werten
        mapping = {}
        
        if upload_id is not None:
            mapping['upload_id'] = str(upload_id)
            
        if status is not None:
            mapping['status'] = str(status)
            
        if results_available is not None:
            # Boolean in String umwandeln
            mapping['results_available'] = 'true' if results_available else 'false'
            
        if flashcards_count is not None:
            mapping['flashcards_count'] = str(flashcards_count)
            
        if questions_count is not None:
            mapping['questions_count'] = str(questions_count)
            
        if topics_count is not None:
            mapping['topics_count'] = str(topics_count)
            
        if main_topic is not None:
            mapping['main_topic'] = str(main_topic)
            
        # Zusätzliche Informationen hinzufügen
        for key, value in additional_info.items():
            # Stelle sicher, dass alle Werte Strings sind
            mapping[key] = str(value)
            
        # Redis-Update durchführen
        if mapping:
            redis_client.hset(f"session_info:{session_id}", mapping=mapping)
            logger.info(f"Session-Info für {session_id} in Redis aktualisiert: {mapping}")
            return True
        else:
            logger.warning(f"Keine Updates für Session {session_id} - leeres Mapping")
            return False
            
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren der Session-Info für {session_id}: {str(e)}")
        return False


def delete_session(session_id):
    """
    Löscht eine Session und alle zugehörigen Daten.
    
    Args:
        session_id: Die Session-ID
        
    Returns:
        JSON-Antwort mit dem Status der Löschung
    """
    try:
        # Upload aus der Datenbank holen
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        if not upload:
            logger.warning(f"Sitzung {session_id} nicht gefunden, keine Daten zu löschen")
            return jsonify({
                "success": False,
                "error": {"code": "SESSION_NOT_FOUND", "message": "Sitzung nicht gefunden"}
            }), 404
            
        # Lösche Upload und zugehörige Daten
        if delete_upload_and_related_data(upload):
            return jsonify({
                "success": True,
                "message": f"Sitzung {session_id} erfolgreich gelöscht"
            })
        else:
            return jsonify({
                "success": False,
                "error": {"code": "DELETE_ERROR", "message": "Fehler beim Löschen der Sitzung"}
            }), 500
            
    except Exception as e:
        logger.error(f"Fehler beim Löschen der Sitzung {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "DELETE_ERROR", "message": f"Fehler beim Löschen der Sitzung: {str(e)}"}
        }), 500


def delete_session_data(session_id, include_uploads=False):
    """Löscht alle mit einer bestimmten Session-ID verbundenen Daten."""
    try:
        # Finde den Upload für diese Session
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        if not upload:
            return {
                "success": False,
                "message": f"Keine Session mit ID {session_id} gefunden."
            }
        
        upload_id = upload.id
        logger.info(f"Lösche alle Daten für Upload {upload_id} (Session {session_id})")
        
        # Lösche abhängige Daten
        Flashcard.query.filter_by(upload_id=upload_id).delete()
        Question.query.filter_by(upload_id=upload_id).delete()
        Topic.query.filter_by(upload_id=upload_id).delete()
        
        # Lösche den Upload selbst, wenn gewünscht
        if include_uploads:
            Upload.query.filter_by(id=upload_id).delete()
        
        # Lösche Redis-Schlüssel
        redis_client.delete(f"session:{session_id}")
        redis_client.delete(f"upload_status:{session_id}")
        redis_client.delete(f"processing_status:{session_id}")
        redis_client.delete(f"processing_progress:{session_id}")
        
        # Commit der Änderungen
        db.session.commit()
        
        return {
            "success": True,
            "message": f"Alle Daten für Session {session_id} wurden erfolgreich gelöscht."
        }
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Löschen der Session-Daten: {str(e)}")
        return {
            "success": False,
            "message": f"Fehler beim Löschen der Session-Daten: {str(e)}"
        }


def create_or_refresh_session():
    """
    Erstellt eine neue Session oder aktualisiert die bestehende.
    Gibt immer eine neue Session-ID zurück.
    
    Returns:
        Neue Session-ID als String
    """
    # Immer eine neue Session-ID generieren
    session_id = str(uuid.uuid4())
    
    # Redis-Client holen
    redis_client = get_redis_client()
    
    # Session in Redis erstellen
    redis_client.hset(f"session:{session_id}:info", mapping={
        "created_at": datetime.now().isoformat(),
        "last_access": datetime.now().isoformat(),
        "results_available": "false",
        "flashcards_count": 0,
        "questions_count": 0,
        "topics_count": 0
    })
    
    # TTL auf 48 Stunden setzen
    redis_client.expire(f"session:{session_id}:info", 60 * 60 * 48)
    
    logger.info(f"Neue Session erstellt: {session_id}")
    return session_id


def check_session_exists(session_id):
    """
    Prüft, ob eine Session mit der angegebenen ID existiert.
    
    Args:
        session_id: Die zu prüfende Session-ID
        
    Returns:
        True, wenn die Session existiert, sonst False
    """
    redis_client = get_redis_client()
    return redis_client.exists(f"session:{session_id}:info") > 0


def enforce_session_limit(user_id, limit=5):
    """
    Stellt sicher, dass ein Benutzer nicht mehr als 'limit' Uploads hat.
    Markiert die ältesten Uploads zum Löschen, wenn das Limit überschritten wird.
    Der eigentliche Commit muss in der aufrufenden Funktion erfolgen.

    Args:
        user_id (str): Die ID des Benutzers.
        limit (int): Die maximale Anzahl erlaubter Uploads.

    Returns:
        int: Die Anzahl der zum Löschen markierten Uploads.
    """
    if not user_id:
        return 0

    try:
        # Zähle aktuelle Uploads des Benutzers
        current_uploads = db.session.query(Upload).filter_by(user_id=user_id)
        count = current_uploads.count()
        logger.debug(f"Benutzer {user_id} hat {count} Uploads (Limit: {limit}).")

        num_to_delete = count - limit

        if num_to_delete > 0:
            logger.info(f"Limit von {limit} für User {user_id} überschritten ({count} vorhanden). Markiere {num_to_delete} älteste Uploads zum Löschen...")
            # Finde die ältesten Uploads zum Löschen
            uploads_to_delete = current_uploads.order_by(Upload.created_at.asc()).limit(num_to_delete).all()

            deleted_count = 0
            for upload in uploads_to_delete:
                logger.info(f"  -> Markiere Upload ID: {upload.id} (Session: {upload.session_id}, Erstellt: {upload.created_at}) für User {user_id} zum Löschen.")
                # Nur zum Löschen markieren, nicht committen!
                db.session.delete(upload)
                deleted_count += 1

            # KEIN COMMIT HIER! Der Commit erfolgt in der aufrufenden Funktion.
            # db.session.commit()
            logger.info(f"{deleted_count} Upload(s) für User {user_id} zum Löschen markiert.")
            return deleted_count
        else:
            return 0 # Kein Limit überschritten

    except Exception as e:
        logger.error(f"Fehler beim Anwenden des Session-Limits für User {user_id}: {e}", exc_info=True)
        # Rollback ist hier wichtig, um die Transaktion bei Fehlern zurückzusetzen!
        db.session.rollback() 
        # Fehler weitergeben, damit die aufrufende Funktion nicht weitermacht?
        raise e # Oder return 0 und hoffe, dass der nächste Commit geht? Besser Fehler werfen.
