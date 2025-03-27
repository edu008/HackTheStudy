"""
Logging-Utilities für die API-Komponenten.
Vereinfachter Wrapper für die zentrale Konfiguration in config.py.
"""

import logging
import traceback
from typing import Dict, Optional

from config.config import config

# Basislogger für dieses Modul einrichten
logger = config.get_logger(__name__)


class AppLogger:
    """
    Optimiertes Logging für die Anwendung.
    Wrapper für die zentrale Logging-Konfiguration.
    """

    def __init__(self, name):
        """
        Initialisiert einen Logger mit dem angegebenen Namen.

        Args:
            name: Name des Loggers
        """
        self.logger = config.get_logger(name)

    def info(self, message, **kwargs):
        """
        Loggt eine Informationsnachricht.

        Args:
            message: Die zu loggende Nachricht
            **kwargs: Weitere Attribute für strukturierte Logs
        """
        self.logger.info(message)
        config.structured_log("INFO", message, **kwargs)

    def error(self, message, **kwargs):
        """
        Loggt eine Fehlermeldung.

        Args:
            message: Die zu loggende Nachricht
            **kwargs: Weitere Attribute für strukturierte Logs
        """
        self.logger.error(message)
        config.structured_log("ERROR", message, **kwargs)

    def warning(self, message, **kwargs):
        """
        Loggt eine Warnung.

        Args:
            message: Die zu loggende Nachricht
            **kwargs: Weitere Attribute für strukturierte Logs
        """
        self.logger.warning(message)
        config.structured_log("WARNING", message, **kwargs)

    def debug(self, message, **kwargs):
        """
        Loggt eine Debug-Nachricht.

        Args:
            message: Die zu loggende Nachricht
            **kwargs: Weitere Attribute für strukturierte Logs
        """
        self.logger.debug(message)
        config.structured_log("DEBUG", message, **kwargs)

    @staticmethod
    def structured_log(level, message, session_id=None, component=None, **extra):
        """
        Erzeugt strukturierte Logs im JSON-Format.

        Args:
            level: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Die zu loggende Nachricht
            session_id: Session-ID (optional)
            component: Komponente (optional)
            **extra: Weitere Attribute für das Log
        """
        config.structured_log(level, message, session_id=session_id, component=component, **extra)

    @staticmethod
    def track_session_progress(session_id, progress_percent, message, stage="processing"):
        """
        Session-Fortschritt aktualisieren mit Logging.

        Args:
            session_id: Session-ID
            progress_percent: Fortschritt in Prozent
            message: Fortschrittsnachricht
            stage: Verarbeitungsstufe
        """
        config.track_session_progress(session_id, progress_percent, message, stage)

    @staticmethod
    def track_error(session_id, error_type, message, trace=None, diagnostics=None):
        """
        Fehler mit strukturiertem Logging und Redis-Speicherung.

        Args:
            session_id: Session-ID
            error_type: Fehlertyp
            message: Fehlermeldung
            trace: Stacktrace (optional)
            diagnostics: Diagnosedaten (optional)
        """
        # Wenn kein Trace angegeben wurde, aktuellen Stacktrace verwenden
        if trace is None:
            trace = traceback.format_exc()

        config.track_error(session_id, error_type, message, trace, diagnostics)

    @staticmethod
    def log_openai_request(session_id, model, system_preview, prompt_preview, tokens_in=None):
        """
        OpenAI-Anfrage in strukturiertem Format loggen.

        Args:
            session_id: Session-ID
            model: Modellname
            system_preview: System-Nachricht
            prompt_preview: Prompt-Text
            tokens_in: Anzahl der Input-Tokens (optional)
        """
        config.structured_log(
            "INFO",
            f"OpenAI Anfrage: Session {session_id}, Modell {model}",
            session_id=session_id,
            component="openai_client",
            model=model,
            system_preview=system_preview[:150] + "..." if len(system_preview) > 150 else system_preview,
            prompt_preview=prompt_preview[:150] + "..." if len(prompt_preview) > 150 else prompt_preview,
            tokens_in=tokens_in
        )

    @staticmethod
    def log_openai_response(session_id, response_preview, tokens_out=None, duration_ms=None):
        """
        OpenAI-Antwort in strukturiertem Format loggen.

        Args:
            session_id: Session-ID
            response_preview: Antworttext
            tokens_out: Anzahl der Output-Tokens (optional)
            duration_ms: Dauer in Millisekunden (optional)
        """
        config.structured_log(
            "INFO",
            f"OpenAI Antwort: Session {session_id}",
            session_id=session_id,
            component="openai_client",
            response_preview=response_preview[:150] + "..." if len(response_preview) > 150 else response_preview,
            tokens_out=tokens_out,
            duration_ms=duration_ms
        )

    @staticmethod
    def debug_openai_api(enable=True):
        """
        Aktiviert oder deaktiviert das ausführliche DEBUG-Logging für die OpenAI API.

        Args:
            enable: True, um Debug-Logging zu aktivieren, False, um es zu deaktivieren
        """
        import os

        from core.redis_client import redis_client

        # OpenAI API Logger konfigurieren
        openai_logger = config.get_logger('api.openai_client')
        openai_logger.setLevel(logging.DEBUG if enable else logging.INFO)

        # Python-OpenAI Bibliothek Logger konfigurieren
        openai_lib_logger = config.get_logger('openai')
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
