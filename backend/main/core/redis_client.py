"""
Redis-Client für die HackTheStudy Core-Komponenten.
Diese Datei bietet eine vereinfachte Schnittstelle für Redis-Operationen
und importiert die Hauptfunktionalität aus redis_utils.
"""

import logging
from typing import Any, Dict, List, Optional, Union
import json

# Importiere vorhandene Redis-Funktionen
from redis_utils.client import get_redis_client, safe_redis_get, safe_redis_set
from redis_utils.locks import acquire_lock, release_lock, with_redis_lock

# Logger konfigurieren
logger = logging.getLogger(__name__)

class RedisClient:
    """
    Vereinfachte Schnittstelle für Redis-Operationen.
    Dient als Wrapper um die redis_utils Funktionen.
    """
    
    @staticmethod
    def get_client():
        """Gibt den Redis-Client zurück"""
        return get_redis_client()
    
    @staticmethod
    def get(key: str, default: Any = None, as_json: bool = False) -> Any:
        """Wrapper um safe_redis_get"""
        return safe_redis_get(key, default, as_json)
    
    @staticmethod
    def set(key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> bool:
        """Wrapper um safe_redis_set"""
        return safe_redis_set(key, value, ex, nx)
    
    @staticmethod
    def delete(key: str) -> bool:
        """Löscht einen Schlüssel aus Redis"""
        try:
            client = get_redis_client()
            return client.delete(key) > 0
        except Exception as e:
            logger.error(f"Fehler beim Löschen aus Redis (Schlüssel: {key}): {str(e)}")
            return False
    
    @staticmethod
    def exists(key: str) -> bool:
        """Prüft, ob ein Schlüssel existiert"""
        try:
            client = get_redis_client()
            return client.exists(key) > 0
        except Exception as e:
            logger.error(f"Fehler beim Prüfen der Existenz in Redis (Schlüssel: {key}): {str(e)}")
            return False
    
    @staticmethod
    def acquire_lock(lock_name: str, expiry: int = 10, retry: int = 3) -> str:
        """Wrapper um acquire_lock aus redis_utils"""
        return acquire_lock(lock_name, expiry, retry)
    
    @staticmethod
    def release_lock(lock_name: str, lock_id: str) -> bool:
        """Wrapper um release_lock aus redis_utils"""
        return release_lock(lock_name, lock_id)
    
    @staticmethod
    def with_lock(lock_name: str, expiry: int = 10, retry: int = 3):
        """Decorator für with_redis_lock aus redis_utils"""
        return with_redis_lock(lock_name, expiry, retry)
    
    @staticmethod
    def increment(key: str, amount: int = 1) -> Optional[int]:
        """Inkrementiert einen Zähler in Redis"""
        try:
            client = get_redis_client()
            return client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Fehler beim Inkrementieren in Redis (Schlüssel: {key}): {str(e)}")
            return None

# Singleton-Instanz für einfachen Zugriff
redis_client = RedisClient()

# Exports für Import aus anderen Modulen
__all__ = ['redis_client', 'RedisClient'] 