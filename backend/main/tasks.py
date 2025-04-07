"""
Zentrales Task-Management für die Kommunikation mit dem Worker-Container.
Enthält Task-Definitionen und Task-Dispatching-Funktionalität.
"""

import json
import logging
import os
import socket
import tempfile
import time
import uuid
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Union

from celery import Celery
from celery.exceptions import OperationalError

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Dateisystem-Task-Queue konfigurieren
TASK_DIRECTORY = os.path.join(tempfile.gettempdir(), 'hackthestudy_tasks')
os.makedirs(TASK_DIRECTORY, exist_ok=True)

# Redis-URL für Celery konfigurieren
redis_password = os.environ.get('REDIS_PASSWORD', 'hackthestudy_redis_password')
redis_host = os.environ.get('REDIS_HOST', 'localhost')
redis_port = os.environ.get('REDIS_PORT', '6379')
redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"

# Celery-Client zum Senden von Tasks an den Worker
celery_app = Celery('api', broker=redis_url, backend=redis_url)
celery_app.conf.update(
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_connection_retry_on_startup=True,
    task_publish_retry=True,
    task_publish_retry_policy={
        'max_retries': 5,
        'interval_start': 0.2,
        'interval_step': 0.5,
        'interval_max': 3,
    }
)

#
# Task-Definitionen
#


class UploadTask:
    """
    Definition für den Upload-Verarbeitungs-Task.

    Attribute:
        session_id (str): ID der Upload-Session
        files_data (List[Tuple[str, str]]): Liste von Tupeln mit Dateinamen und -inhalt (als Hex)
        user_id (Optional[str]): ID des Benutzers, falls angemeldet
    """

    def __init__(self, session_id: str, files_data: List[Tuple[str, str]], user_id: Optional[str] = None):
        self.session_id = session_id
        self.files_data = files_data
        self.user_id = user_id

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Task-Definition in ein Dictionary für die Übertragung."""
        return {
            'session_id': self.session_id,
            'files_data': self.files_data,
            'user_id': self.user_id
        }

# Hilfsfunktionen für Dateisystem-Speicherung


def save_to_fs(key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
    """
    Speichert Daten im Dateisystem anstelle von Redis.

    Args:
        key: Eindeutiger Schlüssel
        value: Zu speichernder Wert
        expire_seconds: Lebensdauer in Sekunden

    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        # Erstelle sicheren Dateinamen
        safe_key = key.replace(':', '_').replace('/', '_')
        file_path = os.path.join(TASK_DIRECTORY, safe_key + '.json')

        # Füge Ablaufzeit-Informationen hinzu
        data = {
            'value': value,
            'created_at': time.time()
        }

        if expire_seconds is not None:
            data['expires_at'] = time.time() + expire_seconds

        # Schreibe in Datei mit UTF-8 Encoding
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        return True
    except Exception as e:
        logger.error("Fehler beim Speichern in Datei (%s): %s", key, str(e))
        return False


def get_from_fs(key: str, default: Any = None) -> Any:
    """
    Liest Daten aus dem Dateisystem anstelle von Redis.

    Args:
        key: Eindeutiger Schlüssel
        default: Standardwert, falls Schlüssel nicht existiert

    Returns:
        Gespeicherter Wert oder default
    """
    try:
        # Erstelle sicheren Dateinamen
        safe_key = key.replace(':', '_').replace('/', '_')
        file_path = os.path.join(TASK_DIRECTORY, safe_key + '.json')

        # Prüfe, ob Datei existiert
        if not os.path.exists(file_path):
            return default

        # Lese aus Datei mit UTF-8 Encoding
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Prüfe auf Ablaufzeit
        if 'expires_at' in data and data['expires_at'] < time.time():
            # Abgelaufen, lösche Datei
            os.remove(file_path)
            return default

        return data['value']
    except Exception as e:
        logger.error("Fehler beim Lesen aus Datei (%s): %s", key, str(e))
        return default


