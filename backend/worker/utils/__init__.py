"""
Zentrale Utils für den Worker.

Dieses Modul stellt gemeinsame Utilities und Import-Hilfsfunktionen bereit.
"""
import os
import sys
import logging
import importlib.util
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, cast

logger = logging.getLogger(__name__)

# Füge das Basis-Verzeichnis zum Python-Pfad hinzu
base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)
    logger.debug(f"Base-Directory zum Python-Pfad hinzugefügt: {base_dir}")

# Füge das Worker-Verzeichnis zum Python-Pfad hinzu (falls noch nicht vorhanden)
worker_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if worker_dir not in sys.path:
    sys.path.insert(0, worker_dir)
    logger.debug(f"Worker-Directory zum Python-Pfad hinzugefügt: {worker_dir}")

T = TypeVar('T')

def import_module_safely(module_paths: list[str], fallback_func: Optional[Callable[..., T]] = None) -> Optional[Any]:
    """
    Importiert ein Modul sicher mit mehreren Fallback-Pfaden.
    
    Args:
        module_paths: Liste von Modulpfaden, die versucht werden sollen
        fallback_func: Optionale Fallback-Funktion, die zurückgegeben wird, wenn kein Import funktioniert
        
    Returns:
        Das importierte Modul oder die Fallback-Funktion
    """
    last_error = None
    for path in module_paths:
        try:
            return importlib.import_module(path)
        except ImportError as e:
            last_error = e
            logger.debug(f"Konnte Modul nicht importieren: {path} - {e}")
    
    if last_error:
        logger.warning(f"Keiner der Import-Pfade funktionierte: {', '.join(module_paths)} - {last_error}")
    
    return fallback_func() if callable(fallback_func) else fallback_func

def import_function_safely(module_paths: list[str], function_name: str, 
                          fallback_func: Optional[Callable[..., T]] = None) -> Tuple[Optional[Callable[..., T]], str]:
    """
    Importiert eine Funktion sicher aus einer Liste von Modulpfaden.
    
    Args:
        module_paths: Liste von Modulpfaden, die versucht werden sollen
        function_name: Name der zu importierenden Funktion
        fallback_func: Optionale Fallback-Funktion
        
    Returns:
        Tuple aus (Funktion, Quelle) - wobei Quelle angibt, woher die Funktion kommt
    """
    for path in module_paths:
        try:
            module = importlib.import_module(path)
            if hasattr(module, function_name):
                return getattr(module, function_name), f"{path}.{function_name}"
        except ImportError:
            continue
    
    logger.warning(f"Konnte Funktion {function_name} nicht importieren, verwende Fallback")
    return fallback_func, "fallback"

# Importiere die Untermodule für einfacheren Zugriff
from . import text_extraction
# from . import ai_tools # Entfernt, da Datei gelöscht wurde
from .call_openai import call_openai_api, extract_json_from_response

__all__ = [
    'text_extraction', 
    'call_openai_api', 
    'extract_json_from_response',
    'import_module_safely', 
    'import_function_safely'
] 