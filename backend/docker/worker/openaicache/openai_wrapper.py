"""
OpenAI API-Wrapper mit Caching-Funktionalität
"""

import hashlib
import json
import os
import time
import logging
from datetime import datetime, timedelta
import redis
from functools import lru_cache
from openai import OpenAI
from flask import current_app, g

logger = logging.getLogger(__name__)

class CachedOpenAI:
    """
    Ein Wrapper für OpenAI-API-Aufrufe mit Caching-Funktionalität.
    Speichert identische Anfragen, um API-Kosten zu reduzieren und Antwortzeiten zu verbessern.
    """
    
    def __init__(self, client=None, redis_client=None, cache_ttl=86400, use_cache=True):
        """
        Initialisiert den CachedOpenAI Wrapper.
        
        Args:
            client: OpenAI-Client, falls nicht angegeben, wird einer erstellt
            redis_client: Redis-Client für Cache-Speicherung, falls nicht angegeben, wird aus der Umgebung verwendet
            cache_ttl: Lebensdauer der Cache-Einträge in Sekunden (Standard: 24 Stunden)
            use_cache: Flag, ob Caching aktiviert sein soll
        """
        self.client = client or OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        
        if redis_client:
            self.redis = redis_client
        else:
            # Versuche, eine Redis-Verbindung aus der Anwendungskonfiguration zu holen
            try:
                # Prüfe, ob Redis deaktiviert ist
                if os.environ.get('DISABLE_REDIS') == 'true':
                    logger.warning("Redis ist deaktiviert, Cache wird nicht verwendet")
                    self.redis = None
                    self.use_cache = False
                    return
                
                redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
                
                # Prüfe, ob memory:// als URL verwendet wird (Dummy-Modus)
                if redis_url.startswith('memory://'):
                    logger.warning("Redis ist im Memory-Modus, Cache wird nicht verwendet")
                    self.redis = None
                    self.use_cache = False
                    return
                    
                self.redis = redis.from_url(redis_url, socket_connect_timeout=2.0, socket_timeout=2.0)
                # Ping-Test, um sicherzustellen, dass die Verbindung funktioniert
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis-Verbindung konnte nicht hergestellt werden: {e}")
                self.redis = None
                self.use_cache = False
    
    def _generate_cache_key(self, model, messages, temperature, functions=None, **kwargs):
        """
        Generiert einen eindeutigen Cache-Schlüssel basierend auf den Anfrageparametern.
        
        Args:
            model: Das zu verwendende Modell
            messages: Liste der Nachrichten im Chat
            temperature: Temperaturwert für die Antwortgenerierung
            functions: Funktionsdefinitionen, falls vorhanden
            **kwargs: Zusätzliche Parameter
            
        Returns:
            str: Ein Hashwert, der als Cache-Schlüssel dient
        """
        # Erstelle ein Wörterbuch mit allen relevanten Parametern
        cache_dict = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
        }
        
        if functions:
            cache_dict['functions'] = functions
        
        # Füge alle anderen relevanten Parameter hinzu
        for key, value in kwargs.items():
            if key in ['max_tokens', 'top_p', 'frequency_penalty', 'presence_penalty', 'stop']:
                cache_dict[key] = value
        
        # Konvertiere das Wörterbuch in einen JSON-String und berechne den MD5-Hash
        cache_str = json.dumps(cache_dict, sort_keys=True)
        return hashlib.md5(cache_str.encode('utf-8')).hexdigest()
    
    def _get_from_cache(self, cache_key):
        """
        Versucht, eine Antwort aus dem Cache zu laden.
        
        Args:
            cache_key: Der Cache-Schlüssel
            
        Returns:
            dict oder None: Die gecachte Antwort oder None, wenn nicht im Cache
        """
        if not self.use_cache or not self.redis:
            return None
            
        try:
            cached_data = self.redis.get(f"openai_cache:{cache_key}")
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            logger.warning(f"Fehler beim Laden aus dem Cache: {e}")
            return None
    
    def _save_to_cache(self, cache_key, response_data):
        """
        Speichert eine Antwort im Cache.
        
        Args:
            cache_key: Der Cache-Schlüssel
            response_data: Die zu speichernden Daten
            
        Returns:
            bool: True bei Erfolg, False bei Fehler
        """
        if not self.use_cache or not self.redis:
            return False
            
        try:
            # Speichere die Antwort im Cache
            self.redis.setex(
                f"openai_cache:{cache_key}",
                self.cache_ttl,
                json.dumps(response_data)
            )
            return True
        except Exception as e:
            logger.warning(f"Fehler beim Speichern im Cache: {e}")
            return False

    def chat_completion(self, model, messages, temperature=0.7, functions=None, retries=3, backoff_time=2, **kwargs):
        """
        Erzeugt eine Chat-Completion mit Caching und Retry-Mechanismus.
        
        Args:
            model: OpenAI-Modell (z.B. "gpt-3.5-turbo")
            messages: Liste der Chat-Nachrichten
            temperature: Kreativitätsparameter (0-1)
            functions: Optional, Liste der Funktionsdefinitionen
            retries: Anzahl der Wiederholungsversuche bei Fehlern
            backoff_time: Wartezeit zwischen Wiederholungsversuchen in Sekunden
            **kwargs: Zusätzliche Parameter für die OpenAI-API
            
        Returns:
            dict: Die OpenAI-Antwort
            
        Raises:
            Exception: Bei dauerhaftem Fehler nach allen Wiederholungsversuchen
        """
        # Leere Nachrichten verhindern
        if not messages:
            raise ValueError("Die Nachrichtenliste darf nicht leer sein")
        
        # Cache-Schlüssel generieren
        cache_key = self._generate_cache_key(model, messages, temperature, functions, **kwargs)
        
        # Versuche, aus dem Cache zu laden
        cached_response = self._get_from_cache(cache_key)
        if cached_response:
            logger.info(f"Cache-Treffer für {cache_key[:8]}...")
            return cached_response
        
        # Nicht im Cache, rufe die API auf
        logger.info(f"Cache-Fehltreffer für {cache_key[:8]}...")
        
        attempts = 0
        while attempts < retries:
            try:
                # API-Aufruf mit oder ohne Funktionen
                if functions:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        functions=functions,
                        **kwargs
                    )
                else:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        **kwargs
                    )
                
                # Konvertiere das Response-Objekt in ein Wörterbuch
                response_dict = {
                    'id': response.id,
                    'model': response.model,
                    'created': response.created,
                    'choices': [
                        {
                            'index': choice.index,
                            'message': {
                                'role': choice.message.role,
                                'content': choice.message.content,
                            },
                            'finish_reason': choice.finish_reason
                        }
                        for choice in response.choices
                    ],
                    'usage': {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens
                    }
                }
                
                # Füge function_call hinzu, falls vorhanden
                for i, choice in enumerate(response.choices):
                    if hasattr(choice.message, 'function_call') and choice.message.function_call:
                        response_dict['choices'][i]['message']['function_call'] = {
                            'name': choice.message.function_call.name,
                            'arguments': choice.message.function_call.arguments
                        }
                
                # Speichere die Antwort im Cache
                self._save_to_cache(cache_key, response_dict)
                
                return response_dict
                
            except Exception as e:
                attempts += 1
                logger.warning(f"OpenAI API-Fehler (Versuch {attempts}/{retries}): {e}")
                
                # Bei temporären Fehlern erneut versuchen
                if attempts < retries:
                    wait_time = backoff_time * (2 ** (attempts - 1))  # Exponentielles Backoff
                    logger.info(f"Warte {wait_time} Sekunden vor dem nächsten Versuch...")
                    time.sleep(wait_time)
                else:
                    # Alle Versuche fehlgeschlagen
                    logger.error(f"Alle {retries} Versuche fehlgeschlagen: {e}")
                    raise e 