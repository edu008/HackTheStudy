"""
OpenAI-Cache-Manager für den Worker.
Bietet Funktionen zum Caching von OpenAI-Anfragen und optimiert die Token-Nutzung.
"""
import hashlib
import json
import logging
# System-Imports
import os
import time
from functools import wraps

# Interne Imports
from redis_utils.client import get_redis_client

logger = logging.getLogger(__name__)


class OpenAICacheManager:
    """
    Verwaltet den OpenAI-Cache und bietet statische Methoden für Cache-Operationen.
    Verwendet einen zentralen Redis-Client für alle Cache-Operationen.
    """
    # Klassenattribute statt globaler Variablen
    _redis_client = None
    _cache_enabled = os.environ.get('OPENAI_CACHE_ENABLED', 'true').lower() == 'true'
    _cache_ttl = int(os.environ.get('OPENAI_CACHE_TTL', 86400))  # 24 Stunden Standard-TTL
    
    @classmethod
    def initialize_openai_cache(cls):
        """
        Initialisiert den OpenAI-Cache mit Redis.

        Returns:
            bool: True, wenn die Initialisierung erfolgreich war, sonst False.
        """
        if not cls._cache_enabled:
            logger.info("OpenAI-Cache ist deaktiviert, überspringe Initialisierung")
            return False

        try:
            # Redis-Client importieren
            cls._redis_client = get_redis_client()

            if cls._redis_client:
                # Cache-Status in Redis setzen
                cache_info = {
                    "initialized_at": time.time(),
                    "ttl": cls._cache_ttl,
                    "enabled": cls._cache_enabled
                }
                cls._redis_client.set("openai:cache:status", json.dumps(cache_info))
                logger.info("OpenAI-Cache erfolgreich initialisiert mit TTL=%ss", cls._cache_ttl)
                return True
                
            logger.warning("Redis-Client ist nicht verfügbar, OpenAI-Cache deaktiviert")
            return False
        except Exception as e:
            logger.error("Fehler bei der Initialisierung des OpenAI-Cache: %s", e)
            return False
            
    @classmethod
    def get_redis_client(cls):
        """
        Gibt den Redis-Client für Cache-Operationen zurück oder initialisiert ihn bei Bedarf.
        
        Returns:
            Redis-Client oder None bei Fehler
        """
        if cls._redis_client is None:
            cls.initialize_openai_cache()
        return cls._redis_client
            
    @staticmethod
    def generate_cache_key(model, messages, temperature=None, max_tokens=None, **kwargs):
        """
        Generiert einen eindeutigen Cache-Key basierend auf den Anfrageparametern.

        Args:
            model (str): Das verwendete OpenAI-Modell.
            messages (list): Die Nachrichtenliste für die Anfrage.
            temperature (float, optional): Die Temperatur-Einstellung.
            max_tokens (int, optional): Maximale Token-Anzahl.
            **kwargs: Weitere Parameter für die Anfrage.

        Returns:
            str: Ein eindeutiger Cache-Schlüssel.
        """
        # Relevante Parameter für den Cache-Key
        cache_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Zusätzliche relevante Parameter hinzufügen
        for key in ["top_p", "frequency_penalty", "presence_penalty", "stop"]:
            if key in kwargs:
                cache_params[key] = kwargs[key]

        # Cache-Key erstellen
        params_str = json.dumps(cache_params, sort_keys=True)
        return f"openai:cache:{hashlib.md5(params_str.encode('utf-8')).hexdigest()}"
            
    @classmethod
    def clear_cache(cls, pattern="openai:cache:*"):
        """
        Löscht Cache-Einträge basierend auf einem Muster.

        Args:
            pattern (str): Redis-Schlüsselmuster zum Löschen.

        Returns:
            int: Anzahl der gelöschten Cache-Einträge.
        """
        redis_client = cls.get_redis_client()
        if not redis_client:
            logger.warning("Redis-Client nicht verfügbar, Cache-Bereinigung übersprungen")
            return 0

        try:
            keys = redis_client.keys(pattern)
            if keys:
                deleted = redis_client.delete(*keys)
                logger.info("%s Cache-Einträge gelöscht mit Muster: %s", deleted, pattern)
                return deleted
            return 0
        except Exception as e:
            logger.error("Fehler bei der Cache-Bereinigung: %s", e)
            return 0


# Funktionen für Abwärtskompatibilität
def initialize_openai_cache():
    """Leitet an die Klassenmethode weiter."""
    return OpenAICacheManager.initialize_openai_cache()

def generate_cache_key(model, messages, temperature=None, max_tokens=None, **kwargs):
    """Leitet an die Klassenmethode weiter."""
    return OpenAICacheManager.generate_cache_key(model, messages, temperature, max_tokens, **kwargs)

def clear_cache(pattern="openai:cache:*"):
    """Leitet an die Klassenmethode weiter."""
    return OpenAICacheManager.clear_cache(pattern)


def cache_openai_response(func):
    """
    Decorator für das Caching von OpenAI-Anfragen.

    Args:
        func: Die zu cachende Funktion.

    Returns:
        function: Die dekorierte Funktion mit Caching-Funktionalität.
    """
    @wraps(func)
    async def wrapper(model, messages, *args, **kwargs):
        # Cache überspringen, wenn deaktiviert oder kein Redis-Client
        redis_client = OpenAICacheManager.get_redis_client()
        if not OpenAICacheManager._cache_enabled or not redis_client:
            return await func(model, messages, *args, **kwargs)

        # Prüfen, ob Force-Refresh angefordert
        force_refresh = kwargs.pop('force_refresh', False)

        # Cache-Key generieren
        cache_key = OpenAICacheManager.generate_cache_key(model, messages, **kwargs)

        # Aus Cache laden, wenn nicht Force-Refresh
        if not force_refresh:
            cached_response = redis_client.get(cache_key)
            if cached_response:
                try:
                    response_data = json.loads(cached_response)
                    logger.info("Cache-Hit für OpenAI-Anfrage: %s", cache_key)
                    return response_data
                except json.JSONDecodeError:
                    logger.warning("Ungültige Cache-Daten gefunden für: %s", cache_key)

        # Anfrage ausführen, wenn kein Cache-Hit
        response = await func(model, messages, *args, **kwargs)

        # Ergebnis im Cache speichern
        try:
            redis_client.setex(
                cache_key,
                OpenAICacheManager._cache_ttl,
                json.dumps(response)
            )
            logger.info("OpenAI-Antwort im Cache gespeichert: %s", cache_key)
        except Exception as e:
            logger.error("Fehler beim Speichern im Cache: %s", e)

        return response

    return wrapper
