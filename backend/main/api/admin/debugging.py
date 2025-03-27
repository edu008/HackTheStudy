"""
Debugging-Funktionen für das Admin-Modul.
Enthält Funktionen zum Testen und Debuggen von API-Komponenten.
"""

import logging
import json
import uuid
import redis
import os
from flask import jsonify, request
from api.log_utils import AppLogger
from api.openai_client import OptimizedOpenAIClient

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Redis-Client erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.from_url(redis_url)

def toggle_openai_debug():
    """Aktiviert oder deaktiviert das OpenAI API-Debug-Logging."""
    data = request.get_json()
    enable = data.get('enable', True) if data else True
    
    # Debug-Logging aktivieren oder deaktivieren
    AppLogger.debug_openai_api(enable)
    
    return jsonify({
        "success": True,
        "message": f"OpenAI API Debug-Logging {'aktiviert' if enable else 'deaktiviert'}",
        "enabled": enable
    })

def test_openai_api():
    """Sendet eine Test-Anfrage an die OpenAI API, um die Protokollierung zu testen."""
    # Temporäre Session-ID für das Tracking
    session_id = str(uuid.uuid4())
    
    # Aktiviere Debug-Logging falls noch nicht aktiviert
    AppLogger.debug_openai_api(True)
    
    logger.info(f"Sende Test-Anfrage an OpenAI API mit Session-ID: {session_id}")
    
    try:
        client = OptimizedOpenAIClient()
        response = client.query(
            prompt="Sage 'Hallo Welt' und erkläre was ein Python-Logger ist.",
            system_content="Du bist ein hilfreicher Assistent, der Debugging-Tests durchführt.",
            session_id=session_id,
            function_name="test_openai_api"
        )
        
        return jsonify({
            "success": True,
            "message": "OpenAI API-Test erfolgreich",
            "response": response,
            "session_id": session_id
        })
    except Exception as e:
        logger.error(f"OpenAI API-Test fehlgeschlagen: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"OpenAI API-Test fehlgeschlagen: {str(e)}",
            "session_id": session_id
        }), 500

def get_openai_errors():
    """Ruft OpenAI-Fehler und -Anfragen aus Redis ab."""
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({
            "success": False,
            "message": "session_id ist erforderlich"
        }), 400
    
    try:
        # Alle relevanten OpenAI-Schlüssel für diese Session abrufen
        request_key = f"openai_last_request:{session_id}"
        response_key = f"openai_last_response:{session_id}"
        error_key = f"openai_error:{session_id}"
        error_details_key = f"error_details:{session_id}"
        
        # Daten aus Redis abrufen
        request_data = redis_client.get(request_key)
        response_data = redis_client.get(response_key)
        error_data = redis_client.get(error_key)
        error_details = redis_client.get(error_details_key)
        
        # JSON-Decode für alle Daten
        result = {
            "session_id": session_id,
            "last_request": json.loads(request_data.decode('utf-8')) if request_data else None,
            "last_response": json.loads(response_data.decode('utf-8')) if response_data else None,
            "openai_error": json.loads(error_data.decode('utf-8')) if error_data else None,
            "error_details": json.loads(error_details.decode('utf-8')) if error_details else None,
        }
        
        # Status-Informationen hinzufügen
        progress_key = f"processing_progress:{session_id}"
        status_key = f"processing_status:{session_id}"
        progress_data = redis_client.get(progress_key)
        status_data = redis_client.get(status_key)
        
        result["processing_progress"] = json.loads(progress_data.decode('utf-8')) if progress_data else None
        result["processing_status"] = status_data.decode('utf-8') if status_data else None
        
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von OpenAI-Fehlern: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Fehler beim Abrufen von OpenAI-Fehlern: {str(e)}"
        }), 500

def get_system_logs(lines=100):
    """
    Gibt die letzten Zeilen der System-Logs zurück.
    
    Args:
        lines: Die Anzahl der letzten Zeilen, die zurückgegeben werden sollen
        
    Returns:
        dict: Die letzten Zeilen der System-Logs
    """
    try:
        # Auf Linux-Systemen können wir die tail-Befehle verwenden
        if os.name == 'posix':
            import subprocess
            result = subprocess.run(
                ["tail", f"-{lines}", "/var/log/app.log"], 
                capture_output=True, 
                text=True
            )
            log_lines = result.stdout.splitlines()
        else:
            # Auf anderen Systemen können wir die Logs aus dem Speicher abrufen
            from logging import getLogger
            root_logger = getLogger()
            for handler in root_logger.handlers:
                if hasattr(handler, 'buffer'):
                    log_lines = handler.buffer.splitlines()[-lines:]
                    break
            else:
                log_lines = ["Logs nicht verfügbar"]
        
        return jsonify({
            "success": True,
            "data": {
                "log_lines": log_lines,
                "count": len(log_lines)
            }
        })
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der System-Logs: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "LOG_ERROR", "message": str(e)}
        }), 500 