def delete_from_fs(key: str) -> bool:
    """
    Löscht Daten aus dem Dateisystem anstelle von Redis.

    Args:
        key: Eindeutiger Schlüssel

    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        # Erstelle sicheren Dateinamen
        safe_key = key.replace(':', '_').replace('/', '_')
        file_path = os.path.join(TASK_DIRECTORY, safe_key + '.json')

        # Prüfe, ob Datei existiert
        if not os.path.exists(file_path):
            return False

        # Lösche Datei
        os.remove(file_path)
        return True
    except Exception as e:
        logger.error("Fehler beim Löschen aus Datei (%s): %s", key, str(e))
        return False


def check_worker_connection() -> bool:
    """
    Prüft, ob eine Verbindung zum Worker hergestellt werden kann.

    Returns:
        True, wenn der Worker erreichbar ist, sonst False
    """
    try:
        # Versuche eine Verbindung zum Broker herzustellen
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=3, interval_start=0.2)
        conn.release()

        # Versuche eine einfache Ping-Task zu senden
        ping_result = celery_app.control.ping(timeout=2)
        workers_responding = len(ping_result) > 0

        if workers_responding:
            logger.info("Worker-Verbindung OK: %s", ping_result)
            return True
        
        logger.warning("Keine Worker antworten auf Ping")
        return False
    except Exception as e:
        logger.error("Fehler beim Prüfen der Worker-Verbindung: %s", str(e))
        return False


def _dispatch_upload_task(
        session_id: str, files_data: List[Tuple[str, str]], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sendet einen Upload-Verarbeitungs-Task an den Worker.

    Args:
        session_id: ID der Upload-Session
        files_data: Liste von Tupeln mit Dateinamen und -inhalt (als Hex)
        user_id: ID des Benutzers, falls angemeldet

    Returns:
        Dict mit Status und Task-ID
    """
    # Prüfe Worker-Verbindung
    if not check_worker_connection():
        logger.warning("Worker nicht erreichbar - Task für Session %s wird in Queue gestellt", session_id)

    # Für große Datensätze: Speichere Dateidaten im Dateisystem
    save_to_fs(
        f"upload_files_data:{session_id}",
        files_data,
        expire_seconds=3600  # 1 Stunde Gültigkeit
    )

    try:
        # Task an Worker senden
        celery_task = celery_app.send_task(
            'process_upload',
            args=[session_id, files_data, user_id],
            kwargs={}
        )

        # Task-ID im Dateisystem speichern
        save_to_fs(f"task_id:{session_id}", celery_task.id, expire_seconds=3600)

        logger.info("Upload-Task für Session %s gesendet, Task-ID: %s", session_id, celery_task.id)

        return {
            "success": True,
            "task_id": celery_task.id,
            "session_id": session_id
        }
    except Exception as e:
        logger.error("Fehler beim Senden des Upload-Tasks: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "session_id": session_id
        }


