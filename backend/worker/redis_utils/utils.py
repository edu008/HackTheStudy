"""
Redis-Hilfsfunktionen für sichere Operationen und Debugging
"""
import json
import logging
import traceback
from datetime import datetime
import time
from config import REDIS_TTL_DEFAULT, REDIS_TTL_SHORT

# Logger konfigurieren
logger = logging.getLogger(__name__)

def safe_redis_set(key, value, ex=REDIS_TTL_DEFAULT, redis_client=None):
    """
    Sichere Methode zum Setzen von Redis-Werten mit Fehlerbehandlung.
    
    Args:
        key: Der Redis-Schlüssel
        value: Der zu speichernde Wert (kann ein Objekt sein)
        ex: Ablaufzeit in Sekunden
        redis_client: Redis-Client-Instanz, falls nicht global verwendet
        
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    if not key:
        logger.error("Leerer Redis-Key übergeben")
        return False
    
    # Hole Redis-Client, falls nicht übergeben    
    if redis_client is None:
        from redis_utils.client import get_redis_client
        redis_client = get_redis_client()
        
    try:
        # Umwandeln von komplexen Typen in JSON
        if isinstance(value, (dict, list, tuple)):
            try:
                value = json.dumps(value)
            except (TypeError, ValueError) as json_err:
                logger.error(f"JSON-Serialisierungsfehler für Key {key}: {str(json_err)}")
                # Versuche eine einfachere String-Repräsentation
                value = str(value)
        
        # None-Werte als leeren String speichern
        if value is None:
            value = ""
            
        # Stelle sicher, dass der Wert ein String ist
        if not isinstance(value, (str, bytes, bytearray, memoryview)):
            value = str(value)
            
        # Setze den Wert mit Timeout
        redis_client.set(key, value, ex=ex)
        return True
    except Exception as e:
        logger.error(f"Redis-Fehler beim Setzen von {key}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def safe_redis_get(key, default=None, redis_client=None):
    """
    Sichere Methode zum Lesen von Redis-Werten mit Fehlerbehandlung.
    
    Args:
        key: Der Redis-Schlüssel
        default: Standardwert, falls der Schlüssel nicht existiert
        redis_client: Redis-Client-Instanz, falls nicht global verwendet
        
    Returns:
        Der Wert aus Redis oder der Standardwert
    """
    if not key:
        return default
    
    # Hole Redis-Client, falls nicht übergeben    
    if redis_client is None:
        from redis_utils.client import get_redis_client
        redis_client = get_redis_client()
        
    try:
        value = redis_client.get(key)
        if value is None:
            return default
            
        # Versuche JSON zu parsen
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Wenn kein JSON, gib den Rohwert zurück
            if isinstance(value, bytes):
                return value.decode('utf-8', errors='replace')
            return value
    except Exception as e:
        logger.error(f"Redis-Fehler beim Lesen von {key}: {str(e)}")
        return default

def log_debug_info(session_id, message, **extra_data):
    """
    Loggt Debug-Informationen sowohl in die Logs als auch nach Redis.
    
    Args:
        session_id: Die ID der Session
        message: Die zu loggende Nachricht
        **extra_data: Weitere Key-Value-Paare für die Debug-Info
    """
    if not session_id:
        logger.warning("log_debug_info aufgerufen ohne Session-ID")
        return
        
    # Hole Redis-Client   
    from redis_utils.client import get_redis_client
    redis_client = get_redis_client()
    
    # Schreibe zuerst ins Log
    logger.debug(f"[{session_id}] {message}")
    
    try:
        # Prüfe auf bestimmte Parameter und formatiere sie besser
        progress = extra_data.get("progress", 0)
        stage = extra_data.get("stage", "debug")
        
        # Speichere Debug-Info in Redis mit Zeitstempel
        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            **extra_data
        }
        
        # Verwende eine eindeutige Timestamp für jeden Debug-Eintrag
        timestamp = int(time.time() * 1000)  # Millisekunden für höhere Genauigkeit
        debug_key = f"debug:{session_id}:{timestamp}"
        
        # Speichere mit einer kürzeren Aufbewahrungszeit (1 Stunde)
        safe_redis_set(debug_key, debug_data, ex=REDIS_TTL_SHORT, redis_client=redis_client)
        
        # Halte eine Liste der letzten Debug-Einträge (max. 100)
        try:
            # Füge den neuen Key zur Liste hinzu
            debug_list_key = f"debug_list:{session_id}"
            redis_client.lpush(debug_list_key, debug_key)
            redis_client.ltrim(debug_list_key, 0, 99)  # Behalte nur die letzten 100 Einträge
            redis_client.expire(debug_list_key, REDIS_TTL_DEFAULT)
        except Exception as list_error:
            logger.debug(f"Fehler beim Aktualisieren der Debug-Liste: {str(list_error)}")
        
        # Aktualisiere den Fortschritt
        if progress > 0 or stage != "debug":
            progress_key = f"processing_progress:{session_id}"
            progress_data = {
                "progress": progress,
                "stage": stage,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            safe_redis_set(progress_key, progress_data, ex=REDIS_TTL_DEFAULT, redis_client=redis_client)
            
            # Aktualisiere auch den letzten Aktualisierungszeitstempel
            safe_redis_set(f"processing_last_update:{session_id}", str(time.time()), ex=REDIS_TTL_DEFAULT, redis_client=redis_client)
    except Exception as e:
        # Bei Fehlern in der Debug-Funktion nur loggen, aber nicht abbrechen
        logger.warning(f"Fehler beim Speichern von Debug-Infos: {str(e)}") 