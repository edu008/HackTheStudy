"""
Logging-Konfiguration für die Anwendung.
Vereinfachter Wrapper für die zentrale Konfiguration in config.py.
"""

import logging
from typing import Optional

# Importiere die zentrale Konfiguration
from config.config import config


def setup_logging() -> logging.Logger:
    """
    Konfiguriert das Logging-System für die Anwendung.
    Delegiert an die zentrale Konfiguration.

    Returns:
        Logger-Instanz
    """
    return config.setup_logging()


def get_logger(name: str) -> logging.Logger:
    """
    Gibt einen konfigurierten Logger zurück.

    Args:
        name: Name des Loggers

    Returns:
        Logger-Instanz
    """
    return config.get_logger(name)


def structured_log(level: str, message: str, **kwargs):
    """
    Erzeugt strukturierte Logs im JSON-Format.

    Args:
        level: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log-Nachricht
        **kwargs: Weitere Attribute für das Log
    """
    config.structured_log(level, message, **kwargs)


def force_flush_handlers():
    """
    Erzwingt das Leeren aller Log-Handler-Puffer.
    Nützlich vor einem geordneten Shutdown.
    """
    config.force_flush_handlers()
