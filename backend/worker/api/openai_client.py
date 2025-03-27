"""
Optimierter OpenAI-Client - Wrapper für die zentrale Implementierung.
Delegiert alle Funktionen an core/openai_integration.py.
"""

import logging
import functools
from typing import Dict, List, Any, Optional, Union

# Importiere die zentralen Implementierungen
from core.openai_integration import (
    get_openai_client,
    chat_completion,
    extract_content_from_response,
    clear_cache,
    count_tokens,
    calculate_token_cost,
    track_token_usage,
    check_credits_available,
    deduct_credits,
    get_user_credits,
    get_usage_stats
)

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
        logger.warning(f"Fehler beim Tracking der Cache-Nutzung: {e}")

def invalidate_cache(pattern="openai:chat:*"):
    """
    Ungültigmachen von Cache-Einträgen.
    """
    return clear_cache(pattern)

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
            logger.error(f"Fehler bei Chat-Completion: {e}")
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "response": None
            }

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
    # Standardpreise verwenden, wenn das Modell nicht in der Konfiguration enthalten ist
    if model not in MODEL_PRICING:
        logger.warning(f"Unbekanntes Modell für Preisberechnung: {model}, verwende gpt-4-Preise")
        pricing = MODEL_PRICING['gpt-4']
    else:
        pricing = MODEL_PRICING[model]
    
    # Kosten berechnen
    input_cost = input_tokens * pricing['input']
    output_cost = output_tokens * pricing['output']
    
    return input_cost + output_cost

def track_cached_usage(model, messages, cached_response, user_id, session_id, function_name):
    """
    Trackt die Token-Nutzung für zwischengespeicherte Antworten.
    
    Args:
        model: Das verwendete Modell
        messages: Die gesendeten Nachrichten
        cached_response: Die zwischengespeicherte Antwort
        user_id: Benutzer-ID (optional)
        session_id: Sitzungs-ID (optional)
        function_name: Funktionsname (optional)
    """
    try:
        # Token-Zählung aus der zwischengespeicherten Antwort extrahieren
        input_tokens = cached_response.get('usage', {}).get('prompt_tokens', 0)
        output_tokens = cached_response.get('usage', {}).get('completion_tokens', 0)
        
        # Wenn keine Token-Zählung verfügbar, schätzen wir sie
        if input_tokens == 0:
            input_tokens = count_tokens(messages, model)
        
        if output_tokens == 0 and 'choices' in cached_response:
            content = cached_response['choices'][0].get('message', {}).get('content', '')
            output_tokens = count_tokens([{"role": "assistant", "content": content}], model)
        
        # Token-Nutzung mit Cache-Flag tracken
        track_token_usage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            function_name=function_name,
            cached=True
        )
        
        logger.debug(
            f"Cache-Treffer verfolgt: Modell={model}, "
            f"Tokens={input_tokens}+{output_tokens}, User={user_id}, Session={session_id}"
        )
    
    except Exception as e:
        logger.warning(f"Fehler beim Tracken der zwischengespeicherten Nutzung: {e}")

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
    # Standardpreise verwenden, wenn das Modell nicht in der Konfiguration enthalten ist
    if model not in MODEL_PRICING:
        logger.warning(f"Unbekanntes Modell für Preisberechnung: {model}, verwende gpt-4-Preise")
        pricing = MODEL_PRICING['gpt-4']
    else:
        pricing = MODEL_PRICING[model]
    
    # Kosten berechnen
    input_cost = input_tokens * pricing['input']
    output_cost = output_tokens * pricing['output']
    
    return input_cost + output_cost

def extract_content_from_response(response):
    """
    Extrahiert den Inhaltstext aus einer OpenAI-Antwort.
    
    Args:
        response: Die OpenAI-Antwort
    
    Returns:
        str: Der extrahierte Inhalt
    """
    if not response or 'choices' not in response or not response['choices']:
        return ""
    
    # Inhalt aus der ersten Wahl extrahieren
    first_choice = response['choices'][0]
    if 'message' in first_choice and 'content' in first_choice['message']:
        return first_choice['message']['content'] or ""
    
    return ""

def invalidate_cache(pattern="openai:chat:*"):
    """
    Invalidiert den Cache basierend auf einem Muster.
    
    Args:
        pattern: Das zu verwendende Redis-Muster
    
    Returns:
        int: Anzahl der gelöschten Schlüssel
    """
    try:
        keys = redis_client.keys(pattern)
        if keys:
            return redis_client.delete(*keys)
        return 0
    except Exception as e:
        logger.error(f"Fehler beim Invalidieren des Caches: {e}")
        return 0