def dispatch_upload_task(session_id: str, files: List[Dict[str, Any]], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Öffentliche Schnittstelle für das Senden eines Upload-Tasks.

    Args:
        session_id: ID der Upload-Session
        files: Liste von Datei-Objekten mit name und content
        user_id: ID des Benutzers, falls angemeldet

    Returns:
        Dict mit Status und Task-ID
    """
    # Konvertiere Dateien in das erwartete Format
    files_data = [(f['name'], f['content']) for f in files]

    # Mehrere Versuche für den Upload-Task
    max_retries = 3
    retry_delay = 1

    for retry in range(max_retries):
        try:
            # Sende den Task
            result = _dispatch_upload_task(session_id, files_data, user_id)
            if result.get("success", False):
                return result

            # Bei Fehler kurz warten und dann neu versuchen
            if retry < max_retries - 1:
                logger.warning(
                    f"Wiederhole Upload-Task für Session {session_id} "
                    f"in {retry_delay} Sekunden (Versuch {retry+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponentieller Backoff
        except Exception as e:
            logger.error("Exception bei Upload-Task für Session %s: %s", session_id, str(e))
            if retry < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2

    # Wenn alle Versuche fehlgeschlagen sind
    logger.error("Alle Versuche (%s) für Upload-Task fehlgeschlagen", max_retries)
    return {
        "success": False,
        "error": "Alle Versuche fehlgeschlagen",
        "session_id": session_id
    }


def dispatch_api_request(method: str, endpoint: str,
                         data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sendet einen API-Request-Task an den Worker.

    Args:
        method: HTTP-Methode ('GET', 'POST', etc.)
        endpoint: API-Endpunkt (z.B. '/api/v1/analyze')
        data: Request-Daten als Dictionary
        user_id: ID des Benutzers, falls angemeldet

    Returns:
        Dict mit Status und Task-ID
    """
    # Generiere eine Task-ID
    request_id = str(uuid.uuid4())

    # Speichere Request-Daten im Dateisystem
    request_data = {
        'method': method,
        'endpoint': endpoint,
        'data': data,
        'user_id': user_id,
        'timestamp': datetime.now().isoformat()
    }
    save_to_fs(f"api_request:{request_id}", request_data, expire_seconds=3600)

    # Prüfe Worker-Verbindung
    if not check_worker_connection():
        logger.warning("Worker nicht erreichbar - API-Request-Task wird in Queue gestellt")

    try:
        # Sende Task an Worker
        celery_task = celery_app.send_task(
            'process_api_request',
            args=[endpoint, method, data, user_id],
            kwargs={}
        )

        logger.info("API-Request-Task für %s %s gesendet, Task-ID: %s", method, endpoint, celery_task.id)

        # Erstelle Antwort-Dictionary
        return {
            "success": True,
            "task_id": celery_task.id,
            "request_id": request_id
        }
    except Exception as e:
        logger.error("Fehler beim Senden des API-Request-Tasks: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "request_id": request_id
        }


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Prüft den Status eines Tasks.

    Args:
        task_id: Die Celery-Task-ID

    Returns:
        Dict mit Status-Informationen
    """
    logger.info("Prüfe Status für Task-ID %s", task_id)

    try:
        # Task-Status über Celery abfragen
        task_result = celery_app.AsyncResult(task_id)

        status = {
            "task_id": task_id,
            "status": task_result.status,
            "ready": task_result.ready(),
            "info": None,
            "error": None
        }

        # Falls Task abgeschlossen oder fehlgeschlagen ist, Ergebnis/Fehler abrufen
        if task_result.ready():
            try:
                status["info"] = task_result.result
                logger.info("Task %s abgeschlossen mit Ergebnis: %s", task_id, status['info'])
            except Exception as e:
                status["error"] = str(e)
                logger.error("Fehler beim Abrufen des Ergebnisses für Task %s: %s", task_id, str(e))

        return status
    except Exception as e:
        logger.error("Fehler beim Abrufen des Task-Status: %s", str(e))
        return {
            "task_id": task_id,
            "status": "unknown",
            "error": str(e)
        }


def _dispatch_processing_task(task):
    """
    Sendet einen ProcessingTask an den Worker.

    Args:
        task: Ein ProcessingTask-Objekt

    Returns:
        Dict mit Status und Task-ID
    """
    # Prüfe Worker-Verbindung
    if not check_worker_connection():
        logger.warning("Worker nicht erreichbar - Task für Upload %s wird in Queue gestellt", task.upload_id)

    try:
        # Konvertiere ProcessingTask in ein Dictionary
        task_data = task.to_dict()
        
        # Task an Worker senden
        celery_task = celery_app.send_task(
            'process_document',
            args=[task.id, task.upload_id, task.session_id],
            kwargs={"task_metadata": task.task_metadata}
        )

        # Task-ID im Redis-Cache speichern
        from core.redis_client import get_redis_client
        redis_client = get_redis_client()
        redis_client.hset(
            f"processing_task:{task.id}",
            mapping={
                "celery_task_id": celery_task.id,
                "status": "dispatched",
                "timestamp": time.time()
            }
        )
        redis_client.expire(f"processing_task:{task.id}", 86400)  # 24 Stunden TTL

        logger.info("Processing-Task %s für Upload %s gesendet, Celery-Task-ID: %s", 
                    task.id, task.upload_id, celery_task.id)

        return {
            "success": True,
            "task_id": celery_task.id,
            "processing_task_id": task.id
        }
    except Exception as e:
        logger.error("Fehler beim Senden des Processing-Tasks: %s", str(e))
        task.status = "error"
        task.error_message = f"Task-Dispatch-Fehler: {str(e)}"
        from core.models import db
        db.session.commit()
        
        return {
            "success": False,
            "error": str(e),
            "processing_task_id": task.id
        }
