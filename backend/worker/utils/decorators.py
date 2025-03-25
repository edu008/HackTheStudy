"""
Dekoratoren für die Task-Funktionen
"""
import logging
import time
import functools
import traceback
import inspect
import threading

# Logger konfigurieren
logger = logging.getLogger(__name__)

def log_function_call(func):
    """
    Dekorator zur Protokollierung von Funktionsaufrufen mit ihren Parametern und der Ausführungszeit.
    
    Args:
        func: Die zu dekorierende Funktion
        
    Returns:
        Eine dekorierte Funktion
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        session_id = None
        # Versuche, session_id aus den Argumenten zu extrahieren
        for arg in args:
            if isinstance(arg, str) and len(arg) > 8 and '-' in arg:
                session_id = arg
                break
        
        # Alternativ aus Kwargs extrahieren
        if not session_id and 'session_id' in kwargs:
            session_id = kwargs['session_id']
            
        logger.info(f"🔄 FUNKTION START: {func.__name__}() - Session: {session_id or 'unbekannt'}")
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"✅ FUNKTION ENDE: {func.__name__}() - Ausführungszeit: {execution_time:.2f}s - Session: {session_id or 'unbekannt'}")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ FUNKTION FEHLER: {func.__name__}() - Zeit: {execution_time:.2f}s - Fehler: {str(e)} - Session: {session_id or 'unbekannt'}")
            logger.error(traceback.format_exc())
            raise
    
    return wrapper

def timeout(seconds, error_message="Operation timed out"):
    """
    Dekorator, der eine Zeitüberschreitung für Funktionen erzwingt.
    
    Args:
        seconds: Timeout in Sekunden
        error_message: Fehlermeldung bei Timeout
        
    Returns:
        Dekorator-Funktion
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            error = [None]
            finished = [False]
            
            def target():
                try:
                    result[0] = func(*args, **kwargs)
                    finished[0] = True
                except Exception as e:
                    error[0] = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True  # Thread läuft im Hintergrund
            thread.start()
            thread.join(seconds)
            
            if finished[0]:
                if error[0]:
                    raise error[0]
                return result[0]
            else:
                raise TimeoutError(error_message)
                
        return wrapper
    return decorator

def retry(max_retries=3, delay=1, backoff=2, exceptions=(Exception,), logger=None):
    """
    Dekorator für automatische Wiederholungen bei Fehlern.
    
    Args:
        max_retries: Maximale Anzahl von Wiederholungsversuchen
        delay: Anfangsverzögerung zwischen Versuchen in Sekunden
        backoff: Multiplikator für die Verzögerung bei jedem Versuch
        exceptions: Tupel von Ausnahmen, die abgefangen werden sollen
        logger: Logger-Instanz für Protokollierung (optional)
    
    Returns:
        Dekorator-Funktion
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            local_logger = logger or logging.getLogger(func.__module__)
            retry_count = 0
            current_delay = delay
            
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        local_logger.error(f"Maximale Wiederholungen erschöpft ({max_retries}) für {func.__name__}: {str(e)}")
                        raise
                    
                    local_logger.warning(f"Fehler in {func.__name__} (Versuch {retry_count}/{max_retries}): {str(e)}")
                    local_logger.warning(f"Wiederholung in {current_delay} Sekunden...")
                    
                    time.sleep(current_delay)
                    current_delay *= backoff  # Exponentielles Backoff
        
        return wrapper
    return decorator 