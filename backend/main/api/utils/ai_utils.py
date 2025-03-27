# api/ai_utils.py
"""
Funktionen für die Interaktion mit KI-Diensten (OpenAI).
"""

import json
import logging
import time
import hashlib
import random
from functools import lru_cache
from .token_tracking import count_tokens, calculate_token_cost, check_credits_available, deduct_credits

logger = logging.getLogger(__name__)

# Cache für OpenAI-Antworten
_response_cache = {}

def query_chatgpt(prompt, client, system_content=None, temperature=0.7, max_retries=5, use_cache=True, session_id=None, function_name="query_chatgpt"):
    """
    Sendet eine Anfrage an die OpenAI API mit Caching und Token-Tracking.
    
    Args:
        prompt: Der Prompt-Text für die Anfrage
        client: Der OpenAI-Client
        system_content: Optionaler System-Prompt
        temperature: Temperatur für die Antwortgenerierung (0.0-1.0)
        max_retries: Maximale Anzahl von Wiederholungsversuchen bei Fehlern
        use_cache: Ob Caching verwendet werden soll
        session_id: ID der aktuellen Session für Redis-Speicher
        function_name: Name der aufrufenden Funktion für Logging
        
    Returns:
        str: Die generierte Antwort
    """
    # Verwende die zentrale OpenAI-Integration
    try:
        from core.openai_integration import OpenAIIntegration
        openai_client = OpenAIIntegration()
        
        # Erstelle die Nachrichten für die API
        messages = []
        
        # Füge System-Prompt hinzu, falls vorhanden
        if system_content:
            messages.append({"role": "system", "content": system_content})
            
        # Füge den Benutzer-Prompt hinzu
        messages.append({"role": "user", "content": prompt})
        
        # Hole Ergebnis mit integriertem Caching, Token-Tracking und Fehlerbehandlung
        response = openai_client.generate_completion(
            messages=messages,
            temperature=temperature,
            max_retries=max_retries,
            use_cache=use_cache,
            session_id=session_id,
            function_name=function_name
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Fehler in query_chatgpt: {str(e)}")
        # Fallback auf legacy-Implementierung
        return _query_chatgpt_legacy(
            prompt=prompt, 
            client=client, 
            system_content=system_content, 
            temperature=temperature, 
            max_retries=max_retries, 
            use_cache=use_cache, 
            session_id=session_id,
            function_name=function_name
        )

def _query_chatgpt_legacy(prompt, client, system_content=None, temperature=0.7, max_retries=5, use_cache=True, session_id=None, function_name="query_chatgpt"):
    """
    Legacy-Implementierung der OpenAI-Anfrage für Abwärtskompatibilität.
    
    Args:
        prompt: Der Prompt-Text für die Anfrage
        client: Der OpenAI-Client
        system_content: Optionaler System-Prompt
        temperature: Temperatur für die Antwortgenerierung (0.0-1.0)
        max_retries: Maximale Anzahl von Wiederholungsversuchen bei Fehlern
        use_cache: Ob Caching verwendet werden soll
        session_id: ID der aktuellen Session für Redis-Speicher
        function_name: Name der aufrufenden Funktion für Logging
        
    Returns:
        str: Die generierte Antwort
    """
    global _response_cache
    
    try:
        # Erstelle einen Cache-Schlüssel aus dem Prompt und System-Content
        if use_cache:
            cache_key = f"{hashlib.md5((prompt + (system_content or '')).encode()).hexdigest()}"
            
            # Prüfe, ob die Antwort bereits im Cache ist
            if cache_key in _response_cache:
                logger.info(f"Cache-Treffer für Prompt in {function_name}")
                return _response_cache[cache_key]
        
        # Erstelle die Nachrichten für die API
        messages = []
        
        # Füge System-Prompt hinzu, falls vorhanden
        if system_content:
            messages.append({"role": "system", "content": system_content})
            
        # Füge den Benutzer-Prompt hinzu
        messages.append({"role": "user", "content": prompt})
        
        # Zähle die Token für das Kreditmanagement
        token_count = count_tokens("\n".join([msg["content"] for msg in messages]))
        
        # Token-Kosten berechnen
        token_cost = calculate_token_cost(token_count)
        
        # Benutzer aus der Session-ID ermitteln
        user_id = None
        if session_id:
            from core.models import Upload
            upload = Upload.query.filter_by(session_id=session_id).first()
            if upload:
                user_id = upload.user_id
                
        # Überprüfe, ob genügend Kredite vorhanden sind
        if user_id and not check_credits_available(user_id, token_count):
            logger.warning(f"Nicht genügend Kredite für Benutzer {user_id} in {function_name}")
            return "INSUFFICIENT_CREDITS: Nicht genügend Kredite für diese Operation."
        
        # Versuche die Anfrage mit Wiederholungen bei Fehlern
        retries = 0
        backoff_time = 1  # Initiale Wartezeit für Exponential Backoff
        
        while retries <= max_retries:
            try:
                # API-Anfrage senden
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=1024
                )
                
                # Extrahiere die Antwort
                answer = response.choices[0].message.content.strip()
                
                # Speichere im Cache, falls aktiviert
                if use_cache:
                    _response_cache[cache_key] = answer
                
                # Berechne die Kredite ab, falls ein Benutzer vorhanden ist
                if user_id:
                    deduct_credits(user_id, token_cost)
                
                return answer
                
            except Exception as e:
                retries += 1
                logger.warning(f"Fehler bei OpenAI-Anfrage in {function_name} (Versuch {retries}/{max_retries}): {str(e)}")
                
                if retries <= max_retries:
                    # Exponential Backoff für Wiederholungsversuche
                    sleep_time = backoff_time + random.uniform(0, 1)
                    logger.info(f"Warte {sleep_time:.2f}s vor dem nächsten Versuch...")
                    time.sleep(sleep_time)
                    backoff_time *= 2  # Verdopple die Wartezeit für den nächsten Versuch
                else:
                    logger.error(f"Alle Wiederholungsversuche fehlgeschlagen in {function_name}: {str(e)}")
                    return f"ERROR: Konnte keine Antwort von OpenAI erhalten nach {max_retries} Versuchen."
                    
    except Exception as e:
        logger.error(f"Unerwarteter Fehler in _query_chatgpt_legacy: {str(e)}")
        return f"ERROR: {str(e)}"

