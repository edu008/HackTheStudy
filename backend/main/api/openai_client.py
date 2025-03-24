"""
Optimierter OpenAI-Client mit verbesserter Fehlerbehandlung, Caching und Retry-Logik.
"""

import os
import time
import logging
import json
import hashlib
import functools
from datetime import datetime, timedelta
import threading
import backoff  # Für exponentielles Backoff bei Wiederholungen
from openai import OpenAI, APIError, APITimeoutError, RateLimitError
from flask import current_app, g
from api.log_utils import AppLogger
from api.token_tracking import count_tokens, calculate_token_cost, deduct_credits, check_credits_available, track_token_usage
import traceback
import redis

# Redis-Client direkt erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.from_url(redis_url)

# Thread-lokaler Speicher für Client-Instanzen
_thread_local = threading.local()

# Logger konfigurieren
logger = logging.getLogger('api.openai_client')

# Konfigurationswerte aus Umgebungsvariablen
DEFAULT_MODEL = os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-4o')
CACHE_TTL = int(os.environ.get('OPENAI_CACHE_TTL', 86400))  # 24 Stunden Standard-TTL
CACHE_ENABLED = os.environ.get('OPENAI_CACHE_ENABLED', 'true').lower() == 'true'
MAX_RETRIES = int(os.environ.get('OPENAI_MAX_RETRIES', 3))
MAX_TIMEOUT = int(os.environ.get('OPENAI_TIMEOUT', 120))  # Timeout in Sekunden

# Modell-Preiskonfiguration
MODEL_PRICING = {
    'gpt-4o': {'input': 0.00005, 'output': 0.00015},
    'gpt-4-turbo': {'input': 0.00001, 'output': 0.00003},
    'gpt-3.5-turbo': {'input': 0.000001, 'output': 0.000002},
    'gpt-4-vision-preview': {'input': 0.00001, 'output': 0.00003},
    'gpt-4': {'input': 0.00003, 'output': 0.00006},
    'gpt-4-32k': {'input': 0.00006, 'output': 0.00012},
}

def get_openai_client():
    """
    Holt oder erstellt einen OpenAI-Client für den aktuellen Thread.
    
    Returns:
        OpenAI: Eine thread-lokale OpenAI-Client-Instanz
    """
    if not hasattr(_thread_local, 'client'):
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY nicht konfiguriert")
        
        # Client mit angepassten Timeout-Einstellungen erstellen
        _thread_local.client = OpenAI(
            api_key=api_key,
            timeout=MAX_TIMEOUT,
            max_retries=MAX_RETRIES
        )
        
    return _thread_local.client

def generate_cache_key(model, messages, **kwargs):
    """
    Generiert einen eindeutigen Cache-Schlüssel basierend auf Anfrageparametern.
    
    Args:
        model: Das verwendete Modell
        messages: Die Nachrichten für die Anfrage
        **kwargs: Andere OpenAI-Parameter
    
    Returns:
        str: Ein eindeutiger Cache-Schlüssel
    """
    # Relevante Parameter für den Cache-Schlüssel extrahieren
    cache_params = {
        'model': model,
        'messages': messages,
    }
    
    # Optionale Parameter hinzufügen, die das Ergebnis beeinflussen
    for param in ['temperature', 'top_p', 'n', 'stream', 'stop', 'max_tokens', 
                  'presence_penalty', 'frequency_penalty', 'logit_bias', 'functions']:
        if param in kwargs and kwargs[param] is not None:
            cache_params[param] = kwargs[param]
    
    # JSON-String erzeugen und Hash berechnen
    param_str = json.dumps(cache_params, sort_keys=True)
    return f"openai:chat:{hashlib.md5(param_str.encode()).hexdigest()}"

