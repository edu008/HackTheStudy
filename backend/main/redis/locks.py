"""
Redis-basierte Locking-Mechanismen für koordinierten Zugriff.
"""

import time
import uuid
import logging
import functools
from typing import Any, Callable, Optional
from contextlib import contextmanager

from .client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

def acquire_lock(lock_name: str, timeout: int = 60, blocking: bool = True, blocking_timeout: int = 10) -> Optional[str]:
    """
    Erwirbt einen verteilten Lock mit Redis.
    
    Args:
        lock_name: Name des Locks
        timeout: Gültigkeitsdauer des Locks in Sekunden
        blocking: Falls True, wartet die Funktion, bis der Lock verfügbar ist
        blocking_timeout: Maximale Wartezeit in Sekunden bei blocking=True
    
    Returns:
        Lock-Token bei Erfolg, None bei Fehler oder Timeout
    """
    client = get_redis_client()
    
    # Generiere eindeutiges Token für diesen Lock
    token = str(uuid.uuid4())
    lock_key = f"lock:{lock_name}"
    
    # Versuche, den Lock zu erwerben
    start_time = time.time()
    
    while True:
        # Setze den Lock nur, wenn er noch nicht existiert
        acquired = client.set(lock_key, token, ex=timeout, nx=True)
        
        if acquired:
            logger.debug(f"Lock '{lock_name}' erworben mit Token {token}")
            return token
        
        if not blocking:
            logger.debug(f"Lock '{lock_name}' nicht verfügbar und nicht-blockierend")
            return None
        
        # Prüfe Timeout
        if time.time() - start_time > blocking_timeout:
            logger.warning(f"Timeout beim Erwerben von Lock '{lock_name}' (nach {blocking_timeout}s)")
            return None
        
        # Warte kurz und versuche es erneut
        time.sleep(0.1)

def release_lock(lock_name: str, token: str) -> bool:
    """
    Gibt einen verteilten Lock frei.
    
    Args:
        lock_name: Name des Locks
        token: Das beim Erwerb zurückgegebene Token
    
    Returns:
        True bei Erfolg, False wenn der Lock nicht existiert oder falsch ist
    """
    client = get_redis_client()
    lock_key = f"lock:{lock_name}"
    
    # Atomare Überprüfung und Löschen (nur, wenn der Token übereinstimmt)
    lua_script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """
    
    # Lua-Script ausführen
    try:
        result = client.eval(lua_script, 1, lock_key, token)
        success = bool(result)
        
        if success:
            logger.debug(f"Lock '{lock_name}' freigegeben mit Token {token}")
        else:
            logger.warning(f"Lock '{lock_name}' konnte nicht freigegeben werden (falscher Token oder nicht existent)")
        
        return success
    except Exception as e:
        logger.error(f"Fehler beim Freigeben des Locks '{lock_name}': {str(e)}")
        return False

@contextmanager
def with_redis_lock(lock_name: str, timeout: int = 60, blocking: bool = True, blocking_timeout: int = 10):
    """
    Context-Manager für Redis-Locks.
    
    Args:
        lock_name: Name des Locks
        timeout: Gültigkeitsdauer des Locks in Sekunden
        blocking: Falls True, wartet die Funktion, bis der Lock verfügbar ist
        blocking_timeout: Maximale Wartezeit in Sekunden bei blocking=True
    
    Raises:
        TimeoutError: Wenn der Lock nicht erworben werden konnte
    """
    token = acquire_lock(lock_name, timeout, blocking, blocking_timeout)
    
    if not token:
        raise TimeoutError(f"Konnte Lock '{lock_name}' nicht erwerben")
    
    try:
        yield token
    finally:
        release_lock(lock_name, token)

def with_lock(lock_name_or_func: str = None, timeout: int = 60, blocking: bool = True, blocking_timeout: int = 10):
    """
    Dekorator für Redis-Locks. Kann auf zwei Arten verwendet werden:
    
    1. Mit Lock-Namen:
       @with_lock("my_lock")
       def my_function():
           ...
    
    2. Ohne Lock-Namen (verwendet Funktionsnamen):
       @with_lock
       def my_function():
           ...
    
    Args:
        lock_name_or_func: Name des Locks oder die dekorierte Funktion
        timeout: Gültigkeitsdauer des Locks in Sekunden
        blocking: Falls True, wartet die Funktion, bis der Lock verfügbar ist
        blocking_timeout: Maximale Wartezeit in Sekunden bei blocking=True
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Bestimme Lock-Namen
            lock_name = lock_name_or_func if isinstance(lock_name_or_func, str) else func.__name__
            
            # Verwende with_redis_lock als Context-Manager
            with with_redis_lock(lock_name, timeout, blocking, blocking_timeout):
                return func(*args, **kwargs)
        return wrapper
    
    # Unterscheide zwischen direktem Dekorator und Dekorator mit Parametern
    if callable(lock_name_or_func):
        # @with_lock ohne Parameter
        func = lock_name_or_func
        lock_name_or_func = func.__name__
        return decorator(func)
    else:
        # @with_lock("name") oder @with_lock()
        return decorator 