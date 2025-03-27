# api/processing.py
"""
Funktionen zur Verarbeitung hochgeladener Dateien und zur Analyse des Inhalts.
"""

import json
import logging
import os
import time
import traceback

import redis
from celery import Celery
from flask import current_app, jsonify, request

from api.auth import token_required
from . import api_bp
from ..token_tracking import (calculate_token_cost, check_credits_available,
                             deduct_credits)

# Redis-Client direkt erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://hackthestudy-backend-main:6379/0')
redis_client = redis.from_url(redis_url)

# Celery-Client zum Senden von Tasks an den Worker
celery_app = Celery('api', broker=redis_url, backend=redis_url)

# Konfiguriere Logger
logger = logging.getLogger(__name__)

# Fehlercodes
ERROR_INVALID_INPUT = "INVALID_INPUT"
ERROR_PROCESSING_FAILED = "PROCESSING_FAILED"
ERROR_INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"


def create_error_response(message, error_code, details=None):
    """Erstellt eine standardisierte Fehlerantwort"""
    error_response = {
        "success": False,
        "message": message,
        "error": {
            "code": error_code
        }
    }

    if details:
        error_response["error"]["details"] = details

    return jsonify(error_response), 400


def delegate_to_worker(task_name, *args, **kwargs):
    """Delegiert eine Aufgabe an den Worker über Celery."""
    try:
        logger.info(
            f"📤 WORKER-DELEGATION: Sende Task '{task_name}' an Worker mit "
            f"args={args[:30] if args else []} und kwargs={kwargs}")
        task = celery_app.send_task(task_name, args=args, kwargs=kwargs)
        logger.info("✅ WORKER-DELEGATION: Task erfolgreich gesendet - Task-ID: %s", task.id)

        # Zusätzliche Diagnoseinformationen
        celery_broker = celery_app.conf.broker_url
        logger.info("📊 WORKER-DIAGNOSE: Broker-URL=%s, Worker-Task-ID=%s", celery_broker, task.id)

        # Versuche Verbindungsstatus zu prüfen
        try:
            broker_reachable = celery_app.connection().ensure_connection(max_retries=1)
            logger.info("🔌 WORKER-VERBINDUNG: Broker erreichbar = %s", broker_reachable)
        except Exception as conn_err:
            logger.error("❌ WORKER-VERBINDUNG: Broker-Verbindungsfehler: %s", str(conn_err))

        return task
    except Exception as e:
        error_message = f"❌ WORKER-DELEGATION: Fehler beim Senden der Task '{task_name}' an Worker: {str(e)}"
        logger.error(error_message)
        logger.error("Stacktrace: %s", traceback.format_exc())
        raise RuntimeError(error_message) from e


def initiate_processing(session_id, upload_id):
    """
    Initiiert die Verarbeitung eines hochgeladenen Dokuments.
    """
    try:
        # Setze den Verarbeitungsstatus
        update_processing_status(session_id, "waiting")

        # Setze den Startzeit-Zeitstempel
        redis_client.set(f"processing_start_time:{session_id}", int(time.time()))

        # Erstelle die Antwort für den Client
        response = {
            "success": True,
            "message": "Datei erfolgreich hochgeladen. Verarbeitung wird gestartet.",
            "session_id": session_id,
            "upload_id": upload_id,
            "status": "waiting",
            "next_steps": {
                "status_check": f"/api/v1/session-info/{session_id}",
                "process": f"/api/v1/process-upload/{session_id}",
                "results": f"/api/v1/results/{session_id}"
            }
        }

        return jsonify(response)
    except Exception as e:
        logger.error("Fehler beim Initiieren der Verarbeitung: %s", str(e))
        return create_error_response(
            "Fehler beim Initiieren der Verarbeitung",
            ERROR_PROCESSING_FAILED,
            {"detail": str(e)}
        )


def update_processing_status(session_id, status):
    """
    Aktualisiert den Verarbeitungsstatus einer Session.
    """
    try:
        redis_client.set(f"processing_status:{session_id}", status)
        redis_client.set(f"processing_last_update:{session_id}", int(time.time()))

        # Bei completed oder error auch den Fortschritt auf 100% setzen
        if status in ["completed", "error"]:
            redis_client.set(f"processing_progress:{session_id}", "100")

        logger.info("Verarbeitungsstatus für Session %s auf '%s' gesetzt", session_id, status)
        return True
    except Exception as e:
        logger.error("Fehler beim Aktualisieren des Verarbeitungsstatus für Session %s: %s", session_id, str(e))
        return False