class OptimizedOpenAIClient:
    _instance = None
    _api_key = None
    _model_name = None
    
    @classmethod
    def get_instance(cls):
        """Singleton-Pattern für den OpenAI-Client"""
        if cls._instance is None:
            api_key = cls._get_api_key()
            if not api_key:
                return None
                
            cls._api_key = api_key
            cls._instance = OpenAI(api_key=api_key)
            
        return cls._instance
        
    @classmethod
    def _get_api_key(cls):
        """API-Schlüssel aus verschiedenen Quellen mit Caching"""
        if cls._api_key:
            return cls._api_key
            
        # Versuche aus App-Kontext
        try:
            key = current_app.config.get('OPENAI_API_KEY')
            if key:
                return key
        except RuntimeError:
            pass
            
        # Versuche aus Umgebungsvariable
        return os.environ.get('OPENAI_API_KEY')
        
    @classmethod
    def get_model(cls):
        """Modellname abrufen mit Caching"""
        if cls._model_name:
            return cls._model_name
            
        try:
            model = current_app.config.get('OPENAI_MODEL', 'gpt-4o').strip()
        except RuntimeError:
            model = os.environ.get('OPENAI_MODEL', 'gpt-4o').strip()
            
        cls._model_name = model
        return model
        
    @classmethod
    def query(cls, prompt, system_content=None, session_id=None, user_id=None, function_name=None, temperature=0.7, max_tokens=4000):
        """Optimierte OpenAI-Anfrage mit umfassendem Logging und Fehlerbehandlung"""
        client = cls.get_instance()
        if not client:
            error_msg = "OpenAI-Client konnte nicht initialisiert werden"
            if session_id:
                AppLogger.track_error(session_id, "openai_client_error", error_msg)
            raise ValueError(error_msg)
            
        model = cls.get_model()
        
        # System-Content standardisieren
        if not system_content:
            system_content = "You are a helpful assistant that provides concise, accurate information."
            
        # Token-Zählung
        input_tokens = count_tokens(system_content) + count_tokens(prompt)
        
        # Anfrage loggen
        AppLogger.log_openai_request(
            session_id=session_id, 
            model=model,
            system_preview=system_content,
            prompt_preview=prompt,
            tokens_in=input_tokens
        )
        
        # Kredit-Check wenn Benutzer-ID vorhanden
        if user_id:
            estimated_output_tokens = min(4000, input_tokens // 2)
            estimated_cost = calculate_token_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=estimated_output_tokens
            )
            
            # Prüfen, ob genügend Credits vorhanden sind
            if not check_credits_available(estimated_cost, user_id):
                error_msg = f"Nicht genügend Credits für diese Operation (benötigt: {estimated_cost})"
                if session_id:
                    AppLogger.track_error(
                        session_id, 
                        "insufficient_credits", 
                        error_msg,
                        diagnostics={"estimated_cost": estimated_cost, "tokens": input_tokens}
                    )
                raise ValueError(error_msg)
                
        # API-Aufruf mit Zeitmessung
        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Erfolgreiche Antwort
            duration_ms = int((time.time() - start_time) * 1000)
            response_text = response.choices[0].message.content.strip()
            
            # Response loggen
            AppLogger.log_openai_response(
                session_id=session_id,
                response_preview=response_text,
                tokens_out=response.usage.completion_tokens if hasattr(response, 'usage') else None,
                duration_ms=duration_ms
            )
            
            # Credits abziehen wenn Benutzer-ID vorhanden
            if user_id and hasattr(response, 'usage'):
                actual_cost = calculate_token_cost(
                    model=model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens
                )
                deduct_credits(
                    user_id, 
                    actual_cost, 
                    session_id=session_id,
                    function_name=function_name
                )
                
            # Antwort in Redis cachen für Diagnose
            if session_id:
                cache_key = f"openai_last_response:{session_id}"
                redis_client.set(
                    cache_key, 
                    json.dumps({
                        "text": response_text[:1000] + "..." if len(response_text) > 1000 else response_text,
                        "tokens_in": response.usage.prompt_tokens if hasattr(response, 'usage') else input_tokens,
                        "tokens_out": response.usage.completion_tokens if hasattr(response, 'usage') else None,
                        "model": model,
                        "timestamp": time.time()
                    }),
                    ex=3600
                )
                
            return response_text
            
        except Exception as e:
            # Fehlerbehandlung mit detailliertem Logging
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            if session_id:
                AppLogger.track_error(
                    session_id,
                    "openai_api_error",
                    error_msg,
                    trace=traceback.format_exc(),
                    diagnostics={
                        "model": model,
                        "duration_ms": duration_ms,
                        "input_tokens": input_tokens
                    }
                )
                
            raise 

    def chat_completion(self, prompt, system_content=None, model=None, temperature=0.7, 
                       max_tokens=4000, use_cache=True, user_id=None, session_id=None, 
                       function_name="chat_completion", endpoint=None, max_retries=3):
        logger = logging.getLogger(__name__)
        
        # Ausführliches Logging der OpenAI-Anfrage
        logger.debug(f"OpenAI API-Anfrage gestartet: session_id={session_id}, function={function_name}, model={model}")
        logger.debug(f"Prompt: {prompt[:100]}...")  # Nur Anfang des Prompts loggen
        
        # Überwache Start der Anfrage
        start_time = time.time()
        
        # Import hier, um Zirkelbezüge zu vermeiden
        import traceback
        import json
        
        client = self.get_instance()
        if not client:
            error_msg = "OpenAI-Client konnte nicht initialisiert werden"
            if session_id:
                # In Redis für Debugging speichern
                error_data = {
                    "error_type": "client_initialization",
                    "message": error_msg,
                    "timestamp": time.time(),
                    "function": function_name
                }
                redis_key = f"openai_error:{session_id}"
                try:
                    redis_client.set(redis_key, json.dumps(error_data), ex=3600)
                except Exception as redis_err:
                    logger.error(f"Fehler beim Speichern des OpenAI-Errors in Redis: {str(redis_err)}")
                
                # Auch den processing_status auf "error" setzen
                status_key = f"processing_status:{session_id}"
                redis_client.set(status_key, "error", ex=3600)
                
                # Speichere detaillierte Fehlerinformationen
                error_details_key = f"error_details:{session_id}"
                error_details = {
                    "error_type": "openai_client_error",
                    "message": error_msg,
                    "timestamp": time.time(),
                    "function": function_name
                }
                redis_client.set(error_details_key, json.dumps(error_details), ex=3600)
                
                from api.log_utils import AppLogger
                AppLogger.track_error(session_id, "openai_client_error", error_msg)
            
            raise ValueError(error_msg)
        
        try:
            # Führe OpenAI API-Anfrage durch und protokolliere bei Fehler
            response = client.chat.completions.create(
                model=model or self.get_model(),
                messages=[
                    {"role": "system", "content": system_content or "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Erfolgsfall protokollieren
            end_time = time.time()
            duration = end_time - start_time
            
            logger.debug(f"OpenAI API-Anfrage erfolgreich: session_id={session_id}, dauer={duration:.2f}s")
            
            # Extrahiere und gib Antworttext zurück
            response_text = response.choices[0].message.content.strip()
            
            # Speichere erfolgreiche Antwort in Redis für Debugging
            if session_id:
                response_key = f"openai_last_response:{session_id}"
                response_data = {
                    "text_preview": response_text[:500] + "..." if len(response_text) > 500 else response_text,
                    "model": model or self.get_model(),
                    "tokens_in": response.usage.prompt_tokens if hasattr(response, 'usage') else None,
                    "tokens_out": response.usage.completion_tokens if hasattr(response, 'usage') else None,
                    "duration": duration,
                    "timestamp": time.time()
                }
                try:
                    redis_client.set(response_key, json.dumps(response_data), ex=3600)
                except Exception as redis_err:
                    logger.error(f"Fehler beim Speichern der OpenAI-Antwort in Redis: {str(redis_err)}")
            
            return response_text
            
        except Exception as e:
            # Fehlerbehandlung mit detailliertem Logging
            end_time = time.time()
            duration = end_time - start_time
            error_msg = str(e)
            
            logger.error(f"OpenAI API-Fehler: session_id={session_id}, error={error_msg}, dauer={duration:.2f}s")
            logger.error(traceback.format_exc())
            
            # Details in Redis für Debugging speichern
            if session_id:
                # Speichere Fehlerinformationen
                error_data = {
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "timestamp": time.time(),
                    "duration": duration,
                    "function": function_name,
                    "traceback": traceback.format_exc()
                }
                error_key = f"openai_error:{session_id}"
                try:
                    redis_client.set(error_key, json.dumps(error_data), ex=3600)
                except Exception as redis_err:
                    logger.error(f"Fehler beim Speichern des OpenAI-Errors in Redis: {str(redis_err)}")
                
                # Setze processing_status auf "error"
                status_key = f"processing_status:{session_id}"
                redis_client.set(status_key, "error", ex=3600)
                
                # Speichere detaillierte Fehlerinformationen für Frontend
                error_details_key = f"error_details:{session_id}"
                error_details = {
                    "error_type": "openai_api_error",
                    "message": f"OpenAI API-Fehler: {error_msg}",
                    "timestamp": time.time(),
                    "function": function_name,
                    "traceback": traceback.format_exc()
                }
                redis_client.set(error_details_key, json.dumps(error_details), ex=3600)
                
                from api.log_utils import AppLogger
                AppLogger.track_error(
                    session_id,
                    "openai_api_error",
                    f"OpenAI API-Fehler: {error_msg}",
                    trace=traceback.format_exc()
                )
            
            # Weitergabe des Fehlers
            raise 