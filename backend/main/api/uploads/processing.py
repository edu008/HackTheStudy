"""
(Refaktoriert) Enthält Hilfsfunktionen für den Upload-Prozess,
wie Fortschrittsberechnung und Fehlerbehandlung.
Die Kernlogik für Upload und Task-Start liegt in upload_core.py.
Die Verarbeitung selbst geschieht im Worker.
"""

import json
import logging
import os
import time
import traceback
from datetime import datetime, timedelta # timedelta hinzugefügt
import uuid
import re
import random

# Nur notwendige Flask/Werkzeug-Imports
from flask import jsonify

# Redis-Client (wird für Hilfsfunktionen benötigt)
from core.redis_client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

# --- Konstanten --- #
ERROR_INVALID_INPUT = "INVALID_INPUT"
ERROR_PROCESSING_FAILED = "PROCESSING_FAILED"
ERROR_INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
# ... (weitere Fehlercodes nach Bedarf)

# --- Hilfsfunktionen --- #

def create_error_response(message, error_code, details=None, status_code=400):
    """Erstellt eine standardisierte Fehlerantwort."""
    error_response = {
        "success": False,
        "message": message,
        "error": {
            "code": error_code
        }
    }
    if details:
        error_response["error"]["details"] = details
    return jsonify(error_response), status_code

def calculate_upload_progress(session_id):
    """Berechnet den Upload-Fortschritt basierend auf Redis-Daten."""
    try:
        redis_client = get_redis_client()
        # Annahme: Chunked-Upload-Infos liegen unter "upload:meta:{session_id}"
        # oder normale Upload-Infos unter "upload:{session_id}"
        progress_data = redis_client.hgetall(f"upload:meta:{session_id}")
        if not progress_data:
            progress_data = redis_client.hgetall(f"upload:{session_id}")

        if not progress_data:
             # Vielleicht ist der Status schon direkt gesetzt?
             status = redis_client.get(f"processing_status:{session_id}")
             if status == b'completed': return 100
             if status == b'ready_for_processing': return 100 # Nach Upload, vor Worker
             logger.debug(f"Keine Fortschrittsdaten in Redis für Session {session_id} gefunden.")
             return 0

        # Chunked Upload Logik
        total_chunks_b = progress_data.get(b'total_chunks')
        # Versuche beide möglichen Schlüssel für abgeschlossene Chunks
        completed_chunks_b = progress_data.get(b'uploaded_chunks') or progress_data.get(b'completed_chunks')
        if total_chunks_b and completed_chunks_b:
            try:
                 total_chunks = int(total_chunks_b)
                 completed_chunks = int(completed_chunks_b)
                 if total_chunks > 0:
                     progress_percent = int((completed_chunks / total_chunks) * 100)
                     # Wenn Chunks abgeschlossen, aber Status noch nicht finalized, gib 99% zurück
                     if progress_percent == 100 and progress_data.get(b'status') != b'finalized':
                         return 99
                     return progress_percent
            except ValueError:
                 logger.warning(f"Ungültige Chunk-Werte in Redis für Session {session_id}")
                 pass # Falle zurück zur Statusprüfung

        # Statusprüfung als Fallback
        status = progress_data.get(b'status')
        if status == b'completed': return 100
        if status == b'finalized': return 100 # Chunked upload abgeschlossen
        if status == b'ready_for_processing': return 100

        # Fortschritt für Worker-Verarbeitung (falls implementiert)
        worker_progress = redis_client.get(f"processing_progress:{session_id}")
        if worker_progress:
            try:
                return int(float(worker_progress))
            except ValueError:
                 pass

        logger.debug(f"Konnte Fortschritt für Session {session_id} nicht bestimmen, gebe 0 zurück.")
        return 0
        
    except Exception as e:
        logger.error(f"Fehler beim Berechnen des Upload-Fortschritts für Session {session_id}: {e}")
        return 0 # Fallback

