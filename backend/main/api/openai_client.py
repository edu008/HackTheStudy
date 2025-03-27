"""
Optimierter OpenAI-Client - Wrapper für die zentrale Implementierung.
Delegiert alle Funktionen an core/openai_integration.py.
"""

import functools
import logging
import time
import traceback
from typing import Any, Dict, List, Optional, Union

# Importiere die zentralen Implementierungen
from core.openai_integration import (calculate_token_cost, chat_completion,
                                     check_credits_available, clear_cache,
                                     count_tokens, deduct_credits,
                                     extract_content_from_response,
                                     get_openai_client, get_usage_stats,
                                     get_user_credits, track_token_usage)
from core.redis_client import get_redis_client

# Importiere Modellpreise und andere Konstanten aus der zentralen Implementierung
from core.openai_integration import MODEL_PRICING

# Logger konfigurieren
logger = logging.getLogger('api.openai_client')

# Kompatibilitätsfunktion für den alten Aufruf
def chat_completion_with_backoff(model, messages, user_id=None, session_id=None,
                                 function_name=None, use_cache=True, **kwargs):
    """
    Kompatibilitätsfunktion für die alte Schnittstelle.
    Delegiert an die zentrale Implementierung.
    """
    return chat_completion(
        model=model,
        messages=messages,
        user_id=user_id,
        session_id=session_id,
        function_name=function_name,
        use_cache=use_cache,
        **kwargs
    )

# Rückwärtskompatible Funktionen
def generate_cache_key(model, messages, **kwargs):
    """
    Generiert einen eindeutigen Cache-Schlüssel.
    Verwendet die integrierte Funktion des OpenAICache-Objekts.
    """
    from core.openai_integration import OpenAICache
    cache = OpenAICache()
    return cache.generate_key(model, messages, **kwargs)


def get_cached_response(cache_key):
    """
    Abrufen einer Antwort aus dem Cache.
    """
    from core.openai_integration import OpenAICache
    cache = OpenAICache()
    return cache.get(cache_key)


def cache_response(cache_key, response, ttl=None):
    """
    Speichern einer Antwort im Cache.
    """
    from core.openai_integration import OpenAICache
    cache = OpenAICache()
    return cache.set(cache_key, response)


def track_cached_usage(model, messages, cached_response, user_id, session_id, function_name):
    """
    Token-Tracking für Cache-Treffer.
    
    Args:
        model: Das verwendete Modell
        messages: Die gesendeten Nachrichten
        cached_response: Die zwischengespeicherte Antwort
        user_id: Benutzer-ID (optional)
        session_id: Sitzungs-ID (optional)
        function_name: Funktionsname (optional)
    """
    try:
        # Token-Zählung aus der gecachten Antwort extrahieren
        input_tokens = cached_response.get('usage', {}).get('prompt_tokens', 0)
        output_tokens = cached_response.get('usage', {}).get('completion_tokens', 0)

        # Wenn keine Token-Zählung verfügbar, schätzen wir sie
        if input_tokens == 0:
            input_tokens = count_tokens(messages, model)

        if output_tokens == 0 and 'choices' in cached_response:
            content = cached_response['choices'][0].get('message', {}).get('content', '')
            output_tokens = count_tokens(content, model)

        # Token-Nutzung tracken mit reduziertem Preis
        track_token_usage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            function_name=function_name,
            cached=True
        )
    except Exception as e:
        logger.warning("Fehler beim Tracking der Cache-Nutzung: %s", e)


def invalidate_cache(pattern="openai:chat:*"):
    """
    Ungültigmachen von Cache-Einträgen.
    """
    return clear_cache(pattern)


def calculate_cost(model, input_tokens, output_tokens):
    """
    Berechnet die Kosten für eine API-Anfrage basierend auf dem Modell und der Token-Anzahl.

    Args:
        model: Das verwendete Modell
        input_tokens: Anzahl der Eingabe-Token
        output_tokens: Anzahl der Ausgabe-Token

    Returns:
        float: Die berechneten Kosten in USD
    """
    # Verwende die calculate_token_cost-Funktion aus der zentralen Implementierung
    return calculate_token_cost(model, input_tokens, output_tokens)


# Rückwärtskompatible Klasse
class OptimizedOpenAIClient:
    """
    Kompatibilitätsklasse für vorhandene Aufrufstellen.
    Alle Methoden delegieren an die zentrale Implementierung.
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        """
        Gibt die Singleton-Instanz zurück.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def get_model():
        """
        Gibt das Standard-Modell zurück.
        """
        from core.openai_integration import DEFAULT_MODEL
        return DEFAULT_MODEL

    @classmethod
    def query(cls, prompt, system_content=None, session_id=None, user_id=None,
              function_name=None, temperature=0.7, max_tokens=4000):
        """
        Einfache Schnittstelle für Textanfragen.
        """
        instance = cls.get_instance()
        return instance.chat_completion(
            prompt=prompt,
            system_content=system_content,
            session_id=session_id,
            user_id=user_id,
            function_name=function_name or "query",
            temperature=temperature,
            max_tokens=max_tokens
        )

    def chat_completion(self, prompt, system_content=None, model=None, temperature=0.7,
                        max_tokens=4000, use_cache=True, user_id=None, session_id=None,
                        function_name="chat_completion", endpoint=None, max_retries=3):
        """
        Führt eine Chat-Completion für den gegebenen Prompt durch.
        """
        # Standardwerte verwenden
        model = model or self.get_model()

        # Nachrichten erstellen
        messages = []

        # System-Nachricht hinzufügen, wenn vorhanden
        if system_content:
            messages.append({"role": "system", "content": system_content})

        # Prompt als Benutzernachricht hinzufügen
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            # Wenn prompt bereits eine Liste von Nachrichten ist
            messages.extend(prompt)

        # Chat-Completion durchführen
        try:
            response = chat_completion(
                model=model,
                messages=messages,
                user_id=user_id,
                session_id=session_id,
                function_name=function_name,
                use_cache=use_cache,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Antworttext extrahieren
            content = extract_content_from_response(response)

            return {
                "success": True,
                "text": content,
                "response": response
            }
        except Exception as e:
            logger.error("Fehler bei Chat-Completion: %s", e)
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "response": None
            }
