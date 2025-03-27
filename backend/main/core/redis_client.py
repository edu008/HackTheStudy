"""
Zentraler Redis-Client für alle Komponenten des Main-Containers.
Bietet eine einheitliche Schnittstelle für alle Redis-Operationen.
Nur für OpenAI-Cache verwendet.
"""

import os
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps

# Direkter Import von Redis, um Abhängigkeiten zu reduzieren
import redis as redis_lib

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Singleton-Instanz
_redis_client = None

# Standardwerte für Redis-Konfiguration
DEFAULT_REDIS_URL = 'redis://localhost:6379/0'
DEFAULT_LOCK_EXPIRY = 10  # Sekunden
DEFAULT_LOCK_RETRY = 3
DEFAULT_CACHE_TTL = 3600  # 1 Stunde


class RedisClient:
    """
    Vereinfachte, zentrale Schnittstelle für alle Redis-Operationen.
    Implementiert als Singleton-Klasse mit statischen Methoden für einfachen Zugriff.
    """
    
    @staticmethod
    def get_client() -> redis_lib.Redis:
        """
        Gibt den Redis-Client zurück oder erstellt ihn, falls er noch nicht existiert.
        
        Returns:
            Redis-Client-Instanz
        """
        global _redis_client
        
        if _redis_client is None:
            try:
                # Importiere Konfiguration nur wenn nötig, um zirkuläre Importe zu vermeiden
                from config.config import config
                redis_url = config.redis_url
            except ImportError:
                # Fallback, wenn die Config nicht verfügbar ist
                redis_url = os.environ.get('REDIS_URL', DEFAULT_REDIS_URL)
            
            try:
                _redis_client = redis_lib.from_url(
                    redis_url, 
                    decode_responses=True,
                    socket_timeout=3,
                    socket_keepalive=True,
                    health_check_interval=30
                )
                # Teste die Verbindung
                _redis_client.ping()
                logger.info(f"Redis-Client erfolgreich initialisiert mit URL: {redis_url}")
            except Exception as e:
                logger.error(f"Fehler beim Initialisieren des Redis-Clients ({redis_url}): {str(e)}")
                
                # Erstelle einen Dummy-Redis-Client für Fehlertoleranz
                class DummyRedis:
                    def __init__(self, *args, **kwargs):
                        self.data = {}  # In-Memory-Speicher für Dummy-Operationen
                        
                    def ping(self):
                        logger.warning("DummyRedis.ping() aufgerufen")
                        return True
                        
                    def get(self, key):
                        logger.warning(f"DummyRedis.get({key}) aufgerufen")
                        return self.data.get(key)
                        
                    def set(self, key, value, *args, **kwargs):
                        logger.warning(f"DummyRedis.set({key}) aufgerufen")
                        self.data[key] = value
                        return True
                        
                    def delete(self, key):
                        logger.warning(f"DummyRedis.delete({key}) aufgerufen")
                        if key in self.data:
                            del self.data[key]
                            return 1
                        return 0
                        
                    def exists(self, key):
                        logger.warning(f"DummyRedis.exists({key}) aufgerufen")
                        return key in self.data
                        
                    def incr(self, key, amount=1):
                        logger.warning(f"DummyRedis.incr({key}, {amount}) aufgerufen")
                        self.data[key] = int(self.data.get(key, 0)) + amount
                        return self.data[key]
                    
                    def incrby(self, key, amount=1):
                        return self.incr(key, amount)
                    
                    def __getattr__(self, name):
                        def dummy_method(*args, **kwargs):
                            logger.warning(f"DummyRedis.{name}() aufgerufen")
                            return None
                        return dummy_method
                
                _redis_client = DummyRedis()
                logger.warning("⚠️ Dummy-Redis wird verwendet! Redis-Funktionalität ist eingeschränkt.")
        
        return _redis_client
    
    @staticmethod
    def get(key: str, default: Any = None, as_json: bool = False) -> Any:
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
            logger.warning(f"Zugriff auf nicht-OpenAI-Cache-Schlüssel verweigert: {key}")
            return default
            
        try:
            client = RedisClient.get_client()
            value = client.get(key)
            
            if value is None:
                return default
            
            # Als JSON interpretieren, falls gewünscht
            if as_json and isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(f"Konnte Redis-Wert für Schlüssel {key} nicht als JSON interpretieren")
                    return default
            
            return value
        except Exception as e:
            logger.error(f"Fehler beim Lesen aus Redis (Schlüssel: {key}): {str(e)}")
            return default
    
    @staticmethod
    def set(key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> bool:
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
            logger.warning(f"Schreiben auf nicht-OpenAI-Cache-Schlüssel verweigert: {key}")
            return False
            
        try:
            client = RedisClient.get_client()
            
            # Wert serialisieren, falls nötig
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            # In Redis schreiben
            result = client.set(key, value, ex=ex, nx=nx)
            return result is not None
        except Exception as e:
            logger.error(f"Fehler beim Schreiben in Redis (Schlüssel: {key}): {str(e)}")
            return False
    
    @staticmethod
    def delete(key: str) -> bool:
        """
        Löscht einen Schlüssel aus Redis.
        
        Args:
            key: Redis-Schlüssel
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning(f"Löschen von nicht-OpenAI-Cache-Schlüssel verweigert: {key}")
            return False
            
        try:
            client = RedisClient.get_client()
            return client.delete(key) > 0
        except Exception as e:
            logger.error(f"Fehler beim Löschen aus Redis (Schlüssel: {key}): {str(e)}")
            return False
    
    @staticmethod
    def exists(key: str) -> bool:
        """
        Prüft, ob ein Schlüssel existiert.
        
        Args:
            key: Redis-Schlüssel
        
        Returns:
            True, wenn der Schlüssel existiert, sonst False
        """
        # Nur OpenAI-Cache-Schlüssel erlauben
        if not key.startswith('openai:'):
            logger.warning(f"Existenzprüfung für nicht-OpenAI-Cache-Schlüssel verweigert: {key}")
            return False
            
        try:
            client = RedisClient.get_client()
            return client.exists(key) > 0
        except Exception as e:
            logger.error(f"Fehler beim Prüfen der Existenz in Redis (Schlüssel: {key}): {str(e)}")
            return False
    
    @staticmethod
    def increment(key: str, amount: int = 1) -> Optional[int]:
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
            logger.warning(f"Inkrementieren von nicht-OpenAI-Cache-Schlüssel verweigert: {key}")
            return None
            
        try:
            client = RedisClient.get_client()
            return client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Fehler beim Inkrementieren in Redis (Schlüssel: {key}): {str(e)}")
            return None

# Singleton-Instanz für einfachen Zugriff
redis_client = RedisClient()

# Einfache Aliase für Direktzugriff auf häufig verwendete Funktionen
get_redis_client = RedisClient.get_client
get_from_redis = RedisClient.get
set_in_redis = RedisClient.set

# Exports für Import aus anderen Modulen
__all__ = [
    'redis_client', 'RedisClient', 
    'get_redis_client', 'get_from_redis', 'set_in_redis'
] 