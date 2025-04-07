"""
Zentraler Redis-Client für alle Komponenten des Main-Containers.
Bietet eine einheitliche Schnittstelle für alle Redis-Operationen.
Nur für OpenAI-Cache verwendet.
"""

import json
import logging
import os
import time
import uuid
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

# Direkter Import von Redis, um Abhängigkeiten zu reduzieren
import redis as redis_lib

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Redis-Konfiguration
REDIS_HOST = os.environ.get('REDIS_HOST', 'main')  # Verwende 'main' statt 'redis'
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', 'hackthestudy_redis_password')
REDIS_URL = os.environ.get('REDIS_URL', f"redis://:hackthestudy_redis_password@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

# Singleton-Redis-Client
_redis_client = None


class RedisClient:
    """
    Vereinfachte, zentrale Schnittstelle für alle Redis-Operationen.
    Implementiert als Singleton-Klasse mit statischen Methoden für einfachen Zugriff.
    """
    
    # Klassenattribute statt globaler Variablen
    _redis_instance = None
    _default_redis_url = 'redis://localhost:6379/0'
    _default_lock_expiry = 10  # Sekunden
    _default_lock_retry = 3
    _default_cache_ttl = 3600  # 1 Stunde

    @classmethod
    def get_client(cls) -> redis_lib.Redis:
        """
        Gibt den Redis-Client zurück oder erstellt ihn, falls er noch nicht existiert.

        Returns:
            Redis-Client-Instanz
        """
        global _redis_client
        if _redis_client is None:
            try:
                # Verwende Redis-URL mit Authentifizierung
                logger.info(f"Versuche Redis-Verbindung zu {REDIS_URL}")
                _redis_client = redis_lib.from_url(REDIS_URL)
                
                # Teste die Verbindung
                _redis_client.ping()
                logger.info(f"Redis-Verbindung erfolgreich hergestellt zu {REDIS_URL}")
            except redis_lib.ConnectionError as e:
                logger.error(f"Fehler beim Verbinden mit Redis: {str(e)}")
                logger.info("Versuche alternative Verbindungsmethode...")
                
                # Alternatives Verbindungsverfahren
                try:
                    _redis_client = redis_lib.Redis(
                        host=REDIS_HOST,
                        port=REDIS_PORT,
                        db=REDIS_DB,
                        password=REDIS_PASSWORD,
                        decode_responses=False,
                        socket_timeout=5
                    )
                    _redis_client.ping()
                    logger.info(f"Alternative Redis-Verbindung erfolgreich hergestellt zu {REDIS_HOST}:{REDIS_PORT}")
                except Exception as alt_e:
                    logger.error(f"Alle Redis-Verbindungsversuche fehlgeschlagen: {str(alt_e)}")
                    # Statt None zurückzugeben, werfen wir eine Exception oder verwenden einen Mock
                    # Hier erstellen wir eine Dummy-Redis-Instanz für Entwicklung/Tests
                    if os.environ.get('FLASK_ENV') == 'development':
                        from fakeredis import FakeRedis
                        logger.warning("Verwende FakeRedis für Entwicklungsumgebung")
                        _redis_client = FakeRedis()
                    else:
                        # In Produktion sollte der Fehler weitergegeben werden
                        raise
        
        return _redis_client

    @classmethod
    def get(cls, key: str, default: Any = None, as_json: bool = False) -> Any:
        """
        Liest einen Wert aus Redis und behandelt Fehler.

        Args:
            key: Redis-Schlüssel
            default: Standardwert, falls Schlüssel nicht existiert
            as_json: Falls True, wird der Wert als JSON interpretiert

        Returns:
            Wert aus Redis oder default
        """
        # Nur erlaubte Schlüssel zulassen
        if not (key.startswith('openai:') or key.startswith('processing:') or key.startswith('health:')):
            logger.warning("Zugriff auf nicht erlaubten Schlüssel verweigert: %s", key)
            return default

        try:
            client = cls.get_client()
            value = client.get(key)

            if value is None:
                return default

            # Als JSON interpretieren, falls gewünscht
            if as_json and isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    logger.warning("Konnte Redis-Wert für Schlüssel %s nicht als JSON interpretieren", key)
                    return default

            return value
        except Exception as e:
            logger.error("Fehler beim Lesen aus Redis (Schlüssel: %s): %s", key, str(e))
            return default

    @classmethod
    def set(cls, key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> bool:
        """
        Schreibt einen Wert in Redis und behandelt Fehler.

        Args:
            key: Redis-Schlüssel
            value: Zu speichernder Wert (String, Dict oder Liste)
            ex: Time-to-Live in Sekunden (optional)
            nx: Falls True, Wert nur setzen, wenn Schlüssel nicht existiert

        Returns:
            True bei Erfolg, False bei Fehler
        """
        # Nur erlaubte Schlüssel zulassen
        if not (key.startswith('openai:') or key.startswith('processing:') or key.startswith('health:')):
            logger.warning("Schreiben auf nicht erlaubten Schlüssel verweigert: %s", key)
            return False

        try:
            client = cls.get_client()

            # Wert serialisieren, falls nötig
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            # In Redis schreiben
            result = client.set(key, value, ex=ex, nx=nx)
            return result is not None
        except Exception as e:
            logger.error("Fehler beim Schreiben in Redis (Schlüssel: %s): %s", key, str(e))
            return False

    @classmethod
    def delete(cls, key: str) -> bool:
        """
        Löscht einen Schlüssel aus Redis.

        Args:
            key: Redis-Schlüssel

        Returns:
            True bei Erfolg, False bei Fehler
        """
        # Nur erlaubte Schlüssel zulassen
        if not (key.startswith('openai:') or key.startswith('processing:') or key.startswith('health:')):
            logger.warning("Löschen von nicht erlaubtem Schlüssel verweigert: %s", key)
            return False

        try:
            client = cls.get_client()
            return client.delete(key) > 0
        except Exception as e:
            logger.error("Fehler beim Löschen aus Redis (Schlüssel: %s): %s", key, str(e))
            return False

    @classmethod
    def exists(cls, key: str) -> bool:
        """
        Prüft, ob ein Schlüssel existiert.

        Args:
            key: Redis-Schlüssel

        Returns:
            True, wenn der Schlüssel existiert, sonst False
        """
        # Nur erlaubte Schlüssel zulassen
        if not (key.startswith('openai:') or key.startswith('processing:') or key.startswith('health:')):
            logger.warning("Existenzprüfung für nicht erlaubten Schlüssel verweigert: %s", key)
            return False

        try:
            client = cls.get_client()
            return client.exists(key) > 0
        except Exception as e:
            logger.error("Fehler beim Prüfen der Existenz in Redis (Schlüssel: %s): %s", key, str(e))
            return False

    @classmethod
    def increment(cls, key: str, amount: int = 1) -> Optional[int]:
        """
        Inkrementiert einen Zähler in Redis.

        Args:
            key: Redis-Schlüssel
            amount: Wert, um den inkrementiert werden soll

        Returns:
            Neuer Wert oder None bei Fehler
        """
        # Nur erlaubte Schlüssel zulassen
        if not (key.startswith('openai:') or key.startswith('processing:') or key.startswith('health:')):
            logger.warning("Inkrementieren von nicht erlaubtem Schlüssel verweigert: %s", key)
            return None

        try:
            client = cls.get_client()
            return client.incrby(key, amount)
        except Exception as e:
            logger.error("Fehler beim Inkrementieren in Redis (Schlüssel: %s): %s", key, str(e))
            return None


# Singleton-Instanz für einfachen Zugriff
redis_client = RedisClient()

# Funktionen für Abwärtskompatibilität
get_redis_client = RedisClient.get_client
get_from_redis = RedisClient.get
set_in_redis = RedisClient.set

# Exports für Import aus anderen Modulen
__all__ = [
    'redis_client', 'RedisClient',
    'get_redis_client', 'get_from_redis', 'set_in_redis'
]
