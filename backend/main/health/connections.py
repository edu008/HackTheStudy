"""
Verbindungsprüfungen für das Health-Monitoring-System.
Enthält spezialisierte Funktionen zum Überprüfen der Verbindungen zu Datenbank, Redis und Celery.
"""

import json
import logging
import os
from typing import Optional, Tuple

# Logger konfigurieren
logger = logging.getLogger(__name__)


def get_redis_client():
    """
    Gibt einen Redis-Client zurück.
    Verwendet die zentrale RedisClient-Klasse aus dem Core-Modul.

    Returns:
        Redis-Client oder None bei Fehlern
    """
    try:
        from core.redis_client import get_redis_client as core_get_redis_client
        return core_get_redis_client()
    except ImportError:
        logger.warning("Konnte core.redis_client nicht importieren, versuche Fallback.")
        try:
            from redis import Redis
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            return Redis.from_url(redis_url, decode_responses=True, socket_timeout=3)
        except ImportError:
            logger.warning("Redis-Paket nicht installiert")
            return None
        except Exception as e:
            logger.error("Fehler beim Erstellen des Redis-Clients: %s", str(e))
            return None


def check_db_connection() -> Tuple[bool, str]:
    """
    Überprüft die Datenbankverbindung.

    Returns:
        Tuple: (ist_verbunden, status_nachricht)
    """
    try:
        # Import in der Funktion, um zirkuläre Imports zu vermeiden
        from core.models import check_db_connection as core_check_db_connection
        from flask import current_app

        # Wir benötigen einen Anwendungskontext für den Datenbankzugriff
        # Falls kein Anwendungskontext verfügbar ist, verwende einen temporären
        if current_app:
            return (core_check_db_connection(), "connected") if core_check_db_connection() else (False, "disconnected")
        else:
            # Fallback: Versuche, einen temporären Anwendungskontext zu erstellen
            try:
                from flask import Flask
                from config.config import config
                
                # Erstelle eine Mini-App nur für diesen Zweck
                app = Flask(__name__)
                app.config['SQLALCHEMY_DATABASE_URI'] = config.db_uri
                
                # Verwende den Anwendungskontext dieser App
                with app.app_context():
                    return (core_check_db_connection(), "connected") if core_check_db_connection() else (False, "disconnected")
            except Exception as temp_app_err:
                logger.error(f"Konnte keinen temporären Anwendungskontext erstellen: {str(temp_app_err)}")
                return False, f"error: {str(temp_app_err)}"
    except ImportError:
        logger.warning("Konnte core.models nicht importieren, versuche Fallback.")
        try:
            # Versuche, einen lokalen Anwendungskontext zu verwenden
            from flask import current_app, Flask
            from flask_sqlalchemy import SQLAlchemy
            from config.config import config
            
            # Wenn kein Anwendungskontext vorhanden ist, erstelle einen temporären
            if not current_app:
                app = Flask(__name__)
                app.config['SQLALCHEMY_DATABASE_URI'] = config.db_uri
                context = app.app_context()
                context.push()
            else:
                context = None
                
            try:
                db = SQLAlchemy(current_app)
                db.session.execute("SELECT 1")
                return True, "connected"
            finally:
                # Pop den temporären Kontext, falls wir einen erstellt haben
                if context:
                    context.pop()
        except Exception as e:
            return False, f"error: {str(e)}"


def check_redis_connection() -> Tuple[bool, str]:
    """
    Überprüft die Redis-Verbindung.

    Returns:
        Tuple: (ist_verbunden, status_nachricht)
    """
    try:
        redis_client = get_redis_client()
        if redis_client and redis_client.ping():
            return True, "connected"
        return False, "disconnected"
    except Exception as e:
        return False, f"error: {str(e)}"


def check_celery_connection() -> Tuple[bool, str]:
    """
    Überprüft die Celery-Verbindung.

    Returns:
        Tuple: (ist_verbunden, status_nachricht)
    """
    try:
        from tasks import celery_app

        if celery_app.connection().connected:
            return True, "connected"
        return False, "disconnected"
    except ImportError:
        return False, "unavailable"
    except Exception as e:
        return False, f"error: {str(e)}"


def store_health_in_redis(health_data: dict) -> bool:
    """
    Speichert Health-Daten in Redis für Worker-Zugriff.

    Args:
        health_data: Die zu speichernden Health-Daten

    Returns:
        bool: True bei Erfolg, sonst False
    """
    try:
        from core.redis_client import set_in_redis

        return set_in_redis(
            "health:api",
            health_data,
            ex=60  # 1 Minute TTL
        )
    except ImportError:
        # Fallback für den Fall, dass core.redis_client nicht importiert werden kann
        redis_client = get_redis_client()
        if redis_client:
            try:
                value = json.dumps(health_data)
                redis_client.set("health:api", value, ex=60)
                return True
            except Exception as e:
                logger.warning("Fehler beim JSON-Serialisieren von Health-Daten: %s", str(e))
                return False
        return False
    except Exception as e:
        logger.warning("Konnte Health-Status nicht in Redis speichern: %s", str(e))
        return False
