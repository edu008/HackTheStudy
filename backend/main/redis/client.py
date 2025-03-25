"""
Redis-Client-Funktionen für den API-Container.
Bietet eine einheitliche Schnittstelle für Redis-Operationen.
"""

import os
import json
import logging
from typing import Any, Dict, Optional, Union
import redis as redis_lib

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Redis-Client als Singleton
_redis_client = None

def get_redis_client() -> redis_lib.Redis:
    """
    Gibt einen Redis-Client zurück. 
    Erstellt ihn bei Bedarf neu und speichert ihn als Singleton.
    
    Returns:
        Redis-Client-Instanz
    """
    global _redis_client
    
    if _redis_client is None:
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        _redis_client = redis_lib.from_url(redis_url)
        logger.info(f"Redis-Client initialisiert mit URL: {redis_url}")
    
    return _redis_client

def safe_redis_get(key: str, default: Any = None, as_json: bool = False) -> Any:
    """
    Liest einen Wert aus Redis und behandelt Fehler.
    
    Args:
        key: Redis-Schlüssel
        default: Standardwert, falls Schlüssel nicht existiert
        as_json: Falls True, wird der Wert als JSON interpretiert
    
    Returns:
        Wert aus Redis oder default
    """
    try:
        client = get_redis_client()
        value = client.get(key)
        
        if value is None:
            return default
        
        # Decodieren
        value_str = value.decode('utf-8')
        
        # Als JSON interpretieren, falls gewünscht
        if as_json:
            try:
                return json.loads(value_str)
            except json.JSONDecodeError:
                logger.warning(f"Konnte Redis-Wert für Schlüssel {key} nicht als JSON interpretieren")
                return default
        
        return value_str
    except Exception as e:
        logger.error(f"Fehler beim Lesen aus Redis (Schlüssel: {key}): {str(e)}")
        return default

def safe_redis_set(key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> bool:
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
    try:
        client = get_redis_client()
        
        # Wert serialisieren, falls nötig
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        
        # In Redis schreiben
        result = client.set(key, value, ex=ex, nx=nx)
        return result is not None
    except Exception as e:
        logger.error(f"Fehler beim Schreiben in Redis (Schlüssel: {key}): {str(e)}")
        return False

def log_debug_info(session_id: str, message: str, **kwargs) -> None:
    """
    Speichert Debug-Informationen für eine Session in Redis.
    
    Args:
        session_id: ID der Session
        message: Debug-Nachricht
        **kwargs: Weitere Debug-Informationen
    """
    try:
        from datetime import datetime
        
        debug_info = {
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        
        client = get_redis_client()
        
        # Liste mit Debug-Informationen aktualisieren
        key = f"debug_info:{session_id}"
        
        # Bestehende Liste holen
        existing_info = safe_redis_get(key, as_json=True)
        if existing_info is None:
            existing_info = []
        
        # Neue Info hinzufügen
        existing_info.append(debug_info)
        
        # Zurück in Redis schreiben
        safe_redis_set(key, existing_info, ex=86400)  # 24 Stunden TTL
        
    except Exception as e:
        logger.error(f"Fehler beim Protokollieren von Debug-Informationen: {str(e)}") 