def get_cached_response(cache_key):
    """
    Holt eine zwischengespeicherte Antwort, wenn verfügbar.
    
    Args:
        cache_key: Der Cache-Schlüssel für die Anfrage
    
    Returns:
        dict oder None: Die zwischengespeicherte Antwort oder None
    """
    if not CACHE_ENABLED:
        return None
    
    try:
        cached = redis_client.get(cache_key)
        if cached:
            logger.debug(f"Cache-Treffer für Schlüssel: {cache_key}")
            return json.loads(cached)
        logger.debug(f"Cache-Fehltreffer für Schlüssel: {cache_key}")
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen aus Cache: {e}")
    
    return None

def cache_response(cache_key, response, ttl=None):
    """
    Speichert eine Antwort im Cache.
    
    Args:
        cache_key: Der Cache-Schlüssel
        response: Die zu speichernde Antwort
        ttl: Time-to-Live in Sekunden (optional)
    """
    if not CACHE_ENABLED:
        return
    
    if ttl is None:
        ttl = CACHE_TTL
    
    try:
        redis_client.setex(
            cache_key,
            ttl,
            json.dumps(response)
        )
        logger.debug(f"Antwort im Cache gespeichert: {cache_key}, TTL: {ttl}s")
    except Exception as e:
        logger.warning(f"Fehler beim Speichern im Cache: {e}")

@backoff.on_exception(
    backoff.expo,
    (APIError, APITimeoutError, RateLimitError),
    max_tries=MAX_RETRIES + 1,  # +1, da der erste Versuch nicht als Wiederholung zählt
    giveup=lambda e: isinstance(e, RateLimitError) and "exceeded your quota" in str(e),
    on_backoff=lambda details: logger.warning(
        f"Wiederhole OpenAI-Anfrage nach {details['wait']:.1f}s "
        f"(Versuch {details['tries']}/{MAX_RETRIES + 1})"
    )
)
def chat_completion_with_backoff(model, messages, user_id=None, session_id=None, 
                                function_name=None, use_cache=True, **kwargs):
    """
    Führt eine OpenAI-Chat-Completion mit Backoff-Wiederholungen durch.
    
    Args:
        model: Das zu verwendende OpenAI-Modell
        messages: Die Nachrichten für die Anfrage
        user_id: Benutzer-ID für Tracking (optional)
        session_id: Sitzungs-ID für Tracking (optional)
        function_name: Funktionsname für Tracking (optional)
        use_cache: Ob der Cache verwendet werden soll (Standard: True)
        **kwargs: Weitere Parameter für die OpenAI-API
    
    Returns:
        dict: Die OpenAI-Antwort
    """
    # Cache-Schlüssel generieren
    cache_key = generate_cache_key(model, messages, **kwargs)
    
    # Zwischengespeicherte Antwort abrufen, wenn Cache aktiviert
    if use_cache:
        cached_response = get_cached_response(cache_key)
        if cached_response:
            # Token-Nutzung für zwischengespeicherte Antwort tracken
            track_cached_usage(model, messages, cached_response, user_id, session_id, function_name)
            return cached_response
    
    # OpenAI-Client abrufen
    client = get_openai_client()
    
    start_time = time.time()
    try:
        # Anfrage an OpenAI senden
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        
        # Response in Dict umwandeln
        response_dict = response.model_dump()
        
        # Im Cache speichern, wenn aktiviert
        if use_cache:
            cache_response(cache_key, response_dict)
        
        # Token-Nutzung tracken
        track_token_usage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            function_name=function_name,
            cached=False
        )
        
        # Erfolgreiche Anfrage protokollieren
        logger.info(
            f"OpenAI-Anfrage erfolgreich: Modell={model}, "
            f"Tokens={response.usage.prompt_tokens}+{response.usage.completion_tokens}, "
            f"Zeit={time.time() - start_time:.2f}s"
        )
        
        return response_dict
    
    except Exception as e:
        logger.error(f"Fehler bei OpenAI-Anfrage: {type(e).__name__}: {e}")
        raise

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