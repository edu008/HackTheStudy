import json
import time
import logging
import traceback
from datetime import datetime
from core.redis_client import redis_client
from flask import current_app, g
import os

logger = logging.getLogger(__name__)

class AppLogger:
    """Optimiertes Logging für Digital Ocean App Platform"""
    
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.redis_client = redis_client

    def info(self, message, **kwargs):
        self.logger.info(message)
        self._store_log("INFO", message, **kwargs)

    def error(self, message, **kwargs):
        self.logger.error(message)
        self._store_log("ERROR", message, **kwargs)

    def warning(self, message, **kwargs):
        self.logger.warning(message)
        self._store_log("WARNING", message, **kwargs)

    def debug(self, message, **kwargs):
        self.logger.debug(message)
        self._store_log("DEBUG", message, **kwargs)

    def _store_log(self, level, message, **kwargs):
        try:
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message,
                **kwargs
            }
            self.redis_client.lpush("app_logs", json.dumps(log_data))
            self.redis_client.ltrim("app_logs", 0, 999)  # Behalte nur die letzten 1000 Logs
        except Exception as e:
            self.logger.error(f"Fehler beim Speichern des Logs: {str(e)}")

    @staticmethod
    def structured_log(level, message, session_id=None, component=None, **extra):
        """Erzeugt strukturierte Logs im JSON-Format für bessere Analysierbarkeit"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "component": component or "backend"
        }
        
        # Wichtige Kontext-Informationen
        if session_id:
            log_data["session_id"] = session_id
        
        # Benutzer-ID aus g-Objekt oder Parameter
        user_id = extra.pop("user_id", None) or (g.user.id if hasattr(g, "user") and g.user else None)
        if user_id:
            log_data["user_id"] = user_id
            
        # Weitere Attribute hinzufügen
        log_data.update(extra)
        
        # Logger mit passendem Level aufrufen
        log_message = json.dumps(log_data)
        
        if level == "DEBUG":
            logger.debug(log_message)
        elif level == "INFO":
            logger.info(log_message)
        elif level == "WARNING":
            logger.warning(log_message)
        elif level == "ERROR":
            logger.error(log_message)
        elif level == "CRITICAL":
            logger.critical(log_message)
    
    @staticmethod
    def track_session_progress(session_id, progress_percent, message, stage="processing"):
        """Session-Fortschritt aktualisieren mit Logging"""
        details = {
            "stage": stage,
            "message": message,
            "progress": progress_percent,
            "timestamp": time.time()
        }
        
        # In Redis speichern
        redis_client.set(f"processing_progress:{session_id}", json.dumps(details), ex=3600)
        redis_client.set(f"processing_status:{session_id}", stage, ex=3600)
        
        # In Logs schreiben
        AppLogger.structured_log(
            "INFO",
            f"Session {session_id}: {message} ({progress_percent}%)",
            session_id=session_id,
            component="progress_tracker",
            progress=progress_percent,
            stage=stage
        )
    
    @staticmethod
    def track_error(session_id, error_type, message, trace=None, diagnostics=None):
        """Fehler mit strukturiertem Logging und Redis-Speicherung"""
        # Bereinige Traceback für Logs
        if trace and len(trace) > 1500:
            trace_preview = trace[:700] + "\n...[gekürzt]...\n" + trace[-700:]
        else:
            trace_preview = trace
            
        # Log erstellen
        AppLogger.structured_log(
            "ERROR",
            f"Fehler in Session {session_id}: {message}",
            session_id=session_id,
            component="error_handler",
            error_type=error_type,
            trace_preview=trace_preview[:200] + "..." if trace_preview and len(trace_preview) > 200 else trace_preview
        )
        
        # Kompletten Fehler in Redis speichern
        error_data = {
            "error_type": error_type,
            "message": message,
            "timestamp": time.time()
        }
        
        if trace:
            error_data["trace"] = trace
            
        if diagnostics:
            error_data["diagnostics"] = diagnostics
            
        # In Redis speichern für Frontend-Zugriff
        redis_client.set(f"error_details:{session_id}", json.dumps(error_data), ex=3600)
        redis_client.set(f"processing_status:{session_id}", "error", ex=3600)
        
    @staticmethod
    def log_openai_request(session_id, model, system_preview, prompt_preview, tokens_in=None):
        """OpenAI-Anfrage in strukturiertem Format loggen"""
        AppLogger.structured_log(
            "INFO",
            f"OpenAI Anfrage: Session {session_id}, Modell {model}",
            session_id=session_id,
            component="openai_client",
            model=model,
            system_preview=system_preview[:150] + "..." if len(system_preview) > 150 else system_preview,
            prompt_preview=prompt_preview[:150] + "..." if len(prompt_preview) > 150 else prompt_preview,
            tokens_in=tokens_in
        )
        
        # Ausführliches DEBUG-Logging für vollständige OpenAI-Anfragen
        debug_logger = logging.getLogger("api.openai_client")
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_log = {
                "type": "openai_request",
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "model": model,
                "tokens_in": tokens_in,
                "system_content": system_preview,
                "prompt": prompt_preview
            }
            debug_logger.debug(f"OPENAI_DEBUG_REQUEST: {json.dumps(debug_log)}")
            
            # Zusätzlich unmittelbare Ausgabe im Standardlog
            logger.debug(f"OpenAI API-Anfrage - Session {session_id}, Modell {model}, Tokens: {tokens_in}")
            logger.debug(f"System: {system_preview[:300]}...")
            logger.debug(f"Prompt: {prompt_preview[:500]}...")
        
    @staticmethod
    def log_openai_response(session_id, response_preview, tokens_out=None, duration_ms=None):
        """OpenAI-Antwort in strukturiertem Format loggen"""
        AppLogger.structured_log(
            "INFO",
            f"OpenAI Antwort: Session {session_id}",
            session_id=session_id,
            component="openai_client",
            response_preview=response_preview[:150] + "..." if len(response_preview) > 150 else response_preview,
            tokens_out=tokens_out,
            duration_ms=duration_ms
        )
        
        # Ausführliches DEBUG-Logging für vollständige OpenAI-Antworten
        debug_logger = logging.getLogger("api.openai_client")
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_log = {
                "type": "openai_response",
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "tokens_out": tokens_out,
                "duration_ms": duration_ms,
                "response": response_preview
            }
            debug_logger.debug(f"OPENAI_DEBUG_RESPONSE: {json.dumps(debug_log)}")
            
            # Zusätzlich unmittelbare Ausgabe im Standardlog
            logger.debug(f"OpenAI API-Antwort - Session {session_id}, Dauer: {duration_ms}ms, Tokens: {tokens_out}")
            logger.debug(f"Antwort: {response_preview[:500]}...")
    
    @staticmethod
    def debug_openai_api(enable=True):
        """Aktiviert oder deaktiviert das ausführliche DEBUG-Logging für die OpenAI API.
        
        Args:
            enable (bool): True, um Debug-Logging zu aktivieren, False, um es zu deaktivieren
        """
        # OpenAI API Logger konfigurieren
        openai_logger = logging.getLogger('api.openai_client')
        openai_logger.setLevel(logging.DEBUG if enable else logging.INFO)
        
        # Python-OpenAI Bibliothek Logger konfigurieren
        openai_lib_logger = logging.getLogger('openai')
        openai_lib_logger.setLevel(logging.DEBUG if enable else logging.INFO)
        
        # Umgebungsvariable setzen
        if enable:
            os.environ['OPENAI_LOG'] = 'debug'
            # Direktes Log zur Bestätigung
            logger.info("🐞 OpenAI API Debug-Logging aktiviert - alle API-Anfragen werden nun vollständig geloggt")
        else:
            os.environ['OPENAI_LOG'] = 'info'
            logger.info("OpenAI API Debug-Logging deaktiviert")
        
        # Aktuelle Einstellung in Redis speichern für persistente Konfiguration
        redis_client.set('openai_debug_enabled', str(enable).lower(), ex=86400)  # 24 Stunden gültig 