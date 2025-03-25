"""
Session-Management für den Worker-Microservice
"""
import logging
import time
from redis import get_redis_client, safe_redis_set, safe_redis_get

# Logger konfigurieren
logger = logging.getLogger(__name__)

def acquire_session_lock(session_id, lock_timeout=300):
    """
    Erwirbt einen Lock für eine bestimmte Session, um mehrfache Verarbeitung zu verhindern.
    
    Args:
        session_id: Die Session-ID
        lock_timeout: Timeout in Sekunden, nach dem der Lock automatisch abläuft
        
    Returns:
        bool: True, wenn der Lock erfolgreich erworben wurde, False sonst
    """
    if not session_id:
        logger.error("Leere Session-ID beim Versuch, einen Lock zu erwerben")
        return False
    
    redis_client = get_redis_client()
    lock_key = f"session_lock:{session_id}"
    
    try:
        # Versuche den Lock zu erwerben mit "SET NX" (nur setzen, wenn nicht existiert)
        lock_acquired = redis_client.set(
            lock_key, 
            str(time.time()), 
            nx=True, 
            ex=lock_timeout
        )
        
        if lock_acquired:
            logger.info(f"Lock für Session {session_id} erfolgreich erworben (Timeout: {lock_timeout}s)")
            # Speichere zusätzliche Informationen zum Lock
            safe_redis_set(
                f"session_lock_info:{session_id}", 
                {
                    "acquired_at": time.time(),
                    "timeout": lock_timeout,
                    "expires_at": time.time() + lock_timeout
                },
                ex=lock_timeout
            )
            return True
        else:
            # Prüfe den bestehenden Lock
            lock_time = safe_redis_get(lock_key)
            try:
                lock_time = float(lock_time) if lock_time else 0
                lock_age = time.time() - lock_time
                logger.warning(f"Konnte Lock für Session {session_id} nicht erwerben - bereits gesperrt vor {lock_age:.1f}s")
            except (ValueError, TypeError):
                logger.warning(f"Konnte Lock für Session {session_id} nicht erwerben - ungültiger Lock-Wert")
            
            return False
    except Exception as e:
        logger.error(f"Fehler beim Erwerben des Locks für Session {session_id}: {str(e)}")
        return False

def release_session_lock(session_id):
    """
    Gibt einen erworbenen Lock für eine Session frei.
    
    Args:
        session_id: Die Session-ID
        
    Returns:
        bool: True, wenn der Lock erfolgreich freigegeben wurde, False sonst
    """
    if not session_id:
        logger.error("Leere Session-ID beim Versuch, einen Lock freizugeben")
        return False
    
    redis_client = get_redis_client()
    lock_key = f"session_lock:{session_id}"
    lock_info_key = f"session_lock_info:{session_id}"
    
    try:
        # Prüfe, ob der Lock existiert
        lock_exists = redis_client.exists(lock_key)
        
        if lock_exists:
            # Lösche den Lock und die Info
            redis_client.delete(lock_key)
            redis_client.delete(lock_info_key)
            logger.info(f"Lock für Session {session_id} erfolgreich freigegeben")
            return True
        else:
            logger.warning(f"Kein Lock zum Freigeben für Session {session_id} gefunden")
            return False
    except Exception as e:
        logger.error(f"Fehler beim Freigeben des Locks für Session {session_id}: {str(e)}")
        return False

def check_session_lock(session_id):
    """
    Prüft, ob ein Lock für eine Session existiert.
    
    Args:
        session_id: Die Session-ID
        
    Returns:
        bool: True, wenn ein Lock existiert, False sonst
    """
    if not session_id:
        return False
    
    redis_client = get_redis_client()
    lock_key = f"session_lock:{session_id}"
    
    try:
        return bool(redis_client.exists(lock_key))
    except Exception as e:
        logger.error(f"Fehler beim Prüfen des Locks für Session {session_id}: {str(e)}")
        return False 