@api_bp.route('/process-upload/<session_id>', methods=['POST', 'OPTIONS'])
def process_upload(session_id):
    """
    Startet die eigentliche Verarbeitung eines hochgeladenen Dokuments.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        return jsonify(success=True)

    try:
        # Überprüfe, ob die Session existiert
        from core.models import Upload
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({
                "success": False,
                "message": "Session nicht gefunden",
                "error": {"code": "SESSION_NOT_FOUND"}
            }), 404

        # Kredit-Check für angemeldete Benutzer
        user_id = upload.user_id
        if user_id:
            # Schätze den Token-Verbrauch basierend auf der Textlänge
            estimated_token_count = len(upload.content.split()) * 1.5  # Grobe Schätzung

            # Überprüfe, ob genügend Kredite vorhanden sind
            if not check_credits_available(user_id, estimated_token_count):
                return jsonify({
                    "success": False,
                    "message": "Nicht genügend Kredite für die Verarbeitung",
                    "error": {"code": ERROR_INSUFFICIENT_CREDITS}
                }), 402

        # Setze den Verarbeitungsstatus auf "processing"
        update_processing_status(session_id, "processing")

        # Sende die Verarbeitungsaufgabe an den Worker
        task = delegate_to_worker(
            "worker.ai_processing_task",
            upload.id,
            session_id,
            upload.content,
            user_id
        )

        # Speichere die Task-ID in Redis
        redis_client.set(f"task_id:{session_id}", task.id)

        return jsonify({
            "success": True,
            "message": "Verarbeitung gestartet",
            "task_id": task.id,
            "session_id": session_id,
            "status": "processing",
            "status_check": f"/api/v1/session-info/{session_id}"
        })
    except Exception as e:
        # Bei einem Fehler den Status auf "error" setzen
        update_processing_status(session_id, "error")

        # Fehlerdetails in Redis speichern
        redis_client.set(f"error_details:{session_id}", str(e))

        logger.error("Fehler bei der Verarbeitung von Session %s: %s", session_id, str(e))
        logger.error(traceback.format_exc())

        return jsonify({
            "success": False,
            "message": "Fehler bei der Verarbeitung",
            "error": {"code": ERROR_PROCESSING_FAILED, "detail": str(e)}
        }), 500


def calculate_upload_progress(session_id):
    """
    Berechnet den Fortschritt der Verarbeitung.
    """
    try:
        progress = redis_client.get(f"processing_progress:{session_id}")
        if progress:
            return float(progress.decode('utf-8'))
        return 0
    except Exception as e:
        logger.error("Fehler beim Berechnen des Fortschritts für Session %s: %s", session_id, str(e))
        return 0


def estimate_remaining_time(session_id):
    """
    Schätzt die verbleibende Zeit für die Verarbeitung.
    """
    try:
        # Hole Start-Zeit und aktuellen Fortschritt
        start_time = redis_client.get(f"processing_start_time:{session_id}")
        progress = redis_client.get(f"processing_progress:{session_id}")

        if not start_time or not progress or float(progress.decode('utf-8')) <= 0:
            return None

        start_time = int(start_time.decode('utf-8'))
        progress = float(progress.decode('utf-8'))

        # Berechne die vergangene Zeit
        elapsed_time = int(time.time()) - start_time

        # Schätze die Gesamtzeit basierend auf dem Fortschritt
        estimated_total_time = elapsed_time / (progress / 100)

        # Berechne die verbleibende Zeit
        remaining_time = estimated_total_time - elapsed_time

        # Runde auf ganze Sekunden
        return max(0, int(remaining_time))
    except Exception as e:
        logger.error("Fehler beim Schätzen der verbleibenden Zeit für Session %s: %s", session_id, str(e))
        return None


@api_bp.route('/retry-processing/<session_id>', methods=['POST', 'OPTIONS'])
@token_required
def retry_processing(session_id):
    """
    Startet die Verarbeitung einer fehlgeschlagenen Session neu.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        return jsonify(success=True)

    try:
        # Überprüfe, ob die Session existiert
        from core.models import Upload
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({
                "success": False,
                "message": "Session nicht gefunden",
                "error": {"code": "SESSION_NOT_FOUND"}
            }), 404

        # Lösche alle Fehler- und Status-Informationen in Redis
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
            f"openai_error:{session_id}"
        ]

        pipeline = redis_client.pipeline()
        for key in keys_to_delete:
            pipeline.delete(key)
        pipeline.execute()

        # Setze den Verarbeitungsstatus auf "waiting"
        update_processing_status(session_id, "waiting")

        # Leite zur Verarbeitungs-Route weiter
        return process_upload(session_id)
    except Exception as e:
        logger.error("Fehler beim Neustart der Verarbeitung für Session %s: %s", session_id, str(e))

        return jsonify({
            "success": False,
            "message": "Fehler beim Neustart der Verarbeitung",
            "error": {"code": ERROR_PROCESSING_FAILED, "detail": str(e)}
        }), 500