def estimate_remaining_time(session_id, total_size_bytes=0):
    """Schätzt die verbleibende Upload-Zeit (hauptsächlich für Chunked Uploads)."""
    try:
        redis_client = get_redis_client()
        upload_info = redis_client.hgetall(f"upload:meta:{session_id}")

        start_time_str_b = upload_info.get(b'timestamp')
        total_chunks_b = upload_info.get(b'total_chunks')
        completed_chunks_b = upload_info.get(b'uploaded_chunks') or upload_info.get(b'completed_chunks')
        total_size_redis_b = upload_info.get(b'total_size')

        if not start_time_str_b or not total_chunks_b or not completed_chunks_b:
            logger.debug(f"Nicht genügend Daten für Zeitschätzung (Chunked) für Session {session_id}")
            return None

        start_time = float(start_time_str_b.decode('utf-8'))
        completed_chunks = int(completed_chunks_b)
        total_chunks = int(total_chunks_b)

        # Versuche die genaueste Gesamtgröße zu ermitteln
        if total_size_bytes and total_size_bytes > 0:
            actual_total_size = total_size_bytes
        elif total_size_redis_b:
            try:
                actual_total_size = int(total_size_redis_b)
            except ValueError:
                logger.warning(f"Ungültiger total_size Wert in Redis: {total_size_redis_b}")
                actual_total_size = 0
        else:
            actual_total_size = 0

        # Schätze bisher hochgeladene Bytes, wenn Gesamtgröße bekannt ist
        completed_bytes = 0
        if total_chunks > 0 and actual_total_size > 0:
             completed_bytes = int((completed_chunks / total_chunks) * actual_total_size)
        elif completed_chunks > 0:
            # Wenn Gesamtgröße unbekannt, nutze grobe Schätzung
             CHUNK_SIZE_APPROX = 5 * 1024 * 1024 # Muss ggf. angepasst werden!
             completed_bytes = completed_chunks * CHUNK_SIZE_APPROX
             # Setze actual_total_size auf Schätzwert, wenn unbekannt
             if actual_total_size == 0: actual_total_size = total_chunks * CHUNK_SIZE_APPROX

        elapsed_time = time.time() - start_time

        if elapsed_time <= 1 or completed_bytes <= 0 or actual_total_size <= 0:
            return None

        upload_speed_bps = completed_bytes / elapsed_time # Bytes pro Sekunde
        remaining_bytes = actual_total_size - completed_bytes

        if upload_speed_bps <= 0 or remaining_bytes < 0:
            # Wenn Upload abgeschlossen scheint (remaining <= 0) oder Geschwindigkeit ungültig
            if completed_chunks >= total_chunks:
                 return 0 # Upload fertig
                else:
                 return None # Schätzung nicht möglich

        remaining_time_sec = remaining_bytes / upload_speed_bps
        return max(0, int(remaining_time_sec))
        
    except Exception as e:
        logger.error(f"Fehler beim Schätzen der verbleibenden Zeit für Session {session_id}: {e}", exc_info=True)
        return None

# -------------------------------------------------------------------------
# -- Gelöschte Funktionen (waren hier vorher):                         --
# --                                                                     --
# -- process_uploaded_file: Logik jetzt in upload_core.upload_file     --
# -- delegate_to_worker: Wird nicht mehr direkt hier verwendet         --
# -- process_upload: Veraltet, Route sollte entfernt/angepasst werden  --
# -- retry_processing: Veraltet, Route sollte entfernt/angepasst werden --
# -- update_session_with_extracted_text: Veraltet                      --
# -- generate_demo_flashcards: Demo-Code, ausgelagert                 --
# -- generate_demo_questions: Demo-Code, ausgelagert                --
# -- generate_demo_topics: Demo-Code, ausgelagert                   --
# -- Celery/Redis Konfigurationsblöcke: Gehören in app_factory        --
# -- Imports für gelöschte Funktionen entfernt                         --
# -------------------------------------------------------------------------
