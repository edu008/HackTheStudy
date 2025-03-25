"""
Hilfsfunktionen für das Logging.
"""

import sys
import time
import logging
import functools
import traceback
from typing import Callable, Any, Dict, List, Optional
from datetime import datetime
import inspect

# Logger konfigurieren
logger = logging.getLogger(__name__)

def log_function_call(func: Callable) -> Callable:
    """
    Dekoriert eine Funktion, um Eingabe- und Ausgabe-Parameter zu loggen.
    
    Args:
        func: Die zu dekorierende Funktion
    
    Returns:
        Dekorierte Funktion
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Funktionssignatur und -informationen
        func_name = func.__name__
        module_name = func.__module__
        
        # Konfigurieren des Loggers für diese Funktion
        function_logger = logging.getLogger(f"{module_name}.{func_name}")
        
        # Nur loggen, wenn Logger auf DEBUG gestellt ist
        if function_logger.isEnabledFor(logging.DEBUG):
            # Argumente für Logging formatieren
            arg_names = inspect.getfullargspec(func).args
            
            # Wenn es sich um eine Methode handelt, 'self' oder 'cls' überspringen
            if arg_names and arg_names[0] in ('self', 'cls'):
                arg_names = arg_names[1:]
                args = args[1:]
            
            # Sichere Darstellung der Argumente (für vertrauliche Daten)
            safe_args = []
            for i, arg in enumerate(args):
                arg_name = arg_names[i] if i < len(arg_names) else f"arg{i}"
                if arg_name.lower() in ('password', 'token', 'secret', 'key', 'credentials'):
                    safe_args.append(f"{arg_name}=*****")
                else:
                    # Für große Objekte nur Typ und Größe loggen
                    if hasattr(arg, '__len__') and len(arg) > 1000:
                        safe_args.append(f"{arg_name}=<{type(arg).__name__} mit {len(arg)} Elementen>")
                    else:
                        try:
                            safe_args.append(f"{arg_name}={arg}")
                        except:
                            safe_args.append(f"{arg_name}=<nicht darstellbar>")
            
            # Sichere Darstellung der Keyword-Argumente
            safe_kwargs = {}
            for k, v in kwargs.items():
                if k.lower() in ('password', 'token', 'secret', 'key', 'credentials'):
                    safe_kwargs[k] = "*****"
                else:
                    # Für große Objekte nur Typ und Größe loggen
                    if hasattr(v, '__len__') and len(v) > 1000:
                        safe_kwargs[k] = f"<{type(v).__name__} mit {len(v)} Elementen>"
                    else:
                        try:
                            safe_kwargs[k] = v
                        except:
                            safe_kwargs[k] = "<nicht darstellbar>"
            
            # Eingang loggen
            function_logger.debug(f"AUFRUF {func_name}({', '.join(safe_args)}{',' if safe_args and safe_kwargs else ''} {safe_kwargs if safe_kwargs else ''})")
        
        # Zeit messen
        start_time = time.time()
        
        # Funktion ausführen
        try:
            result = func(*args, **kwargs)
            
            # Zeit berechnen
            execution_time = time.time() - start_time
            
            # Ergebnis loggen wenn Logger auf DEBUG gestellt ist
            if function_logger.isEnabledFor(logging.DEBUG):
                # Für große Objekte nur Typ und Größe loggen
                if result is not None and hasattr(result, '__len__') and len(result) > 1000:
                    result_str = f"<{type(result).__name__} mit {len(result)} Elementen>"
                else:
                    try:
                        result_str = str(result)
                        if len(result_str) > 1000:
                            result_str = result_str[:1000] + "..."
                    except:
                        result_str = "<nicht darstellbar>"
                
                function_logger.debug(f"ERGEBNIS {func_name} => {result_str} (in {execution_time:.3f}s)")
            
            # Erfolgsmeldung loggen wenn Logger auf INFO gestellt ist
            elif function_logger.isEnabledFor(logging.INFO):
                function_logger.info(f"{func_name} erfolgreich ausgeführt in {execution_time:.3f}s")
            
            return result
        except Exception as e:
            # Fehler loggen
            execution_time = time.time() - start_time
            function_logger.error(f"FEHLER in {func_name}: {str(e)} (nach {execution_time:.3f}s)")
            function_logger.error(traceback.format_exc())
            raise
    
    return wrapper

def setup_function_logging(level: int = logging.INFO, module_name: str = None) -> Callable:
    """
    Dekoriert eine Funktion mit angepasstem Logging-Level.
    
    Args:
        level: Logging-Level (z.B. logging.DEBUG, logging.INFO)
        module_name: Optionaler Modulname für Logger (sonst wird der Modul der Funktion verwendet)
    
    Returns:
        Dekorator-Funktion
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Originalen Logger speichern
            func_name = func.__name__
            orig_module_name = module_name or func.__module__
            
            # Logger konfigurieren
            function_logger = logging.getLogger(f"{orig_module_name}.{func_name}")
            original_level = function_logger.level
            
            # Logger-Level temporär anpassen
            function_logger.setLevel(level)
            
            try:
                # Funktion ausführen
                return func(*args, **kwargs)
            finally:
                # Logger-Level zurücksetzen
                function_logger.setLevel(original_level)
        
        return wrapper
    
    return decorator

def log_step(step_name: str, status: str, message: str):
    """
    Protokolliert einen Schritt mit einheitlichem Format.
    
    Args:
        step_name: Name des Schritts
        status: Status (z.B. "INFO", "SUCCESS", "ERROR")
        message: Nachricht
    """
    status_upper = status.upper()
    logger.info(f"[{step_name}] {status_upper}: {message}") 