@lru_cache(maxsize=100)
def cached_query_chatgpt(prompt, system_content=None, temperature=0.7):
    """
    Gecachte Version der query_chatgpt-Funktion mit LRU-Cache.
    Nur für Anfragen ohne Session- und Benutzerbezug geeignet.
    
    Args:
        prompt: Der Prompt-Text für die Anfrage
        system_content: Optionaler System-Prompt
        temperature: Temperatur für die Antwortgenerierung (0.0-1.0)
        
    Returns:
        str: Die generierte Antwort
    """
    # Verwende die zentrale OpenAI-Integration
    try:
        from core.openai_integration import OpenAIIntegration
        openai_client = OpenAIIntegration()
        
        # Erstelle die Nachrichten für die API
        messages = []
        
        # Füge System-Prompt hinzu, falls vorhanden
        if system_content:
            messages.append({"role": "system", "content": system_content})
            
        # Füge den Benutzer-Prompt hinzu
        messages.append({"role": "user", "content": prompt})
        
        # Hole Ergebnis mit integriertem Caching
        response = openai_client.generate_completion(
            messages=messages,
            temperature=temperature,
            use_cache=True,
            function_name="cached_query_chatgpt"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Fehler in cached_query_chatgpt: {str(e)}")
        return f"ERROR: {str(e)}"

def format_json_response(response, default_value=None):
    """
    Versucht, eine JSON-Antwort aus einer OpenAI-Antwort zu extrahieren.
    
    Args:
        response: Die OpenAI-Antwort als String
        default_value: Standardwert, falls kein JSON gefunden wird
        
    Returns:
        dict: Das geparste JSON oder der Standardwert
    """
    try:
        # Versuche, JSON-Blöcke zu finden
        json_pattern = r'```json\s*([\s\S]*?)\s*```'
        json_matches = re.findall(json_pattern, response)
        
        if json_matches:
            # Verwende den ersten gefundenen JSON-Block
            return json.loads(json_matches[0])
        
        # Wenn kein JSON-Block gefunden wird, versuche direkt zu parsen
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Konnte JSON nicht aus Antwort extrahieren: {str(e)}")
        return default_value 