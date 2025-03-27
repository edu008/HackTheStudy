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
        # Wenn Instanz bereits existiert, direkt zurückgeben
        if cls._redis_instance is not None:
            return cls._redis_instance

        # Redis-URL ermitteln
        try:
            # Importiere Konfiguration nur wenn nötig, um zirkuläre Importe zu vermeiden
            from config.config import config
            redis_url = config.redis_url
        except ImportError:
            # Fallback, wenn die Config nicht verfügbar ist
            redis_url = os.environ.get('REDIS_URL', cls._default_redis_url)

        # Versuche echten Redis-Client zu erstellen
        try:
            cls._redis_instance = redis_lib.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=3,
                socket_keepalive=True,
                health_check_interval=30
            )
            # Teste die Verbindung
            cls._redis_instance.ping()
            logger.info("Redis-Client erfolgreich initialisiert mit URL: %s", redis_url)
            
        # Bei Fehler Dummy-Client erstellen
        except Exception as e:
            logger.error("Fehler beim Initialisieren des Redis-Clients (%s): %s", redis_url, str(e))

            # Erstelle einen Dummy-Redis-Client für Fehlertoleranz
            class DummyRedis:
                def __init__(self, *args, **kwargs):
                    self.data = {}  # In-Memory-Speicher für Dummy-Operationen

                def ping(self):
                    logger.warning("DummyRedis.ping() aufgerufen")
                    return True

                def get(self, key):
                    logger.warning("DummyRedis.get(%s) aufgerufen", key)
                    return self.data.get(key)

                def set(self, key, value, *args, **kwargs):
                    logger.warning("DummyRedis.set(%s) aufgerufen", key)
                    self.data[key] = value
                    return True

                def delete(self, key):
                    logger.warning("DummyRedis.delete(%s) aufgerufen", key)
                    if key in self.data:
                        del self.data[key]
                        return 1
                    return 0

                def exists(self, key):
                    logger.warning("DummyRedis.exists(%s) aufgerufen", key)
                    return key in self.data

                def incr(self, key, amount=1):
                    logger.warning("DummyRedis.incr(%s, %s) aufgerufen", key, amount)
                    self.data[key] = int(self.data.get(key, 0)) + amount
                    return self.data[key]

                def incrby(self, key, amount=1):
                    # Rufe die incr-Methode auf, kein eigener return nötig da diese bereits einen Wert zurückgibt
                    return self.incr(key, amount)

                def __getattr__(self, name):
                    def dummy_method(*args, **kwargs):
                        logger.warning("DummyRedis.%s() aufgerufen", name)
                        return None
                    return dummy_method

            cls._redis_instance = DummyRedis()
            logger.warning("⚠️ Dummy-Redis wird verwendet! Redis-Funktionalität ist eingeschränkt.")

        # Fertig initialisierte Instanz zurückgeben
        return cls._redis_instance

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
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning("Zugriff auf nicht-OpenAI-Cache-Schlüssel verweigert: %s", key)
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
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning("Schreiben auf nicht-OpenAI-Cache-Schlüssel verweigert: %s", key)
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
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning("Löschen von nicht-OpenAI-Cache-Schlüssel verweigert: %s", key)
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
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning("Existenzprüfung für nicht-OpenAI-Cache-Schlüssel verweigert: %s", key)
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
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning("Inkrementieren von nicht-OpenAI-Cache-Schlüssel verweigert: %s", key)
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
