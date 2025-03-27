"""
Redis-Client-Schnittstelle für den Worker-Microservice.
Stellt vereinfachte Funktionen zur Verfügung, die mit Redis interagieren.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Union

from redis_utils.client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

def set_key(key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
    """
    Setzt einen Wert in Redis.
    
    Args:
        key: Redis-Schlüssel
        value: Zu speichernder Wert (wird automatisch in JSON umgewandelt, wenn nötig)
        expire_seconds: Time-to-Live in Sekunden (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        client = get_redis_client()
        
        # Wert serialisieren, falls nötig
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value)
            
        # In Redis speichern
        result = client.set(key, value, ex=expire_seconds)
        
        return result is not None
    except Exception as e:
        logger.error(f"Fehler beim Speichern in Redis ({key}): {str(e)}")
        return False

def get_key(key: str, default: Any = None, as_json: bool = False) -> Any:
    """
    Holt einen Wert aus Redis.
    
    Args:
        key: Redis-Schlüssel
        default: Standardwert, falls Schlüssel nicht existiert
        as_json: Ob der Wert als JSON interpretiert werden soll
    
    Returns:
        Wert aus Redis oder default
    """
    try:
        client = get_redis_client()
        value = client.get(key)
        
        if value is None:
            return default
            
        # Als JSON interpretieren, falls gewünscht
        if as_json and isinstance(value, (str, bytes)):
            try:
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Konnte Redis-Wert für Schlüssel {key} nicht als JSON interpretieren")
                return default
        
        # Bytes in String umwandeln
        if isinstance(value, bytes):
            value = value.decode('utf-8')
            
        return value
    except Exception as e:
        logger.error(f"Fehler beim Lesen aus Redis ({key}): {str(e)}")
        return default

def delete_key(key: str) -> bool:
    """
    Löscht einen Schlüssel aus Redis.
    
    Args:
        key: Redis-Schlüssel
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        client = get_redis_client()
        result = client.delete(key)
        return result > 0
    except Exception as e:
        logger.error(f"Fehler beim Löschen aus Redis ({key}): {str(e)}")
        return False

def exists_key(key: str) -> bool:
    """
    Prüft, ob ein Schlüssel in Redis existiert.
    
    Args:
        key: Redis-Schlüssel
    
    Returns:
        True, wenn der Schlüssel existiert, sonst False
    """
    try:
        client = get_redis_client()
        result = client.exists(key)
        return result > 0
    except Exception as e:
        logger.error(f"Fehler beim Prüfen der Existenz in Redis ({key}): {str(e)}")
        return False

def increment_key(key: str, amount: int = 1) -> Optional[int]:
    """
    Inkrementiert einen Zählerwert in Redis.
    
    Args:
        key: Redis-Schlüssel
        amount: Zu inkrementierender Betrag
    
    Returns:
        Neuer Wert nach Inkrementierung oder None bei Fehler
    """
    try:
        client = get_redis_client()
        result = client.incrby(key, amount)
        return result
    except Exception as e:
        logger.error(f"Fehler beim Inkrementieren in Redis ({key}): {str(e)}")
        return None

def add_to_list(list_key: str, value: Any) -> bool:
    """
    Fügt einen Wert zu einer Redis-Liste hinzu.
    
    Args:
        list_key: Redis-Schlüssel für die Liste
        value: Hinzuzufügender Wert (wird bei Bedarf in JSON umgewandelt)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        client = get_redis_client()
        
        # Wert serialisieren, falls nötig
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value)
        
        result = client.rpush(list_key, value)
        return result > 0
    except Exception as e:
        logger.error(f"Fehler beim Hinzufügen zur Liste ({list_key}): {str(e)}")
        return False

# Exportierte Funktionen
__all__ = [
    'set_key',
    'get_key',
    'delete_key',
    'exists_key',
    'increment_key',
    'add_to_list'
] 