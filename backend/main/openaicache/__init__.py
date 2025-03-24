"""
OpenAI Cache Module für HackTheStudy

Dieses Modul bietet Caching-Funktionalität für OpenAI-API-Aufrufe 
und ein Token-Tracking-System zur Überwachung des API-Verbrauchs.
"""

import os
import logging
from openai import OpenAI
from flask import current_app

__version__ = '1.0.0'

from .openai_wrapper import CachedOpenAI
from .token_tracker import TokenTracker, update_token_usage

logger = logging.getLogger(__name__)

# Eine global verwendete OpenAI-Client-Instanz
_openai_client = None
_openai_cached_client = None

def calculate_token_cost(prompt_tokens, completion_tokens, model_name="gpt-4o"):
    """
    Berechnet die Kosten für Token basierend auf dem Modell.
    
    Args:
        prompt_tokens: Anzahl der Tokens in der Anfrage
        completion_tokens: Anzahl der Tokens in der Antwort
        model_name: Name des verwendeten Modells
        
    Returns:
        float: Kosten in USD
    """
    from .token_tracker import TokenTracker
    return TokenTracker.calculate_token_cost(model_name, prompt_tokens, completion_tokens)

def track_token_usage(user_id, usage_type, prompt_tokens, completion_tokens, model_name="gpt-4o", metadata=None):
    """
    Verfolgt die Token-Nutzung eines Benutzers.
    
    Args:
        user_id: ID des Benutzers
        usage_type: Art der Nutzung (z.B. 'chat', 'image', etc.)
        prompt_tokens: Anzahl der Tokens in der Anfrage
        completion_tokens: Anzahl der Tokens in der Antwort
        model_name: Name des verwendeten Modells
        metadata: Zusätzliche Metadaten zur Nutzung (optional)
        
    Returns:
        dict: Trackinginformationen oder None bei Fehler
    """
    return update_token_usage(user_id, usage_type, prompt_tokens, completion_tokens, model_name, metadata)

def get_openai_client(use_cache=True):
    """
    Gibt eine Instanz des OpenAI-Clients zurück, optional mit Caching.
    
    Args:
        use_cache: Ob der Client mit Caching verwendet werden soll
        
    Returns:
        Eine Instanz von CachedOpenAI oder OpenAI
        
    Raises:
        ValueError: Wenn kein API-Key gefunden oder der Client nicht erstellt werden kann
    """
    global _openai_client, _openai_cached_client
    import traceback
    
    # API-Key-Beschaffung mit detaillierter Fehlerbehandlung
    api_key = None
    try:
        # Versuche zuerst aus dem Flask-Kontext
        logger.info("Versuche API-Key aus Flask-Kontext zu erhalten")
        api_key = current_app.config.get("OPENAI_API_KEY")
        logger.info(f"API-Key aus Flask-Kontext: {'Vorhanden' if api_key else 'Fehlt'}")
    except RuntimeError as e:
        logger.warning(f"Kein Flask-Kontext verfügbar: {str(e)}")
    
    # Falls nicht im Flask-Kontext, versuche Umgebungsvariable
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
        logger.info(f"API-Key aus Umgebungsvariable: {'Vorhanden' if api_key else 'Fehlt'}")
    
    # Prüfe, ob ein API-Key gefunden wurde
    if not api_key:
        error_msg = "OPENAI_API_KEY ist weder in der Flask-Konfiguration noch in den Umgebungsvariablen gesetzt"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Erstelle den Client basierend auf dem Cache-Parameter
    if use_cache:
        logger.info("Cache-Modus aktiviert, versuche CachedOpenAI-Client zu erstellen oder wiederzuverwenden")
        # Verwende gecachten Client, wenn verfügbar oder erstelle einen neuen
        if _openai_cached_client is None:
            try:
                logger.info("Erstelle neuen OpenAI-Client für CachedOpenAI")
                direct_client = OpenAI(api_key=api_key)
                
                logger.info("Überprüfe direkten OpenAI-Client")
                if not hasattr(direct_client, 'chat'):
                    error_msg = f"Erstellter OpenAI-Client hat kein 'chat'-Attribut (Typ: {type(direct_client).__name__})"
                    logger.error(f"{error_msg}, Client-Dir: {dir(direct_client)}")
                    raise ValueError(error_msg)
                
                logger.info("Erstelle CachedOpenAI-Wrapper mit validiertem OpenAI-Client")
                _openai_cached_client = CachedOpenAI(client=direct_client)
                logger.info(f"CachedOpenAI-Client erfolgreich erstellt: {type(_openai_cached_client)}")
            except Exception as e:
                logger.error(f"Fehler beim Erstellen des CachedOpenAI-Clients: {str(e)}")
                logger.error(f"Stacktrace: {traceback.format_exc()}")
                
                # Versuche Fallback auf Standard-Client
                logger.info("Versuche Fallback auf Standard-Client")
                if _openai_client is None:
                    try:
                        _openai_client = OpenAI(api_key=api_key)
                        logger.info(f"Fallback auf Standard-Client erfolgreich: {type(_openai_client)}")
                    except Exception as fallback_error:
                        error_msg = f"Sowohl CachedOpenAI als auch Fallback-Client konnten nicht erstellt werden: {str(e)} / {str(fallback_error)}"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                return _openai_client
        
        logger.info(f"Gebe CachedOpenAI-Client zurück: {type(_openai_cached_client)}")
        return _openai_cached_client
    else:
        logger.info("Standard-Modus (ohne Cache) aktiviert")
        # Verwende Standard-Client, wenn verfügbar oder erstelle einen neuen
        if _openai_client is None:
            try:
                _openai_client = OpenAI(api_key=api_key)
                logger.info(f"Standard OpenAI-Client erstellt: {type(_openai_client)}")
                
                # Validiere den Client
                if not hasattr(_openai_client, 'chat'):
                    error_msg = f"Erstellter OpenAI-Client hat kein 'chat'-Attribut (Typ: {type(_openai_client).__name__})"
                    logger.error(f"{error_msg}, Client-Dir: {dir(_openai_client)}")
                    raise ValueError(error_msg)
            except Exception as e:
                error_msg = f"Fehler beim Erstellen des Standard-OpenAI-Clients: {str(e)}"
                logger.error(error_msg)
                logger.error(f"Stacktrace: {traceback.format_exc()}")
                raise ValueError(error_msg)
        
        logger.info(f"Gebe Standard-OpenAI-Client zurück: {type(_openai_client)}")
        return _openai_client 